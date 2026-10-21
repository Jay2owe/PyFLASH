import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from reproducibility import run


def test_snapshot_copy_retries_transient_missing_source(tmp_path, monkeypatch):
    source = tmp_path / "input.bin"
    target = tmp_path / "snapshot" / "input.bin"
    source.write_bytes(b"stable bytes" * 2048)
    original_open = Path.open
    failures = {"remaining": 1}

    def flaky_open(path, *args, **kwargs):
        if path == source and args and args[0] == "rb" and failures["remaining"]:
            failures["remaining"] -= 1
            raise FileNotFoundError("transient source lookup race")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky_open)
    monkeypatch.setattr(run.time, "sleep", lambda _delay: None)
    record = run.copy_snapshot_file(source, target)

    assert failures["remaining"] == 0
    assert target.read_bytes() == source.read_bytes()
    assert record["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert not list(target.parent.glob("*.snapshot-tmp"))


def test_snapshot_copy_permanent_missing_source_is_bounded(tmp_path, monkeypatch):
    source = tmp_path / "missing.bin"
    source.write_bytes(b"still present for stat")
    attempts = {"count": 0}
    original_open = Path.open

    def missing_open(path, *args, **kwargs):
        if path == source and args and args[0] == "rb":
            attempts["count"] += 1
            raise FileNotFoundError("still missing")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", missing_open)
    monkeypatch.setattr(run.time, "sleep", lambda _delay: None)
    with pytest.raises(FileNotFoundError, match="still missing"):
        run.copy_snapshot_file(source, tmp_path / "snapshot.bin", attempts=3)
    assert attempts["count"] == 3


def test_snapshot_sources_records_order_hashes_and_progress(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(run, "ROOT", root)
    sources = [root / "a.txt", root / "nested" / "b.txt"]
    sources[0].write_text("alpha", encoding="utf-8")
    sources[1].parent.mkdir()
    sources[1].write_text("beta", encoding="utf-8")
    progress_path = tmp_path / "snapshot-progress.json"

    records = run.snapshot_sources(sources, tmp_path / "copies", workers=2,
                                  progress_path=progress_path)

    assert [record["sha256"] for record in records] == [
        hashlib.sha256(source.read_bytes()).hexdigest() for source in sources]
    assert json.loads(progress_path.read_text(encoding="utf-8"))["status"] == "finished"
    assert (tmp_path / "copies" / "a.txt").read_text() == "alpha"
    assert (tmp_path / "copies" / "nested" / "b.txt").read_text() == "beta"


def test_snapshot_failure_receipt_is_terminal_and_retains_partial_snapshot(tmp_path):
    output = tmp_path / "run"
    (output / "sources").mkdir(parents=True)
    progress = output / "snapshot-progress.json"
    run.write_json(progress, {"status": "failed", "completed_files": 1})
    error = FileNotFoundError("source vanished")
    receipt = {"status": "running", "passed": False, "workflow_gate": True}

    failure = run.record_snapshot_failure(output, receipt, error,
                                          stage="source-snapshot", progress_path=progress)

    assert failure["status"] == "failed-before-start"
    assert not failure["passed"]
    assert failure["workflow_stages_started"] is False
    assert failure["partial_snapshot_retained"] is True
    assert failure["snapshot_progress"]["completed_files"] == 1
    assert json.loads((output / "run.json").read_text())["stage"] == "source-snapshot"
    assert "source vanished" in (output / "snapshot-failure.log").read_text()


def test_real_data_space_reserve_covers_the_trial_peak(tmp_path, monkeypatch):
    source = tmp_path / "source.py"
    source.write_text("pass\n", encoding="utf-8")
    real_data = tmp_path / "batch.pkl"
    real_data.write_bytes(b"x")
    original_stat = Path.stat

    def report_large_saved_input(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if path == real_data:
            return SimpleNamespace(st_mode=result.st_mode, st_size=600 * 1024**2)
        return result

    monkeypatch.setattr(Path, "stat", report_large_saved_input)
    requirement = run.run_space_requirement([source], full=True, real_data=real_data)

    assert requirement["test_scratch_reserve_bytes"] == 8 * 1024**3
    assert requirement["real_data_scratch_reserve_bytes"] == 5 * 600 * 1024**2
    assert requirement["total_bytes"] == sum(requirement[key] for key in (
        "source_snapshot_bytes", "reference_output_reserve_bytes",
        "test_scratch_reserve_bytes", "real_data_scratch_reserve_bytes",
        "finalization_reserve_bytes"))


def test_disk_admission_failure_writes_terminal_receipt(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(run, "ROOT", tmp_path)
    source = tmp_path / "source.py"
    source.write_text("pass\n", encoding="utf-8")
    output_root = tmp_path / "runs"
    monkeypatch.setattr(run, "verification_sources", lambda: [source])
    monkeypatch.setattr(run, "versions", lambda: {"python": "test"})
    monkeypatch.setattr(run.shutil, "disk_usage",
                        lambda _: SimpleNamespace(total=10, used=9, free=1))
    monkeypatch.setattr(run.subprocess, "run",
                        lambda *args, **kwargs: SimpleNamespace(stdout="test-commit\n"))
    monkeypatch.setattr(sys, "argv", ["reproducibility.run", "--output", str(output_root)])

    with pytest.raises(SystemExit) as failure:
        run.main()

    assert failure.value.code == 1
    run_folder = next(output_root.iterdir())
    started = json.loads((run_folder / "run-started.json").read_text(encoding="utf-8"))
    terminal = json.loads((run_folder / "run.json").read_text(encoding="utf-8"))
    assert started["status"] == "running"
    assert terminal["status"] == "failed-before-start"
    assert terminal["stage"] == "disk-admission"
    assert terminal["workflow_stages_started"] is False
    assert "Needs estimated" in terminal["error"]
    assert not (run_folder / "sources").exists()
