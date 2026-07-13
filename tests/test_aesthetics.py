from types import SimpleNamespace
import re

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
import pytest

import PyFLASH.plotting as plotting
from PyFLASH import stats
from PyFLASH.aesthetics import (
    get_pyflash_style,
    pyflash_style_context,
    reset_pyflash_style,
    set_pyflash_style,
)


@pytest.fixture(autouse=True)
def _reset_pyflash_style():
    reset_pyflash_style()
    yield
    reset_pyflash_style()


def test_pyflash_style_context_restores_and_validates_keys():
    original = get_pyflash_style("condition_style_cycle")

    with pyflash_style_context(condition_style_cycle=["fill", "xxx"]):
        assert plotting._bar_style_cycle() == ["fill", "xxx"]

    assert get_pyflash_style("condition_style_cycle") == original
    with pytest.raises(KeyError):
        set_pyflash_style(not_a_real_style_key=True)


def test_set_pyflash_style_invalid_update_is_atomic():
    original = get_pyflash_style("point_size")

    with pytest.raises(KeyError):
        set_pyflash_style({"point_size": 4, "not_a_real_style_key": True})

    assert get_pyflash_style("point_size") == original


def test_set_pyflash_style_invalid_rcparam_update_is_atomic():
    original_point_size = get_pyflash_style("point_size")
    original_tick_direction = get_pyflash_style("tick_direction")
    original_rc_direction = matplotlib.rcParams["xtick.direction"]

    with pytest.raises(ValueError):
        set_pyflash_style({"point_size": 4, "tick_direction": "sideways"})

    assert get_pyflash_style("point_size") == original_point_size
    assert get_pyflash_style("tick_direction") == original_tick_direction
    assert matplotlib.rcParams["xtick.direction"] == original_rc_direction


def test_set_pyflash_style_is_front_door_for_matplotlib_rcparams():
    set_pyflash_style(
        title_size=17,
        labelsize=19,
        despine=False,
        legend_frame=True,
        tick_direction="in",
        figure_size=(4.0, 3.0),
        save_bbox="fixed",
        save_pad_inches=0.2,
        save_dpi=300,
    )

    assert matplotlib.rcParams["axes.titlesize"] == 17
    assert matplotlib.rcParams["axes.labelsize"] == 19
    assert matplotlib.rcParams["axes.spines.top"] is True
    assert matplotlib.rcParams["axes.spines.right"] is True
    assert matplotlib.rcParams["legend.frameon"] is True
    assert matplotlib.rcParams["xtick.direction"] == "in"
    assert matplotlib.rcParams["figure.figsize"] == [4.0, 3.0]
    assert matplotlib.rcParams["savefig.bbox"] == "tight"
    assert matplotlib.rcParams["savefig.pad_inches"] == pytest.approx(0.2)
    assert matplotlib.rcParams["savefig.dpi"] == pytest.approx(300)


def test_save_fig_uses_fixed_pyflash_download_canvas(tmp_path):
    from PyFLASH.utils import save_fig

    with pyflash_style_context(figure_size=(4.0, 3.0), save_bbox="fixed"):
        fig, ax = plt.subplots(figsize=(2.0, 2.0))
        try:
            ax.set_title("A deliberately long title that would change a tight bbox")
            ax.set_xlabel("X label")
            ax.set_ylabel("Y label")
            out = save_fig(fig, str(tmp_path), "fixed_canvas", verbose=False, rasterize=False)
            assert tuple(fig.get_size_inches()) == pytest.approx((4.0, 3.0))
        finally:
            plt.close(fig)

    text = open(out, encoding="utf-8").read()
    width = float(re.search(r'width="([0-9.]+)pt"', text).group(1))
    height = float(re.search(r'height="([0-9.]+)pt"', text).group(1))
    assert width == pytest.approx(4.0 * 72)
    assert height == pytest.approx(3.0 * 72)


