"""Tests for PyFLASH.stats_extra (effect sizes, FDR, Dunnett, proportions,
time-course) and PyFLASH.plots_extra (power / PCA / time-course figures)."""

import matplotlib
matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

from PyFLASH import stats_extra as se


# ── effect sizes ─────────────────────────────────────────────────────
def _groups():
    rng = np.random.default_rng(0)
    a = rng.normal(10, 2, 8)
    b = rng.normal(14, 2, 8)
    c = rng.normal(11, 2, 8)
    return a, b, c


def test_hedges_g_sign_and_magnitude():
    a, b, _ = _groups()
    g = se.hedges_g(a, b)
    assert g < 0  # group a is smaller than b
    assert se.interpret_magnitude(g, "d") in {"medium", "large"}


def test_rank_biserial_sign_matches_means():
    a, b, _ = _groups()
    # a < b -> negative, consistent with hedges_g
    assert se.rank_biserial(a, b) < 0
    assert np.isclose(se.rank_biserial(a, b), -se.rank_biserial(b, a))


def test_anova_and_kw_effect_sizes_in_range():
    a, b, c = _groups()
    es = se.anova_effect_sizes([a, b, c])
    assert 0 <= es["eta_squared"] <= 1
    assert es["omega_squared"] <= es["eta_squared"]
    assert 0 <= se.kw_epsilon_squared([a, b, c]) <= 1


def test_effect_ci_brackets_point_estimate():
    a, b, _ = _groups()
    lo, hi = se.effect_ci(a, b, n_resamples=1000)
    g = se.hedges_g(a, b)
    assert lo <= g <= hi


def test_effect_sizes_for_test_parametric_vs_nonparametric():
    a, b, c = _groups()
    para = se.effect_sizes_for_test([a, b, c], "One-Way ANOVA", ["1-2", "2-3"], ci=False)
    assert para["pairwise"][0]["metric"] == "hedges_g"
    assert "omega_squared" in para["overall"]
    nonpara = se.effect_sizes_for_test([a, b, c], "Kruskal-Wallis", ["1-2"], ci=False)
    assert nonpara["pairwise"][0]["metric"] == "rank_biserial_r"
    assert "epsilon_squared" in nonpara["overall"]


def test_effect_sizes_handle_degenerate_groups():
    out = se.effect_sizes_for_test([[1.0], [2.0]], "Independent T-Test", ["1-2"], ci=True)
    assert np.isnan(out["pairwise"][0]["value"])


# ── multiplicity ─────────────────────────────────────────────────────
def test_apply_fdr_global_and_families():
    pvals = {"m1": 0.001, "m2": 0.02, "m3": 0.2, "m4": 0.6}
    out = se.apply_fdr(pvals, method="fdr_bh", alpha=0.05)
    assert set(out["label"]) == set(pvals)
    # monotone: adjusted >= raw
    assert (out["p_adjusted"] >= out["p_value"] - 1e-9).all()
    assert out.loc[out["label"] == "m1", "reject"].iloc[0]

    fams = {"m1": "abeta", "m2": "abeta", "m3": "glia", "m4": "glia"}
    out2 = se.apply_fdr(pvals, families=fams)
    assert set(out2["family"]) == {"abeta", "glia"}


def test_apply_fdr_passes_nan_through():
    out = se.apply_fdr([0.01, float("nan"), 0.04])
    assert np.isnan(out["p_adjusted"]).sum() == 1


# ── Dunnett ──────────────────────────────────────────────────────────
def test_dunnett_vs_control():
    from scipy import stats as sps
    if getattr(sps, "dunnett", None) is None:
        pytest.skip("scipy.stats.dunnett requires SciPy >= 1.11")
    a, b, c = _groups()
    out = se.dunnett_vs_control([a, b, c], labels=["ctrl", "drugA", "drugB"], control="ctrl")
    assert list(out["comparison"]) == ["drugA vs ctrl", "drugB vs ctrl"]
    assert out["p_value"].between(0, 1).all()


# ── proportions ──────────────────────────────────────────────────────
def test_proportion_test_chi2_large_table():
    table = [[40, 60], [30, 70], [55, 45]]  # 3x2
    res = se.proportion_test(table)
    assert res["test"] == "Chi-square"
    assert 0 <= res["p_value"] <= 1


