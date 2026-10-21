"""Keep Streamlit's REPL check from materializing slow Windows stack frames."""
from __future__ import annotations

import os
import sys
from types import ModuleType


def _root_frame_filename(frame=None):
    frame = sys._getframe(1) if frame is None else frame
    while frame.f_back is not None:
        frame = frame.f_back
    return frame.f_code.co_filename


def is_repl():
    """Match Streamlit's REPL check without building every ``FrameInfo``."""
    filename = _root_frame_filename()
    if filename.endswith(os.path.join('bin', 'ipython')):
        return True
    return filename in {'<stdin>', '<string>'}


def install_fast_repl_detection(env_util: ModuleType | None = None):
    """Replace only Streamlit's equivalent helper before the first UI delta."""
    if env_util is None:
        from streamlit import env_util
    if hasattr(env_util, 'is_repl'):
        env_util.is_repl = is_repl
