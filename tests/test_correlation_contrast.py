import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest
from matplotlib import pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from scipy import stats as scipy_stats

import PyFLASH.report as report
from PyFLASH import ConditionBuilder, from_dataframe, stats
from PyFLASH.plotting import plot_correlation_contrast
from PyFLASH.spec import PLOT_REGISTRY, describe_status


# ── stats helpers (pure numeric) ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _close_figures_after_test():
    yield
    plt.close("all")


def test_fisher_z_difference_identical_correlations_is_nonsignificant():
    # Same correlation in both groups → no evidence of a difference.
    p = stats.fisher_z_correlation_difference(0.5, 30, 0.5, 30, "pearson")
    assert p == pytest.approx(1.0, abs=1e-6)


def test_fisher_z_difference_detects_opposite_correlations():
    p = stats.fisher_z_correlation_difference(0.8, 25, -0.6, 25, "pearson")
    assert p < 0.001


def test_zou_ci_brackets_zero_for_equal_correlations():
    d, lo, hi = stats.zou_correlation_difference_ci(0.5, 30, 0.5, 30, "pearson")
    assert d == pytest.approx(0.0, abs=1e-9)
    assert lo < 0 < hi


def test_spearman_se_is_wider_than_pearson():
    assert stats.fisher_z_se(0.6, 20, "spearman") > stats.fisher_z_se(0.6, 20, "pearson")


def test_fisher_se_nan_for_tiny_n():
    assert not np.isfinite(stats.fisher_z_se(0.5, 3, "pearson"))


def test_cauchy_combination_uniform_returns_half():
    assert stats.cauchy_combination_test([0.5, 0.5, 0.5]) == pytest.approx(0.5, abs=1e-6)


def test_cauchy_combination_driven_by_small_p():
    assert stats.cauchy_combination_test([1e-4, 0.9, 0.8]) < 0.05


def test_cauchy_combination_empty_is_nan():
    assert not np.isfinite(stats.cauchy_combination_test([]))


# ── plot ─────────────────────────────────────────────────────────────────────

def _contrast_experiment(tmp_path):
    """3 diagnosis groups where the Volume↔activity correlation is strong in
    Control and collapses in MCI/AD — plus numeric (Age) and categorical (Sex)
    covariates for the partial-correlation path."""
    rng = np.random.default_rng(0)
    n = 10
    rows = []
    for grp, slope in (("Control", 1.0), ("MCI", 0.0), ("AD", -1.0)):
        vol = np.linspace(10.0, 20.0, n)
        for i in range(n):
            rows.append({
                "Subject": f"{grp}{i}",
                "Diagnosis": grp,
                "Volume": float(vol[i]),
                "M1": float(slope * vol[i] + rng.normal(0, 0.6)),
                "M2": float(slope * vol[i] * 0.8 + rng.normal(0, 0.6)),
                "Age": float(60 + rng.normal(0, 5)),
                "Sex": "Male" if i % 2 == 0 else "Female",
            })
    df = pd.DataFrame(rows)
    conditions = (
        ConditionBuilder("Diagnosis")
        .add("Control", color="black")
        .add("MCI", color="blue")
        .add("AD", color="orange")
        .build()
    )
    return from_dataframe(
        df, conditions=conditions, name="contrast-table",
        condition_col="Diagnosis", animal_col="Subject",
        fig_path=tmp_path / "figures", data_path=tmp_path / "data",
    )


def test_explicit_y_list_and_factor(tmp_path):
    exp = _contrast_experiment(tmp_path)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", test="spearmanr", save=False)
    assert isinstance(fig, Figure)


def test_inferred_columns_path(tmp_path):
    exp = _contrast_experiment(tmp_path)
    fig = plot_correlation_contrast(
        exp, x="Volume", column_strings=["M"], factor="Diagnosis",
        reference="Control", save=False)
    assert isinstance(fig, Figure)


def test_covariates_partial_correlation_path(tmp_path):
    exp = _contrast_experiment(tmp_path)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", covariates=["Age", "Sex"], save=False)
    assert isinstance(fig, Figure)