def test_tight_save_bbox_remains_available(tmp_path):
    from PyFLASH.utils import save_fig

    with pyflash_style_context(figure_size=(4.0, 3.0), save_bbox="tight"):
        fig, ax = plt.subplots(figsize=(2.0, 2.0))
        try:
            ax.set_xlabel("X label")
            out = save_fig(fig, str(tmp_path), "tight_canvas", verbose=False, rasterize=False)
            assert tuple(fig.get_size_inches()) == pytest.approx((2.0, 2.0))
        finally:
            plt.close(fig)

    assert out.endswith("tight_canvas.svg")


def test_plotly_save_helper_uses_fixed_pyflash_canvas(tmp_path):
    class FakePlotlyFigure:
        def write_image(self, path, format="svg"):
            assert format == "svg"
            open(path, "w", encoding="utf-8").write(
                '<svg width="1200" height="500" viewBox="0 0 288 216"></svg>'
            )

        def write_html(self, path, include_plotlyjs="cdn"):
            raise AssertionError("SVG write should not fall back to HTML")

    with pyflash_style_context(figure_size=(4.0, 3.0), save_bbox="fixed"):
        out = plotting._save_plotly_figure(
            FakePlotlyFigure(), str(tmp_path), "plotly_canvas", verbose=False
        )

    text = open(out, encoding="utf-8").read()
    assert 'width="288pt"' in text
    assert 'height="216pt"' in text


def test_pyflash_style_controls_significance_annotations():
    with pyflash_style_context(
        significance_thresholds={0.01: "**", 0.1: "*"},
        significance_ns="n.s.",
    ):
        assert get_pyflash_style("significance_thresholds") == {0.01: "**", 0.1: "*"}
        assert stats.get_annotation(0.0005) == "**"
        assert stats.get_annotation(0.005) == "**"
        assert plotting._get_annotation(0.05) == "*"
        assert stats.get_annotation(0.5) == "n.s."
        assert stats.get_annotation(0.2, ns="p") == 0.2


def test_render_value_matrix_uses_pyflash_matrix_style():
    matrix = pd.DataFrame([[1.0]], index=["a"], columns=["b"])
    annotations = pd.DataFrame([["*"]], index=["a"], columns=["b"])

    with pyflash_style_context(
        matrix_cmap="viridis",
        matrix_value_color="#654321",
        matrix_annotation_color="#123456",
        matrix_x_tick_rotation=30,
        matrix_y_tick_rotation=15,
    ):
        fig, ax = plt.subplots()
        try:
            plotting._render_value_matrix(
                matrix,
                ax=ax,
                fig=fig,
                annotations=annotations,
                show_values=True,
                show_colorbar=False,
            )
            assert ax.collections[0].cmap.name == "viridis"
            colors = {text.get_text(): text.get_color() for text in ax.texts}
            assert colors["1.00"] == "#654321"
            assert colors["*"] == "#123456"
            assert ax.get_xticklabels()[0].get_rotation() == pytest.approx(30)
            assert ax.get_yticklabels()[0].get_rotation() == pytest.approx(15)
        finally:
            plt.close(fig)


def test_matrix_action_uses_pyflash_matrix_cmap():
    ctx = SimpleNamespace(
        condition_df=pd.DataFrame({
            "A": [1.0, 2.0, 3.0, 4.0],
            "B": [4.0, 3.0, 2.0, 1.0],
        }),
        factor_df=None,
        factor_value=None,
        condition="Group",
        label="Group",
    )

    with pyflash_style_context(matrix_cmap="viridis"):
        fig, ax = plt.subplots()
        try:
            result = plotting.matrix_action(
                ctx,
                {"fig": fig, "ax": ax},
                filtered_columns=["A", "B"],
                tick_label_size=10,
            )
            assert result["heatmap"].collections[0].cmap.name == "viridis"
        finally:
            plt.close(fig)


def test_corr_pipeline_heatmap_uses_pyflash_matrix_cmap():
    matrix = pd.DataFrame([[1.0, 0.5], [0.5, 1.0]], index=["a", "b"], columns=["a", "b"])

    with pyflash_style_context(matrix_cmap="viridis"):
        fig = plotting._corr_pipeline_heatmap(
            matrix,
            None,
            "Correlation matrix",
            tick_label_size=10,
            vmin=-1,
            vmax=1,
        )
        try:
            assert fig.axes[0].collections[0].cmap.name == "viridis"
        finally:
            plt.close(fig)