def test_proportion_test_fisher_for_small_2x2():
    table = [[1, 9], [8, 2]]  # small expected counts -> Fisher
    res = se.proportion_test(table)
    assert res["test"] == "Fisher exact"


# ── time-course ──────────────────────────────────────────────────────
def _timecourse_df():
    rows = []
    rng = np.random.default_rng(1)
    tmap = {"WeekTwo": 2, "WeekFour": 4, "WeekEight": 8}
    for gt, base in (("hAPP", 1.0), ("NLGF", 2.0)):
        for animal in range(4):
            for wk, t in tmap.items():
                rows.append({"Genotype": gt, "Time": wk,
                             "AnimalName": f"{gt}_{animal}",
                             "Abeta_Count": base * t + rng.normal(0, 0.5)})
    return pd.DataFrame(rows), tmap


def test_timecourse_auc_one_value_per_animal():
    df, tmap = _timecourse_df()
    out = se.timecourse_auc(df, "Time", "Abeta_Count", group_col="Genotype", time_map=tmap)
    assert len(out) == 8  # 2 genotypes x 4 animals
    assert {"Genotype", "AnimalName", "auc"} <= set(out.columns)


def test_fit_growth_curve_linear_recovers_slope():
    x = np.array([2, 4, 8, 2, 4, 8], float)
    y = 3.0 * x + 1.0
    fit = se.fit_growth_curve(x, y, model="linear")
    assert fit["model"] == "linear"
    assert abs(fit["params"]["slope"]["value"] - 3.0) < 1e-6
    assert fit["r_squared"] > 0.99


def test_fit_growth_curve_auto_picks_a_model():
    df, tmap = _timecourse_df()
    x = df["Time"].map(tmap).to_numpy(float)
    y = df["Abeta_Count"].to_numpy(float)
    fit = se.fit_growth_curve(x, y, model="auto")
    assert fit["model"] in {"linear", "exponential", "logistic"}
    assert callable(fit["predict"])


def test_icc1_high_for_clustered_data():
    rng = np.random.default_rng(2)
    rows = []
    for a, mean in enumerate([5, 15, 25]):
        for _ in range(5):
            rows.append({"AnimalName": f"A{a}", "val": mean + rng.normal(0, 0.5)})
    df = pd.DataFrame(rows)
    assert se.icc1(df, "val") > 0.8


# ── figures (smoke) ──────────────────────────────────────────────────
class _Batch:
    def __init__(self, summary):
        self.summary = summary


def test_plot_power_curve_smoke():
    from PyFLASH import plotting as pe
    fig, data = pe.plot_power_curve(effect_sizes=(0.5, 0.8), n_range=(2, 12),
                                    observed=0.6, observed_n=5, return_data=True)
    assert fig is not None
    assert {"effect_size", "n_per_group", "power"} <= set(data.columns)


def test_plot_marker_pca_smoke():
    from PyFLASH import plotting as pe
    rng = np.random.default_rng(3)
    n = 12
    summary = pd.DataFrame({
        "Condition": (["hAPP"] * 6) + (["NLGF"] * 6),
        "Iba1_Count": rng.normal(10, 2, n),
        "GFAP_IntDen": rng.normal(100, 20, n),
        "Abeta_PercentArea": rng.normal(5, 1, n),
        "CK1d_IntDen": rng.normal(50, 10, n),
    })
    fig, data = pe.plot_marker_pca(_Batch(summary), column_strings=["Count", "IntDen", "PercentArea"],
                                   hue_column="Condition", return_data=True)
    assert fig is not None
    assert list(data["scores"].columns[:2]) == ["PC1", "PC2"]
    assert len(data["explained_variance"]) >= 2


def test_plot_timecourse_smoke():
    from PyFLASH import plotting as pe
    df, tmap = _timecourse_df()
    fig, fits = pe.plot_timecourse(_Batch(df), "Abeta_Count", time_col="Time",
                                   group_col="Genotype", time_map=tmap, return_data=True)
    assert fig is not None
    assert set(fits) == {"hAPP", "NLGF"}
