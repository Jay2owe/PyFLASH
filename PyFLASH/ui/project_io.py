"""UI "project" persistence.

A UI *project* is the small, JSON-serializable description of what the user is
building: a name, the experiment folder paths, and the condition definitions. It
is distinct from the in-memory ``Batch``/``Experiment`` object — a project can
be saved/reloaded without re-running ``create_batch``.

No Streamlit import here: this stays pure Python so it is unit-testable.

Conditions are persisted as a **spec** (factor name, entries, comparison mode,
explanation), never as built ``condition`` objects. On load the spec is replayed
through :class:`PyFLASH.conditions.ConditionBuilder` to rebuild an equivalent
``conditionList`` (house rule: never pickle built condition objects).

Conditions JSON schema (``Project.conditions``)::

    {
      "factor": "Genotype",
      "entries": [{"label": "WT", "short": "WT", "color": "blue"},
                  {"label": "KO", "short": "KO", "color": "red"}],
      "comparisons": {"mode": "pairs", "pairs": [["WT", "KO"]]},
      "explanation": "Wild-type vs <>"
    }

    # comparison modes:
    #   {"mode": "pairs",      "pairs": [["WT", "KO"], ...]}
    #   {"mode": "all_pairs"}
    #   {"mode": "vs_control", "control": "WT"}
    #   {"mode": "sequential"}

A *crossed* (factorial) design instead carries two sub-factor specs plus its own
comparison/ordering settings::

    {
      "crossed": true,
      "factors": [<factor-spec>, <factor-spec>],
      "comparisons": {"mode": "pairs",
                      "pairs": [["Syn", "hAPP", "WeekTwo"], ...]},  # 3rd = within
      "order_by": "Time",
      "explanation": "..."
    }
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from PyFLASH.conditions import ConditionBuilder
from PyFLASH.config import Config

__all__ = [
    "Project",
    "load_project",
    "save_project",
    "build_condition_list",
    "build_factor_list",
    "SCHEMA_VERSION",
]

# Bump when the on-disk schema changes.
SCHEMA_VERSION = 1


def _default_threshold() -> int:
    """Read ``Config.THRESHOLD`` at construction time (defaults to 30)."""
    return Config.THRESHOLD


@dataclass
class Project:
    """A UI project: paths + conditions. JSON round-trippable."""

    name: str = "Untitled"
    experiment_paths: List[str] = field(default_factory=list)
    # ── Stage 03: experiment folder setup ───────────────────────────────────
    # ``batch_path`` is the root/results folder; ``experiments`` maps an
    # experiment name to its folder path (manual mode) and is empty when
    # auto-discovering from ``batch_path``. ``pickle_path`` is the cache dir.
    batch_path: str = ""
    experiments: Dict[str, str] = field(default_factory=dict)
    pickle_path: str = ""
    threshold: int = field(default_factory=_default_threshold)
    import_images: bool = True
    # ── Stage 04: conditions spec ───────────────────────────────────────────
    # The condition *spec* (entries + comparison mode), NOT built condition
    # objects. Replayed through ConditionBuilder by ``build_condition_list``.
    # Empty dict means "not defined yet". See module docstring for the schema.
    conditions: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        # Only accept known fields so forward-compatible files don't crash.
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    # ── JSON round-tripping (Stage 04 contract) ─────────────────────────────

    def to_json(self) -> str:
        """Serialize the whole project (including the conditions spec) to JSON."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Project":
        """Rebuild a :class:`Project` from a JSON string produced by ``to_json``."""
        return cls.from_dict(json.loads(text))

    def condition_list(self):
        """Rebuild and return this project's ``conditionList`` from its spec.

        Returns ``None`` when no conditions are defined. Never returns a pickled
        object — the list is rebuilt fresh via :class:`ConditionBuilder`.
        """
        if not self.conditions:
            return None
        return build_condition_list(self.conditions)


# ── Spec → ConditionBuilder rebuild ─────────────────────────────────────────


def _apply_comparisons(builder, comparisons, *, crossed: bool):
    """Replay a comparisons spec onto a (crossed or simple) builder.

    For a simple builder: ``pairs`` rows are ``[a, b]``. For a crossed builder:
    rows may be ``[a, b]`` or ``[a, b, within]`` and the ``*_within`` modes take
    a ``within_factor`` key. May raise ``ValueError`` (with a difflib suggestion)
    from the underlying builder — surfaced to the caller deliberately.
    """
    comparisons = comparisons or {}
    mode = comparisons.get("mode")
    if not mode:
        return

    if mode == "pairs":
        for pair in comparisons.get("pairs", []):
            if crossed:
                a, b = pair[0], pair[1]
                within = pair[2] if len(pair) > 2 and pair[2] else None
                builder.compare(a, b, within=within)
            else:
                a, b = pair[0], pair[1]
                builder.compare(a, b)
    elif mode == "all_pairs":
        if crossed:
            builder.compare_all_pairs(
                within_factor=comparisons.get("within_factor") or None)
        else:
            builder.compare_all_pairs()
    elif mode == "vs_control":
        control = comparisons.get("control")
        if crossed:
            builder.compare_to_control(
                control, within_factor=comparisons.get("within_factor") or None)
        else:
            builder.compare_to_control(control)
    elif mode == "sequential":
        # Only the simple builder exposes a sequential helper.
        if not crossed:
            builder.compare_sequential()


def build_factor_list(spec):
    """Build a single-factor ``conditionList`` from a factor spec.

    The factor spec is ``{"factor", "entries":[{label,short,color}],
    "comparisons", "explanation"}`` (the non-crossed shape). Used both directly
    and as a sub-list when crossing. Replays through :class:`ConditionBuilder`;
    never pickles condition objects.
    """
    builder = ConditionBuilder(spec["factor"])
    for entry in spec.get("entries", []):
        builder.add(
            entry["label"],
            short=entry.get("short") or None,
            color=entry.get("color") or None,
        )
    _apply_comparisons(builder, spec.get("comparisons"), crossed=False)
    if spec.get("explanation"):
        builder.explain(spec["explanation"])
    return builder.build()


def build_condition_list(spec):
    """Rebuild a ``conditionList`` from a JSON-serializable conditions *spec*.

    Dispatches on ``spec["crossed"]``: a simple single-factor design replays
    one :class:`ConditionBuilder`; a crossed design builds two sub-factor
    lists and crosses them via :meth:`ConditionBuilder.cross`, applying
    ``within=`` comparisons and ``order_by``. Builder ``ValueError``\\ s
    (including difflib "Did you mean…?" suggestions) propagate to the caller.
    """
    if not spec:
        return None

    if spec.get("crossed"):
        factor_specs = spec.get("factors", [])
        if len(factor_specs) != 2:
            raise ValueError(
                "A crossed design needs exactly two factor lists "
                f"(got {len(factor_specs)})."
            )
        cl1 = build_factor_list(factor_specs[0])
        cl2 = build_factor_list(factor_specs[1])
        builder = ConditionBuilder.cross(cl1, cl2)
        if spec.get("order_by"):
            builder.order_by(spec["order_by"])
        _apply_comparisons(builder, spec.get("comparisons"), crossed=True)
        if spec.get("explanation"):
            builder.explain(spec["explanation"])
        return builder.build()

    return build_factor_list(spec)


def save_project(project: Project, path: str) -> None:
    """Write *project* to *path* as UTF-8 JSON."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(project.to_json())


def load_project(path: str) -> Project:
    """Read a project JSON file from *path*."""
    with open(path, "r", encoding="utf-8") as f:
        return Project.from_json(f.read())
