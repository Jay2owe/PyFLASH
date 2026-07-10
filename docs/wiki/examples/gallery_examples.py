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
        "plot_matrices",
        _code("""
        P.plot_matrices(exp, filtered_columns=NUM, save=True)
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
            filtered_columns=NUM,
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
        "plot_volcano",
        _code("""
        P.plot_volcano(exp, filtered_columns=NUM, control="A", save=True)
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
        P.plot_marker_pca(exp, columns=NUM, save=True)
        """),
    ),
    GalleryExample(
        "plot_effect_forest",
        _code("""
        P.plot_effect_forest(
            exp,
            filtered_columns=NUM[:3],
            control="A",
            effect_ci=False,
            save=True,
        )
        """),
    ),
    GalleryExample(
        "plot_group_matrix",
        _code("""
        P.plot_group_matrix(exp, filtered_columns=NUM[:3], control="A", save=True)
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
