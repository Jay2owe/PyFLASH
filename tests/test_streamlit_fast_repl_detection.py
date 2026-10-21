import os
from types import SimpleNamespace

import pytest

from PyFLASH.ui import streamlit_compat


@pytest.mark.parametrize(('filename', 'expected'), [
    (f'C:{os.sep}tools{os.sep}bin{os.sep}ipython', True),
    ('<stdin>', True),
    ('<string>', True),
    ('C:/project/PyFLASH/ui/app.py', False),
])
def test_fast_repl_detection_preserves_streamlit_filename_rules(monkeypatch, filename, expected):
    monkeypatch.setattr(streamlit_compat, '_root_frame_filename', lambda: filename)
    assert streamlit_compat.is_repl() is expected


def test_installer_replaces_only_streamlit_repl_probe():
    module = SimpleNamespace(is_repl=lambda: True, other='untouched')

    streamlit_compat.install_fast_repl_detection(module)

    assert module.is_repl is streamlit_compat.is_repl
    assert module.other == 'untouched'


def test_app_probe_walks_frames_without_inspect_stack(monkeypatch):
    import inspect
    monkeypatch.setattr(inspect, 'stack', lambda: pytest.fail('inspect.stack must not be used'))
    assert isinstance(streamlit_compat._root_frame_filename(), str)
