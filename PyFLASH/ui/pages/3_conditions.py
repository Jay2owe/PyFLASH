"""Conditions page — build a ConditionBuilder design in a grid, with preview.

Defines the experimental conditions for a batch without hand-writing
``ConditionBuilder(...).add(...).compare(...)`` chains. The user fills a grid of
``(label, short, color)`` rows for a factor, picks a comparison mode, and
optionally crosses two factors into a factorial design. A live preview rebuilds
the ``conditionList`` and shows ordered swatches, the resolved ``'1-2'``
comparison index strings, and the explanation expansion. Builder ``ValueError``\\s
(including difflib "Did you mean…?" suggestions) are surfaced inline.

The design is persisted as a *spec* (entries + comparison mode) into
``st.session_state["project"].conditions`` — never as built condition objects.
It is rebuilt via ``services.build_conditions`` on every render. Streamlit is
imported here (a page), never in ``services.py`` / ``project_io.py``.
"""

import streamlit as st

from PyFLASH.config import Config
from PyFLASH.ui import services
from PyFLASH.ui.project_io import Project

# Comparison modes shown in the picker -> spec "mode" value.
_SIMPLE_MODES = {
    "Explicit pairs": "pairs",
    "All pairs": "all_pairs",
    "Versus control": "vs_control",
    "Sequential": "sequential",
    "None": None,
}
_CROSSED_MODES = {
    "Explicit pairs": "pairs",
    "All pairs": "all_pairs",
    "Versus control": "vs_control",
    "None": None,
}


def _project() -> Project:
    """Return the session Project, creating a fresh one on first visit."""
    proj = st.session_state.get("project")
    if not isinstance(proj, Project):
        proj = Project()
        st.session_state["project"] = proj
    return proj


def _swatch(hex_color: str) -> str:
    """Return an inline HTML swatch chip for a resolved hex color."""
    return (
        f"<span style='display:inline-block;width:14px;height:14px;"
        f"border:1px solid #888;border-radius:3px;background:{hex_color};"
        f"vertical-align:middle;margin-right:6px'></span>"
    )


def _entry_editor(seed_entries, key):
    """Render the (label, short, color) grid; return a list of entry dicts.

    Blank rows (no label) are dropped. ``color`` accepts a ``Config.COLORS``
    key, a CSS name, a ``#hex``, or blank (auto). The color column offers the
    palette keys as a dropdown but still accepts free text.
    """
    seed = seed_entries or [{"label": "", "short": "", "color": ""}]
    edited = st.data_editor(
        seed,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "label": st.column_config.TextColumn(
                "Label", help="Full display name (appears on plots / tables)."),
            "short": st.column_config.TextColumn(
                "Short", help="Shorthand used in filenames and comparisons. "
                              "Defaults to the label."),
            "color": st.column_config.TextColumn(
                "Color", help="A palette key (e.g. red), a CSS name "
                              "(e.g. steelblue), a #hex, or blank to auto-assign. "
                              f"Palette keys: {', '.join(Config.COLORS)}."),
        },
        key=key,
    )
    entries = []
    for row in edited:
        label = (row.get("label") or "").strip()
        if not label:
            continue
        entries.append({
            "label": label,
            "short": (row.get("short") or "").strip(),
            "color": (row.get("color") or "").strip(),
        })
    return entries


def _shorts(entries):
    """Resolved short names (falling back to label) for an entry list."""
    return [e["short"] or e["label"] for e in entries]


def _duplicate_shorts(entries):
    """Return any short names that appear more than once (breaks resolution)."""
    seen, dupes = set(), []
    for s in _shorts(entries):
        if s in seen and s not in dupes:
            dupes.append(s)
        seen.add(s)
    return dupes


def _comparison_picker(entries, modes, key_prefix):
    """Render the comparison-mode picker; return a comparisons spec dict.

    Common to a single factor and to each crossed sub-factor. Pairs are picked
    from the available short names; vs-control picks one short name.
    """
    shorts = _shorts(entries)
    label = st.selectbox(
        "Comparison mode", list(modes), key=f"{key_prefix}_mode")
    mode = modes[label]
    spec = {"mode": mode} if mode else {}

    if mode == "pairs":
        pair_options = [
            (a, b)
            for i, a in enumerate(shorts)
            for b in shorts[i + 1:]
        ]
        picked = st.multiselect(
            "Pairs to compare",
            pair_options,
            format_func=lambda p: f"{p[0]} vs {p[1]}",
            key=f"{key_prefix}_pairs",
        )
        spec["pairs"] = [[a, b] for a, b in picked]
    elif mode == "vs_control":
        control = st.selectbox(
            "Control condition", shorts or [""], key=f"{key_prefix}_control")
        spec["control"] = control
    return spec


def _factor_block(seed, key_prefix, modes, *, with_explanation=True):
    """Render one factor: name, grid, comparison picker, explanation.

    Returns a factor spec dict (``factor``/``entries``/``comparisons``/
    ``explanation``) plus the list of duplicate-short warnings to surface.
    """
    factor = st.text_input(
        "Factor name", value=seed.get("factor", ""), key=f"{key_prefix}_factor")
    entries = _entry_editor(seed.get("entries"), key=f"{key_prefix}_entries")
    dupes = _duplicate_shorts(entries)

    spec = {"factor": factor.strip(), "entries": entries}
    if entries and not dupes:
        spec["comparisons"] = _comparison_picker(entries, modes, key_prefix)
    if with_explanation:
        explanation = st.text_input(
            "Explanation template (<> is replaced with each label)",
            value=seed.get("explanation", ""),
            key=f"{key_prefix}_explanation",
        )
        if explanation.strip():
            spec["explanation"] = explanation.strip()
    return spec, dupes