def test_comparison_lines_style_custom_nonsignificant_label():
    from PyFLASH.stats import plot_comparison_lines_from_figdata

    with pyflash_style_context(significance_ns="n.s."):
        fig, ax = plt.subplots()
        try:
            ax.scatter([0, 1], [1.0, 2.0])
            plot_comparison_lines_from_figdata(
                ax,
                None,
                ax,
                annotations=["n.s."],
                comparisons=["1-2"],
                group_values=[pd.Series([1.0]), pd.Series([2.0])],
                group_positions=[0, 1],
                draw_error_bars=False,
            )
            text = next(t for t in ax.texts if t.get_text() == "n.s.")
            assert text.get_fontsize() == pytest.approx(18)
            assert text.get_fontweight() == "normal"
        finally:
            plt.close(fig)


def test_bar_chart_action_uses_pyflash_point_defaults(monkeypatch):
    ctx = SimpleNamespace(
        column="Metric",
        condition_df=pd.DataFrame({"AnimalName": ["a", "b"], "Metric": [1.0, 2.0]}),
        factor_df=None,
        factor_value=None,
        condition="A",
        condition_index=0,
        factor_index=0,
        color="#123456",
        label="A",
    )
    fig, ax = plt.subplots()
    calls = []

    def fake_swarmplot(*args, **kwargs):
        calls.append(kwargs.copy())
        return "scatter"

    monkeypatch.setattr(plotting.sns, "swarmplot", fake_swarmplot)
    try:
        with pyflash_style_context(
            point_size=4,
            bar_point_fill="group",
            bar_point_edge="none",
            bar_point_linewidth=0,
        ):
            plotting.bar_chart_action(ctx, {"ax": ax}, points=True)
        assert calls
        assert calls[-1]["color"] == "#123456"
        assert calls[-1]["edgecolor"] == "none"
        assert calls[-1]["size"] == 4
        assert calls[-1]["linewidth"] == 0
    finally:
        plt.close(fig)


def test_regression_action_uses_pyflash_scatter_defaults(monkeypatch):
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [2.0, 3.0, 4.0]})
    ctx = SimpleNamespace(
        condition_df=df,
        factor_df=None,
        factor_value=None,
        condition="A",
        condition_index=0,
        factor_index=0,
        factor=None,
        color="#123456",
        label="A",
        experiment=SimpleNamespace(condition_list=[]),
    )
    fig, ax = plt.subplots()
    calls = []

    def fake_regplot(**kwargs):
        calls.append(kwargs.copy())
        return kwargs["ax"]

    monkeypatch.setattr(plotting.sns, "regplot", fake_regplot)
    try:
        with pyflash_style_context(
            point_size=11,
            regression_point_alpha=0.4,
            regression_point_edge="group",
            regression_point_linewidth=2.5,
            regression_line_width=4.0,
        ):
            plotting.regression_action(ctx, {"ax": ax}, x="x", y="y")
        assert calls
        scatter_kws = calls[-1]["scatter_kws"]
        assert scatter_kws["s"] == 121
        assert scatter_kws["alpha"] == pytest.approx(0.4)
        assert scatter_kws["edgecolors"] == "#123456"
        assert scatter_kws["linewidths"] == pytest.approx(2.5)
        assert calls[-1]["line_kws"]["lw"] == pytest.approx(4.0)
    finally:
        plt.close(fig)


