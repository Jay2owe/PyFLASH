"""The normal and editable launches use the documented interpreter/settings."""
import subprocess
import sys
import pytest
from PyFLASH.ui import main


@pytest.fixture(autouse=True)
def isolate_command_checks_from_the_live_assistant(monkeypatch):
    # These tests inspect launch arguments. An installed assistant dependency
    # must not turn a subprocess.call stub into a real, blocking web server.
    monkeypatch.setenv("PYFLASH_AI", "0")


@pytest.mark.parametrize("arguments, expected", [
    (["--", "--demo"], ["--server.fileWatcherType=none"]),
    (["--dev", "--", "--demo"], ["--server.fileWatcherType=poll", "--server.runOnSave=true"]),
    (["--server.fileWatcherType=watchdog", "--", "--demo"], ["--server.fileWatcherType=watchdog"]),
])
def test_launch_honours_analysis_development_and_explicit_settings(monkeypatch, arguments, expected):
    calls = []
    monkeypatch.setattr(sys, "argv", ["pyflash-ui", *arguments])
    monkeypatch.setattr(subprocess, "call", lambda args: calls.append(args) or 0)
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 0
    assert calls[0][1:4] == ["-m", "streamlit", "run"]
    assert [arg for arg in calls[0] if arg.startswith("--server.")] == expected
    assert "--dev" not in calls[0]
    assert calls[0][-2:] == ["--", "--demo"]
    assert '--runner.postScriptGC=false' in calls[0]


def test_explicit_collection_setting_is_preserved(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, 'argv', ['pyflash-ui', '--runner.postScriptGC=true'])
    monkeypatch.setattr(subprocess, 'call', lambda args: calls.append(args) or 0)
    with pytest.raises(SystemExit):
        main()
    assert '--runner.postScriptGC=true' in calls[0]
    assert '--runner.postScriptGC=false' not in calls[0]


@pytest.mark.parametrize("available", [False, True])
@pytest.mark.parametrize("setting", [None, "0", "1"])
def test_assistant_dependency_and_opt_out_choose_the_launch_route(monkeypatch, available, setting):
    import importlib.util
    from PyFLASH.ui import ai_assistant

    if setting is None:
        monkeypatch.delenv("PYFLASH_AI", raising=False)
    else:
        monkeypatch.setenv("PYFLASH_AI", setting)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object() if available else None)
    monkeypatch.setattr(sys, "argv", ["pyflash-ui", "--", "--demo"])
    calls = []
    monkeypatch.setattr(ai_assistant, "launch", lambda args: calls.append(("assistant", args)))
    monkeypatch.setattr(subprocess, "call", lambda args: calls.append(("streamlit", args)) or 0)
    assisted = available and setting != "0"
    if assisted:
        main()
    else:
        with pytest.raises(SystemExit) as result:
            main()
        assert result.value.code == 0
    assert len(calls) == 1
    route, command = calls[0]
    assert route == ("assistant" if assisted else "streamlit")
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[-2:] == ["--", "--demo"]
    assert "--server.fileWatcherType=none" in command
    assert "--runner.postScriptGC=false" in command
