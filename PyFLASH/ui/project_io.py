"""UI "project" persistence (stub).

A UI *project* is the small, JSON-serializable description of what the user is
building: a name, the experiment folder paths, and (later) the condition
definitions. It is distinct from the in-memory ``Batch``/``Experiment`` object
— a project can be saved/reloaded without re-running ``create_batch``.

No Streamlit import here: this stays pure Python so it is unit-testable.

TODO (Stage 04): flesh out the schema. The ``conditions`` field will hold a
serialized ``ConditionBuilder`` grid + comparisons + crossing, and
``project_io`` will gain the rebuild path (JSON <-> ConditionBuilder). For now
it is an opaque placeholder so earlier stages can round-trip a project file.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

__all__ = ["Project", "load_project", "save_project"]

# Bump when the on-disk schema changes (Stage 04 will define v1 fully).
SCHEMA_VERSION = 0


@dataclass
class Project:
    """A UI project: paths + (later) conditions. JSON round-trippable."""

    name: str = "Untitled"
    experiment_paths: List[str] = field(default_factory=list)
    # TODO(Stage 04): replace ``Any`` with the real conditions schema.
    conditions: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        # Only accept known fields so forward-compatible files don't crash.
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


def save_project(project: Project, path: str) -> None:
    """Write *project* to *path* as UTF-8 JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project.to_dict(), f, indent=2)


def load_project(path: str) -> Project:
    """Read a project JSON file from *path*."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Project.from_dict(data)
