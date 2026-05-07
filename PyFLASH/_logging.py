"""
Unified output system for PyFLASH.

Provides categorised, silenceable output that works in both Jupyter notebooks
and terminal sessions.  All package modules should use the singleton ``logger``
rather than bare ``print()`` calls.

User-facing API (re-exported from ``PyFLASH``):

    import PyFLASH
    PyFLASH.set_verbosity('debug')   # or int 0-4, or Verbosity enum
    with PyFLASH.silent():
        batch.export_all_excel()         # no output
"""

import sys
import threading
from enum import IntEnum


# ── Verbosity levels ──────────────────────────────────────────────────

class Verbosity(IntEnum):
    """Output verbosity levels, loosely modelled on scanpy."""
    error = 0    # only errors
    warning = 1  # + warnings
    info = 2     # + file confirmations, status updates, progress
    hint = 3     # + diagnostic detail (row counts, backend choices)
    debug = 4    # + per-item trace


# ── Prefixes ──────────────────────────────────────────────────────────

_PREFIXES = {
    'status':  '',
    'confirm': '[OK] ',
    'timing':  '[T]  ',
    'hint':    '     ',
    'warn':    '[!]  ',
    'debug':   '     ',
    'spec':    '     ',
}


# ── IFLogger ──────────────────────────────────────────────────────────

class IFLogger:
    """Singleton output manager with verbosity control.

    Methods mirror output *categories*, not severity levels:
      - status()   — progress updates, stage names         (level >= info)
      - confirm()  — file-saved / export-done messages     (level >= info)
      - timing()   — elapsed time, ETA summaries           (level >= info)
      - hint()     — diagnostic detail (row counts, etc.)  (level >= hint)
      - debug()    — per-item trace                        (level >= debug)
      - warn()     — unexpected but non-fatal situations   (level >= warning)
    """

    def __init__(self):
        self._verbosity = Verbosity.info
        self._level_stack: list[Verbosity] = []
        self._lock = threading.Lock()
        self._output = sys.stdout

    # ── Verbosity control ─────────────────────────────────────────────

    @property
    def verbosity(self) -> Verbosity:
        return self._verbosity

    @verbosity.setter
    def verbosity(self, value):
        self._verbosity = _coerce_verbosity(value)

    def set_output(self, target):
        """Redirect all output to *target* (file path, file object, or None for stdout)."""
        if target is None:
            self._output = sys.stdout
        elif isinstance(target, str):
            self._output = open(target, 'a', encoding='utf-8')
        else:
            self._output = target

    # ── Context managers ──────────────────────────────────────────────

    def _push(self, level: Verbosity):
        with self._lock:
            self._level_stack.append(self._verbosity)
            self._verbosity = level

    def _pop(self):
        with self._lock:
            if self._level_stack:
                self._verbosity = self._level_stack.pop()

    # ── Output methods ────────────────────────────────────────────────

    def _write(self, msg: str):
        try:
            self._output.write(msg + '\n')
            self._output.flush()
        except Exception:
            pass

    def status(self, msg: str):
        if self._verbosity >= Verbosity.info:
            self._write(f"{_PREFIXES['status']}{msg}")

    def confirm(self, msg: str):
        if self._verbosity >= Verbosity.info:
            self._write(f"{_PREFIXES['confirm']}{msg}")

    def timing(self, msg: str):
        if self._verbosity >= Verbosity.info:
            self._write(f"{_PREFIXES['timing']}{msg}")

    def hint(self, msg: str):
        if self._verbosity >= Verbosity.hint:
            self._write(f"{_PREFIXES['hint']}{msg}")

    def debug(self, msg: str):
        if self._verbosity >= Verbosity.debug:
            self._write(f"{_PREFIXES['debug']}{msg}")

    def warn(self, msg: str):
        if self._verbosity >= Verbosity.warning:
            self._write(f"{_PREFIXES['warn']}{msg}")

    def spec(self, msg: str):
        """Spec-runner progress (same level as status)."""
        if self._verbosity >= Verbosity.info:
            self._write(f"{_PREFIXES['spec']}{msg}")


# ── Module-level singleton ────────────────────────────────────────────

logger = IFLogger()


# ── Public helpers ────────────────────────────────────────────────────

def _coerce_verbosity(value) -> Verbosity:
    if isinstance(value, Verbosity):
        return value
    if isinstance(value, str):
        return Verbosity[value.lower()]
    return Verbosity(int(value))


def set_verbosity(level=Verbosity.info):
    """Set package-wide verbosity.

    Parameters
    ----------
    level : int, str, or Verbosity
        0/'error', 1/'warning', 2/'info' (default), 3/'hint', 4/'debug'
    """
    logger.verbosity = level


class silent:
    """Context manager that suppresses all package output.

    Usage::

        with PyFLASH.silent():
            batch.export_all_excel()
    """
    def __enter__(self):
        logger._push(Verbosity.error)
        return self

    def __exit__(self, *exc):
        logger._pop()
        return False


class verbose:
    """Context manager that maximises output detail.

    Usage::

        with PyFLASH.verbose():
            batch.processData()
    """
    def __init__(self, level=Verbosity.debug):
        self._level = _coerce_verbosity(level)

    def __enter__(self):
        logger._push(self._level)
        return self

    def __exit__(self, *exc):
        logger._pop()
        return False
