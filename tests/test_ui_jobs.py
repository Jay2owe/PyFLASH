"""Admission, failure, persistence and result ownership of background processing."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest

from PyFLASH.ui import jobs, services, workspace
from PyFLASH.ui.project_io import Project


def project():
    return Project(name="fixture", batch_path="fixture-inputs", import_images=False,
                   conditions={"factor": "Genotype", "entries": [{"label": "WT", "color": "blue"}]}).to_dict()


def fake_launcher(monkeypatch):
    monkeypatch.setattr(jobs, "_launch", lambda *args: SimpleNamespace(pid=os.getpid(), poll=lambda: None))


def source_fixture(tmp_path):
    path = tmp_path / 'input.pkl'
    if not path.exists():
        path.write_bytes(b'unit-test source; the loader is injected')
    return str(path)


def test_submit_detaches_inputs_and_never_executes_analysis_on_caller(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    monkeypatch.setattr(services, "create_batch", lambda *a, **k: pytest.fail("analysis ran on caller"))
    spec = project()
    identity = jobs.start_processing(spec, root=tmp_path)
    spec["conditions"]["entries"][0]["label"] = "changed later"
    request = json.loads((tmp_path / identity / "request.json").read_text())
    assert request["project"]["conditions"]["entries"][0]["label"] == "WT"
    assert jobs.read_job(identity, tmp_path)["status"] == "queued"
    with pytest.raises(jobs.JobBusyError, match="already running"):
        jobs.start_processing(spec, root=tmp_path)


def test_worker_environment_keeps_unicode_logs_and_bounds_library_threads(tmp_path, monkeypatch):
    observed = {}
    def launch(request, stream, env):
        observed.update(env)
        stream.write("Microscopy: μm — complete\n".encode("utf-8"))
        return SimpleNamespace(pid=os.getpid(), poll=lambda: None)
    monkeypatch.setattr(jobs, "_launch", launch)
    identity = jobs.start_processing(project(), root=tmp_path)
    assert observed["PYTHONIOENCODING"] == "utf-8"
    assert observed["OPENBLAS_NUM_THREADS"] == observed["OMP_NUM_THREADS"] == "1"
    assert "μm — complete" in jobs.log_tail(identity, tmp_path)


def test_worker_uses_running_python_environment_not_version_launcher(tmp_path, monkeypatch):
    import sys
    recorded = []
    monkeypatch.setattr(jobs.subprocess, 'Popen', lambda command, **kwargs: recorded.append(command))
    with (tmp_path / 'worker.log').open('wb') as log:
        jobs._launch(tmp_path / 'request.json', log, {})
    actual = Path(sys.prefix) / 'python.exe'
    expected = str(actual) if os.name == 'nt' and actual.is_file() else sys.executable
    assert recorded[0][0] == expected
    assert recorded[0][1:4] == ['-u', '-m', 'PyFLASH.ui.job_worker']


def test_concurrent_submissions_admit_only_one(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    def submit(_):
        try:
            return jobs.start_processing(project(), root=tmp_path)
        except jobs.JobBusyError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        admitted = [value for value in pool.map(submit, range(4)) if value]
    assert len(admitted) == 1
    assert len(list(tmp_path.glob("*/request.json"))) == 1


def test_worker_forwards_settings_and_persists_completed_result(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    identity = jobs.start_processing(project(), rerun=True, reimport_images=True, root=tmp_path)
    captured = {}
    batch = SimpleNamespace()
    def create(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        assert jobs.read_job(identity, tmp_path)["status"] == "running"
        return batch
    def save(value, path):
        assert value is batch
        Path(path).write_bytes(b"complete fixture")
    before = services.logger._output, services.logger.verbosity
    state = jobs.run_request(tmp_path / identity / "request.json", create=create, save=save)
    assert state["status"] == "succeeded"
    assert Path(state["result_path"]).read_bytes() == b"complete fixture"
    assert captured["args"][0] == "fixture"
    assert captured["kwargs"]["rerun"] is True
    assert captured["kwargs"]["import_images"] is False
    assert captured["kwargs"]["reimport_images"] is True
    assert (services.logger._output, services.logger.verbosity) == before
    # The persisted completion admits another request, without deleting its result.
    assert jobs.start_processing(project(), root=tmp_path) != identity
    assert Path(state["result_path"]).exists()


def test_cached_result_is_not_serialised_twice(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    result = tmp_path / "existing.pkl"; result.write_bytes(b"source")
    identity = jobs.start_processing(project(), root=tmp_path)
    state = jobs.run_request(tmp_path / identity / "request.json",
        create=lambda *a, **k: SimpleNamespace(_state_path=str(result)),
        save=lambda *a: pytest.fail("cached result was written again"))
    assert state["result_path"] == str(result.resolve())
    assert result.read_bytes() == b"source"


def test_failed_worker_preserves_inputs_and_can_be_retried(tmp_path, monkeypatch, capsys):
    fake_launcher(monkeypatch)
    identity = jobs.start_processing(project(), root=tmp_path)
    def fail(*a, **k):
        raise ValueError("invalid fixture input")
    state = jobs.run_request(tmp_path / identity / "request.json", create=fail)
    assert state["status"] == "failed"
    assert "invalid fixture input" in state["error"]
    assert "invalid fixture input" in capsys.readouterr().err
    assert (tmp_path / identity / "request.json").exists()
    assert jobs.start_processing(project(), root=tmp_path) != identity


def test_lost_worker_is_reported_and_finished_handles_are_reaped(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    identity = jobs.start_processing(project(), root=tmp_path)
    monkeypatch.setattr(jobs, "_alive", lambda pid: False)
    jobs._children[identity] = SimpleNamespace(poll=lambda: 1)
    assert jobs.read_job(identity, tmp_path)["status"] == "failed"
    assert identity not in jobs._children


def test_active_job_survives_server_manager_restart(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    identity = jobs.start_processing(project(), root=tmp_path)
    jobs._children.pop(identity)
    assert jobs.latest_job(tmp_path)["id"] == identity
    with pytest.raises(jobs.JobBusyError):
        jobs.start_processing(project(), root=tmp_path)


def test_log_reads_are_bounded_and_ids_cannot_escape_job_store(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    identity = jobs.start_processing(project(), root=tmp_path)
    (tmp_path / identity / "progress.log").write_bytes(b"start" + b"x" * 10000 + b"end")
    tail = jobs.log_tail(identity, tmp_path, max_bytes=100)
    assert len(tail) == 100 and tail.endswith("end")
    with pytest.raises(ValueError):
        jobs.read_job("../outside", tmp_path)


def test_old_dataset_result_cannot_replace_current_views(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    identity = jobs.start_operation("figure", {"kind": "pickle", "path": source_fixture(tmp_path)},
        {"plot_type": "mean_bars", "kwargs": {"data_cols": ["signal"]}},
        name="Figure", dataset_token="first-dataset", target_key="ui_last_plot", root=tmp_path)
    path = tmp_path / identity
    workspace.write_json(path / "result.json", {"paths": ["original-result.svg"]})
    state = jobs.read_job(identity, tmp_path); state["status"] = "succeeded"
    workspace.write_json(path / "state.json", state)
    assert jobs.completed_result(state, "new-dataset", tmp_path) is None
    key, result = jobs.completed_result(state, "first-dataset", tmp_path)
    assert key == 'ui_last_plot' and result['paths'] == ['original-result.svg']
    assert result['schema_version'] == workspace.OPERATION_STATE_SCHEMA_VERSION


def test_worker_rejects_source_changed_since_submission(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    source = tmp_path / "input.pkl"
    source.write_bytes(b"original")
    identity = jobs.start_operation("csv", {"kind": "pickle", "path": str(source), "version": workspace.source_version(source)},
        {"region": "SCN"}, name="CSV", dataset_token="current", target_key="result", root=tmp_path)
    source.write_bytes(b"changed later")
    monkeypatch.setattr(services, "open_pickle", lambda *a: pytest.fail("changed source was loaded"))
    state = jobs.run_request(tmp_path / identity / "request.json")
    assert state["status"] == "failed" and "changed after submission" in state["error"]


def test_background_csv_matches_original_table_and_current_edits(tmp_path, monkeypatch):
    import pandas as pd
    fake_launcher(monkeypatch)
    original = pd.DataFrame({"AnimalName": ["001", "002"], "Condition": ["WT", "KO"],
        "Signal": [1.5, "NOT_INCLUDED_IN_EXPERIMENT"]})
    batch = SimpleNamespace(summary=original)
    edits = pd.DataFrame({"AnimalName": ["A1"], "Marker": ["DAPI"], "Representative": [True]})
    monkeypatch.setattr(services, "open_pickle", lambda path: batch)
    identity = jobs.start_operation("csv", {"kind": "pickle", "path": source_fixture(tmp_path)}, {"region": "SCN"},
        name="CSV", dataset_token="current", target_key="ui_csv_result",
        representatives=workspace.selection_snapshot(edits), root=tmp_path)
    state = jobs.run_request(tmp_path / identity / "request.json")
    assert state["status"] == "succeeded"
    key, result = jobs.completed_result(state, "current", tmp_path)
    assert key == "ui_csv_result"
    assert Path(result["path"]).read_bytes() == original.to_csv(index=False).encode("utf-8")
    pd.testing.assert_frame_equal(batch.representative_images, edits)
    assert original.loc[1, "Signal"] == "NOT_INCLUDED_IN_EXPERIMENT"


def test_plot_worker_passes_identical_parameters_without_changing_parent(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    batch = SimpleNamespace(fig_path=str(tmp_path))
    monkeypatch.setattr(services, "open_pickle", lambda path: batch)
    observed = {}
    def plot(target, plot_type, parameters):
        observed.update(target=target, type=plot_type, parameters=parameters)
    monkeypatch.setattr(services, "run_quick_plot", plot)
    monkeypatch.setattr(workspace, "equivalent_script", lambda *a, **k: "equivalent package call")
    kwargs = {"data_cols": ["Signal"], "save": False, "save_normality": False}
    identity = jobs.start_operation("figure", {"kind": "pickle", "path": source_fixture(tmp_path)},
        {"plot_type": "mean_bars", "kwargs": kwargs}, name="Figure", dataset_token="current", target_key="ui_last_plot", root=tmp_path)
    state = jobs.run_request(tmp_path / identity / "request.json")
    assert state["status"] == "succeeded"
    assert observed["target"] is batch and observed["type"] == "mean_bars"
    assert observed["parameters"]["save"] is False
    assert observed["parameters"].get("data_cols", observed["parameters"].get("filtered_columns")) == ["Signal"]
    result = jobs.completed_result(state, "current", tmp_path)[1]
    assert 'PyFLASH.ui.jobs.replay_request' in result['script']
    receipt = json.loads(Path(result['receipt']).read_text())
    assert receipt['request']['parameters']['kwargs'] == kwargs
    assert result["paths"] == []


@pytest.mark.parametrize("kind", ["save", "workbooks"])
def test_exports_use_exact_current_selections_and_options(tmp_path, monkeypatch, kind):
    import pandas as pd
    fake_launcher(monkeypatch)
    edits = pd.DataFrame({"AnimalName": ["001", "002"],
        "Representative": pd.Series([True, pd.NA], dtype="boolean"),
        "Score": [1.2345678901234567, 3.141592653589793],
        "Identifier": pd.Series([2**63 + 7, 2**63 + 8], dtype="uint64")}, index=pd.Index([0, 1], name="selection"))
    snapshot = workspace.selection_snapshot(edits)
    pd.testing.assert_frame_equal(workspace.restore_selection_snapshot(snapshot), edits, check_exact=True)
    batch = SimpleNamespace()
    monkeypatch.setattr(services, "open_pickle", lambda path: batch)
    filename = str(tmp_path / "saved.pkl")
    options = {"filename": filename} if kind == "save" else {"if_summary": True, "if_extended": False, "behaviour": False}
    seen = {}
    def save(target, path):
        seen.update(target=target, options={"filename": path})
        Path(path).write_bytes(b'unit-test saved result')
    def export(target, **kwargs):
        seen.update(target=target, options=kwargs)
        return []
    monkeypatch.setattr(services, "save_batch", save)
    monkeypatch.setattr(services, "export_excel", export)
    identity = jobs.start_operation(kind, {"kind": "pickle", "path": source_fixture(tmp_path)}, options,
        name=kind, dataset_token="current", target_key="result", representatives=snapshot, root=tmp_path)
    edits.loc[0, "Score"] = 999  # Edits after submission do not change the request.
    state = jobs.run_request(tmp_path / identity / "request.json")
    assert state["status"] == "succeeded"
    assert seen == {"target": batch, "options": options if kind == "save" else {**options, "capture": False, 'return_paths':True}}
    pd.testing.assert_frame_equal(batch.representative_images, workspace.restore_selection_snapshot(snapshot), check_exact=True)
    assert batch.representative_images.loc[0, "AnimalName"] == "001"
    assert batch.representative_images.loc[0, "Score"] == 1.2345678901234567


def test_invalid_figure_spec_reports_failure_not_success(tmp_path, monkeypatch):
    fake_launcher(monkeypatch)
    monkeypatch.setattr(services, "open_pickle", lambda path: SimpleNamespace(fig_path=str(tmp_path)))
    monkeypatch.setattr('PyFLASH.queue.run_spec_queue', lambda *a, **k:{'failures':['missing measurement'], 'pending':[]})
    identity = jobs.start_operation("figure_spec", {"kind": "pickle", "path": source_fixture(tmp_path)},
        {"spec_path": "invalid.yaml"}, name="Figure specification", dataset_token="current", target_key="result", root=tmp_path)
    state = jobs.run_request(tmp_path / identity / "request.json")
    assert state["status"] == "failed"
    assert "missing measurement" in state["error"]


def test_image_worker_selects_experiment_and_replay_retains_exact_edits(tmp_path, monkeypatch):
    import pandas as pd
    fake_launcher(monkeypatch)
    target = SimpleNamespace(name="experiment-2", fig_path=str(tmp_path))
    batch = SimpleNamespace(experiment_list=[SimpleNamespace(name="experiment-1"), target])
    monkeypatch.setattr(services, "open_pickle", lambda path: batch)
    observed = {}
    monkeypatch.setattr(services, "run_quick_plot", lambda b, p, k: observed.update(target=b, plot=p, parameters=k))
    monkeypatch.setattr(workspace, "equivalent_script", lambda *a, **k: "batch = open_input()\nPARAMETERS = {}")
    selections = pd.DataFrame({"AnimalName": ["001"], "Representative": [True]})
    identity = jobs.start_operation("figure", {"kind": "pickle", "path": source_fixture(tmp_path)},
        {"target_experiment": target.name, "plot_type": "locations", "kwargs": {"objects": ["DAPI"], "save": False}},
        name="Locations", dataset_token="current", target_key="ui_location_result",
        representatives=workspace.selection_snapshot(selections), root=tmp_path)
    state = jobs.run_request(tmp_path / identity / "request.json")
    assert state["status"] == "succeeded"
    assert observed["target"] is target and observed["plot"] == "locations"
    result = jobs.completed_result(state, "current", tmp_path)[1]
    receipt = json.loads(Path(result['receipt']).read_text())
    pd.testing.assert_frame_equal(workspace.restore_selection_snapshot(receipt['request']['representatives']), selections)
    pd.testing.assert_frame_equal(batch.representative_images, selections, check_exact=True)


def test_selection_snapshot_checksum_detects_changed_edits():
    import pandas as pd
    snapshot = workspace.selection_snapshot(pd.DataFrame({"Subject": ["001"]}))
    snapshot["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        workspace.restore_selection_snapshot(snapshot)
