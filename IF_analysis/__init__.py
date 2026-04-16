"""
amyloid_analysis — ImageJ confocal microscopy data processing pipeline.

Usage:
    from amyloid_analysis import create_batch, load_state, save_state
    from amyloid_analysis.conditions import *

    batch = create_batch("My Batch", my_conditions, "/path/to/experiments")
    save_state(batch, "my_batch.pkl")
    # ...later...
    batch = load_state("my_batch.pkl")
"""

from IF_analysis.markers import (
    Attribute, Antibody, cellMarker, objectMarker, stainColors,
)
from IF_analysis.experiment import Experiment, MiniExperiment
from IF_analysis.batch import Batch
from IF_analysis.conditions import (
    condition, multiCondition, conditionList,
    zipConditions, zipConditionLists,
    ConditionBuilder,
)
from IF_analysis.factory import create_batch
from IF_analysis.serialization import save_state, load_state, normalize_paths
from IF_analysis.config import Config
from IF_analysis.modelling import iterative_best_fit
from IF_analysis.spec import run_spec
from IF_analysis.plotting import (
    cheat_sheet,
    set_axis_limits,
    clear_axis_limits,
    lock_axis_limits,
)
from IF_analysis.export import format_summary_for_display
from IF_analysis._logging import set_verbosity, silent, verbose, Verbosity
import IF_analysis.stats as stats

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
