"""plot_coefficient_contrast: the slope counterpart of the correlation contrast.

Covers the stats helpers (tails, agreement with statsmodels), the plot paths
(explicit/inferred columns, covariates, value modes, significance modes), the
stats side-summary contract, and registry/describe wiring.
"""

import matplotlib
matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure
from scipy import stats as ss

from PyFLASH import report
from PyFLASH.conditions import ConditionBuilder
from PyFLASH.dataframe import from_dataframe
from PyFLASH.plotting import (
    plot_coefficient_contrast,
    _coefficient_contrast_table,
    _coefficient_contrast_stats,
    _gc_plot_prepare,
    _filter_coefficient_terms,
)
from PyFLASH.spec import PLOT_REGISTRY, describe_status
from PyFLASH.stats import fisher_z_correlation_difference, interaction_slope_difference


# ── stats helpers ────────────────────────────────────────────────────────────

def test_interaction_matches_statsmodels():
    smf = pytest.importorskip("statsmodels.formula.api")
    rng = np.random.default_rng(3)
    n = 40
    df = pd.DataFrame({
        "x": rng.normal(size=n),
        "g": ["A"] * (n // 2) + ["B"] * (n // 2),
    })
    df["y"] = np.where(df.g.eq("A"), 1.0, -0.5) * df.x + rng.normal(0, 0.4, n)
    ours = interaction_slope_difference(df.x, df.y, df.g, reference="A")
    fitted = smf.ols('y ~ x*C(g, Treatment("A"))', df).fit()
    term = [t for t in fitted.params.index if "x:" in t][0]
    assert np.isclose(ours["p"], fitted.pvalues[term])
    assert np.isclose(ours["estimate"], fitted.params[term])
    assert np.isclose(ours["se"], fitted.bse[term])


def test_interaction_covariates_match_statsmodels():
    smf = pytest.importorskip("statsmodels.formula.api")
    rng = np.random.default_rng(4)
    n = 40
    df = pd.DataFrame({
        "x": rng.normal(size=n),
        "age": rng.normal(60, 5, n),
        "g": ["A"] * (n // 2) + ["B"] * (n // 2),
    })
    df["y"] = df.x + 0.3 * df.age + rng.normal(0, 0.4, n)
    ours = interaction_slope_difference(
        df.x, df.y, df.g, reference="A", covariates=df[["age"]])
    fitted = smf.ols('y ~ x*C(g, Treatment("A")) + age', df).fit()
    term = [t for t in fitted.params.index if "x:" in t][0]
    assert np.isclose(ours["p"], fitted.pvalues[term])


def test_tail_halves_two_sided_p_in_observed_direction():
    two = fisher_z_correlation_difference(0.8, 20, -0.2, 20, "pearson", tail="two")
    one = fisher_z_correlation_difference(0.8, 20, -0.2, 20, "pearson", tail="one")
    assert np.isclose(one, two / 2.0)


def test_tail_directions_are_complementary():
    less = fisher_z_correlation_difference(0.8, 20, -0.2, 20, "pearson", tail="less")
    greater = fisher_z_correlation_difference(0.8, 20, -0.2, 20, "pearson", tail="greater")
    assert np.isclose(less + greater, 1.0)
    # r1 > r2 here, so 'greater' is the supported direction
    assert greater < less


def test_invalid_tail_raises():
    with pytest.raises(ValueError, match="tail must be one of"):
        fisher_z_correlation_difference(0.5, 20, 0.2, 20, tail="sideways")


def test_interaction_requires_exactly_two_groups():
    df = pd.DataFrame({"x": range(9), "y": range(9), "g": list("AAABBBCCC")})
    with pytest.raises(ValueError, match="exactly two groups"):
        interaction_slope_difference(df.x, df.y, df.g)


# ── term filtering ───────────────────────────────────────────────────────────

def test_filter_coefficient_terms_regex_and_list():
    coeffs = pd.DataFrame({"term": ["Intercept", "Age", "Age:Dx[T.AD]", "Dx[T.AD]"],
                           "estimate": [1.0, 2.0, 3.0, 4.0]})
    assert list(_filter_coefficient_terms(coeffs, ":")["term"]) == ["Age:Dx[T.AD]"]
    assert list(_filter_coefficient_terms(coeffs, ["Intercept"])["term"]) == ["Intercept"]


def test_filter_coefficient_terms_requires_term_column():
    with pytest.raises(ValueError, match="'term' column"):
        _filter_coefficient_terms(pd.DataFrame({"estimate": [1.0]}), ":")


def test_filter_coefficient_terms_falls_back_to_literal_for_patsy_names():
    """Patsy names are full of regex metacharacters; a literal name must work."""
    coeffs = pd.DataFrame({"term": ["Intercept", "Age", "Age:C(Dx)[T.AD]"],
                           "estimate": [1.0, 2.0, 3.0]})
    got = _filter_coefficient_terms(coeffs, "C(Dx)[T.AD]")
    assert list(got["term"]) == ["Age:C(Dx)[T.AD]"]


def test_filter_coefficient_terms_raises_friendly_error_on_bad_regex():
    coeffs = pd.DataFrame({"term": ["Age"], "estimate": [1.0]})
    with pytest.raises(ValueError, match="not a valid pattern"):
        _filter_coefficient_terms(coeffs, "Age(")


# ── plot ─────────────────────────────────────────────────────────────────────

def _contrast_experiment(tmp_path):
    """3 groups whose Volume->measure SLOPE flips sign across the ordered factor,
    plus numeric (Age) and categorical (Sex) covariates."""
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
        df, conditions=conditions, name="coef-contrast",
        condition_col="Diagnosis", animal_col="Subject",
        fig_path=tmp_path / "figures", data_path=tmp_path / "data",
    ), df


def test_explicit_y_list_and_factor(tmp_path):
    exp, _ = _contrast_experiment(tmp_path)
    fig = plot_coefficient_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", save=False)
    assert isinstance(fig, Figure)


def test_inferred_columns_path(tmp_path):
    exp, _ = _contrast_experiment(tmp_path)
    fig = plot_coefficient_contrast(
        exp, x="Volume", column_strings=["M"], factor="Diagnosis",
        reference="Control", save=False)
    assert isinstance(fig, Figure)


def test_beta_equals_pearson_r_without_covariates(tmp_path):
    """The headline property: a standardized slope IS the correlation when no
    covariates are supplied, so the two contrast plots share an axis."""
    exp, df = _contrast_experiment(tmp_path)
    _rb, scope, _nd, _nc, grps = _gc_plot_prepare(
        exp, ["M1"], None, None, "", "conditions", "Diagnosis", None, None)
    table = _coefficient_contrast_table(scope, "Volume", ["M1"], grps, [], 4, value="beta")
    for _, row in table.iterrows():
        sub = df[df.Diagnosis == row["group"]]
        assert np.isclose(row["r"], ss.pearsonr(sub.Volume, sub.M1)[0])


def test_slope_mode_returns_raw_units(tmp_path):
    exp, df = _contrast_experiment(tmp_path)
    _rb, scope, _nd, _nc, grps = _gc_plot_prepare(
        exp, ["M1"], None, None, "", "conditions", "Diagnosis", None, None)
    table = _coefficient_contrast_table(scope, "Volume", ["M1"], grps, [], 4, value="slope")
    control = table[table.group.eq("Control")]["r"].iloc[0]
    # data were generated with slope 1.0 in Control
    assert 0.8 < control < 1.2


def test_covariate_and_rank_paths(tmp_path):
    exp, _ = _contrast_experiment(tmp_path)
    for kwargs in ({"covariates": ["Age", "Sex"]}, {"rank": True}, {"value": "slope"}):
        fig = plot_coefficient_contrast(
            exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
            reference="Control", save=False, **kwargs)
        assert isinstance(fig, Figure)


def test_invalid_value_raises(tmp_path):
    exp, _ = _contrast_experiment(tmp_path)
    with pytest.raises(ValueError, match="value must be one of"):
        plot_coefficient_contrast(
            exp, x="Volume", y=["M1"], factor="Diagnosis", value="nonsense", save=False)


def test_significance_modes_change_annotations(tmp_path):
    exp, _ = _contrast_experiment(tmp_path)
    kw = dict(x="Volume", y=["M1", "M2"], factor="Diagnosis",
              reference="Control", save=False, show_stats_summary=False)
    fig_none = plot_coefficient_contrast(exp, significance=None, **kw)
    fig_omni = plot_coefficient_contrast(exp, significance="omnibus", **kw)
    fig_stars = plot_coefficient_contrast(exp, significance="stars", **kw)
    fig_lines = plot_coefficient_contrast(exp, significance="lines", **kw)

    def n_stars(fig):
        return sum(1 for t in fig.axes[0].texts
                   if t.get_text() and set(t.get_text()) == {"*"})

    assert len(fig_omni.axes[0].lines) > len(fig_none.axes[0].lines)
    assert len(fig_lines.axes[0].lines) > len(fig_none.axes[0].lines)
    assert n_stars(fig_stars) > 0
    assert n_stars(fig_lines) > 0
    assert n_stars(fig_none) == 0


def test_one_tailed_p_is_half_of_two_tailed(tmp_path):
    exp, _ = _contrast_experiment(tmp_path)
    _rb, scope, _nd, _nc, grps = _gc_plot_prepare(
        exp, ["M1"], None, None, "", "conditions", "Diagnosis", None, None)
    order = ["Control", "MCI", "AD"]
    two, _a, _d = _coefficient_contrast_stats(
        scope, "Volume", ["M1"], grps, order, "Control", [], tail="two")
    one, _a, _d = _coefficient_contrast_stats(
        scope, "Volume", ["M1"], grps, order, "Control", [], tail="one")
    assert np.isclose(one[("M1", "AD")], two[("M1", "AD")] / 2.0)


# ── stats side-summary contract ──────────────────────────────────────────────

def _summary_text(fig):
    return "\n".join(t.get_text() for t in fig.axes[0].texts)


def test_side_summary_carries_exact_values(tmp_path):
    exp, _ = _contrast_experiment(tmp_path)
    fig = plot_coefficient_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", save=False)
    text = _summary_text(fig)
    assert "OLS x*group interaction" in text   # test/model name
    assert "Reference: Control" in text
    assert "n=" in text                        # sample size
    assert "p=" in text                        # exact p-values
    assert "dif=" in text                      # effect size / coefficient difference
    assert "[" in text and "]" in text         # node confidence intervals


def test_side_summary_reports_tail_and_value_mode(tmp_path):
    exp, _ = _contrast_experiment(tmp_path)
    fig = plot_coefficient_contrast(
        exp, x="Volume", y=["M1"], factor="Diagnosis", reference="Control",
        value="slope", tail="less", save=False)
    text = _summary_text(fig)
    assert "less-tailed" in text
    assert "raw slope" in text


def test_side_summary_is_removable_and_axis_stays_compact(tmp_path):
    """Contract: the graph itself carries only compact marks; exact readouts live
    in the removable side block."""
    exp, _ = _contrast_experiment(tmp_path)
    kw = dict(x="Volume", y=["M1", "M2"], factor="Diagnosis",
              reference="Control", save=False)
    with_summary = plot_coefficient_contrast(exp, show_stats_summary=True, **kw)
    without = plot_coefficient_contrast(exp, show_stats_summary=False, **kw)
    assert len(with_summary.axes[0].texts) > len(without.axes[0].texts)
    # no exact p-value readouts inside the plotted area when the block is off
    assert "p=" not in _summary_text(without)


def test_side_summary_caps_listed_rows(tmp_path):
    exp, _ = _contrast_experiment(tmp_path)
    fig = plot_coefficient_contrast(
        exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
        reference="Control", stats_summary_max_items=1, save=False)
    assert "p=" in _summary_text(fig)


# ── registry / describe ──────────────────────────────────────────────────────

def test_emits_records_when_armed(tmp_path):
    exp, _ = _contrast_experiment(tmp_path)
    report.start()
    try:
        plot_coefficient_contrast(
            exp, x="Volume", y=["M1", "M2"], factor="Diagnosis",
            reference="Control", save=False)
        records = report.collect()
    finally:
        report.collect()
    corr = [r for r in records if r.get("kind") == "correlation"]
    assert len(corr) == 6  # 2 measures x 3 groups


def test_registered_and_describe_covered():
    assert PLOT_REGISTRY.get("coefficient_contrast") == "plot_coefficient_contrast"
    assert describe_status("coefficient_contrast") == "covered"


# ── regressions found by verification ────────────────────────────────────────

def test_directional_tail_agrees_between_the_two_contrast_plots(tmp_path):
    """'greater' must mean group > reference in BOTH plots, not opposite things.

    The correlation contrast drops from Control to AD, so 'less' is the supported
    direction and must give the small p in both.
    """
    exp, _ = _contrast_experiment(tmp_path)
    _rb, scope, _nd, _nc, grps = _gc_plot_prepare(
        exp, ["M1"], None, None, "", "conditions", "Diagnosis", None, None)
    order = ["Control", "MCI", "AD"]
    from PyFLASH.plotting import _correlation_contrast_table, _correlation_contrast_stats

    tbl, method = _correlation_contrast_table(
        scope, "Volume", ["M1"], grps, "pearsonr", [], 4)
    corr_less, _ = _correlation_contrast_stats(tbl, order, "Control", method, tail="less")
    corr_greater, _ = _correlation_contrast_stats(tbl, order, "Control", method, tail="greater")
    coef_less, _a, _d = _coefficient_contrast_stats(
        scope, "Volume", ["M1"], grps, order, "Control", [], tail="less")
    coef_greater, _a, _d = _coefficient_contrast_stats(
        scope, "Volume", ["M1"], grps, order, "Control", [], tail="greater")

    key = ("M1", "AD")
    # AD is below Control in both parameterisations, so 'less' is the small one
    assert corr_less[key] < 0.05 and corr_greater[key] > 0.5
    assert coef_less[key] < 0.05 and coef_greater[key] > 0.5
    # and the two plots agree on which tail is supported
    assert (corr_less[key] < corr_greater[key]) == (coef_less[key] < coef_greater[key])


def test_reported_difference_matches_plotted_nodes(tmp_path):
    """The side panel's dif= must be commensurate with the plotted node values."""
    exp, _ = _contrast_experiment(tmp_path)
    for value in ("beta", "slope"):
        fig = plot_coefficient_contrast(
            exp, x="Volume", y=["M1"], factor="Diagnosis", reference="Control",
            value=value, save=False)
        text = _summary_text(fig)
        _rb, scope, _nd, _nc, grps = _gc_plot_prepare(
            exp, ["M1"], None, None, "", "conditions", "Diagnosis", None, None)
        table = _coefficient_contrast_table(
            scope, "Volume", ["M1"], grps, [], 4, value=value)
        b = {r["group"]: r["r"] for _, r in table.iterrows()}
        expected = b["AD"] - b["Control"]
        line = [l for l in text.split("\n") if "AD:" in l][0]
        reported = float(line.split("dif=")[1].split(",")[0].split("+/-")[0])
        assert abs(reported - expected) < 5e-3, f"{value}: {reported} vs {expected}"


def test_contrast_skipped_when_a_node_is_missing(tmp_path):
    """No p-value (and so no star) for a comparison whose endpoint has no node."""
    exp, _ = _contrast_experiment(tmp_path)
    _rb, scope, _nd, _nc, grps = _gc_plot_prepare(
        exp, ["M1"], None, None, "", "conditions", "Diagnosis", None, None)
    order = ["Control", "MCI", "AD"]
    table = _coefficient_contrast_table(scope, "Volume", ["M1"], grps, [], 4)
    # min_n above every group size -> every node unusable -> no contrasts at all
    inter_p, acat_p, _d = _coefficient_contrast_stats(
        scope, "Volume", ["M1"], grps, order, "Control", [],
        table=table, min_n=999)
    assert inter_p == {}
    assert all(not np.isfinite(v) for v in acat_p.values())


def _tall_legend_experiment(tmp_path, n_measures):
    """Wide, long-named measures so the legend is both tall AND wide enough to
    actually reach the stats block horizontally."""
    rng = np.random.default_rng(1)
    measures = [f"Iba1_Soma_Branch_Volume_Region{i}_Mean" for i in range(n_measures)]
    rows = []
    for grp, slope in (("Control", 1.0), ("AD", -1.0)):
        vol = np.linspace(10.0, 20.0, 10)
        for i in range(10):
            row = {"Subject": f"{grp}{i}", "Diagnosis": grp, "Volume": float(vol[i])}
            for m in measures:
                row[m] = float(slope * vol[i] + rng.normal(0, 0.6))
            rows.append(row)
    conditions = (ConditionBuilder("Diagnosis")
                  .add("Control", color="black").add("AD", color="orange").build())
    exp = from_dataframe(
        pd.DataFrame(rows), conditions=conditions, name="tall-legend",
        condition_col="Diagnosis", animal_col="Subject",
        fig_path=tmp_path / "f", data_path=tmp_path / "d")
    return exp, measures


@pytest.mark.parametrize("n_measures", [3, 8, 12, 20])
def test_stats_block_never_collides_with_legend_in_saved_output(tmp_path, n_measures):
    """Contract: the side block must not collide with the legend.

    Asserted on the SAVED figure (save_fig resizes to the export canvas, which is
    what the measurement has to match) and as a real 2D box intersection, not a
    position threshold.
    """
    from PyFLASH.utils import save_fig

    exp, measures = _tall_legend_experiment(tmp_path, n_measures)
    fig = plot_coefficient_contrast(
        exp, x="Volume", y=measures, factor="Diagnosis",
        reference="Control", save=False)
    save_fig(fig, tmp_path / "out", f"tall{n_measures}", subfolder=None, verbose=False)
    fig.canvas.draw()

    blocks = [t for t in fig.axes[0].texts if "Test:" in t.get_text()]
    assert len(blocks) == 1, "stats block missing from the figure"
    legend = fig.axes[0].get_legend()
    lb = legend.get_window_extent()
    bb = blocks[0].get_window_extent()
    overlap_x = min(lb.x1, bb.x1) - max(lb.x0, bb.x0)
    overlap_y = min(lb.y1, bb.y1) - max(lb.y0, bb.y0)
    try:
        assert not (overlap_x > 0 and overlap_y > 0), (
            f"{n_measures} measures: block overlaps legend by "
            f"{overlap_x:.1f}x{overlap_y:.1f}px")
        # The block is deliberately allowed outside the physical canvas, so its
        # visibility depends entirely on the tight bbox capturing it. Assert that
        # invariant directly — otherwise a change to the save policy could crop
        # the block out of the file while this test stayed green.
        # get_tightbbox is in inches; window extents are in display pixels.
        tight = fig.get_tightbbox(fig.canvas.get_renderer()).transformed(
            fig.dpi_scale_trans)
        assert tight.x0 <= bb.x0 and tight.x1 >= bb.x1, "block outside tight bbox (x)"
        assert tight.y0 <= bb.y0 and tight.y1 >= bb.y1, "block outside tight bbox (y)"
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)
