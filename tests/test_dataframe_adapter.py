import matplotlib

matplotlib.use("Agg")

import inspect
import json
import pandas as pd
import pytest

import PyFLASH.plotting as plotting
from PyFLASH import ConditionBuilder, from_dataframe, group, groupList, run_spec
from PyFLASH.aliases import normalize_filter_by
from PyFLASH.exclusions import exclude_subjects
from PyFLASH.pipeline import correlation
from PyFLASH.plotting import (
    plot_effect_forest,
    plot_group_matrix,
    plot_histograms,
    plot_matrices,
    plot_mean_bars,
    plot_multivariable_regression_matrix,
    plot_rect_matrices,
)
from PyFLASH.utils import build_specificity_alias, filter_df_by_specificity, is_specificity_queue


def test_plot_functions_with_specificity_accept_filter_by_alias():
    missing = []
    for name in dir(plotting):
        if not name.startswith("plot_"):
            continue
        func = getattr(plotting, name)
        if not callable(func):
            continue
        params = inspect.signature(func).parameters
        if "specificity" in params and "filter_by" not in params:
            missing.append(name)

    assert missing == []


def _diagnosis_conditions():
    return (
        ConditionBuilder("Diagnosis")
        .add("Control", short="Control", color="grey")
        .add("AD", short="AD", color="red")
        .compare("Control", "AD")
        .build()
    )


def test_from_dataframe_supports_summary_plot_and_pipeline(tmp_path):
    df = pd.DataFrame({
        "Subject ID": ["C1", "C2", "C3", "A1", "A2", "A3"],
        "Diagnosis": ["Control", "Control", "Control", "AD", "AD", "AD"],
        "Marker A": [1.0, 1.2, 1.1, 2.0, 2.2, 2.1],
        "Marker B": [2.0, 2.4, 2.2, 4.0, 4.4, 4.2],
    })

    exp = from_dataframe(
        df,
        conditions=_diagnosis_conditions(),
        name="human-table",
        condition_col="Diagnosis",
        animal_col="Subject ID",
        fig_path=tmp_path / "figures",
        data_path=tmp_path / "data",
    )

    assert exp.summary["AnimalName"].tolist() == ["C1", "C2", "C3", "A1", "A2", "A3"]
    assert exp.summary["Condition"].tolist() == ["Control", "Control", "Control", "AD", "AD", "AD"]

    bar_result = plot_mean_bars(
        exp,
        filtered_columns=["Marker A"],
        save=False,
        save_normality=False,
    )
    assert isinstance(bar_result, dict)

    result = correlation(
        exp,
        filtered_columns=["Marker A"],
        against_columns=["Marker B"],
        factor="Diagnosis",
        tests=("pearsonr",),
        min_n=3,
        save=False,
        write_manifest=False,
        montage=False,
    )
    assert {group["group"] for group in result["groups"]} == {"Control", "AD"}


def test_from_dataframe_derives_crossed_condition_from_factor_columns(tmp_path):
    diagnosis = (
        ConditionBuilder("Diagnosis")
        .add("Control", short="Control", color="grey")
        .add("AD", short="AD", color="red")
        .build()
    )
    sex = (
        ConditionBuilder("Sex")
        .add("Female", short="Female")
        .add("Male", short="Male")
        .build()
    )
    crossed = ConditionBuilder.cross(diagnosis, sex).build()
    df = pd.DataFrame({
        "ID": ["1", "2", "3", "4"],
        "Diagnosis": ["Control", "Control", "AD", "AD"],
        "Sex": ["Female", "Male", "Female", "Male"],
        "Metric": [1.0, 1.1, 2.0, 2.1],
    })

    exp = from_dataframe(
        df,
        conditions=crossed,
        animal_col="ID",
        fig_path=tmp_path,
    )

    assert exp.summary["Condition"].tolist() == [
        "ControlFemale",
        "ControlMale",
        "ADFemale",
        "ADMale",
    ]


