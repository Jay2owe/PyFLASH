"""
PyFLASH — ImageJ confocal microscopy data processing pipeline.

Usage:
    from PyFLASH import create_batch, load_state, save_state
    from PyFLASH.conditions import *

    batch = create_batch("My Batch", my_conditions, "/path/to/experiments")
    save_state(batch, "my_batch.pkl")
    # ...later...
    batch = load_state("my_batch.pkl")
"""

from PyFLASH.markers import (
    Attribute, Antibody, cellMarker, objectMarker, stainColors,
)
from PyFLASH.experiment import Experiment, MiniExperiment
from PyFLASH.batch import Batch
from PyFLASH.conditions import (
    condition, multiCondition, conditionList,
    zipConditions, zipConditionLists,
    ConditionBuilder,
)
from PyFLASH.factory import create_batch
from PyFLASH.serialization import save_state, load_state, normalize_paths
from PyFLASH.config import Config
from PyFLASH.spec import run_spec
from PyFLASH.export import format_summary_for_display
from PyFLASH._logging import set_verbosity, silent, verbose, Verbosity

__all__ = [
    # Core classes
    "Attribute", "Antibody", "cellMarker", "objectMarker",
    "Experiment", "MiniExperiment", "Batch",
    # Conditions
    "condition", "multiCondition", "conditionList",
    "zipConditions", "zipConditionLists", "ConditionBuilder",
    # Factory & IO
    "create_batch", "save_state", "load_state", "normalize_paths",
    # Modelling
    "iterative_best_fit",
    # Config & output control
    "Config", "stainColors",
    "set_verbosity", "silent", "verbose", "Verbosity",
    # Spec DSL
    "run_spec",
    # Reference
    "cheat_sheet",
    "set_axis_limits", "clear_axis_limits", "lock_axis_limits",
    "format_summary_for_display",
    # Stats module
    "stats",
]


# ── Lazy heavy imports (PEP 562) ──────────────────────────────────────
# A bare ``import PyFLASH`` (e.g. from a UI or a script that only builds or
# loads batches) should not pull in matplotlib, seaborn, scipy, statsmodels,
# scikit-posthocs, or the large plotting module.  The names below are imported
# on first attribute access instead.  ``from PyFLASH import *`` still binds
# them (it triggers ``__getattr__`` for each ``__all__`` entry), as does any
# direct use such as ``PyFLASH.cheat_sheet`` or ``PyFLASH.stats``.
_LAZY_ATTRS = {
    "iterative_best_fit": ("PyFLASH.modelling", "iterative_best_fit"),
    "cheat_sheet": ("PyFLASH.plotting", "cheat_sheet"),
    "set_axis_limits": ("PyFLASH.plotting", "set_axis_limits"),
    "clear_axis_limits": ("PyFLASH.plotting", "clear_axis_limits"),
    "lock_axis_limits": ("PyFLASH.plotting", "lock_axis_limits"),
    "stats": ("PyFLASH.stats", None),  # submodule
}


def __getattr__(name):
    """Lazily import heavy public attributes on first access (PEP 562)."""
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    module_name, attr = target
    module = importlib.import_module(module_name)
    value = module if attr is None else getattr(module, attr)
    globals()[name] = value  # cache so the import only happens once
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_ATTRS))
