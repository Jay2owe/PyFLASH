"""Failure during a scientific save must preserve the previous good analysis."""
from types import SimpleNamespace
import pickle

import pandas as pd
import pytest

from PyFLASH import serialization


def state(value=1):
    return SimpleNamespace(name="example", summary=pd.DataFrame({"x": [value]}),
                           data={}, filePath=None)


def test_interrupted_pickle_write_preserves_previous_state(tmp_path, monkeypatch):
    path = tmp_path / "analysis.pkl"
    serialization.save_state(state(), path, verbose=False)
    previous = path.read_bytes()

    def interrupted(obj, stream, **kwargs):
        stream.write(b"incomplete")
        raise OSError("simulated interruption")

    monkeypatch.setattr(serialization.pickle, "dump", interrupted)
    with pytest.raises(OSError, match="interruption"):
        serialization.save_state(state(2), path, verbose=False)
    assert path.read_bytes() == previous
    assert serialization.load_state(path, verbose=False).summary.iloc[0, 0] == 1
    assert not list(tmp_path.glob(".pyflash-state-*"))


def test_replace_failure_preserves_previous_state(tmp_path, monkeypatch):
    path = tmp_path / "analysis.pkl"
    serialization.save_state(state(), path, verbose=False)
    previous = path.read_bytes()
    def unavailable(*args):
        raise PermissionError("file busy")
    monkeypatch.setattr(serialization.os, "replace", unavailable)
    with pytest.raises(PermissionError, match="busy"):
        serialization.save_state(state(2), path, verbose=False)
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob(".pyflash-state-*"))


def test_legacy_state_migrates_without_rewriting_source(tmp_path):
    path = tmp_path / "old.pkl"
    path.write_bytes(pickle.dumps(state()))
    previous = path.read_bytes()
    restored = serialization.load_state(path, verbose=False)
    assert restored._state_schema_version == serialization.STATE_SCHEMA_VERSION
    assert path.read_bytes() == previous


def test_future_state_is_rejected_without_rewriting_source(tmp_path):
    obj = state()
    obj._state_schema_version = serialization.STATE_SCHEMA_VERSION + 1
    path = tmp_path / "future.pkl"
    path.write_bytes(pickle.dumps(obj))
    previous = path.read_bytes()
    with pytest.raises(ValueError, match="schema version"):
        serialization.load_state(path, verbose=False)
    assert path.read_bytes() == previous


def test_provenance_failure_is_visible_without_breaking_output(tmp_path, monkeypatch):
    from PyFLASH import provenance
    from PyFLASH._logging import logger
    output = tmp_path / "figure.svg"
    output.write_text("already saved")
    def broken(*args):
        raise OSError("disk unavailable")
    notices = []
    monkeypatch.setattr(provenance, "_write", broken)
    monkeypatch.setattr(logger, "warn", notices.append)
    provenance.record(output, function="test")
    assert len(notices) == 1
    assert "disk unavailable" in notices[0]
    assert output.read_text() == "already saved"