def test_scatter_3d_action_uses_style_and_explicit_overrides(monkeypatch):
    df = pd.DataFrame({
        "x": [1.0, 2.0],
        "y": [3.0, 4.0],
        "z": [5.0, 6.0],
    })
    ctx = SimpleNamespace(
        condition_df=df,
        factor_df=None,
        factor_value=None,
        condition="A",
        condition_index=0,
        factor_index=0,
        factor=None,
        color="#123456",
        label="A",
        experiment=SimpleNamespace(condition_list=[]),
    )
    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")
    calls = []

    def fake_scatter(*args, **kwargs):
        calls.append(kwargs.copy())
        return None

    monkeypatch.setattr(ax, "scatter", fake_scatter)
    try:
        with pyflash_style_context(
            point_size=7,
            scatter_3d_alpha=0.33,
            scatter_3d_edge="group",
            scatter_3d_linewidth=1.1,
        ):
            plotting.scatter_3d_action(
                ctx, {"ax": ax}, x="x", y="y", z="z")
            plotting.scatter_3d_action(
                ctx, {"ax": ax}, x="x", y="y", z="z",
                point_size=12, alpha=0.2, point_edge="none",
                point_linewidth=0,
            )

        assert np.all(np.asarray(calls[0]["s"], dtype=float) == 49)
        assert calls[0]["alpha"] == pytest.approx(0.33)
        assert calls[0]["edgecolors"] == "#123456"
        assert calls[0]["linewidths"] == pytest.approx(1.1)
        assert np.all(np.asarray(calls[1]["s"], dtype=float) == 144)
        assert calls[1]["alpha"] == pytest.approx(0.2)
        assert calls[1]["edgecolors"] == "none"
        assert calls[1]["linewidths"] == 0
    finally:
        plt.close(fig)


def test_cosinor_uses_pyflash_significance_and_point_style(monkeypatch):
    import PyFLASH.stats_extra as stats_extra

    def fake_fit_cosinor(*args, **kwargs):
        return {
            "p": 0.4,
            "amplitude": 1.0,
            "acrophase": 2.0,
            "r_squared": 0.5,
            "predict": lambda x: np.zeros_like(np.asarray(x, dtype=float)),
        }

    monkeypatch.setattr(stats_extra, "fit_cosinor", fake_fit_cosinor)
    df = pd.DataFrame({
        "Time": [0.0, 6.0, 12.0],
        "Value": [1.0, 2.0, 1.0],
        "Group": ["A", "A", "A"],
    })

    with pyflash_style_context(
        point_size=6,
        significance_thresholds={0.5: "SIG"},
        significance_ns="n.s.",
    ):
        fig, ax = plt.subplots()
        try:
            plotting._cosinor_axes(
                ax,
                df,
                value="Value",
                time_col="Time",
                group_col="Group",
                period=24.0,
                period_free=False,
                palette=None,
                show_points=True,
                time_map=None,
                night_shade=None,
            )
            labels = [text.get_text() for text in ax.get_legend().texts]
            assert any(label.endswith("SIG") for label in labels)
            point_lines = [line for line in ax.lines if line.get_marker() == "o"]
            assert point_lines
            assert point_lines[0].get_markersize() == pytest.approx(6)
        finally:
            plt.close(fig)


def test_public_helper_scatters_use_pyflash_point_size():
    with pyflash_style_context(point_size=6):
        batch = SimpleNamespace(summary=pd.DataFrame({
            "FeatureA": [1.0, 2.0, 3.0],
            "FeatureB": [1.0, 4.0, 9.0],
            "Group": ["A", "B", "A"],
        }))
        fig = plotting.plot_marker_pca(
            batch,
            data_cols=["FeatureA", "FeatureB"],
            hue_column="Group",
            annotate_loadings=False,
            save=False,
        )
        try:
            sizes = [
                float(size)
                for coll in fig.axes[0].collections
                for size in getattr(coll, "get_sizes", lambda: [])()
            ]
            assert sizes
            assert set(sizes) == {36.0}
        finally:
            plt.close(fig)

        fig, ax = plt.subplots(subplot_kw={"projection": "polar"})
        try:
            stats = plotting._acrophase_clock_axes(
                ax,
                pd.DataFrame({"Phase": [1.0, 2.0], "Group": ["A", "A"]}),
                phase_col="Phase",
                group_col="Group",
                period=24.0,
                radius_col=None,
                palette=None,
            )
            sizes = [
                float(size)
                for coll in ax.collections
                for size in getattr(coll, "get_sizes", lambda: [])()
            ]
            assert stats["groups"]
            assert sizes
            assert set(sizes) == {36.0}
        finally:
            plt.close(fig)