def _residualize_for_test(values, cov_frame, *, rank_numeric=False):
    design_parts = [np.ones((len(cov_frame), 1))]
    for col in cov_frame.columns:
        series = cov_frame[col]
        numeric = pd.to_numeric(series, errors="coerce")
        if int(numeric.notna().sum()) == int(series.notna().sum()):
            if rank_numeric:
                numeric = numeric.rank(method="average")
            design_parts.append(numeric.to_numpy(dtype=float).reshape(-1, 1))
        else:
            design_parts.append(series.eq("Male").astype(float).to_numpy().reshape(-1, 1))
    design = np.column_stack(design_parts)
    y = np.asarray(values, dtype=float)
    return y - design @ np.linalg.lstsq(design, y, rcond=None)[0]


def _reported_control_m1(exp, covariate_adjustment=None):
    report.start()
    try:
        kwargs = {}
        if covariate_adjustment is not None:
            kwargs["covariate_adjustment"] = covariate_adjustment
        plot_correlation_contrast(
            exp,
            x="Volume",
            y=["M1"],
            factor="Diagnosis",
            reference="Control",
            covariates=["Age", "Sex"],
            save=False,
            **kwargs,
        )
        records = report.collect()
    finally:
        report.collect()
    return [
        record
        for record in records
        if record.get("kind") == "correlation"
        and record.get("group") == "Control"
        and record.get("y") == "M1"
    ][0]


def test_correlation_contrast_covariate_adjustment_modes(tmp_path):
    exp = _contrast_experiment(tmp_path)
    source = exp.summary.loc[
        exp.summary["Diagnosis"].eq("Control"),
        ["Volume", "M1", "Age", "Sex"],
    ].dropna()
    cov_frame = source[["Age", "Sex"]]

    ranked_volume = pd.Series(source["Volume"].to_numpy(dtype=float)).rank(method="average")
    ranked_m1 = pd.Series(source["M1"].to_numpy(dtype=float)).rank(method="average")
    rank_x = _residualize_for_test(ranked_volume, cov_frame, rank_numeric=True)
    rank_y = _residualize_for_test(ranked_m1, cov_frame, rank_numeric=True)
    expected_rank_first = scipy_stats.pearsonr(rank_x, rank_y).statistic

    raw_x = _residualize_for_test(source["Volume"], cov_frame)
    raw_y = _residualize_for_test(source["M1"], cov_frame)
    expected_residual_first = scipy_stats.spearmanr(raw_x, raw_y).statistic

    default_record = _reported_control_m1(exp)
    residual_first_record = _reported_control_m1(
        exp,
        covariate_adjustment="residual_then_correlation",
    )

    assert default_record["covariate_adjustment"] == "rank_then_residual"
    assert default_record["r"] == pytest.approx(expected_rank_first)
    assert residual_first_record["covariate_adjustment"] == "residual_then_correlation"
    assert residual_first_record["r"] == pytest.approx(expected_residual_first)


def test_significance_modes_change_annotations(tmp_path):
    exp = _contrast_experiment(tmp_path)
    kw = dict(x="Volume", y=["M1", "M2"], factor="Diagnosis",
              reference="Control", save=False)
    fig_none = plot_correlation_contrast(exp, significance=None, **kw)
    fig_omni = plot_correlation_contrast(exp, significance="omnibus", **kw)
    fig_stars = plot_correlation_contrast(exp, significance="stars", **kw)
    fig_lines = plot_correlation_contrast(exp, significance="lines", **kw)

    def n_stars(fig):
        return sum(1 for t in fig.axes[0].texts if t.get_text() and set(t.get_text()) == {"*"})

    # omnibus / lines add comparison Line2D artists above the axis
    assert len(fig_omni.axes[0].lines) > len(fig_none.axes[0].lines)
    assert len(fig_lines.axes[0].lines) > len(fig_none.axes[0].lines)
    # stars and lines mark per-measure stars; neither mode marks none
    assert n_stars(fig_stars) > 0
    assert n_stars(fig_lines) > 0
    assert n_stars(fig_none) == 0


def test_pearson_and_kendall_tests_run(tmp_path):
    exp = _contrast_experiment(tmp_path)
    for test in ("pearsonr", "kendalltau"):
        fig = plot_correlation_contrast(
            exp, x="Volume", y=["M1"], factor="Diagnosis",
            reference="Control", test=test, save=False)
        assert isinstance(fig, Figure)