def test_from_dataframe_enriches_marker_tables_for_marker_plots(tmp_path):
    summary = pd.DataFrame({
        "ID": ["C1", "C2", "A1", "A2"],
        "Diagnosis": ["Control", "Control", "AD", "AD"],
        "Summary Metric": [1.0, 1.1, 2.0, 2.1],
    })
    cells = pd.DataFrame({
        "ID": ["C1", "C1", "C2", "A1", "A2", "A2"],
        "Area": [10.0, 11.0, 12.0, 20.0, 21.0, 22.0],
    })

    exp = from_dataframe(
        summary,
        conditions=_diagnosis_conditions(),
        condition_col="Diagnosis",
        animal_col="ID",
        data={"Cells": cells},
        fig_path=tmp_path,
    )

    marker_df = exp.data["Cells"].df
    assert marker_df["Condition"].tolist() == [
        "Control",
        "Control",
        "Control",
        "AD",
        "AD",
        "AD",
    ]

    result = plot_histograms(
        exp,
        marker="Cells",
        x_attr="Area",
        save=False,
        bins=3,
    )
    assert isinstance(result, dict)


def test_summary_plot_accepts_dataframe_directly(tmp_path):
    df = pd.DataFrame({
        "Subject": ["C1", "C2", "A1", "A2"],
        "Diagnosis": ["Control", "Control", "AD", "AD"],
        "A": [1.0, 1.2, 2.0, 2.2],
        "B": [2.0, 2.4, 4.0, 4.4],
    })

    bars = plot_mean_bars(
        df,
        filtered_columns=["A"],
        condition_col="Diagnosis",
        animal_col="Subject",
        save=False,
        save_normality=False,
    )
    assert isinstance(bars, dict)

    result = plot_matrices(
        df,
        filtered_columns=["A", "B"],
        condition_col="Diagnosis",
        animal_col="Subject",
        by="conditions",
        save=False,
    )

    assert isinstance(result, dict)


def test_pipeline_accepts_dataframe_directly_with_crossed_factors(tmp_path):
    df = pd.DataFrame({
        "Subject": ["C1", "C2", "A1", "A2", "C3", "A3"],
        "Diagnosis": ["Control", "Control", "AD", "AD", "Control", "AD"],
        "Sex": ["Female", "Male", "Female", "Male", "Female", "Male"],
        "A": [1.0, 1.2, 2.0, 2.2, 1.1, 2.1],
        "B": [2.0, 2.4, 4.0, 4.4, 2.2, 4.2],
    })

    result = correlation(
        df,
        filtered_columns=["A"],
        against_columns=["B"],
        factor_cols=["Diagnosis", "Sex"],
        animal_col="Subject",
        factor="Diagnosis",
        tests=("pearsonr",),
        min_n=2,
        save=False,
        write_manifest=False,
        montage=False,
    )

    assert {group["group"] for group in result["groups"]} == {"Control", "AD"}


def test_group_alias_objects_match_condition_objects():
    control = group("Control", "Control", "grey", "Diagnosis")
    ad = group("AD", "AD", "red", "Diagnosis")
    groups = groupList([control, ad], comparisons=["1-2"])

    assert [g.name for g in groups] == ["Control", "AD"]
    assert groups.comparisons == ["1-2"]
    assert groups.factor == ["Diagnosis"]


