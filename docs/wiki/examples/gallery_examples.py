"""Curated gallery examples shared by the renderer and Markdown snippet updater."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from textwrap import dedent


@dataclass(frozen=True)
class GalleryExample:
    name: str
    code: str
    pick: int = 0
    plotly_file: bool = False


def _code(source: str) -> str:
    return dedent(source).strip()


GALLERY_EXAMPLES: tuple[GalleryExample, ...] = (
    GalleryExample(
        "plot_mean_bars",
        _code("""
        P.plot_mean_bars(exp, filtered_columns=["Marker1_Count"], save=True)
        """),
    ),
    GalleryExample(
        "plot_baseline_characteristics",
        _code("""
        import numpy as np
        from PyFLASH import from_dataframe

        summary = ex.summary.copy()
        summary["AgeYears"] = 70 + 3 * summary["x1"]
        summary["Sex"] = np.where(np.arange(len(summary)) % 2, "Female", "Male")
        summary["SleepTreatment"] = np.where(summary["Condition"].eq("C"), "Yes", "No")
        baseline_exp = from_dataframe(
            summary,
            group_col="Condition",
            subject_col="AnimalName",
            fig_path=TMP,
        )
        P.plot_baseline_characteristics(
            baseline_exp,
            columns={
                "age": "AgeYears",
                "sex": "Sex",
                "sleep_treatment": "SleepTreatment",
            },
            factor="Condition",
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_significance_audit_table",
        _code("""
        import pandas as pd

        audit = pd.DataFrame({
            "metric": [
                "Marker1 Count",
                "Marker2 Count",
                "Marker3 Intensity",
                "Signal",
            ],
            "p_group": [0.018, 0.42, 0.073, 0.004],
            "p_cohort": [0.31, 0.026, 0.58, 0.14],
            "p_interaction": [0.049, 0.66, 0.009, 0.21],
        })
        P.plot_significance_audit_table(
            exp,
            audit_table=audit,
            row_label_col="metric",
            pvalue_cols=["p_group", "p_cohort", "p_interaction"],
            column_labels={
                "p_group": "Group",
                "p_cohort": "Cohort",
                "p_interaction": "Interaction",
            },
            aesthetic="table",
            title="Significance audit",
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_category_counts",
        _code("""
        P.plot_category_counts(
            exp,
            category="Cohort",
            factor="Condition",
            kind="stacked",
            normalize=True,
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_matrices",
        _code("""
        P.plot_matrices(
            exp,
            filtered_columns=[
                "Marker1_Count",
                "Marker2_Count",
                "Marker3_Count",
                "Marker1_IntDenMean",
                "Marker2_IntDenMean",
                "Marker3_IntDenMean",
            ],
            save=True,
        )
        """),
        pick=0,
    ),
    GalleryExample(
        "plot_rect_matrices",
        _code("""
        P.plot_rect_matrices(
            exp,
            filtered_columns=["Marker1_Count", "Marker2_Count", "Marker3_Count"],
            against_columns=["x1", "x2", "Signal"],
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_matrix_differences",
        _code("""
        P.plot_matrix_differences(
            exp,
            filtered_columns=[
                "Marker1_Count",
                "Marker2_Count",
                "Marker3_Count",
                "Marker1_IntDenMean",
                "Marker2_IntDenMean",
                "Marker3_IntDenMean",
            ],
            comparisons=[("A", "C")],
            save=True,
        )
        """),
        pick=0,
    ),
    GalleryExample(
        "plot_regressions",
        _code("""
        P.plot_regressions(exp, x="x1", y="Signal", combine=True, save=True)
        """),
    ),
    GalleryExample(
        "plot_multivariable_regression_matrix",
        _code("""
        P.plot_multivariable_regression_matrix(
            exp,
            filtered_columns=["Signal"],
            predictors={"Predictors": ["x1", "x2"]},
            by="all",
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_model_result_matrix",
        _code("""
        import pandas as pd

        model_results = pd.DataFrame({
            "outcome": [
                "Marker1_Count",
                "Marker1_Count",
                "Marker2_Count",
                "Marker2_Count",
                "Signal",
                "Signal",
                "Marker3_Count",
                "Marker3_Count",
            ],
            "label": [
                "Marker 1 count",
                "Marker 1 count",
                "Marker 2 count",
                "Marker 2 count",
                "Signal",
                "Signal",
                "Marker 3 count",
                "Marker 3 count",
            ],
            "Diagnosis": [
                "Control",
                "Control",
                "Control",
                "Control",
                "MCI",
                "MCI",
                "MCI",
                "MCI",
            ],
            "predictor": [
                "Month",
                "Season",
                "Month",
                "Season",
                "Month",
                "Season",
                "Month",
                "Season",
            ],
            "r2": [0.80, 0.58, 0.35, 0.12, 0.66, 0.44, 0.27, 0.09],
            "p": [0.012, 0.041, 0.18, 0.55, 0.026, 0.061, 0.21, 0.72],
            "q": [0.036, 0.082, 0.24, 0.68, 0.052, 0.11, 0.30, 0.81],
        })
        exp.model_results = model_results
        P.plot_model_result_matrix(
            exp,
            model_table="model_results",
            row_col="outcome",
            row_label_col="label",
            group_col="Diagnosis",
            profile_col="predictor",
            group_order=["Control", "MCI"],
            profile_order=["Month", "Season"],
            title="Model result matrix",
            palette="Greens",
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_volcano",
        _code("""
        P.plot_volcano(
            exp,
            filtered_columns=[
                "Marker1_Count",
                "Marker2_Count",
                "Marker3_Count",
                "Marker1_IntDenMean",
                "Marker2_IntDenMean",
                "Marker3_IntDenMean",
            ],
            control="A",
            save=True,
        )
        """),
        pick=1,
    ),
    GalleryExample(
        "plot_radar",
        _code("""
        P.plot_radar(
            exp,
            filtered_columns=[
                "Marker1_Count",
                "Marker2_Count",
                "Marker3_Count",
                "Marker1_IntDenMean",
            ],
            combine=True,
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_scatter_3d",
        _code("""
        P.plot_scatter_3d(exp, x="x1", y="x2", z="Signal", combine=True, save=True)
        """),
    ),
    GalleryExample(
        "plot_marker_pca",
        _code("""
        P.plot_marker_pca(
            exp,
            columns=[
                "Marker1_Count",
                "Marker2_Count",
                "Marker3_Count",
                "Marker1_IntDenMean",
                "Marker2_IntDenMean",
                "Marker3_IntDenMean",
            ],
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_effect_forest",
        _code("""
        P.plot_effect_forest(
            exp,
            filtered_columns=["Marker1_Count", "Marker2_Count", "Marker3_Count"],
            control="A",
            effect_ci=False,
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_group_matrix",
        _code("""
        P.plot_group_matrix(
            exp,
            filtered_columns=["Marker1_Count", "Marker2_Count", "Marker3_Count"],
            control="A",
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_correlation_contrast",
        _code("""
        P.plot_correlation_contrast(
            exp,
            x="x1",
            y=["Signal", "Marker1_Count", "Marker2_Count"],
            factor="Condition",
            reference="A",
            significance="omnibus",
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_histograms",
        _code("""
        P.plot_histograms(exp, marker="Marker1", x_attr="Volume", combine=True, save=True)
        """),
    ),
    GalleryExample(
        "plot_ridgeline",
        _code("""
        P.plot_ridgeline(exp, marker="Marker1", x_attr="Volume", save=True)
        """),
    ),
    GalleryExample(
        "plot_ecdf",
        _code("""
        P.plot_ecdf(exp, marker="Marker1", x_attr="Volume", save=True)
        """),
        pick=0,
    ),
    GalleryExample(
        "plot_pie_charts",
        _code("""
        P.plot_pie_charts(
            exp,
            marker="Marker1",
            x_attr="Volume",
            threshold=12.0,
            save=True,
        )
        """),
        pick=1,
    ),
    GalleryExample(
        "plot_combo_pies",
        _code("""
        P.plot_combo_pies(exp, marker="Marker1", family="comboany", save=True)
        """),
        pick=2,
    ),
    GalleryExample(
        "plot_superplot",
        _code("""
        P.plot_superplot(
            exp,
            filtered_columns=["Marker1_IntDenMean"],
            by="conditions",
            roi="ROIa",
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_locations",
        _code("""
        import numpy as np
        import pandas as pd
        from PyFLASH import from_dataframe

        r = np.random.default_rng(7)
        n = 110
        cluster = r.integers(0, 2, n)
        x = np.where(cluster == 0, r.normal(180, 45, n), r.normal(330, 50, n))
        y = np.where(cluster == 0, r.normal(300, 55, n), r.normal(520, 60, n))
        marker_table = pd.DataFrame(
            {
                "AnimalName": ["A1"] * n,
                "Condition": ["A"] * n,
                "Region": ["ROIa1"] * n,
                "ROI": ["ROIa"] * n,
                "Marker1_XM": np.clip(x, 20, 480),
                "Marker1_YM": -np.clip(y, 20, 780),
                "Marker1_IntDen": np.clip(r.normal(100, 25, n), 0, None),
                "Marker1_Volume": np.clip(r.normal(12, 3, n), 1, None),
            }
        )
        summary = pd.DataFrame(
            {"AnimalName": ["A1"], "Condition": ["A"], "Marker1_Count": [float(n)]}
        )
        spatial_exp = from_dataframe(
            summary,
            group_col="Condition",
            subject_col="AnimalName",
            data={"Marker1": marker_table},
            fig_path=TMP,
        )
        P.plot_locations(
            spatial_exp,
            objects=["Marker1"],
            roi="ROIa",
            black_background=True,
            marker_colors={"Marker1": "#19e6ff"},
            save=True,
        )
        """),
        pick=0,
    ),
    GalleryExample(
        "plot_coloc_upset",
        _code("""
        P.plot_coloc_upset(exp, "Marker1", save=True)
        """),
        pick=2,
    ),
    GalleryExample(
        "plot_condition_key",
        _code("""
        P.plot_condition_key(exp, save=False)
        """),
    ),
    GalleryExample(
        "plot_power_curve",
        _code("""
        P.plot_power_curve(effect_sizes=(0.2, 0.5, 0.8), n_range=(2, 20), save=False)
        """),
    ),
    GalleryExample(
        "plot_cosinor",
        _code("""
        P.plot_cosinor(
            ex.cosinor,
            column="Response",
            time_col="ZT",
            group_col="Condition",
            period=24,
            save=False,
        )
        """),
    ),
    GalleryExample(
        "plot_timecourse",
        _code("""
        P.plot_timecourse(
            ex.timecourse,
            column="Response",
            time_col="Timepoint",
            group_col="Condition",
            time_map={"T1": 1, "T2": 2, "T3": 4, "T4": 8},
            save=False,
        )
        """),
    ),
    GalleryExample(
        "plot_acrophase_clock",
        _code("""
        P.plot_acrophase_clock(
            exp,
            phase_col="Acrophase (h)",
            group_col="Condition",
            period=24,
            radius_col="Amplitude",
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_coloc_sankey",
        _code("""
        P.plot_coloc_sankey(exp, "Marker1", save=True)
        """),
        plotly_file=True,
    ),
)


def gallery_examples() -> tuple[GalleryExample, ...]:
    return GALLERY_EXAMPLES


def gallery_snippets() -> dict[str, str]:
    return {example.name: example.code for example in GALLERY_EXAMPLES}


def execute_gallery_code(code: str, context: dict[str, object]) -> object:
    """Execute a gallery snippet and return the value of its final expression."""
    tree = ast.parse(code, mode="exec")
    local_context = context
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        setup = ast.Module(body=tree.body[:-1], type_ignores=[])
        expression = ast.Expression(body=tree.body[-1].value)
        ast.fix_missing_locations(setup)
        ast.fix_missing_locations(expression)
        exec(compile(setup, "<gallery-example>", "exec"), local_context)
        return eval(compile(expression, "<gallery-example>", "eval"), local_context)
    exec(compile(tree, "<gallery-example>", "exec"), local_context)
    return None