def test_emits_correlation_records_when_armed(tmp_path):
    exp = _contrast_experiment(tmp_path)
    report.start()
    try:
        plot_correlation_contrast(
            exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
            reference="Control", save=False)
        records = report.collect()
    finally:
        report.collect()  # ensure disarmed even on failure
    corr = [r for r in records if r.get("kind") == "correlation"]
    assert len(corr) == 6  # 2 measures × 3 groups
    assert all(r.get("method") == "spearman" for r in corr)


def test_side_summary_carries_confidence_intervals(tmp_path):
    exp = _contrast_experiment(tmp_path)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", save=False)
    text = "\n".join(t.get_text() for t in fig.axes[0].texts)
    assert "Fisher r-to-z" in text
    assert "p=" in text
    assert "[" in text and "]" in text


def test_registered_and_describe_covered():
    assert PLOT_REGISTRY.get("correlation_contrast") == "plot_correlation_contrast"
    assert describe_status("correlation_contrast") == "covered"


# ── x-axis spacing ───────────────────────────────────────────────────────────
# A slopegraph has one node per group, so the default axes box spreads the
# groups much further apart than the data warrants. These pin the narrowed
# data region and, in particular, that the gap between adjacent x-ticks does
# not depend on how many groups there are.

def _n_group_experiment(tmp_path, n_groups):
    rng = np.random.default_rng(3)
    specs = [("Control", 1.0), ("MCI", 0.4), ("AD", -1.0), ("AD2", -0.7), ("AD3", -0.3)]
    rows = []
    for grp, slope in specs[:n_groups]:
        vol = np.linspace(10.0, 20.0, 10)
        for i in range(10):
            rows.append({"Subject": f"{grp}{i}", "Diagnosis": grp,
                         "Volume": float(vol[i]),
                         "M1": float(slope * vol[i] + rng.normal(0, 0.6)),
                         "M2": float(slope * vol[i] * 0.8 + rng.normal(0, 0.9))})
    cb = ConditionBuilder("Diagnosis")
    for grp, _ in specs[:n_groups]:
        cb = cb.add(grp)
    return from_dataframe(
        pd.DataFrame(rows), conditions=cb.build(), name="ngroup",
        condition_col="Diagnosis", animal_col="Subject",
        fig_path=tmp_path / "f", data_path=tmp_path / "d")


def _axes_width_fraction(fig):
    """Axes box width as a fraction of the figure width."""
    return float(fig.axes[0].get_position().width)


def _tick_gap_fraction(fig):
    """Figure-width fraction spanned by one gap between adjacent x-ticks."""
    ax = fig.axes[0]
    lo, hi = ax.get_xlim()
    return _axes_width_fraction(fig) / (hi - lo)


def _node_marker_sizes(fig):
    return [
        float(line.get_markersize())
        for line in fig.axes[0].lines
        if line.get_marker() == "o"
    ]


def _ci_line_collections(fig):
    return [
        coll for coll in fig.axes[0].collections
        if isinstance(coll, LineCollection) and len(coll.get_segments()) > 0
    ]


def _ci_cap_marker_sizes(fig):
    return [
        float(line.get_markersize())
        for line in fig.axes[0].lines
        if line.get_marker() == "_"
    ]


def _comparison_star_texts(fig):
    return [
        text for text in fig.axes[0].texts
        if text.get_text() and set(text.get_text()) == {"*"}
    ]


def _comparison_line_ys(fig):
    ax = fig.axes[0]
    ymax = ax.get_ylim()[1]
    ys = []
    for line in ax.lines:
        ydata = np.asarray(line.get_ydata(), dtype=float)
        if len(ydata) == 2 and np.all(np.isfinite(ydata)):
            if ydata[0] == pytest.approx(ydata[1]) and ydata[0] > ymax:
                ys.append(float(ydata[0]))
    return ys


def _node_star_connector_end_ys(fig):
    ys = []
    for line in fig.axes[0].lines:
        if line.get_linestyle() != ":":
            continue
        ydata = np.asarray(line.get_ydata(), dtype=float)
        if len(ydata) >= 2 and np.all(np.isfinite(ydata)):
            ys.append(float(ydata[-1]))
    return ys


