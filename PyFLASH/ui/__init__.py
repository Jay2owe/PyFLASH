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
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "streamlit", "run", app, *sys.argv[1:]]
        )
    )
