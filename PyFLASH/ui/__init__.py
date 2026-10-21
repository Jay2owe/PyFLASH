"""Optional Streamlit UI for PyFLASH.

Import is lazy; core PyFLASH never depends on this subpackage. ``main()`` is the
``pyflash-ui`` console-script entry point. A console_script runs in-process and
cannot host a Streamlit server directly, so it shells out to ``streamlit run``.
"""


def main():
    """Launch the Streamlit app via subprocess (``streamlit run app.py``)."""
    import os
    import sys
    import subprocess

    app = os.path.join(os.path.dirname(__file__), "app.py")
    args = sys.argv[1:]
    development = "--dev" in args
    args = [arg for arg in args if arg != "--dev"]
    # Streamlit scans every imported module after a run to implement automatic
    # source reload. That blocks asset requests on Windows in synced folders; ordinary
    # analysis sessions need no source watcher. Keep an explicit development
    # mode and honour an explicitly requested Streamlit watcher setting.
    watcher = [] if any(arg.startswith("--server.fileWatcherType") for arg in args) else [
        "--server.fileWatcherType=" + ("poll" if development else "none")]
    if development and not any(arg.startswith("--server.runOnSave") for arg in args):
        watcher.append("--server.runOnSave=true")
    # Leave Python's automatic cyclic collector enabled. Streamlit's optional
    # full-generation collection after every script/fragment delays linked
    # redraws; owned browser comparisons retain timings and bounded memory.
    if not any(arg.startswith("--runner.postScriptGC") for arg in args):
        watcher.append("--runner.postScriptGC=false")
    actual = os.path.join(sys.prefix, "python.exe")
    executable = actual if os.name == "nt" and os.path.isfile(actual) else sys.executable
    from importlib.util import find_spec
    if os.environ.get("PYFLASH_AI", "1") != "0" and find_spec("aiify") is not None:
        from .ai_assistant import launch
        launch([executable, "-m", "streamlit", "run", app, *watcher, *args])
        return
    raise SystemExit(
        subprocess.call(
            [executable, "-m", "streamlit", "run", app, *watcher, *args]
        )
    )