def test_new_dataframe_alias_names_work_for_plots_and_pipelines(tmp_path):
    df = pd.DataFrame({
        "AnimalName": ["wrong1", "wrong2", "wrong3", "wrong4", "wrong5", "wrong6"],
        "Subject": ["C1", "C2", "C3", "A1", "A2", "A3"],
        "Diagnosis": ["Control", "Control", "Control", "AD", "AD", "AD"],
        "Sex": ["Female", "Male", "Female", "Female", "Male", "Male"],
        "Region": ["SCN", "SCN", "OC", "SCN", "SCN", "SCN"],
        "A": [1.0, 1.2, 1.1, 2.0, 2.2, 2.1],
        "B": [2.0, 2.4, 2.2, 4.0, 4.4, 4.2],
    })

    exp = from_dataframe(
        df,
        group_col="Diagnosis",
        subject_col="Subject",
        group_order=["Control", "AD"],
        group_comparisons=[("Control", "AD")],
        fig_path=tmp_path / "figures",
        data_path=tmp_path / "data",
    )
    assert exp.summary["AnimalName"].tolist() == ["C1", "C2", "C3", "A1", "A2", "A3"]
    assert exp.condition_list.comparisons == ["1-2"]

    bars = plot_mean_bars(
        df,
        data_cols=["A"],
        group_col="Diagnosis",
        subject_col="Subject",
        save=False,
        save_normality=False,
    )
    assert isinstance(bars, dict)

    matrices = plot_matrices(
        df,
        data_cols=["A", "B"],
        leading_data_cols=["B"],
        group_col="Diagnosis",
        subject_col="Subject",
        split_by="Diagnosis",
        save=False,
    )
    assert isinstance(matrices, dict)

    corr = correlation(
        df,
        data_cols=["A"],
        against_data_cols=["B"],
        group_col="Diagnosis",
        subject_col="Subject",
        split_by="Diagnosis",
        tests=("pearsonr",),
        min_n=3,
        save=False,
        write_manifest=False,
        montage=False,
    )
    assert {row["group"] for row in corr["groups"]} == {"Control", "AD"}

    filtered = correlation(
        df,
        data_cols=["A"],
        against_data_cols=["B"],
        group_col="Diagnosis",
        subject_col="Subject",
        filter_by={"Sex": "Female", "Region": "SCN"},
        tests=("pearsonr",),
        min_n=2,
        save=False,
        write_manifest=False,
        montage=False,
    )
    assert filtered["groups"][0]["n_rows"] == 2


def test_filter_by_mapping_is_and_filter_not_queue():
    df = pd.DataFrame({
        "Sex": ["Female", "Female", "Male", "Female"],
        "Region": ["SCN", "OC", "SCN", "SCN"],
        "A": [1, 2, 3, 4],
    })

    spec = normalize_filter_by({"Sex": "Female", "Region": "SCN"})

    assert spec == {"Sex": "Female", "Region": "SCN"}
    assert not is_specificity_queue(spec)
    assert filter_df_by_specificity(df, spec)["A"].tolist() == [1, 4]
    assert build_specificity_alias(spec) == "Sex.Female+Region.SCN"

    queued = normalize_filter_by([
        {"Sex": "Female", "Region": "SCN"},
        {"Sex": "Male", "Region": "SCN"},
    ])
    assert is_specificity_queue(queued)


def test_filter_by_mapping_queue_works_for_plots_and_pipelines(tmp_path):
    df = pd.DataFrame({
        "Subject": ["C1", "C2", "C3", "A1", "A2", "A3"],
        "Diagnosis": ["Control", "Control", "Control", "AD", "AD", "AD"],
        "Sex": ["Female", "Male", "Female", "Female", "Male", "Male"],
        "Region": ["SCN", "SCN", "OC", "SCN", "SCN", "SCN"],
        "A": [1.0, 1.2, 1.1, 2.0, 2.2, 2.1],
        "B": [2.0, 2.4, 2.2, 4.0, 4.4, 4.2],
    })
    queue = [
        {"Sex": "Female", "Region": "SCN"},
        {"Sex": "Male", "Region": "SCN"},
    ]

    bars = plot_mean_bars(
        df,
        data_cols=["A"],
        group_col="Diagnosis",
        subject_col="Subject",
        filter_by=queue,
        save=False,
        save_normality=False,
    )
    assert len(bars) == 2

    corr = correlation(
        df,
        data_cols=["A"],
        against_data_cols=["B"],
        group_col="Diagnosis",
        subject_col="Subject",
        filter_by=queue,
        tests=("pearsonr",),
        min_n=2,
        save=False,
        write_manifest=False,
        montage=False,
    )
    assert corr["n_conditions"] == 2
    assert corr["specificity"] == [
        {"Sex": ["Female"], "Region": ["SCN"]},
        {"Sex": ["Male"], "Region": ["SCN"]},
    ]
    assert corr["conditions"][0]["specificity"] == {"Sex": ["Female"], "Region": ["SCN"]}
    assert corr["conditions"][1]["specificity"] == {"Sex": ["Male"], "Region": ["SCN"]}


