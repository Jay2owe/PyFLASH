"""Opt-in timings for the owned real-data responsiveness diagnostic."""
from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from time import perf_counter

_LOCK = Lock()


def start():
    return perf_counter()


def record(name, started, **details):
    """Append a timing only when a diagnostic explicitly opts in."""
    path = os.environ.get("PYFLASH_UI_PERFORMANCE_TRACE")
    if not path:
        return
    row = {"name": name, "seconds": perf_counter() - started, **details}
    payload = json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
    with _LOCK:
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(payload)
