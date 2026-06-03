"""Unit tests for PyFLASH.ui.services.

The services adapter must be importable and usable with **no Streamlit
installed** (house rule 2). These tests therefore:

* import ``PyFLASH.ui.services`` and assert ``streamlit`` was not pulled in,
* check ``package_info()`` reports a clean core import,
* check ``open_pickle`` is wired to ``serialization.load_state`` (verified via
  a real round-tripped pickle, with no streamlit dependency).
"""

import os
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


# ── Stage 03: experiment folder validation ──────────────────────────────────


def _make_experiment(parent, name, *, data_subdirs=(), csv_in_data=False,
                     no_data_analysis=False):
    """Create a fake experiment folder tree under *parent*; return its path.

    Strictly local tmp dirs — never touches real data. Builds
    ``<parent>/<name>/Data Analysis/<subdirs...>`` and, optionally, a stray
    ``.csv`` directly under ``Data Analysis/``.
    """
    exp = os.path.join(parent, name)
    os.makedirs(exp, exist_ok=True)
    if no_data_analysis:
        return exp
    data = os.path.join(exp, "Data Analysis")
    os.makedirs(data, exist_ok=True)
    for sub in data_subdirs:
        os.makedirs(os.path.join(data, sub), exist_ok=True)
    if csv_in_data:
        with open(os.path.join(data, "stray.csv"), "w", encoding="utf-8") as f:
            f.write("col1,col2\n1,2\n")
    return exp


def test_validate_folder_valid_via_required_subdir(tmp_path):
    # Data Analysis/Objects/ present -> valid (the REQUIRED_ANY branch).
    exp = _make_experiment(str(tmp_path), "expA", data_subdirs=["Objects"])
    # Drop a csv inside Objects/ to mirror the fixture description.
    with open(os.path.join(exp, "Data Analysis", "Objects", "x.csv"),
              "w", encoding="utf-8") as f:
        f.write("a,b\n1,2\n")

    result = services.validate_experiment_folder(exp)
    assert result["valid"] is True
    assert result["reason"] == "ok"
    assert result["layout"]["Objects"] is True


def test_validate_folder_valid_via_stray_csv(tmp_path):
    # Data Analysis/ with only a stray .csv (no required subdirs) -> valid.
    exp = _make_experiment(str(tmp_path), "expB", csv_in_data=True)
    result = services.validate_experiment_folder(exp)
    assert result["valid"] is True
    assert result["reason"] == "ok"
    # No required subdirs exist, but structure is still satisfied by the csv.
    assert result["layout"]["Objects"] is False


def test_validate_folder_invalid_missing_data_analysis(tmp_path):
    exp = _make_experiment(str(tmp_path), "expC", no_data_analysis=True)
    result = services.validate_experiment_folder(exp)
    assert result["valid"] is False
    assert result["reason"] == "missing 'Data Analysis/'"
    assert all(v is False for v in result["layout"].values())


def test_validate_folder_invalid_empty_data_analysis(tmp_path):
    # Data Analysis/ exists but is empty -> invalid with the no-CSV reason.
    exp = _make_experiment(str(tmp_path), "expD")
    result = services.validate_experiment_folder(exp)
    assert result["valid"] is False
    assert result["reason"] == "no Objects/Attributes/ROI Intensities or CSVs"


def test_validate_folder_has_images_reflects_images_subdir(tmp_path):
    with_images = _make_experiment(
        str(tmp_path), "expWith", data_subdirs=["Objects", "Images"])
    without_images = _make_experiment(
        str(tmp_path), "expWithout", data_subdirs=["Objects"])

    assert services.validate_experiment_folder(with_images)["has_images"] is True
    res = services.validate_experiment_folder(without_images)
    assert res["has_images"] is False
    assert res["layout"]["Images"] is False


