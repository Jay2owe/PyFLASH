import pandas as pd
import pytest

from IF_analysis.batch import Batch
from IF_analysis.conditions import condition, conditionList
from IF_analysis.experiment import Experiment, NOT_INCLUDED_SENTINEL
from IF_analysis.markers import Attribute


def _build_behavior_experiment(name, behavior_rows, metadata_rows=None):
    exp = Experiment(name, ".")
    data = {
        "Behaviour": Attribute("Behaviour", pd.DataFrame(behavior_rows), exp),
    }
    if metadata_rows is not None:
        data["Metadata"] = Attribute("Metadata", pd.DataFrame(metadata_rows), exp)
    exp.data = data
    exp.createSummary(progress=False)
    return exp


def test_experiment_summary_fills_missing_behaviour_values_with_sentinel():
    exp = _build_behavior_experiment(
        "behaviour_missing_values",
        behavior_rows=[
            {"AnimalName": "Mouse1", "Period": 24.0, "AOE": 1.0},
            {"AnimalName": "Mouse2", "Period": None, "AOE": 2.0},
        ],
        metadata_rows=[
            {"AnimalName": "Mouse1", "BodyWeight": 30.0},
            {"AnimalName": "Mouse2", "BodyWeight": 31.0},
            {"AnimalName": "Mouse3", "BodyWeight": 32.0},
        ],
    )

    summary = exp.summary.set_index("AnimalName")

    assert summary.loc["Mouse1", "PeriodMean"] == pytest.approx(24.0)
    assert summary.loc["Mouse2", "PeriodMean"] == NOT_INCLUDED_SENTINEL
    assert summary.loc["Mouse3", "PeriodMean"] == NOT_INCLUDED_SENTINEL
    assert summary.loc["Mouse1", "AOEMean"] == pytest.approx(1.0)
    assert summary.loc["Mouse3", "AOEMean"] == NOT_INCLUDED_SENTINEL


def test_batch_summary_preserves_behaviour_sentinel_for_missing_values():
    exp1 = _build_behavior_experiment(
        "exp1",
        behavior_rows=[
            {"AnimalName": "Mouse1", "Period": 24.0, "AOE": 1.0},
            {"AnimalName": "Mouse2", "Period": None, "AOE": 2.0},
        ],
    )
    exp2 = _build_behavior_experiment(
        "exp2",
        behavior_rows=[
            {"AnimalName": "Mouse1", "LocomotoractivityIR(counts)": None},
        ],
    )

    conds = conditionList([condition("Mouse", "Mouse", "#000000", "Group")])
    batch = Batch("behaviour_batch", [exp1, exp2], conds, ".")
    batch._create_data_dict()
    batch._create_batch_summary()

    summary = batch.summary.set_index("AnimalName")

    assert summary.loc["Mouse1", "PeriodMean"] == pytest.approx(24.0)
    assert summary.loc["Mouse2", "PeriodMean"] == NOT_INCLUDED_SENTINEL
    assert summary.loc["Mouse1", "LocomotoractivityIR(counts)"] == NOT_INCLUDED_SENTINEL
    assert summary.loc["Mouse2", "LocomotoractivityIR(counts)"] == NOT_INCLUDED_SENTINEL
