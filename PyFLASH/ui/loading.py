"""One read-only source cache; editable selection tables belong to each session."""
from copy import copy
from contextlib import contextmanager
from pathlib import Path
import streamlit as st
from PyFLASH.ui import services, workspace


@contextmanager
def opening_charts():
    """Load the browser's live-chart assets alongside verified data reading.

    The empty request carries no measurements and is removed before displaying
    the actual views, including when data verification refuses the input.
    """
    from PyFLASH.ui.performance_trace import record, start
    stage = start()
    placeholder = st.empty()
    record("create_opening_chart_placeholder", stage)
    try:
        stage = start()
        placeholder.vega_lite_chart(
            {"data": {"values": []}, "mark": "point", "height": 1},
            width="stretch",
        )
        record("render_opening_chart_placeholder", stage)
        yield
    finally:
        placeholder.empty()


def _code_version():
    root = Path(workspace.__file__).resolve().parents[1]
    files = ("ui/workspace.py", "ui/services.py", "serialization.py", "export.py",
             "batch.py", "experiment.py", "config.py", "markers.py",
             "dataframe.py", "conditions.py", "aliases.py", "palette.py",
             "utils.py", "ui/loading.py", "ui/preparation.py", "_cache_identity.py")
    return tuple((name, workspace.content_hash(root / name)) for name in files)


@st.cache_resource(max_entries=1, show_spinner=False)
def _source(path, identity, kind, group_col, subject_col, code_version, _prepared=None):
    batch = (_prepared.batch if _prepared is not None else
        services.open_pickle(path, source_sha256=identity['sha256']) if kind == "pickle" else
        workspace.load_table(path, demo=kind == "demo", group_col=group_col,
                             subject_col=subject_col, source_sha256=identity['sha256']))
    region = services.roi_bases(batch)[0]
    return batch, region


def open_source(source, *, initial_identity=None, _prepared=None):
    """Reuse immutable measurements, never share edited selections or UI state."""
    from PyFLASH.ui.performance_trace import record, start
    path = Path(source["path"]).resolve()
    stage = start()
    identity = workspace.source_version(path) if initial_identity is None else initial_identity
    if initial_identity is None:
        record("initial_source_hash", stage)
    if _prepared is not None:
        if (source['kind'] != 'pickle' or _prepared.path != str(path)
                or _prepared.sha256 != identity['sha256']
                or getattr(_prepared.batch, '_pyflash_resident_input_sha256', None) != _prepared.sha256):
            raise ValueError("Prepared source does not match the requested input.")
    prepared_args = {} if _prepared is None else {'_prepared': _prepared}
    stage = start()
    template, region = _source(str(path), identity,
        source["kind"], source.get("group_col", "Condition"), source.get("subject_col", "AnimalName"), _code_version(), **prepared_args)
    record("source_cache_access", stage)
    def prepare_catalogue():
        initial = getattr(template,'_ui_initial_catalogue',None)
        if initial is None or initial[0] != region:
            initial = (region,workspace.measurement_catalogue(template,region))
            template._ui_initial_catalogue = initial
        return initial[1]

    # Verify after every opening stage that could overlap a source change.
    # A read completed during catalogue work cannot certify its end state.
    stage = start()
    catalogue = prepare_catalogue()
    record("measurement_catalogue", stage, rows=len(catalogue[0]), columns=len(catalogue[0].columns))
    stage = start()
    final_identity = workspace.source_version(path)
    record("final_source_hash", stage)
    if final_identity != identity:
        _source.clear()
        raise ValueError("The source file changed while it was being opened. Reopen it before retrying.")
    stage = start()
    batch = copy(template)
    selections = services.get_representative_selections(template)
    if selections is not None:
        services.set_representative_selections(batch, selections.copy(deep=True))
    # Pages only read shared summaries/experiment metadata. Scientific work
    # loads its own full object in the process worker, never this template.
    batch._ui_initial_catalogue = (region, catalogue)
    batch._ui_source_version = identity
    record("copy_session_batch", stage)
    return batch
