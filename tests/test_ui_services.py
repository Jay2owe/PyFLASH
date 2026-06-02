"""Unit tests for PyFLASH.ui.services.

The services adapter must be importable and usable with **no Streamlit
installed** (house rule 2). These tests therefore:

* import ``PyFLASH.ui.services`` and assert ``streamlit`` was not pulled in,
* check ``package_info()`` reports a clean core import,
* check ``open_pickle`` is wired to ``serialization.load_state`` (verified via
  a real round-tripped pickle, with no streamlit dependency).
"""

import sys
import types

import pandas as pd

from PyFLASH.batch import Batch
from PyFLASH.serialization import save_state
from PyFLASH.ui import services


def test_importing_services_does_not_import_streamlit():
    # Importing the adapter must not drag in the UI dependency.
    assert "streamlit" not in sys.modules


def test_package_info_reports_clean_import():
    info = services.package_info()
    assert info["import_ok"] is True
    assert info["has_create_batch"] is True
    assert info["has_load_state"] is True


def test_services_module_has_no_streamlit_attribute():
    # services.py must not import streamlit at module top.
    assert not hasattr(services, "streamlit")
    assert not hasattr(services, "st")


def _make_minimal_batch():
    batch = Batch.__new__(Batch)
    batch.name = "ui_test_batch"
    batch.data = {}
    batch.summary = pd.DataFrame()
    batch.experiment_list = []
    batch.filePath = None
    return batch


def test_open_pickle_round_trips_via_load_state(tmp_path):
    batch = _make_minimal_batch()
    pickle_path = tmp_path / "ui_batch.pkl"
    save_state(batch, str(pickle_path), verbose=False)

    loaded = services.open_pickle(str(pickle_path))

    assert isinstance(loaded, Batch)
    assert loaded.name == "ui_test_batch"
    # open_pickle records the load path on the object (load_state behaviour).
    assert loaded._state_path == str(pickle_path)


def test_open_pickle_is_backed_by_load_state():
    # Wiring check: the symbol services calls is serialization.load_state.
    from PyFLASH import serialization

    assert services.load_state is serialization.load_state


# ── Stage 02: summary browsing ──────────────────────────────────────────────


def _fake_summary():
    # An " end-of-day" -shaped summary: identifier columns + a couple of
    # measurement columns whose raw names differ from their display labels.
    return pd.DataFrame(
        {
            "AnimalName": ["A1", "A2"],
            "Condition": ["WT", "KO"],
            "SCN_DAPI_Count": [10, 12],
            "SCN_NeuN_Area_um2": [1.5, 2.0],
        }
    )


def _fake_batch():
    """A lightweight stand-in exposing just the attrs services needs.

    No real .pkl, no data files — only ``summaries`` (with the backward-compat
    ``summary`` property emulated) plus minimal identity attrs so
    ``summary_table`` / ``roi_bases`` / ``batch_overview`` can be exercised.
    """
    scn = _fake_summary()
    oc = scn.rename(columns={"SCN_DAPI_Count": "OC_DAPI_Count"})

    cond_wt = types.SimpleNamespace(name="WT")
    cond_ko = types.SimpleNamespace(name="KO")
    exp = types.SimpleNamespace(name="exp1")

    return types.SimpleNamespace(
        name="fake_batch",
        summaries={"SCN": scn, "OC": oc},
        summary=scn,
        condition_list=[cond_wt, cond_ko],
        experiment_list=[exp],
        markers={"NeuN", "DAPI"},
    )


def test_roi_bases_returns_summary_keys():
    batch = _fake_batch()
    assert services.roi_bases(batch) == ["SCN", "OC"]


def test_roi_bases_falls_back_to_scn():
    empty = types.SimpleNamespace()
    assert services.roi_bases(empty) == ["SCN"]


def test_summary_table_raw_keeps_original_columns():
    batch = _fake_batch()
    raw = services.summary_table(batch, roi_base="SCN", display=False)
    assert list(raw.columns) == [
        "AnimalName",
        "Condition",
        "SCN_DAPI_Count",
        "SCN_NeuN_Area_um2",
    ]


def test_summary_table_display_relabels_columns():
    batch = _fake_batch()
    raw = services.summary_table(batch, roi_base="SCN", display=False)
    disp = services.summary_table(batch, roi_base="SCN", display=True)
    # Same shape, but at least one header should change under display mapping.
    assert disp.shape == raw.shape
    assert list(disp.columns) != list(raw.columns)


def test_summary_table_roi_base_selects_table():
    batch = _fake_batch()
    oc = services.summary_table(batch, roi_base="OC", display=False)
    assert "OC_DAPI_Count" in oc.columns
    assert "SCN_DAPI_Count" not in oc.columns


def test_summary_table_unknown_roi_falls_back_to_summary():
    batch = _fake_batch()
    df = services.summary_table(batch, roi_base="DOES_NOT_EXIST", display=False)
    # Falls back to batch.summary (SCN).
    assert "SCN_DAPI_Count" in df.columns


def test_summary_table_column_filter_narrows_and_keeps_ids():
    batch = _fake_batch()
    filtered = services.summary_table(
        batch,
        roi_base="SCN",
        display=False,
        column_strings=["DAPI"],
    )
    # Identifier columns retained, only DAPI measurement kept.
    assert list(filtered.columns) == ["AnimalName", "Condition", "SCN_DAPI_Count"]


def test_summary_table_column_filter_exclude():
    batch = _fake_batch()
    filtered = services.summary_table(
        batch,
        roi_base="SCN",
        display=False,
        column_strings=["SCN"],
        exclude=["NeuN"],
    )
    assert "SCN_DAPI_Count" in filtered.columns
    assert "SCN_NeuN_Area_um2" not in filtered.columns


def test_batch_overview_reports_identity():
    batch = _fake_batch()
    overview = services.batch_overview(batch)
    assert overview["name"] == "fake_batch"
    assert overview["summary_shape"] == (2, 4)
    assert overview["conditions"] == ["WT", "KO"]
    assert overview["markers"] == ["DAPI", "NeuN"]
    assert overview["experiments"] == ["exp1"]
    assert overview["roi_bases"] == ["SCN", "OC"]
