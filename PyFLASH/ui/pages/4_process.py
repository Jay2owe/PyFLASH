"""Process page — run ``create_batch`` and hold the resulting Batch in session.

This is the heart of "create a new analysis without code": it takes the
experiment folders (Experiments page) and groups (Groups page) held in
the session ``Project`` and runs :func:`PyFLASH.factory.create_batch` via
``services.run_create_batch``. PyFLASH's progress/log output is captured into a
buffer (``services.capture_output``) and shown as a code block inside a
``st.status`` panel, since ``ProgressTracker`` has no callback hook off-notebook
(house rule 1 — we capture output rather than patch core).

On success the built ``Batch`` is stored in ``st.session_state["batch"]`` so the
Summary / Export / Plot pages can reuse it without reloading, and the
``_last_process_summary`` ("N experiments | M subjects") line is surfaced. A
cache hit (an existing ``<name>.pkl`` returned instantly with ``rerun=False``)
is detected and labelled. Errors (e.g. ``ValueError: No experiment folders
found``) are caught and shown as a clean message, not a stack trace.

A synchronous ``st.status`` is used (the documented v1 fallback): ``create_batch``
runs to completion, then the full captured log is rendered. Streamlit threading
proved fragile for this blocking call, and the pickle cache means it is usually
a one-time cost. Streamlit is imported here (a page), never in ``services.py``.
"""

import streamlit as st

from PyFLASH.ui import services
from PyFLASH.ui.project_io import Project


def _project() -> Project:
    """Return the session Project, creating a fresh one on first visit."""
    proj = st.session_state.get("project")
    if not isinstance(proj, Project):
        proj = Project()
        st.session_state["project"] = proj
    return proj


def _is_cache_hit(log_text: str) -> bool:
    """Heuristically detect a pickle cache hit from the captured log.

    ``create_batch`` (``factory.py:154-157``) emits
    "Loaded existing pickle: …" and short-circuits before processing when an
    existing ``<name>.pkl`` is found and ``rerun=False``. The post-cache steps
    ("Prepare Experiments", "Process Batch") never run, so their absence plus
    that marker line distinguishes a cache hit from a fresh build.
    """
    return ("Loaded existing pickle" in log_text
            and "Process Batch" not in log_text)


st.header("Process")
st.caption(
    "Build the batch from the experiment folders and groups you set up on "
    "the previous pages. This runs create_batch and may take a while on a fresh "
    "dataset; a cached pickle (if any) is returned quickly."
)

project = _project()

# ── Pre-flight: do we have enough to build? ─────────────────────────────────

problems = []
if not project.batch_path:
    problems.append("a batch root folder (Experiments page)")
if not project.conditions:
    problems.append("a group design (Groups page)")

if problems:
    st.warning(
        "Before processing, set up: " + "; ".join(problems) + "."
    )

# Rebuild the conditionList from the saved spec so we can show what will run and
# surface any builder error here rather than mid-run.
condition_list = None
if project.conditions:
    try:
        condition_list = services.build_conditions(project.conditions)
    except Exception as exc:  # builder ValueError incl. difflib suggestions
        st.error(f"Could not build the group design: {exc}")

# ── What will be built ──────────────────────────────────────────────────────

st.subheader("What will be built")
col_a, col_b = st.columns(2)
with col_a:
    st.markdown(f"**Name:** {project.name or '(unnamed)'}")
    st.markdown(f"**Batch root:** `{project.batch_path or '—'}`")
    st.markdown(
        f"**Pickle cache:** `{project.pickle_path or '(none — not cached)'}`")
with col_b:
    if project.experiments:
        st.markdown(
            f"**Experiments:** {len(project.experiments)} (manual mapping)")
    else:
        st.markdown("**Experiments:** auto-discover from batch root")
    st.markdown(f"**Threshold:** {project.threshold}")
    st.markdown(f"**Import images:** {'yes' if project.import_images else 'no'}")

if condition_list is not None:
    preview = services.preview_conditions(condition_list)
    names = [c["name"] for c in preview["conditions"]]
    st.markdown(f"**Groups:** {', '.join(names)}"
                if names else "**Groups:** (none)")

# ── Run options ─────────────────────────────────────────────────────────────

st.subheader("Run options")
col_rerun, col_reimport = st.columns(2)
rerun = col_rerun.toggle(
    "Force rerun (ignore cached pickle)",
    value=False,
    help="Reprocess even if a cached <name>.pkl exists. Representative "
         "selections from the previous pickle are carried over.",
)
reimport_images = col_reimport.toggle(
    "Reimport images on rerun",
    value=False,
    disabled=not rerun,
    help="Only applies with 'Force rerun': force image import during the rerun "
         "even if 'Import images' was off.",
)

# ── Run ─────────────────────────────────────────────────────────────────────

ready = bool(project.batch_path) and condition_list is not None
run = st.button("Run create_batch", type="primary", disabled=not ready)

if run:
    # Auto-discover mode keeps project.experiments empty -> pass None so
    # create_batch discovers from batch_path (factory.py:161-186).
    experiments = project.experiments or None
    pickle_path = project.pickle_path or None

    with st.status("Processing…", expanded=True) as status:
        st.caption("Running create_batch — progress is captured below.")
        try:
            batch, log = services.run_create_batch(
                name=project.name,
                conditions=condition_list,
                batch_path=project.batch_path,
                experiments=experiments,
                pickle_path=pickle_path,
                threshold=project.threshold,
                rerun=bool(rerun),
                import_images=bool(project.import_images),
                reimport_images=bool(reimport_images),
            )
        except ValueError as exc:
            # Expected, user-actionable errors (e.g. "No experiment folders
            # found in …", bad conditions) — show cleanly, no stack trace.
            status.update(label="Could not build the batch", state="error")
            st.error(str(exc))
        except Exception as exc:  # pragma: no cover - defensive UI guard
            status.update(label="Processing failed", state="error")
            st.exception(exc)
        else:
            if log.strip():
                st.code(log)
            else:
                st.caption("(no progress output was captured)")

            st.session_state["batch"] = batch

            summary = getattr(batch, "_last_process_summary", None)
            cache_hit = _is_cache_hit(log)
            if cache_hit:
                label = "Loaded cached batch (cache hit)"
            elif summary:
                label = summary
            else:
                label = "Done"
            status.update(label=label, state="complete")

            if cache_hit:
                st.info(
                    "Cache hit: an existing pickle was returned without "
                    "reprocessing. Tick 'Force rerun' above to rebuild."
                )
            if summary:
                st.success(summary)

            state_path = getattr(batch, "_state_path", None) \
                or getattr(batch, "filePath", None)
            if state_path:
                st.caption(f"Pickle: {state_path}")

            st.caption(
                "The batch is now loaded for this session. Browse it on the "
                "Summary page, or export / plot it on the later pages."
            )

# ── Already-built reminder ──────────────────────────────────────────────────

existing_batch = st.session_state.get("batch")
if not run and existing_batch is not None:
    st.caption(
        f"A {type(existing_batch).__name__} is already loaded "
        f"(name: {getattr(existing_batch, 'name', '?')}). Running again will "
        "replace it."
    )