def _render_preview(spec):
    """Build and preview *spec*, surfacing builder ValueErrors inline."""
    try:
        cl = services.build_conditions(spec)
    except ValueError as exc:
        # Builder validation (incl. difflib "Did you mean…?") — show, don't crash.
        st.error(str(exc))
        return
    except Exception as exc:  # pragma: no cover - defensive UI guard
        st.error(f"Could not build conditions: {exc}")
        return

    if cl is None:
        st.info("Add at least one condition to see a preview.")
        return

    preview = services.preview_conditions(cl)
    st.markdown(f"**Factor:** {preview['factor']}")

    rows = []
    for i, cond in enumerate(preview["conditions"], start=1):
        rows.append(
            f"{_swatch(cond['color'])} **{i}. {cond['name']}** — "
            f"{cond['label']}  `{cond['color']}`"
        )
    st.markdown("<br>".join(rows), unsafe_allow_html=True)

    comparisons = preview["comparisons"]
    if comparisons:
        st.markdown("**Comparisons** (resolved index strings):")
        for idx_str, labelled in zip(comparisons,
                                     preview["labelled_comparisons"]):
            st.markdown(f"- `{idx_str}` — {labelled}")
    else:
        st.caption("No comparisons defined.")

    with st.expander("Explanation expansion"):
        any_expl = False
        for cond in preview["conditions"]:
            if cond["explanation"]:
                any_expl = True
                st.markdown(f"- **{cond['name']}**: {cond['explanation']}")
        if not any_expl:
            st.caption("No explanation template set.")


# ── Page body ───────────────────────────────────────────────────────────────

st.header("Conditions")
st.caption(
    "Define your experimental conditions in a grid and choose how to compare "
    "them. The design is rebuilt and previewed live, then saved to the project."
)

project = _project()
existing = project.conditions or {}

design = st.radio(
    "Design",
    ["Single factor", "Crossed (two factors)"],
    index=1 if existing.get("crossed") else 0,
    horizontal=True,
)

spec = None
all_dupes = []

if design.startswith("Single"):
    seed = {} if existing.get("crossed") else existing
    spec, all_dupes = _factor_block(seed, "single", _SIMPLE_MODES)
else:
    st.caption(
        "Build two factors; they are crossed into a factorial design via "
        "ConditionBuilder.cross. Comparisons use named conditions (and an "
        "optional 'within' factor) rather than raw indices."
    )
    factors_seed = existing.get("factors", [{}, {}]) if existing.get("crossed") \
        else [{}, {}]
    factors_seed = (factors_seed + [{}, {}])[:2]

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Factor 1")
        f1, d1 = _factor_block(factors_seed[0], "cross1", {"None": None},
                               with_explanation=False)
    with col2:
        st.subheader("Factor 2")
        f2, d2 = _factor_block(factors_seed[1], "cross2", {"None": None},
                               with_explanation=False)
    all_dupes = d1 + d2

    st.subheader("Crossed comparisons")
    # Crossed comparisons reference the sub-condition short names of either
    # factor; offer all of them to the picker.
    combined_entries = f1.get("entries", []) + f2.get("entries", [])
    crossed_cmp = _comparison_picker(combined_entries, _CROSSED_MODES, "cross_cmp")

    within_options = ["(none)"] + [f1.get("factor", ""), f2.get("factor", "")]
    within_options = [w for w in within_options if w]
    within_factor = st.selectbox(
        "Restrict comparisons within factor (within_factor)",
        within_options,
        help="For 'All pairs' / 'Versus control', compare only within each "
             "level of this factor.",
    )
    if within_factor and within_factor != "(none)" \
            and crossed_cmp.get("mode") in {"all_pairs", "vs_control"}:
        crossed_cmp["within_factor"] = within_factor

    order_options = ["(default)"] + [f1.get("factor", ""), f2.get("factor", "")]
    order_options = [o for o in order_options if o]
    order_by = st.selectbox(
        "Order conditions by factor (order_by)",
        order_options,
        help="Regroup crossed conditions by this factor (default groups by "
             "the first factor).",
    )

    explanation = st.text_input(
        "Explanation template (<> is replaced with each label)",
        value=existing.get("explanation", "") if existing.get("crossed") else "",
        key="cross_explanation",
    )

    spec = {
        "crossed": True,
        "factors": [f1, f2],
        "comparisons": crossed_cmp,
    }
    if order_by and order_by != "(default)":
        spec["order_by"] = order_by
    if explanation.strip():
        spec["explanation"] = explanation.strip()

# ── Validation hints ────────────────────────────────────────────────────────

if all_dupes:
    st.warning(
        "Duplicate short names will break comparison resolution: "
        + ", ".join(all_dupes)
        + ". Make each short name unique before building."
    )

# ── Live preview ────────────────────────────────────────────────────────────

st.subheader("Preview")
if all_dupes:
    st.info("Resolve duplicate short names above to see the preview.")
else:
    _render_preview(spec)

# ── Persist the spec into the session project ───────────────────────────────

if st.button("Save conditions", type="primary", disabled=bool(all_dupes)):
    try:
        # Final validation: must build cleanly before we persist the spec.
        services.build_conditions(spec)
    except ValueError as exc:
        st.error(f"Not saved — {exc}")
    except Exception as exc:  # pragma: no cover - defensive UI guard
        st.error(f"Not saved — could not build conditions: {exc}")
    else:
        project.conditions = spec
        st.session_state["project"] = project
        st.success("Conditions saved to the current project (persists across "
                   "pages). The batch is built on the Batch page.")
