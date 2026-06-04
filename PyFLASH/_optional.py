"""Lazy, non-fatal access to optional third-party dependencies.

Importing PyFLASH (or any submodule) must never fail because an optional
package is absent.  Functions that need one fetch it *at call time* via
``optional_import``/``require``; a minimal install keeps every other function
fully usable.

The lightweight, standard scientific stack (numpy/scipy/pandas/matplotlib/
seaborn/statsmodels/scikit-posthocs/scikit-learn/lmfit) is declared as a hard
dependency in pyproject.toml and imported normally.  This module is only for
the genuinely optional extras (currently ``pointpats`` for spatial statistics
and ``dabest`` for estimation plots).
"""
from __future__ import annotations

import importlib

_CACHE: dict = {}


def optional_import(module_name: str):
    """Return the imported module, or ``None`` if it isn't installed."""
    if module_name in _CACHE:
        return _CACHE[module_name]
    try:
        module = importlib.import_module(module_name)
    except Exception:
        module = None
    _CACHE[module_name] = module
    return module


def have(module_name: str) -> bool:
    """True if *module_name* can be imported."""
    return optional_import(module_name) is not None


def require(module_name: str, *, feature: str, extra: str):
    """Return the module, or raise a clear, actionable ImportError.

    The error is raised only when the calling *feature* actually runs — never
    at import time — so a minimal install still imports cleanly and every other
    feature keeps working.

    Parameters
    ----------
    module_name : str
        Importable module path, e.g. ``"pointpats"``.
    feature : str
        Human-readable name of the calling feature, used in the message.
    extra : str
        The pyproject optional-dependency group that provides it, e.g.
        ``"spatial"``.
    """
    module = optional_import(module_name)
    if module is None:
        raise ImportError(
            f"{feature} requires the optional dependency '{module_name}', "
            f"which is not installed.\n"
            f'Install it with:  pip install "PyFLASH-analysis[{extra}]"'
        )
    return module
