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
)
from IF_analysis.factory import create_batch
from IF_analysis.serialization import save_state, load_state, normalize_paths
from IF_analysis.config import Config
from IF_analysis.modelling import iterative_best_fit
from IF_analysis.spec import run_spec
from IF_analysis.plotting import cheat_sheet
import IF_analysis.stats as stats

__all__ = [
    # Core classes
    "Attribute", "Antibody", "cellMarker", "objectMarker",
    "Experiment", "MiniExperiment", "Batch",
    # Conditions
    "condition", "multiCondition", "conditionList",
    "zipConditions", "zipConditionLists",
    # Factory & IO
    "create_batch", "save_state", "load_state", "normalize_paths",
    # Modelling
    "iterative_best_fit",
    # Config
    "Config", "stainColors",
    # Spec DSL
    "run_spec",
    # Reference
    "cheat_sheet",
    # Stats module
    "stats",
]