def test_discover_experiments_classifies_each_subfolder(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    _make_experiment(str(root), "good_objects", data_subdirs=["Objects"])
    _make_experiment(str(root), "good_csv", csv_in_data=True)
    _make_experiment(str(root), "bad_no_da", no_data_analysis=True)
    # A loose file at the root must be ignored (only directories scanned).
    with open(os.path.join(str(root), "notes.txt"), "w", encoding="utf-8") as f:
        f.write("ignore me")

    records = services.discover_experiments(str(root))
    by_name = {r["name"]: r for r in records}

    # All three subfolders reported (valid and invalid alike), file skipped.
    assert set(by_name) == {"good_objects", "good_csv", "bad_no_da"}
    assert by_name["good_objects"]["valid"] is True
    assert by_name["good_csv"]["valid"] is True
    assert by_name["bad_no_da"]["valid"] is False
    assert by_name["bad_no_da"]["reason"] == "missing 'Data Analysis/'"


def test_discover_experiments_sorted_by_name(tmp_path):
    root = tmp_path / "root2"
    root.mkdir()
    for name in ["zeta", "alpha", "mid"]:
        _make_experiment(str(root), name, data_subdirs=["Objects"])
    records = services.discover_experiments(str(root))
    assert [r["name"] for r in records] == ["alpha", "mid", "zeta"]


# ── Stage 03: Project schema round-trip ─────────────────────────────────────


def test_project_round_trips_new_fields(tmp_path):
    from PyFLASH.config import Config
    from PyFLASH.ui.project_io import Project, load_project, save_project

    proj = Project(
        name="trip",
        batch_path=r"X:\some\root",
        experiments={"exp1": r"X:\some\root\exp1"},
        pickle_path=r"X:\cache",
        threshold=55,
        import_images=False,
        experiment_paths=[r"X:\some\root\exp1"],
    )
    out = tmp_path / "proj.json"
    save_project(proj, str(out))
    loaded = load_project(str(out))

    assert loaded.name == "trip"
    assert loaded.batch_path == r"X:\some\root"
    assert loaded.experiments == {"exp1": r"X:\some\root\exp1"}
    assert loaded.pickle_path == r"X:\cache"
    assert loaded.threshold == 55
    assert loaded.import_images is False
    assert loaded.experiment_paths == [r"X:\some\root\exp1"]
    # Defaults still sensible on a bare Project.
    assert Project().threshold == Config.THRESHOLD
    assert Project().import_images is True


def test_project_from_dict_ignores_unknown_fields():
    from PyFLASH.ui.project_io import Project

    proj = Project.from_dict(
        {"name": "x", "batch_path": "p", "future_field": 123})
    assert proj.name == "x"
    assert proj.batch_path == "p"
    assert not hasattr(proj, "future_field")


# ── Stage 05: batch processing — output capture + run_create_batch ──────────


def test_capture_output_captures_logger_and_stdout_then_restores():
    # capture_output must collect BOTH the package logger and plain stdout
    # (ProgressTracker prints off-notebook), and ALWAYS restore the prior
    # logger output target afterwards.
    from PyFLASH._logging import logger

    prev = logger._output
    with services.capture_output() as buf:
        # Logger channel (status() writes through logger._output).
        logger.status("hello")
        # stdout channel (ProgressTracker fallback uses print()).
        print("world")
        captured = buf.getvalue()

    assert "hello" in captured
    assert "world" in captured
    # The global logger output target is restored to exactly what it was.
    assert logger._output is prev


def test_capture_output_restores_logger_on_exception():
    # Even when the body raises, the finally clause must restore logger._output.
    from PyFLASH._logging import logger

    prev = logger._output
    try:
        with services.capture_output():
            logger.status("before boom")
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert logger._output is prev


def test_run_create_batch_forwards_kwargs_and_returns_log(monkeypatch):
    # Monkeypatch the module-level create_batch with a fake that emits output
    # (both channels) and returns a sentinel batch. Assert the sentinel comes
    # back, the captured log contains the emitted text, and every kwarg is
    # forwarded exactly.
    from PyFLASH._logging import logger

    captured_call = {}
    sentinel = types.SimpleNamespace(name="fake", _last_process_summary="3|9")

    def fake_create_batch(name, conditions, batch_path, **kwargs):
        captured_call["name"] = name
        captured_call["conditions"] = conditions
        captured_call["batch_path"] = batch_path
        captured_call.update(kwargs)
        # Emit on both channels that capture_output redirects.
        logger.status("fake progress line")
        print("ProgressTracker fallback line")
        return sentinel

    monkeypatch.setattr(services, "create_batch", fake_create_batch)

    cond = object()
    batch, log = services.run_create_batch(
        name="run_test",
        conditions=cond,
        batch_path=r"X:\root",
        experiments={"e1": r"X:\root\e1"},
        pickle_path=r"X:\cache",
        threshold=42,
        rerun=True,
        import_images=False,
        reimport_images=True,
    )

    assert batch is sentinel
    # Output from both channels lands in the returned log text.
    assert "fake progress line" in log
    assert "ProgressTracker fallback line" in log

    # Positional args forwarded.
    assert captured_call["name"] == "run_test"
    assert captured_call["conditions"] is cond
    assert captured_call["batch_path"] == r"X:\root"
    # Keyword args forwarded verbatim, including progress=True (always set).
    assert captured_call["experiments"] == {"e1": r"X:\root\e1"}
    assert captured_call["pickle_path"] == r"X:\cache"
    assert captured_call["threshold"] == 42
    assert captured_call["rerun"] is True
    assert captured_call["import_images"] is False
    assert captured_call["reimport_images"] is True
    assert captured_call["progress"] is True


def test_run_create_batch_restores_logger_on_error(monkeypatch):
    # A create_batch error (e.g. ValueError: No experiment folders found) must
    # propagate, but the global logger output is still restored by the
    # capture_output finally clause.
    from PyFLASH._logging import logger

    def boom(*args, **kwargs):
        raise ValueError("No experiment folders found in X:\\root")

    monkeypatch.setattr(services, "create_batch", boom)

    prev = logger._output
    try:
        services.run_create_batch(
            name="bad", conditions=object(), batch_path=r"X:\root")
    except ValueError as exc:
        assert "No experiment folders found" in str(exc)
    else:  # pragma: no cover - the fake always raises
        raise AssertionError("expected ValueError")

    assert logger._output is prev