def test_subject_exclusion_alias(tmp_path):
    df = pd.DataFrame({
        "Subject": ["C1", "C2", "A1", "A2"],
        "Diagnosis": ["Control", "Control", "AD", "AD"],
        "A": [1.0, 1.2, 2.0, 2.2],
    })
    exp = from_dataframe(df, group_col="Diagnosis", subject_col="Subject", fig_path=tmp_path)

    clean = exclude_subjects(exp, "A2", columns=["A"], reason="qc")

    row = clean.summary.loc[clean.summary["AnimalName"] == "A2", "A"].iloc[0]
    assert isinstance(row, str)
    assert "EXCLUDED_MANUAL" in row


def test_run_spec_accepts_new_alias_names_for_dataframe(tmp_path):
    df = pd.DataFrame({
        "Subject": ["C1", "C2", "A1", "A2"],
        "Diagnosis": ["Control", "Control", "AD", "AD"],
        "Sex": ["Female", "Male", "Female", "Male"],
        "A": [1.0, 1.2, 2.0, 2.2],
    })
    path = tmp_path / "plot.json"
    path.write_text(json.dumps({
        "plots": [{
            "type": "mean_bars",
            "data_cols": ["A"],
            "group_col": "Diagnosis",
            "subject_col": "Subject",
            "filter_by": {"Sex": ["Female", "Male"]},
            "save": False,
            "save_normality": False,
        }],
    }), encoding="utf-8")

    result = run_spec(df, path)

    assert len(result) == 1
    assert isinstance(result[0], dict)


def test_run_spec_rejects_conflicting_column_aliases(tmp_path):
    df = pd.DataFrame({
        "Subject": ["C1", "C2", "A1", "A2"],
        "Diagnosis": ["Control", "Control", "AD", "AD"],
        "A": [1.0, 1.2, 2.0, 2.2],
        "B": [2.0, 2.2, 4.0, 4.2],
    })
    path = tmp_path / "plot.json"
    path.write_text(json.dumps({
        "plots": [{
            "type": "mean_bars",
            "columns": ["A"],
            "filtered_columns": ["B"],
            "group_col": "Diagnosis",
            "subject_col": "Subject",
            "save": False,
            "save_normality": False,
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="columns|filtered_columns"):
        run_spec(df, path)


def test_more_summary_plots_accept_dataframe_aliases(tmp_path):
    df = pd.DataFrame({
        "Subject": ["C1", "C2", "C3", "A1", "A2", "A3"],
        "Diagnosis": ["Control", "Control", "Control", "AD", "AD", "AD"],
        "A": [1.0, 1.2, 1.1, 2.0, 2.2, 2.1],
        "B": [2.0, 2.2, 2.1, 4.0, 4.2, 4.1],
        "Y": [3.0, 3.2, 3.1, 5.0, 5.2, 5.1],
    })

    rect = plot_rect_matrices(
        df,
        data_cols=["A", "Y"],
        against_data_cols=["B"],
        group_col="Diagnosis",
        subject_col="Subject",
        split_by="Diagnosis",
        save=False,
    )
    assert isinstance(rect, dict)

    effect = plot_effect_forest(
        df,
        data_cols=["A", "B"],
        group_col="Diagnosis",
        subject_col="Subject",
        control="Control",
        min_n=2,
        save=False,
    )
    assert effect is not None

    matrix = plot_group_matrix(
        df,
        data_cols=["A", "B"],
        group_col="Diagnosis",
        subject_col="Subject",
        control="Control",
        min_n=2,
        save=False,
    )
    assert matrix is not None

    mv = plot_multivariable_regression_matrix(
        df,
        data_cols=["Y"],
        predictors={"markers": ["A", "B"]},
        group_col="Diagnosis",
        subject_col="Subject",
        split_by="all",
        save=False,
    )
    assert isinstance(mv, dict)
