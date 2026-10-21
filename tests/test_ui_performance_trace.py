import json

from PyFLASH.ui import performance_trace


def test_performance_trace_is_opt_in_and_writes_machine_readable_timings(tmp_path, monkeypatch):
    path = tmp_path / "timings.jsonl"
    monkeypatch.delenv("PYFLASH_UI_PERFORMANCE_TRACE", raising=False)
    performance_trace.record("disabled", performance_trace.start())
    assert not path.exists()

    monkeypatch.setenv("PYFLASH_UI_PERFORMANCE_TRACE", str(path))
    started = performance_trace.start()
    performance_trace.record("open_source", started, rows=42)

    event = json.loads(path.read_text(encoding="utf-8"))
    assert event["name"] == "open_source"
    assert event["rows"] == 42
    assert event["seconds"] >= 0
