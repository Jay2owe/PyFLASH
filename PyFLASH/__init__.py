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
from PyFLASH.modelling import iterative_best_fit
from PyFLASH.spec import run_spec
from PyFLASH.plotting import (
    cheat_sheet,
    set_axis_limits,
    clear_axis_limits,
    lock_axis_limits,
)
from PyFLASH.export import format_summary_for_display
from PyFLASH._logging import set_verbosity, silent, verbose, Verbosity
import PyFLASH.stats as stats

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
