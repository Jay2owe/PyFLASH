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
    "iterative_best_fit", "run_linear_model_pipeline", "adjusted_correlation",
    "data_overview",
    # Outlier exclusion / marking
    "exclude_outliers", "mark_outliers", "apply_exclusions", "mark_exclusions",
    # Config & output control
    "Config", "stainColors",
    "set_verbosity", "silent", "verbose", "Verbosity",
    # Spec DSL
    "run_spec",
    # Reference
    "cheat_sheet",
    "set_axis_limits", "clear_axis_limits", "lock_axis_limits",
    "format_summary_for_display",
    # Heavy submodules (lazily imported on first access)
    "plotting", "pipeline", "modelling", "stats",
]


# ── Lazy heavy imports (PEP 562) ──────────────────────────────────────
# A bare ``import PyFLASH`` (e.g. from a UI or a script that only builds or
# loads batches) should not pull in matplotlib, seaborn, scipy, statsmodels,
# scikit-posthocs, or the large plotting module.  The names below are imported
# on first attribute access instead, so all of these work without an explicit
# ``import PyFLASH.plotting`` first::
#
#     import PyFLASH
#     PyFLASH.plotting.plot_mean_bars(batch, ...)   # lazy submodule
#     PyFLASH.cheat_sheet()                         # lazy function
#     PyFLASH.stats.runOWA(...)                     # lazy submodule
#
# ``from PyFLASH import *`` still binds them (it triggers ``__getattr__`` for
# each ``__all__`` entry).
_LAZY_ATTRS = {
    "iterative_best_fit": ("PyFLASH.modelling", "iterative_best_fit"),
    "run_linear_model_pipeline": ("PyFLASH.modelling", "run_linear_model_pipeline"),
    "adjusted_correlation": ("PyFLASH.pipeline", "adjusted_correlation"),
    "data_overview": ("PyFLASH.pipeline", "data_overview"),
    "exclude_outliers": ("PyFLASH.exclusions", "exclude_outliers"),
    "mark_outliers": ("PyFLASH.exclusions", "mark_outliers"),
    "apply_exclusions": ("PyFLASH.exclusions", "apply_exclusions"),
    "mark_exclusions": ("PyFLASH.exclusions", "mark_exclusions"),
    "cheat_sheet": ("PyFLASH.plotting", "cheat_sheet"),
    "set_axis_limits": ("PyFLASH.plotting", "set_axis_limits"),
    "clear_axis_limits": ("PyFLASH.plotting", "clear_axis_limits"),
    "lock_axis_limits": ("PyFLASH.plotting", "lock_axis_limits"),
}

# Heavy submodules exposed as lazy attributes of the package.  Accessing
# ``PyFLASH.plotting`` (etc.) imports the submodule on first use and caches it.
_LAZY_SUBMODULES = ("plotting", "pipeline", "modelling", "stats")


def __getattr__(name):
    """Lazily import heavy public attributes/submodules on first access (PEP 562).

    Resolution order:
      1. A known lazy function/attribute in ``_LAZY_ATTRS``.
      2. A known heavy submodule in ``_LAZY_SUBMODULES``.
      3. Any importable ``PyFLASH.<name>`` submodule (best-effort fallback) —
         this makes ``PyFLASH.<submodule>`` work uniformly and forgivingly.
    Anything else raises ``AttributeError`` as usual.
    """
    import importlib

    target = _LAZY_ATTRS.get(name)
    if target is not None:
        module_name, attr = target
        module = importlib.import_module(module_name)
        value = module if attr is None else getattr(module, attr)
        globals()[name] = value  # cache so the import only happens once
        return value

    if name in _LAZY_SUBMODULES or (not name.startswith("_")):
        try:
            module = importlib.import_module(f"{__name__}.{name}")
        except ModuleNotFoundError as exc:
            # Only swallow "this submodule does not exist"; surface real import
            # errors inside an existing submodule so they are not masked.
            if exc.name in (f"{__name__}.{name}", name):
                raise AttributeError(
                    f"module {__name__!r} has no attribute {name!r}"
                ) from None
            raise
        globals()[name] = module  # cache
        return module

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_LAZY_ATTRS) | set(_LAZY_SUBMODULES))