def test_data_region_is_narrower_than_the_default_axes_box(tmp_path):
    """Matplotlib's default axes spans 0.775 of the figure; a 3-group
    slopegraph must use appreciably less than that."""
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", save=False)
    frac = _axes_width_fraction(fig)
    assert frac < 0.6, f"data region still spans {frac:.2f} of the figure"


def test_tick_gap_is_constant_across_group_counts(tmp_path):
    """The whole point of sizing from the x-span rather than the group count:
    two groups and five groups get the same spacing between ticks."""
    gaps = {}
    for n in (2, 3, 4):
        exp = _n_group_experiment(tmp_path, n)
        fig = plot_correlation_contrast(
            exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
            reference="Control", significance=None, save=False)
        gaps[n] = _tick_gap_fraction(fig)
    assert gaps[2] == pytest.approx(gaps[3], rel=0.02), gaps
    assert gaps[3] == pytest.approx(gaps[4], rel=0.02), gaps


def test_axes_width_is_capped_for_many_groups(tmp_path):
    """Without a cap the data region would grow past the figure once enough
    groups are added, pushing the legend and stats block off the canvas."""
    exp = _n_group_experiment(tmp_path, 5)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", save=False)
    assert _axes_width_fraction(fig) <= 0.70 + 1e-6


def test_x_axis_width_scale_is_public_schema_parameter():
    import inspect

    from PyFLASH.plotting import plot_coefficient_contrast

    for fn in (plot_correlation_contrast, plot_coefficient_contrast):
        param = inspect.signature(fn).parameters["x_axis_width_scale"]
        assert param.default == pytest.approx(0.8)
        node_param = inspect.signature(fn).parameters["node_size"]
        assert node_param.default == pytest.approx(10.0)
        show_ci_param = inspect.signature(fn).parameters["show_ci"]
        assert show_ci_param.default is True
        ci_alpha_param = inspect.signature(fn).parameters["ci_alpha"]
        assert ci_alpha_param.default == pytest.approx(0.05)


def test_default_x_axis_width_scale_reduces_previous_spacing(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    previous = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        x_axis_width_scale=1.0, save=False)
    default = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        save=False)
    assert default.get_size_inches()[0] == pytest.approx(previous.get_size_inches()[0])
    assert _axes_width_fraction(default) == pytest.approx(
        _axes_width_fraction(previous) * 0.8)


def test_explicit_x_axis_width_scale_shrinks_axes_not_figure(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    wide = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        x_axis_width_scale=1.0, save=False)
    narrow = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        x_axis_width_scale=0.5, save=False)
    assert narrow.get_size_inches()[0] == pytest.approx(wide.get_size_inches()[0])
    assert _axes_width_fraction(narrow) == pytest.approx(
        _axes_width_fraction(wide) * 0.5)


def test_coefficient_contrast_uses_same_x_axis_width_scale(tmp_path):
    from PyFLASH.plotting import plot_coefficient_contrast

    exp = _n_group_experiment(tmp_path, 3)
    corr = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        x_axis_width_scale=0.55, save=False)
    coef = plot_coefficient_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        x_axis_width_scale=0.55, save=False)
    assert _axes_width_fraction(coef) == pytest.approx(_axes_width_fraction(corr))


def test_invalid_x_axis_width_scale_raises(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    with pytest.raises(ValueError, match="x_axis_width_scale"):
        plot_correlation_contrast(
            exp, x="Volume", y=["M1"], factor="Diagnosis",
            reference="Control", x_axis_width_scale=0, save=False)


def test_default_node_size_is_larger_than_prior_contrast_nodes(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        save=False)
    assert _node_marker_sizes(fig)
    assert all(size == pytest.approx(10.0) for size in _node_marker_sizes(fig))


def test_top_edge_nodes_are_not_clipped(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        save=False)
    node_lines = [line for line in fig.axes[0].lines if line.get_marker() == "o"]
    assert node_lines
    assert all(line.get_clip_on() is False for line in node_lines)


def test_explicit_node_size_controls_group_nodes(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        node_size=14, save=False)
    assert _node_marker_sizes(fig)
    assert all(size == pytest.approx(14.0) for size in _node_marker_sizes(fig))


def test_coefficient_contrast_uses_same_node_size(tmp_path):
    from PyFLASH.plotting import plot_coefficient_contrast

    exp = _n_group_experiment(tmp_path, 3)
    corr = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        node_size=12.5, save=False)
    coef = plot_coefficient_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_stats_summary=False,
        node_size=12.5, save=False)
    assert _node_marker_sizes(coef) == pytest.approx(_node_marker_sizes(corr))


