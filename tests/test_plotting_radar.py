from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import pandas as pd
import pytest

from PyFLASH.conditions import condition, conditionList
from PyFLASH.plotting import (
    _compute_radar_scale_reference,
    _normalize_radar_value,
    plot_radar,
)


def _fake_experiment(tmp_path):
    syn = condition("Syn", "Syn", "#787a7c", "Genotype")
    happ = condition("hAPP", "hAPP", "#4369b2", "Genotype")
    conditions = conditionList([syn, happ])
    summary = pd.DataFrame(
        {
            "AnimalName": [
                "S1W4", "S2W4", "H1W4", "H2W4",
                "S1W8", "S2W8", "H1W8", "H2W8",
            ],
            "Condition": [
                "Syn", "Syn", "hAPP", "hAPP",
                "Syn", "Syn", "hAPP", "hAPP",
            ],
            "Genotype": [
                "Syn", "Syn", "hAPP", "hAPP",
                "Syn", "Syn", "hAPP", "hAPP",
            ],
            "Time": [
                "WeekFour", "WeekFour", "WeekFour", "WeekFour",
                "WeekEight", "WeekEight", "WeekEight", "WeekEight",
            ],
            "A_Count": [1, 2, 3, 4, 2, 3, 5, 6],
            "B_IntDen": [10, 20, 30, 40, 20, 30, 50, 60],
            "C_Area": [5, "NOT_INCLUDED_IN_EXPERIMENT", 7, 8, 6, 7, 9, 10],
        }
    )
    return SimpleNamespace(
        summary=summary,
        condition_list=conditions,
        fig_path=str(tmp_path),
        aliases={},
    )


def test_radar_normalization_maps_constant_columns_to_midpoint():
    df = pd.DataFrame({"a": [2, 2, 2], "b": [1, 3, 5]})
    reference = _compute_radar_scale_reference(df, ["a", "b"])

    assert _normalize_radar_value(2, reference["a"]) == pytest.approx(0.5)
    assert _normalize_radar_value(3, reference["b"]) == pytest.approx(0.5)


def test_plot_radar_combined_factor_saves_one_svg(tmp_path):
    exp = _fake_experiment(tmp_path)

    result = plot_radar(
        exp,
        filtered_columns=["A_Count", "B_IntDen", "C_Area"],
        factor="Genotype",
        specificity=("Time", "WeekFour"),
        combine=True,
    )

    assert result["group"] == ["Syn", "hAPP"]
    saved = list((tmp_path / "Radar").glob("*.svg"))
    assert len(saved) == 1
    assert "Combined" in saved[0].name


def test_plot_radar_separate_factor_saves_one_svg_per_factor(tmp_path):
    exp = _fake_experiment(tmp_path)

    plot_radar(
        exp,
        filtered_columns=["A_Count", "B_IntDen", "C_Area"],
        factor="Genotype",
        specificity=("Time", "WeekFour"),
        combine=False,
    )

    saved = sorted((tmp_path / "Radar").glob("*.svg"))
    assert len(saved) == 2
    assert any("Syn" in p.name for p in saved)
    assert any("hAPP" in p.name for p in saved)


def test_plot_radar_specificity_queue_returns_and_saves_per_specificity(tmp_path):
    exp = _fake_experiment(tmp_path)
    specificity = [("Time", "WeekFour"), ("Time", "WeekEight")]

    result = plot_radar(
        exp,
        filtered_columns=["A_Count", "B_IntDen", "C_Area"],
        factor="Genotype",
        specificity=specificity,
        combine=True,
    )

    assert set(result) == set(specificity)
    saved = list((tmp_path / "Radar").glob("*.svg"))
    assert len(saved) == 2
    assert any("WeekFour" in p.name for p in saved)
    assert any("WeekEight" in p.name for p in saved)