def test_invalid_node_size_raises(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    with pytest.raises(ValueError, match="node_size"):
        plot_correlation_contrast(
            exp, x="Volume", y=["M1"], factor="Diagnosis",
            reference="Control", node_size=0, save=False)


def test_confidence_intervals_drawn_with_short_caps_by_default(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None,
        show_stats_summary=False, save=False)
    assert _ci_line_collections(fig)
    caps = _ci_cap_marker_sizes(fig)
    assert caps
    assert max(caps) <= 8.0


def test_confidence_interval_display_can_be_disabled(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None, show_ci=False,
        show_stats_summary=False, save=False)
    assert _ci_line_collections(fig) == []
    assert _ci_cap_marker_sizes(fig) == []


def test_invalid_ci_alpha_raises(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    with pytest.raises(ValueError, match="ci_alpha"):
        plot_correlation_contrast(
            exp, x="Volume", y=["M1"], factor="Diagnosis",
            reference="Control", ci_alpha=1.5, save=False)


def test_coefficient_contrast_draws_matching_confidence_intervals(tmp_path):
    from PyFLASH.plotting import plot_coefficient_contrast

    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_coefficient_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=None,
        show_stats_summary=False, save=False)
    assert _ci_line_collections(fig)
    caps = _ci_cap_marker_sizes(fig)
    assert caps
    assert max(caps) <= 8.0


@pytest.mark.parametrize("significance", ["lines", "omnibus", "stars"])
def test_contrast_stars_match_mean_bars_size(tmp_path, significance):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance=significance,
        show_stats_summary=False, save=False)
    stars = _comparison_star_texts(fig)
    assert stars
    assert all(text.get_fontsize() == pytest.approx(35) for text in stars)
    assert all(text.get_va() == "center" for text in stars)


def test_comparison_lines_are_spaced_for_large_stars(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance="lines",
        show_stats_summary=False, save=False)
    ys = sorted(set(round(y, 6) for y in _comparison_line_ys(fig)))
    assert len(ys) >= 2
    assert min(ys) - fig.axes[0].get_ylim()[1] >= 0.075
    gaps = np.diff(ys)
    assert float(np.min(gaps)) >= 0.16


def test_comparison_line_stars_sit_tight_to_lines(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance="lines",
        show_stats_summary=False, save=False)
    line_ys = _comparison_line_ys(fig)
    assert line_ys
    span = fig.axes[0].get_ylim()[1] - fig.axes[0].get_ylim()[0]
    for text in _comparison_star_texts(fig):
        text_y = float(text.get_position()[1])
        nearest_line = min(line_ys, key=lambda y: abs(text_y - y))
        offset = text_y - nearest_line
        assert offset < 0
        assert abs(offset) <= span * 0.01


def test_omnibus_stars_sit_tight_to_brackets(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance="omnibus",
        show_stats_summary=False, save=False)
    line_ys = _comparison_line_ys(fig)
    assert line_ys
    span = fig.axes[0].get_ylim()[1] - fig.axes[0].get_ylim()[0]
    for text in _comparison_star_texts(fig):
        text_y = float(text.get_position()[1])
        nearest_line = min(line_ys, key=lambda y: abs(text_y - y))
        offset = text_y - nearest_line
        assert offset < 0
        assert abs(offset) <= span * 0.01


def test_omnibus_mode_has_no_bottom_caption(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance="omnibus",
        show_stats_summary=False, save=False)
    assert all("brackets:" not in text.get_text() for text in fig.axes[0].texts)


def test_coefficient_contrast_keeps_nodes_unclipped_and_no_caption(tmp_path):
    from PyFLASH.plotting import plot_coefficient_contrast

    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_coefficient_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance="omnibus",
        show_stats_summary=False, save=False)
    node_lines = [line for line in fig.axes[0].lines if line.get_marker() == "o"]
    assert node_lines
    assert all(line.get_clip_on() is False for line in node_lines)
    assert all("brackets:" not in text.get_text() for text in fig.axes[0].texts)


def test_node_stars_are_large_spaced_and_slightly_low(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance="stars",
        show_stats_summary=False, save=False)
    stars = _comparison_star_texts(fig)
    connector_ys = _node_star_connector_end_ys(fig)
    assert stars
    assert connector_ys
    span = fig.axes[0].get_ylim()[1] - fig.axes[0].get_ylim()[0]
    ymax = fig.axes[0].get_ylim()[1]
    by_group = {}
    for text in stars:
        text_x, text_y = text.get_position()
        assert text.get_fontsize() == pytest.approx(35)
        assert float(text_y) <= ymax - span * 0.07
        by_group.setdefault(round(float(text_x), 2), []).append(float(text_y))
    for ys in by_group.values():
        if len(ys) > 1:
            gaps = np.diff(sorted(ys))
            assert float(np.min(gaps)) >= span * 0.09


def test_node_star_connectors_target_directional_star_corners(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance="stars",
        show_stats_summary=False, save=False)
    ax = fig.axes[0]
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    stars = sorted(_comparison_star_texts(fig), key=lambda t: (t.get_position()[0], t.get_position()[1]))
    connectors = []
    for line in ax.lines:
        if line.get_linestyle() != ":":
            continue
        xdata = np.asarray(line.get_xdata(), dtype=float)
        ydata = np.asarray(line.get_ydata(), dtype=float)
        if len(xdata) >= 2 and len(ydata) >= 2 and np.all(np.isfinite(ydata)):
            connectors.append((float(xdata[-1]), float(ydata[0]), float(ydata[-1])))
    connectors = sorted(connectors, key=lambda item: (item[0], item[2]))
    assert len(stars) == len(connectors)
    expected = span * 0.045
    for text, (_x, node_y, connector_y) in zip(stars, connectors):
        star_y = float(text.get_position()[1])
        if node_y > star_y:
            assert connector_y - star_y == pytest.approx(expected)
        else:
            assert star_y - connector_y == pytest.approx(expected)


def test_node_star_group_labels_stay_inside_axis_near_top(tmp_path):
    exp = _n_group_experiment(tmp_path, 3)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance="stars",
        show_stats_summary=False, save=False)
    ax = fig.axes[0]
    ymin, ymax = ax.get_ylim()
    labels = [text for text in ax.texts if text.get_text().startswith("vs ")]
    assert labels
    for text in labels:
        y = float(text.get_position()[1])
        assert ymin < y < ymax


def test_star_annotations_stay_inside_the_axes_at_minimum_width(tmp_path):
    """At 2 groups the figure hits its width floor and the 'vs <reference>'
    label would otherwise overrun the right spine into the legend."""
    exp = _n_group_experiment(tmp_path, 2)
    fig = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance="stars", save=False)
    ax = fig.axes[0]
    fig.canvas.draw()
    x_hi = ax.get_xlim()[1]
    labels = [t for t in ax.texts if t.get_text().startswith("vs ")]
    assert labels, "expected a 'vs <reference>' annotation in stars mode"
    inv = ax.transData.inverted()
    for t in labels:
        right = inv.transform((t.get_window_extent().x1, 0.0))[0]
        assert right <= x_hi, f"{t.get_text()!r} overruns the axes ({right} > {x_hi})"


def test_default_significance_mode_is_comparison_lines(tmp_path):
    """'lines' is the default because it names which contrast each mark belongs
    to; stars at a node leave that implicit. Pinned so the default can't drift."""
    import inspect

    from PyFLASH.plotting import plot_coefficient_contrast

    for fn in (plot_correlation_contrast, plot_coefficient_contrast):
        assert inspect.signature(fn).parameters["significance"].default == "lines", fn.__name__

    exp = _n_group_experiment(tmp_path, 3)
    default = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", save=False)
    explicit = plot_correlation_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", significance="lines", save=False)
    # Same artist counts => the default really is the lines renderer, not merely
    # a matching keyword string.
    assert len(default.axes[0].lines) == len(explicit.axes[0].lines)
    assert len(default.axes[0].lines) > 0
