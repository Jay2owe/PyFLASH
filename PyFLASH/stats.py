"""
Statistical testing and plot annotation utilities.
"""

from __future__ import annotations

import csv
import math
import os
import unicodedata
import warnings
from typing import Iterable

from PyFLASH._logging import logger as _log

import numpy as np
import pandas as pd
import scikit_posthocs as sp
import seaborn as sns
import statsmodels.api as sm
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle
from scipy import stats
from scipy.stats import anderson, f_oneway, kstest, normaltest, ttest_ind_from_stats
from statsmodels.formula.api import ols
import itertools

from PyFLASH.config import apply_matplotlib_fast_path
apply_matplotlib_fast_path()
from PyFLASH.aesthetics import (
    apply_pyflash_figure_geometry,
    get_pyflash_style,
    pyflash_savefig_kwargs,
    pyflash_significance_annotation,
)

try:
    from scipy.stats import tukey_hsd
except ImportError:  # pragma: no cover
    tukey_hsd = None
    from statsmodels.stats.multicomp import pairwise_tukeyhsd

from PyFLASH.utils import save_fig, strip_name

# ── Stats result cache ──────────────────────────────────────────────
# Keyed on (column_name, frozenset(condition_names), specificity_tuple).
# Populated by multipleComparisons when Config.STATS_CACHE is True.
# Call clear_stats_cache() between independent analysis runs.
_stats_cache: dict = {}


def stats_cache_key(column_name, condition_names, specificity, stats_options=None):
    """Build a hashable cache key for a stats computation."""
    conds = frozenset(condition_names) if condition_names else frozenset()
    spec = tuple(specificity) if specificity else ()
    opts = tuple(sorted((stats_options or {}).items()))
    return (str(column_name), conds, spec, opts)


def clear_stats_cache():
    """Reset the stats cache (call between independent analysis runs)."""
    _stats_cache.clear()


def get_annotation(p, ns="ns"):
    """Return significance annotation text for a p-value."""
    return pyflash_significance_annotation(p, ns=ns)


def _is_nonsignificant_annotation(annot):
    try:
        ns = get_pyflash_style("significance_ns")
    except Exception:
        ns = "ns"
    return annot == ns or annot == "ns" or isinstance(annot, (float, int))


def extract_p_and_stats_from_results(result_object, comparisons):
    pvalues = []
    statistics = []
    for comp in comparisons:
        first, second = [int(part) - 1 for part in comp.split("-")]
        pvalues.append(float(result_object.pvalue[first, second]))
        statistics.append(float(result_object.statistic[first, second]))
    return statistics, pvalues


def results_to_excel(results_dict, other, experiment_save_path, save_name,
                     verbose=True, output_dir=None):
    out_dir = output_dir or experiment_save_path
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{save_name}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Statistics Results"])
        writer.writerow(["Test", "Statistic", "P-Values"])
        for test_name, values in results_dict.items():
            if len(values) > 1 and isinstance(values[1], list):
                row = [test_name, values[0], *values[1]]
            else:
                row = [test_name, values[0], values[1]]
            writer.writerow(row)
        writer.writerow([""])
        writer.writerow(["Analysis Summary"])
        for key, value in other.items():
            row = [key, *value] if isinstance(value, list) else [key, value]
            writer.writerow(row)
    if verbose:
        _log.confirm(f"Stats results saved to {out_path}")


def bonferroni_correction(p_value, n_tests):
    return min(float(p_value) * int(n_tests), 1.0)


def sidak_correction(p_value, n_tests):
    return 1 - (1 - float(p_value)) ** int(n_tests)


# ── Correlation-difference inference (independent groups) ────────────────
# Helpers for comparing a correlation coefficient BETWEEN groups (Fisher r-to-z,
# Zou 2007 interval) and for combining several correlated tests into one omnibus
# p-value (Cauchy / ACAT). Generic and pure-numeric; used by
# plotting.plot_correlation_contrast but reusable anywhere.

def _spearman_like(method) -> bool:
    m = str(method).strip().lower()
    return m in ("spearman", "spearmanr", "s")


def fisher_z_se(r, n, method="pearson"):
    """Standard error of the Fisher z-transform of a correlation coefficient.

    Spearman uses the Bonett & Wright (2000) variance ``(1 + r**2 / 2) / (n - 3)``;
    Pearson/Kendall use the classic ``1 / (n - 3)``. Returns NaN for ``n <= 3``.
    """
    n = int(n)
    if n <= 3:
        return float("nan")
    r = float(np.clip(r, -0.999999, 0.999999))
    var = (1.0 + r ** 2 / 2.0) / (n - 3) if _spearman_like(method) else 1.0 / (n - 3)
    return math.sqrt(var)


_TAILS = ("two", "less", "greater", "one")


def _resolve_tail(tail):
    """Normalise a tail/alternative spec to one of ``_TAILS``."""
    t = str(tail if tail is not None else "two").strip().lower()
    aliases = {
        "2": "two", "two-sided": "two", "two_sided": "two", "twosided": "two",
        "both": "two", "ne": "two", "!=": "two",
        "1": "one", "one-sided": "one", "one_sided": "one", "onesided": "one",
        "lt": "less", "<": "less", "smaller": "less",
        "gt": "greater", ">": "greater", "larger": "greater",
    }
    t = aliases.get(t, t)
    if t not in _TAILS:
        raise ValueError(
            f"tail must be one of {_TAILS} (or an alias); got {tail!r}."
        )
    return t


def _tail_p_from_z(z, tail="two"):
    """One- or two-sided normal p-value for a signed z statistic.

    ``'greater'``/``'less'`` test a pre-specified direction for the underlying
    difference; ``'one'`` halves the two-sided p in whichever direction was
    observed and is only valid when that direction was predicted in advance.
    """
    t = _resolve_tail(tail)
    z = float(z)
    if not np.isfinite(z):
        return float("nan")
    if t == "two":
        return float(2.0 * stats.norm.sf(abs(z)))
    if t == "one":
        return float(stats.norm.sf(abs(z)))
    if t == "greater":
        return float(stats.norm.sf(z))
    return float(stats.norm.cdf(z))


def fisher_z_correlation_difference(r1, n1, r2, n2, method="pearson", tail="two"):
    """P-value that two INDEPENDENT correlations (r1, r2) differ.

    Fisher r-to-z test with a method-appropriate SE (see :func:`fisher_z_se`).
    Returns NaN when either sample is too small.

    ``tail`` controls the alternative hypothesis about ``r1 - r2``:
    ``'two'`` (default) for a two-sided test, ``'greater'`` for ``r1 > r2``,
    ``'less'`` for ``r1 < r2``, and ``'one'`` to halve the two-sided p-value in
    the observed direction. A one-sided test is only valid when the direction
    was specified before seeing the data.
    """
    se1 = fisher_z_se(r1, n1, method)
    se2 = fisher_z_se(r2, n2, method)
    if not (np.isfinite(se1) and np.isfinite(se2)):
        return float("nan")
    r1c = float(np.clip(r1, -0.999999, 0.999999))
    r2c = float(np.clip(r2, -0.999999, 0.999999))
    z = (np.arctanh(r1c) - np.arctanh(r2c)) / math.sqrt(se1 ** 2 + se2 ** 2)
    return _tail_p_from_z(z, tail)


def zou_correlation_difference_ci(r1, n1, r2, n2, method="pearson", alpha=0.05):
    """Zou (2007) confidence interval for the difference of two independent
    correlations (``r1 - r2``).

    Returns ``(delta, lower, upper)`` in correlation units. Uses each
    correlation's own asymmetric Fisher-z interval, so it stays accurate for
    large ``|r|`` and small ``n`` where the symmetric variance-sum interval is
    biased. Returns NaNs when either sample is too small.
    """
    se1 = fisher_z_se(r1, n1, method)
    se2 = fisher_z_se(r2, n2, method)
    if not (np.isfinite(se1) and np.isfinite(se2)):
        return float("nan"), float("nan"), float("nan")
    zc = float(stats.norm.ppf(1.0 - alpha / 2.0))
    r1c = float(np.clip(r1, -0.999999, 0.999999))
    r2c = float(np.clip(r2, -0.999999, 0.999999))
    l1, u1 = math.tanh(np.arctanh(r1c) - zc * se1), math.tanh(np.arctanh(r1c) + zc * se1)
    l2, u2 = math.tanh(np.arctanh(r2c) - zc * se2), math.tanh(np.arctanh(r2c) + zc * se2)
    d = r1c - r2c
    lower = d - math.sqrt((r1c - l1) ** 2 + (u2 - r2c) ** 2)
    upper = d + math.sqrt((u1 - r1c) ** 2 + (r2c - l2) ** 2)
    return float(d), float(lower), float(upper)


def cauchy_combination_test(pvalues):
    """Cauchy combination test (ACAT): combine p-values into one omnibus p-value.

    Valid under arbitrary dependence among the individual tests, so it is the
    right tool for combining several correlated measures. Returns NaN when no
    finite p-value is supplied.
    """
    ps = [float(p) for p in pvalues if p is not None and np.isfinite(p)]
    if not ps:
        return float("nan")
    ps = np.clip(np.asarray(ps, dtype=float), 1e-15, 1.0 - 1e-15)
    t = float(np.mean(np.tan((0.5 - ps) * np.pi)))
    return float(0.5 - math.atan(t) / math.pi)


def _design_from_covariates(cov_df, n_rows):
    """Encode covariates into float design columns: numeric as-is, categorical
    one-hot with the first level dropped. Returns an ``(n_rows, k)`` array."""
    if cov_df is None:
        return np.zeros((n_rows, 0), dtype=float)
    parts = []
    for column in cov_df.columns:
        col = cov_df[column]
        num = pd.to_numeric(col, errors="coerce")
        if col.notna().sum() > 0 and int(num.notna().sum()) == int(col.notna().sum()):
            parts.append(num.to_numpy(dtype=float).reshape(-1, 1))
        else:
            dummies = pd.get_dummies(col.astype("object"), drop_first=True, dtype=float)
            if dummies.shape[1]:
                parts.append(dummies.to_numpy(dtype=float))
    if not parts:
        return np.zeros((n_rows, 0), dtype=float)
    return np.column_stack(parts)


def interaction_slope_difference(x, y, group, *, reference=None, covariates=None,
                                 tail="two", standardize=False, rank=False):
    """P-value that the ``y ~ x`` slope differs between two independent groups.

    Fits ``y ~ x + g + x:g`` (plus any covariates as additive terms) by least
    squares over the two groups combined, where ``g`` is an indicator for the
    non-reference group, and tests the ``x:g`` interaction coefficient with a
    t-test. This is the regression counterpart to
    :func:`fisher_z_correlation_difference`: that one compares *correlations*
    (scale-free, estimated within each group), this one compares *slopes* (in
    y-per-x units, pooling the residual variance across both groups). The two
    can disagree when the groups differ in spread.

    Parameters
    ----------
    x, y : array-like
        Predictor and outcome, same length.
    group : array-like
        Group labels, same length as ``x``. Exactly two distinct non-missing
        levels must remain after dropping incomplete rows.
    reference : hashable | None
        Level treated as the baseline. Defaults to the first level encountered.
        The reported estimate is ``slope(other) - slope(reference)``.
    covariates : pandas.DataFrame | None
        Optional additive adjustment columns. Numeric columns are used as-is,
        categorical ones are one-hot encoded. Unlike the partial-correlation
        path, these enter the model rather than residualising the inputs.
    tail : {'two', 'less', 'greater', 'one'}
        Alternative hypothesis about the slope difference. See
        :func:`fisher_z_correlation_difference`.
    standardize : bool
        Z-score ``x`` and ``y`` over the combined sample first, so the estimate
        is a standardized slope difference.
    rank : bool
        Rank-transform ``x`` and ``y`` over the combined sample first, giving a
        Spearman-flavoured (monotonic) version of the test.

    Returns
    -------
    dict
        ``{'p', 'estimate', 'se', 't', 'df', 'n', 'reference', 'other',
        'slope_reference', 'slope_other'}``. Numeric entries are NaN when the
        model cannot be fitted (too few rows, singular design, no variance).
    """
    nan = float("nan")
    empty = {"p": nan, "estimate": nan, "se": nan, "t": nan, "df": 0, "n": 0,
             "reference": None, "other": None,
             "slope_reference": nan, "slope_other": nan}

    frame = pd.DataFrame({"x": pd.to_numeric(pd.Series(x).reset_index(drop=True), errors="coerce"),
                          "y": pd.to_numeric(pd.Series(y).reset_index(drop=True), errors="coerce"),
                          "g": pd.Series(group).reset_index(drop=True)})
    cov = None
    if covariates is not None:
        cov = pd.DataFrame(covariates).reset_index(drop=True)
        if len(cov) != len(frame):
            raise ValueError("interaction_slope_difference: covariates length must match x/y.")
        frame = pd.concat([frame, cov.add_prefix("cov_")], axis=1)
    frame = frame.dropna()
    if frame.empty:
        return empty

    levels = list(dict.fromkeys(frame["g"].astype(object)))
    if len(levels) != 2:
        raise ValueError(
            "interaction_slope_difference: need exactly two groups after dropping "
            f"missing rows; got {len(levels)}."
        )
    ref = levels[0] if reference is None else reference
    if ref not in levels:
        raise ValueError(f"interaction_slope_difference: reference {reference!r} not among {levels}.")
    other = [lv for lv in levels if lv != ref][0]

    xv = frame["x"].to_numpy(dtype=float)
    yv = frame["y"].to_numpy(dtype=float)
    if rank:
        xv = stats.rankdata(xv)
        yv = stats.rankdata(yv)
    if standardize:
        xs, ys = np.std(xv), np.std(yv)
        if xs > 0:
            xv = (xv - np.mean(xv)) / xs
        if ys > 0:
            yv = (yv - np.mean(yv)) / ys
    gv = (frame["g"].astype(object) != ref).to_numpy(dtype=float)

    cov_cols = [c for c in frame.columns if str(c).startswith("cov_")]
    cov_design = _design_from_covariates(frame[cov_cols] if cov_cols else None, len(frame))
    design = np.column_stack([np.ones(len(frame)), xv, gv, xv * gv, cov_design])

    n, k = design.shape
    df_resid = n - k
    if df_resid <= 0 or np.std(xv) == 0 or np.std(yv) == 0:
        return {**empty, "n": int(n), "reference": ref, "other": other}
    try:
        xtx_inv = np.linalg.pinv(design.T @ design)
        beta = xtx_inv @ design.T @ yv
        resid = yv - design @ beta
        sigma2 = float(resid @ resid) / df_resid
        se = math.sqrt(max(sigma2 * float(xtx_inv[3, 3]), 0.0))
    except (np.linalg.LinAlgError, ValueError):
        return {**empty, "n": int(n), "reference": ref, "other": other}
    if not np.isfinite(se) or se == 0:
        return {**empty, "n": int(n), "reference": ref, "other": other}

    t_stat = float(beta[3]) / se
    t = _resolve_tail(tail)
    if t == "two":
        p = float(2.0 * stats.t.sf(abs(t_stat), df_resid))
    elif t == "one":
        p = float(stats.t.sf(abs(t_stat), df_resid))
    elif t == "greater":
        p = float(stats.t.sf(t_stat, df_resid))
    else:
        p = float(stats.t.cdf(t_stat, df_resid))

    return {"p": p, "estimate": float(beta[3]), "se": float(se), "t": t_stat,
            "df": int(df_resid), "n": int(n), "reference": ref, "other": other,
            "slope_reference": float(beta[1]),
            "slope_other": float(beta[1] + beta[3])}


def modified_anderson(data):
    ad_stat, _, _ = anderson(data)
    ad_stat = ad_stat * (1 + (0.75 / 50) + 2.25 / (50**2))
    if ad_stat >= 0.6:
        p = math.exp(1.2937 - 5.709 * ad_stat - 0.0186 * (ad_stat**2))
    elif ad_stat >= 0.34:
        p = math.exp(0.9177 - 4.279 * ad_stat - 1.38 * (ad_stat**2))
    elif ad_stat > 0.2:
        p = 1 - math.exp(-8.318 + 42.796 * ad_stat - 59.938 * (ad_stat**2))
    else:
        p = 1 - math.exp(-13.436 + 101.14 * ad_stat - 223.73 * (ad_stat**2))
    return ad_stat, p


def _coerce_groups(df_list: Iterable) -> list[pd.Series]:
    groups = []
    for g in df_list:
        s = pd.to_numeric(pd.Series(g), errors="coerce").dropna()
        if not s.empty:
            groups.append(s)
    return groups


def _normalize_group_stats_test(value):
    key = _normalize_kw_correction_key("auto" if value is None else value)
    aliases = {
        "": "auto",
        "default": "auto",
        "automatic": "auto",
        "auto": "auto",
        "t": "auto_t",
        "ttest": "auto_t",
        "t_test": "auto_t",
        "independent_t": "auto_t",
        "independent_t_test": "auto_t",
        "student": "student_t",
        "students": "student_t",
        "student_t": "student_t",
        "students_t": "student_t",
        "student_t_test": "student_t",
        "welch": "welch_t",
        "welchs": "welch_t",
        "welch_t": "welch_t",
        "welchs_t": "welch_t",
        "welch_t_test": "welch_t",
        "mann_whitney": "mannwhitney",
        "mann_whitney_u": "mannwhitney",
        "mwu": "mannwhitney",
        "wilcoxon_rank_sum": "mannwhitney",
        "wilcoxon_rank_sum_test": "mannwhitney",
        "anova": "anova",
        "one_way": "anova",
        "one_way_anova": "anova",
        "owa": "anova",
        "welch_anova": "welch_anova",
        "welchs_anova": "welch_anova",
        "welch_one_way": "welch_anova",
        "welch_one_way_anova": "welch_anova",
        "kruskal": "kruskal",
        "kruskal_wallis": "kruskal",
        "kw": "kruskal",
        "two_way": "two_way",
        "two_way_anova": "two_way",
        "twa": "two_way",
        "linear": "linear_model",
        "linear_model": "linear_model",
        "lm": "linear_model",
        "ols": "linear_model",
    }
    if key in aliases:
        return aliases[key]
    valid = (
        "'auto', 'student_t', 'welch_t', 'mannwhitney', 'anova', "
        "'welch_anova', 'kruskal', 'two_way', or 'linear_model'"
    )
    raise ValueError(f"stats_test must be one of: {valid}")


def _normalize_variance_test(value):
    if value is None or value is False:
        return "none", "Not checked"
    key = _normalize_kw_correction_key(value)
    if key in _KW_UNCORRECTED_ALIASES or key in {"skip", "disabled"}:
        return "none", "Not checked"
    if key in {"auto", "default", "brown_forsythe", "brown_forsyth", "bf",
               "levene_median", "median"}:
        return "brown_forsythe", "Brown-Forsythe"
    if key in {"levene", "levene_mean", "mean"}:
        return "levene", "Levene"
    if key in {"levene_trimmed", "trimmed", "trimmed_mean"}:
        return "levene_trimmed", "Levene trimmed"
    if key in {"bartlett", "bartletts"}:
        return "bartlett", "Bartlett"
    if key in {"fligner", "fligner_killeen", "fligner_killeen_test"}:
        return "fligner", "Fligner-Killeen"
    valid = (
        "'Brown-Forsythe', 'Levene', 'Levene trimmed', 'Bartlett', "
        "'Fligner-Killeen', or 'none'"
    )
    raise ValueError(f"variance_test must be one of: {valid}")


def test_equal_variance(df_list, results_dict=None, *, method="brown-forsythe", alpha=0.05):
    """Run a k-group equal-variance screen used by the auto stats selector.

    Brown-Forsythe (Levene with median centre) is the default because it is more
    robust than Bartlett when the normality screen is imperfect.
    """
    groups = _coerce_groups(df_list)
    results_dict = results_dict if results_dict is not None else {}
    method_key, label = _normalize_variance_test(method)
    out = {
        "method": label,
        "statistic": float("nan"),
        "pvalue": float("nan"),
        "equal_var": None,
        "alpha": float(alpha),
    }
    if method_key == "none":
        out["equal_var"] = True
        results_dict["Variance check"] = [label, np.nan]
        return out
    if len(groups) < 2 or any(len(g) < 2 for g in groups):
        results_dict[f"Variance {label}"] = [float("nan"), float("nan")]
        results_dict["Equal variance"] = ["insufficient data", np.nan]
        return out
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if method_key == "brown_forsythe":
                statistic, pvalue = stats.levene(*groups, center="median")
            elif method_key == "levene":
                statistic, pvalue = stats.levene(*groups, center="mean")
            elif method_key == "levene_trimmed":
                statistic, pvalue = stats.levene(*groups, center="trimmed")
            elif method_key == "bartlett":
                statistic, pvalue = stats.bartlett(*groups)
            elif method_key == "fligner":
                statistic, pvalue = stats.fligner(*groups)
            else:  # pragma: no cover - guarded by normalizer
                statistic, pvalue = float("nan"), float("nan")
        out["statistic"] = float(statistic)
        out["pvalue"] = float(pvalue)
        out["equal_var"] = bool(np.isfinite(pvalue) and float(pvalue) >= float(alpha))
    except Exception as exc:
        results_dict["Variance_error"] = [str(exc), np.nan]
    results_dict[f"Variance {label}"] = [out["statistic"], out["pvalue"]]
    results_dict["Equal variance"] = [out["equal_var"], out["pvalue"]]
    return out


def _run_tukey(*groups):
    if tukey_hsd is not None:
        return tukey_hsd(*groups)

    values = np.concatenate([np.asarray(g, dtype=float) for g in groups])
    labels = np.concatenate([[i] * len(g) for i, g in enumerate(groups)])
    result = pairwise_tukeyhsd(values, labels)
    n = len(groups)
    stat = np.zeros((n, n), dtype=float)
    pval = np.ones((n, n), dtype=float)
    idx = 0
    for i in range(n):
        for j in range(i + 1, n):
            stat[i, j] = stat[j, i] = float(result.meandiffs[idx])
            pval[i, j] = pval[j, i] = float(result.pvalues[idx])
            idx += 1

    class TukeyResult:
        statistic = stat
        pvalue = pval

    return TukeyResult()


def runITTest(
    group1,
    group2,
    results_dict,
    ns="ns",
    *,
    equal_var=None,
    variance_test="brown-forsythe",
    variance_alpha=0.05,
):
    g1 = pd.to_numeric(pd.Series(group1), errors="coerce").dropna()
    g2 = pd.to_numeric(pd.Series(group2), errors="coerce").dropna()
    n1, n2 = len(g1), len(g2)
    if n1 < 2 or n2 < 2:
        return [1.0], [ns], (float("nan"), 1.0), results_dict, "Independent T Test"

    mean1, mean2 = g1.mean(), g2.mean()
    var1, var2 = np.var(g1, ddof=1), np.var(g2, ddof=1)
    std1, std2 = np.sqrt(var1), np.sqrt(var2)
    if equal_var is None:
        variance = test_equal_variance(
            [g1, g2],
            results_dict,
            method=variance_test,
            alpha=variance_alpha,
        )
        equal_var = variance.get("equal_var")
    if equal_var is None:
        # If the variance screen is indeterminate, Welch is the safer default.
        equal_var = False
    equal_var = bool(equal_var)
    statistic, pvalue = ttest_ind_from_stats(
        mean1=mean1,
        std1=std1,
        nobs1=n1,
        mean2=mean2,
        std2=std2,
        nobs2=n2,
        equal_var=equal_var,
    )
    method_label = "Student's t-test" if equal_var else "Welch's t-test"
    method_key = "Student's T Test" if equal_var else "Welch's T Test"
    results_dict[method_key] = [float(statistic), float(pvalue)]
    # Legacy key kept for old report/pipeline parsers.
    results_dict["Independent T Test"] = [float(statistic), float(pvalue)]
    annotation = [get_annotation(pvalue, ns)]
    return [float(pvalue)], annotation, (float(statistic), float(pvalue)), results_dict, method_label


def mwu_multiple_comparisons(df_list, comparisons, results_dict, ns="ns"):
    groups = _coerce_groups(df_list)
    if len(groups) < 2:
        return [], [], ([], []), results_dict, "Mann-Whitney U"
    statistics = []
    pvalues = []
    for comparison in comparisons:
        first, second = [int(part) - 1 for part in comparison.split("-")]
        statistic, pvalue = stats.mannwhitneyu(groups[first], groups[second])
        statistics.append(float(statistic))
        pvalues.append(float(pvalue))
    results_dict["Mann-Whitney U"] = [statistics, pvalues]
    annotations = [get_annotation(pvalue, ns) for pvalue in pvalues]
    return pvalues, annotations, (statistics, pvalues), results_dict, "Mann-Whitney U"


def _extract_posthoc_matrix_pvalues(matrix, comparisons):
    pvalues = []
    for comp in comparisons:
        first, second = [int(part) - 1 for part in comp.split("-")]
        pvalues.append(float(matrix.iloc[first, second]))
    return pvalues


def _run_fisher_lsd(groups, comparisons):
    n_groups = len(groups)
    n_total = sum(len(g) for g in groups)
    df_error = n_total - n_groups
    if df_error <= 0:
        return [float("nan")] * len(comparisons), [float("nan")] * len(comparisons)

    ss_error = 0.0
    means = []
    ns = []
    for group in groups:
        arr = np.asarray(group, dtype=float)
        means.append(float(np.mean(arr)))
        ns.append(int(len(arr)))
        ss_error += float(np.sum((arr - np.mean(arr)) ** 2))
    mse = ss_error / df_error if df_error > 0 else float("nan")

    statistics = []
    pvalues = []
    for comp in comparisons:
        first, second = [int(part) - 1 for part in comp.split("-")]
        se = math.sqrt(mse * ((1.0 / ns[first]) + (1.0 / ns[second]))) if mse >= 0 else float("nan")
        if not np.isfinite(se) or se == 0:
            statistic = float("nan")
            pvalue = float("nan")
        else:
            statistic = (means[first] - means[second]) / se
            pvalue = 2.0 * stats.t.sf(abs(statistic), df_error)
        statistics.append(float(statistic))
        pvalues.append(float(pvalue))
    return statistics, pvalues


def _infer_dunnett_control(comparisons, n_groups):
    parsed = []
    for comp in comparisons:
        first, second = [int(part) - 1 for part in comp.split("-")]
        if first < 0 or second < 0 or first >= n_groups or second >= n_groups:
            raise ValueError(f"Comparison {comp!r} is outside the available groups.")
        parsed.append({first, second})
    if not parsed:
        raise ValueError("Dunnett requires comparisons against one control group.")

    common = set.intersection(*parsed)
    if len(common) == 1:
        return common.pop()
    raise ValueError(
        "Dunnett requires comparisons that all share one control group, "
        'for example ["1-2", "1-3"].'
    )


def _run_dunnett(groups, comparisons):
    control_idx = _infer_dunnett_control(comparisons, len(groups))
    sample_indices = [idx for idx in range(len(groups)) if idx != control_idx]
    if not sample_indices:
        return [float("nan")] * len(comparisons), [float("nan")] * len(comparisons)

    result = stats.dunnett(
        *[groups[idx] for idx in sample_indices],
        control=groups[control_idx],
        random_state=0,
    )
    stat_by_group = {
        idx: float(result.statistic[pos])
        for pos, idx in enumerate(sample_indices)
    }
    p_by_group = {
        idx: float(result.pvalue[pos])
        for pos, idx in enumerate(sample_indices)
    }

    statistics = []
    pvalues = []
    for comp in comparisons:
        first, second = [int(part) - 1 for part in comp.split("-")]
        other = second if first == control_idx else first if second == control_idx else None
        statistics.append(stat_by_group.get(other, float("nan")))
        pvalues.append(p_by_group.get(other, float("nan")))
    return statistics, pvalues


def _normalize_owa_posthoc(posthoc):
    if posthoc is None:
        return "tukey", "Tukey", None

    key = _normalize_kw_correction_key(posthoc)
    if key in {"", "auto", "default", "conover", "conover_test", "dunn", "dunns",
               "dunns_test", "dunn_test", "nemenyi", "nemenyi_test", "dscf",
               "dwass_steel_critchlow_fligner"}:
        return "tukey", "Tukey", None
    if key in {"tukey", "tukey_hsd", "hsd"}:
        return "tukey", "Tukey", None
    if key in {"dunnett", "dunnetts", "dunnett_test", "dunnetts_test"}:
        return "dunnett", "Dunnett", None
    if key in {"fisher_lsd", "fishers_lsd", "fisher", "lsd",
               "least_significant_difference"}:
        return "fisher_lsd", "Fisher LSD", None
    if key in {"scheffe", "scheffes", "scheffe_test", "scheffes_test"}:
        return "scheffe", "Scheffe", None
    if key in {"tamhane", "tamhanes", "tamhane_t2", "tamhanes_t2"}:
        return "tamhane", "Tamhane T2", None
    if key in {"bonferroni_dunn", "dunn_bonferroni"}:
        return "lsd_adjusted", "Bonferroni", "bonferroni"
    if key in {"sidak_bonferroni", "bonferroni_sidak"}:
        return "lsd_adjusted", "Sidak", "sidak"
    if key in _KW_CORRECTION_ALIASES:
        method, label = _KW_CORRECTION_ALIASES[key]
        return "lsd_adjusted", label, method
    if key in _KW_UNCORRECTED_ALIASES:
        return "fisher_lsd", "Fisher LSD", None
    valid = (
        "'Tukey', 'Dunnett', 'Fisher LSD', 'Bonferroni', 'Sidak', "
        "'Holm-Sidak', 'Scheffe', or 'Tamhane T2'"
    )
    raise ValueError(f"posthoc for one-way ANOVA must be one of: {valid}")


def _normalize_lsd_correction(posthoc_correction, n_tests):
    key = "auto" if posthoc_correction is None else _normalize_kw_correction_key(posthoc_correction)
    if key == "auto":
        return "none", "Uncorrected"
    return _normalize_kw_correction(posthoc_correction, n_tests)


def runOWA(df_list, comparisons, results_dict, ns="ns", posthoc="Tukey", posthoc_correction="auto"):
    groups = _coerce_groups(df_list)
    posthoc_method, posthoc_label, embedded_correction = _normalize_owa_posthoc(posthoc)
    if len(groups) < 2 or any(len(g) <= 1 for g in groups):
        return [], [], (float("nan"), float("nan")), results_dict, posthoc_label
    f_stat, pvalue = f_oneway(*groups)
    results_dict["OWA"] = [float(f_stat), float(pvalue)]
    try:
        if posthoc_method == "tukey":
            tukey_result = _run_tukey(*groups)
            statistics, pvalues = extract_p_and_stats_from_results(tukey_result, comparisons)
        elif posthoc_method == "dunnett":
            statistics, pvalues = _run_dunnett(groups, comparisons)
        elif posthoc_method == "scheffe":
            pvalues = _extract_posthoc_matrix_pvalues(sp.posthoc_scheffe(groups), comparisons)
            statistics = [1] * len(pvalues)
        elif posthoc_method == "tamhane":
            pvalues = _extract_posthoc_matrix_pvalues(sp.posthoc_tamhane(groups), comparisons)
            statistics = [1] * len(pvalues)
        else:
            statistics, pvalues = _run_fisher_lsd(groups, comparisons)
            if embedded_correction is None:
                method, correction = _normalize_lsd_correction(posthoc_correction, len(comparisons))
                if correction != "Uncorrected":
                    posthoc_label = f"Fisher LSD {correction}"
            else:
                method = embedded_correction
            pvalues = _apply_kw_correction(pvalues, method)
    except ValueError:
        if posthoc_method == "tukey":
            return [], [], (float(f_stat), float(pvalue)), results_dict, posthoc_label
        raise
    results_dict[posthoc_label.replace(" ", "-")] = [statistics, pvalues]
    annotations = [get_annotation(p, ns) for p in pvalues]
    return pvalues, annotations, (float(f_stat), float(pvalue)), results_dict, posthoc_label


def _normalize_welch_owa_posthoc(posthoc):
    key = _normalize_kw_correction_key("auto" if posthoc is None else posthoc)
    if key in {"", "auto", "default", "tamhane", "tamhanes", "tamhane_t2",
               "tamhanes_t2"}:
        return "tamhane", "Tamhane T2"
    if key in {"games_howell", "games_howells", "gh"}:
        return "games_howell", "Games-Howell"
    valid = "'Tamhane T2' or 'Games-Howell'"
    raise ValueError(f"posthoc for Welch ANOVA must be one of: {valid}")


def _run_games_howell(groups, comparisons):
    statistics = []
    pvalues = []
    k = len(groups)
    for comp in comparisons:
        first, second = [int(part) - 1 for part in comp.split("-")]
        a = pd.to_numeric(pd.Series(groups[first]), errors="coerce").dropna().astype(float)
        b = pd.to_numeric(pd.Series(groups[second]), errors="coerce").dropna().astype(float)
        if len(a) < 2 or len(b) < 2:
            statistics.append(float("nan"))
            pvalues.append(float("nan"))
            continue
        mean_diff = float(a.mean() - b.mean())
        va = float(a.var(ddof=1))
        vb = float(b.var(ddof=1))
        na = float(len(a))
        nb = float(len(b))
        se2 = va / na + vb / nb
        if not np.isfinite(se2) or se2 <= 0:
            statistics.append(float("nan"))
            pvalues.append(float("nan"))
            continue
        denom = ((va / na) ** 2 / (na - 1.0)) + ((vb / nb) ** 2 / (nb - 1.0))
        df = (se2 ** 2 / denom) if denom > 0 else np.inf
        q_stat = abs(mean_diff) / math.sqrt(0.5 * se2)
        try:
            pvalue = float(stats.studentized_range.sf(q_stat, k, df))
        except Exception:
            pvalue = float("nan")
        statistics.append(float(q_stat))
        pvalues.append(pvalue)
    return statistics, pvalues


def runWelchOWA(df_list, comparisons, results_dict, ns="ns", posthoc="Tamhane T2"):
    groups = _coerce_groups(df_list)
    posthoc_method, posthoc_label = _normalize_welch_owa_posthoc(posthoc)
    if len(groups) < 2 or any(len(g) <= 1 for g in groups):
        return [], [], (float("nan"), float("nan")), results_dict, posthoc_label
    try:
        from statsmodels.stats.oneway import anova_oneway

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = anova_oneway(groups, use_var="unequal", welch_correction=True)
        f_stat = float(result.statistic)
        pvalue = float(result.pvalue)
    except Exception as exc:
        results_dict["Welch_ANOVA_error"] = [str(exc), np.nan]
        return [], [], (float("nan"), float("nan")), results_dict, posthoc_label
    results_dict["Welch ANOVA"] = [f_stat, pvalue]
    try:
        if posthoc_method == "games_howell":
            statistics, pvalues = _run_games_howell(groups, comparisons)
        else:
            pvalues = _extract_posthoc_matrix_pvalues(sp.posthoc_tamhane(groups), comparisons)
            statistics = [1] * len(pvalues)
    except Exception as exc:
        results_dict["Welch_posthoc_error"] = [str(exc), np.nan]
        return [], [], (f_stat, pvalue), results_dict, f"{posthoc_label} (error: {exc})"
    results_dict[posthoc_label.replace(" ", "-")] = [statistics, pvalues]
    annotations = [get_annotation(p, ns) for p in pvalues]
    return pvalues, annotations, (f_stat, pvalue), results_dict, posthoc_label


def _normalize_kw_posthoc(posthoc):
    name = _normalize_kw_correction_key(posthoc or "Conover")
    if name in {"dunn", "dunns", "dunns_test", "dunn_test"}:
        return "Dunn"
    if name in {"conover", "conover_test"}:
        return "Conover"
    if name in {"nemenyi", "nemenyi_test"}:
        return "Nemenyi"
    if name in {"dscf", "dwass_steel_critchlow_fligner", "dwass_steel",
                "steel_dwass", "dwass_steel_critchlow_flinger"}:
        return "DSCF"
    raise ValueError("posthoc must be 'Conover', 'Dunn', 'Nemenyi', or 'DSCF'")


_KW_CORRECTION_ALIASES = {
    "bonferroni": ("bonferroni", "Bonferroni"),
    "bonf": ("bonferroni", "Bonferroni"),
    "corrected": ("bonferroni", "Bonferroni"),
    "correction": ("bonferroni", "Bonferroni"),
    "adjusted": ("bonferroni", "Bonferroni"),
    "adjust": ("bonferroni", "Bonferroni"),
    "true": ("bonferroni", "Bonferroni"),
    "yes": ("bonferroni", "Bonferroni"),
    "y": ("bonferroni", "Bonferroni"),
    "on": ("bonferroni", "Bonferroni"),
    "1": ("bonferroni", "Bonferroni"),
    "sidak": ("sidak", "Sidak"),
    "sidak_correction": ("sidak", "Sidak"),
    "holm": ("holm", "Holm"),
    "holm_bonferroni": ("holm", "Holm"),
    "holm_sidak": ("holm-sidak", "Holm-Sidak"),
    "hs": ("holm-sidak", "Holm-Sidak"),
    "simes_hochberg": ("simes-hochberg", "Simes-Hochberg"),
    "hochberg": ("simes-hochberg", "Simes-Hochberg"),
    "sh": ("simes-hochberg", "Simes-Hochberg"),
    "hommel": ("hommel", "Hommel"),
    "fdr": ("fdr_bh", "FDR-BH"),
    "fdr_bh": ("fdr_bh", "FDR-BH"),
    "bh": ("fdr_bh", "FDR-BH"),
    "benjamini_hochberg": ("fdr_bh", "FDR-BH"),
    "benjaminihochberg": ("fdr_bh", "FDR-BH"),
    "fdr_by": ("fdr_by", "FDR-BY"),
    "by": ("fdr_by", "FDR-BY"),
    "benjamini_yekutieli": ("fdr_by", "FDR-BY"),
    "benjaminiyekutieli": ("fdr_by", "FDR-BY"),
    "fdr_tsbh": ("fdr_tsbh", "FDR-TSBH"),
    "tsbh": ("fdr_tsbh", "FDR-TSBH"),
    "two_stage_bh": ("fdr_tsbh", "FDR-TSBH"),
    "two_stage_fdr_bh": ("fdr_tsbh", "FDR-TSBH"),
    "fdr_tsbky": ("fdr_tsbky", "FDR-TSBKY"),
    "tsbky": ("fdr_tsbky", "FDR-TSBKY"),
    "two_stage_bky": ("fdr_tsbky", "FDR-TSBKY"),
    "two_stage_fdr_bky": ("fdr_tsbky", "FDR-TSBKY"),
}

_KW_UNCORRECTED_ALIASES = {
    "",
    "none",
    "raw",
    "p",
    "uncorrected",
    "unadjusted",
    "no_correction",
    "no_adjustment",
    "false",
    "no",
    "n",
    "off",
    "0",
}


def _normalize_kw_correction_key(value):
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.strip().lower().replace("'", "")
    for old, new in (("&", " "), ("/", " "), ("+", " "), ("-", "_"), (" ", "_")):
        text = text.replace(old, new)
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def _normalize_kw_correction(posthoc_correction, n_tests):
    if posthoc_correction is None:
        key = "auto"
    elif isinstance(posthoc_correction, (bool, np.bool_)):
        key = "true" if bool(posthoc_correction) else "false"
    else:
        key = _normalize_kw_correction_key(posthoc_correction)

    if key == "auto":
        return ("bonferroni", "Bonferroni") if n_tests > 3 else ("none", "Uncorrected")
    if key in _KW_UNCORRECTED_ALIASES:
        return "none", "Uncorrected"
    if key in _KW_CORRECTION_ALIASES:
        return _KW_CORRECTION_ALIASES[key]

    valid = (
        "'auto', 'Bonferroni', 'Sidak', 'Holm', 'Holm-Sidak', "
        "'Simes-Hochberg', 'Hommel', 'FDR-BH', 'FDR-BY', "
        "'FDR-TSBH', 'FDR-TSBKY', 'Uncorrected', booleans, "
        "or common yes/no synonyms"
    )
    raise ValueError(f"posthoc_correction must be one of: {valid}")


def _apply_kw_correction(pvalues, method):
    values = [float(p) for p in pvalues]
    if method == "none":
        return values
    if method == "bonferroni":
        return [bonferroni_correction(p, len(values)) for p in values]
    if method == "sidak":
        return [sidak_correction(p, len(values)) for p in values]

    from PyFLASH.stats_extra import adjust_pvalues
    _, adjusted = adjust_pvalues(values, method=method)
    return [float(p) for p in adjusted]


def runKW(df_list, comparisons, results_dict, posthoc="Conover", ns="ns", posthoc_correction="auto"):
    groups = _coerce_groups(df_list)
    posthoc = _normalize_kw_posthoc(posthoc)
    if len(groups) < 2:
        return [], [], (float("nan"), float("nan")), results_dict, posthoc
    try:
        kw_statistic, kw_pvalue = stats.kruskal(*groups)
    except ValueError as e:
        msg = str(e)
        results_dict["KW_error"] = [msg, np.nan]
        return [], [], (float("nan"), float("nan")), results_dict, f"{posthoc} (error: {msg})"
    results_dict["KW"] = [float(kw_statistic), float(kw_pvalue)]
    n_tests = len(comparisons)

    if posthoc in {"Nemenyi", "DSCF"}:
        try:
            matrix = sp.posthoc_nemenyi(groups) if posthoc == "Nemenyi" else sp.posthoc_dscf(groups)
            pvalues = _extract_posthoc_matrix_pvalues(matrix, comparisons)
        except Exception as e:
            msg = str(e)
            results_dict["Posthoc_error"] = [msg, np.nan]
            return [], [], (float(kw_statistic), float(kw_pvalue)), results_dict, f"{posthoc} (error: {msg})"
        results_dict[posthoc] = [1, pvalues]
        annotations = [get_annotation(result, ns) for result in pvalues]
        return pvalues, annotations, (float(kw_statistic), float(kw_pvalue)), results_dict, posthoc

    correction_method, correction = _normalize_kw_correction(posthoc_correction, n_tests)

    try:
        dunn_df = sp.posthoc_dunn(groups)
        conover_df = sp.posthoc_conover(groups)
    except Exception as e:
        msg = str(e)
        results_dict["Posthoc_error"] = [msg, np.nan]
        return [], [], (float(kw_statistic), float(kw_pvalue)), results_dict, f"{posthoc} (error: {msg})"
    dunn_uncorrected = []
    conover_uncorrected = []

    for comp in comparisons:
        first, second = [int(part) - 1 for part in comp.split("-")]
        dunn_p = float(dunn_df.iloc[first, second])
        conover_p = float(conover_df.iloc[first, second])
        dunn_uncorrected.append(dunn_p)
        conover_uncorrected.append(conover_p)

    dunn_bonferroni = _apply_kw_correction(dunn_uncorrected, "bonferroni")
    conover_bonferroni = _apply_kw_correction(conover_uncorrected, "bonferroni")

    results_dict["Conover-Bonferroni"] = [1, conover_bonferroni]
    results_dict["Conover-Uncorrected"] = [1, conover_uncorrected]
    results_dict["Dunn-Bonferroni"] = [1, dunn_bonferroni]
    results_dict["Dunn-Uncorrected"] = [1, dunn_uncorrected]

    conover_by_correction = {
        "Bonferroni": conover_bonferroni,
        "Uncorrected": conover_uncorrected,
    }
    dunn_by_correction = {
        "Bonferroni": dunn_bonferroni,
        "Uncorrected": dunn_uncorrected,
    }
    if correction not in conover_by_correction:
        conover_by_correction[correction] = _apply_kw_correction(conover_uncorrected, correction_method)
        dunn_by_correction[correction] = _apply_kw_correction(dunn_uncorrected, correction_method)
        results_dict[f"Conover-{correction}"] = [1, conover_by_correction[correction]]
        results_dict[f"Dunn-{correction}"] = [1, dunn_by_correction[correction]]

    conover = conover_by_correction[correction]
    dunn = dunn_by_correction[correction]
    posthoc_result = conover if posthoc == "Conover" else dunn
    posthoc_string = f"{posthoc} {correction}"
    annotations = [get_annotation(result, ns) for result in posthoc_result]
    return posthoc_result, annotations, (float(kw_statistic), float(kw_pvalue)), results_dict, posthoc_string


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    try:
        return [str(v) for v in value]
    except TypeError:
        return [str(value)]


def _linear_model_covariate_frame(df, covariates, categorical_covariates):
    covariates = _as_list(covariates)
    categorical = {str(c) for c in _as_list(categorical_covariates)}
    out = {}
    terms = []
    reference_values = {}
    raw_to_internal = {}
    for i, cov in enumerate(covariates):
        if cov not in df.columns:
            raise ValueError(f"Linear-model covariate {cov!r} was not found.")
        internal = f"__cov_{i}__"
        raw_to_internal[cov] = internal
        if cov in categorical:
            series = df[cov].astype("category")
            out[internal] = series
            mode = series.dropna().mode()
            reference_values[internal] = mode.iloc[0] if len(mode) else np.nan
            terms.append(f"C({internal})")
        else:
            series = pd.to_numeric(df[cov], errors="coerce")
            out[internal] = series
            reference_values[internal] = float(series.mean()) if series.notna().any() else np.nan
            terms.append(internal)
    return out, terms, reference_values, raw_to_internal


def runLinearModel(
    model_df,
    outcome_col,
    group_col,
    comparisons,
    results_dict,
    ns="ns",
    *,
    covariates=None,
    categorical_covariates=None,
    posthoc_correction="auto",
    cov_type="HC3",
    cov_kwds=None,
    group_order=None,
):
    """Group effect from an OLS model, with pairwise adjusted group contrasts."""
    if model_df is None:
        raise ValueError("Linear-model stats need model_df from the plotting wrapper.")
    if outcome_col not in model_df.columns:
        raise ValueError(f"Linear-model outcome column {outcome_col!r} was not found.")
    if group_col not in model_df.columns:
        raise ValueError(f"Linear-model group column {group_col!r} was not found.")

    df = pd.DataFrame(model_df).copy()
    order = [str(g) for g in (group_order or df[group_col].dropna().astype(str).unique().tolist())]
    if len(order) < 2:
        return [], [], (float("nan"), float("nan")), results_dict, "model contrasts"

    model_data = pd.DataFrame({
        "__outcome__": pd.to_numeric(df[outcome_col], errors="coerce"),
        "__group__": pd.Categorical(df[group_col].astype(str), categories=order),
    })
    cov_frame, cov_terms, reference_values, _ = _linear_model_covariate_frame(
        df,
        covariates,
        categorical_covariates,
    )
    for key, values in cov_frame.items():
        model_data[key] = values
    model_data = model_data.dropna(subset=["__outcome__", "__group__", *cov_frame.keys()])
    if model_data["__group__"].nunique(dropna=True) < 2:
        return [], [], (float("nan"), float("nan")), results_dict, "model contrasts"

    formula = "__outcome__ ~ C(__group__)"
    if cov_terms:
        formula += " + " + " + ".join(cov_terms)
    fit_kwargs = {}
    if cov_type is not None:
        fit_kwargs["cov_type"] = str(cov_type)
        if cov_kwds:
            fit_kwargs["cov_kwds"] = dict(cov_kwds)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = ols(formula, data=model_data).fit(**fit_kwargs)

    params = list(fitted.params.index)
    group_terms = [name for name in params if name.startswith("C(__group__)")]
    overall_stat = float("nan")
    overall_p = float("nan")
    if group_terms:
        contrast = np.zeros((len(group_terms), len(params)), dtype=float)
        for row_idx, name in enumerate(group_terms):
            contrast[row_idx, params.index(name)] = 1.0
        try:
            wald = fitted.wald_test(contrast, scalar=True)
            overall_stat = float(np.asarray(wald.statistic).squeeze())
            overall_p = float(np.asarray(wald.pvalue).squeeze())
        except Exception as exc:
            results_dict["Linear_Model_overall_error"] = [str(exc), np.nan]
    results_dict["Linear Model"] = [overall_stat, overall_p]

    try:
        from patsy import build_design_matrices

        pred_rows = []
        for group in order:
            row = {"__group__": group}
            row.update(reference_values)
            pred_rows.append(row)
        pred_df = pd.DataFrame(pred_rows)
        pred_df["__group__"] = pd.Categorical(pred_df["__group__"], categories=order)
        design = build_design_matrices(
            [fitted.model.data.design_info],
            pred_df,
            return_type="dataframe",
        )[0]
        exog_by_group = {
            order[i]: np.asarray(design.iloc[i, :], dtype=float)
            for i in range(len(order))
        }
        beta = np.asarray(fitted.params, dtype=float)
        cov = np.asarray(fitted.cov_params(), dtype=float)
    except Exception as exc:
        results_dict["Linear_Model_prediction_error"] = [str(exc), np.nan]
        return [], [], (overall_stat, overall_p), results_dict, "model contrasts"

    statistics = []
    raw_pvalues = []
    for comparison in comparisons:
        first, second = [int(part) - 1 for part in comparison.split("-")]
        if not (0 <= first < len(order) and 0 <= second < len(order)):
            statistics.append(float("nan"))
            raw_pvalues.append(float("nan"))
            continue
        contrast = exog_by_group[order[second]] - exog_by_group[order[first]]
        estimate = float(np.dot(contrast, beta))
        variance = float(np.dot(contrast, np.dot(cov, contrast)))
        if not np.isfinite(variance) or variance <= 0:
            statistics.append(float("nan"))
            raw_pvalues.append(float("nan"))
            continue
        se = math.sqrt(variance)
        t_stat = estimate / se
        df_resid = float(getattr(fitted, "df_resid", np.nan))
        pvalue = 2.0 * stats.t.sf(abs(t_stat), df_resid) if np.isfinite(df_resid) else 2.0 * stats.norm.sf(abs(t_stat))
        statistics.append(float(t_stat))
        raw_pvalues.append(float(pvalue))

    correction_method, correction = _normalize_kw_correction(posthoc_correction, len(comparisons))
    pvalues = _apply_kw_correction(raw_pvalues, correction_method)
    results_dict["Linear-Model-Contrasts-Uncorrected"] = [statistics, raw_pvalues]
    results_dict[f"Linear-Model-Contrasts-{correction}"] = [statistics, pvalues]
    annotations = [get_annotation(p, ns) for p in pvalues]
    cov_label = f" {cov_type}" if cov_type else ""
    posthoc_string = f"model contrasts{cov_label} {correction}".strip()
    return pvalues, annotations, (overall_stat, overall_p), results_dict, posthoc_string


def runTWA(experiment, column, factors=None, comparisons=None, results_dict=None, ns="ns"):
    exp_df = experiment.summary
    factors = factors or experiment.condition_list.factor
    comparisons = comparisons or ["1-2", "2-3", "1-3"]
    results_dict = results_dict or {}
    if len(factors) < 2:
        raise ValueError("Two-way ANOVA requires at least two factors.")

    model = ols(
        f"{column} ~ C({factors[0]}) + C({factors[1]}) + C({factors[0]}):C({factors[1]})",
        data=exp_df,
    ).fit()
    anova_results = sm.stats.anova_lm(model, typ=2)
    for index, row in anova_results.iterrows():
        key = f"2WA {index.strip('C()')}"
        results_dict[key] = [float(row["sum_sq"]), float(row["PR(>F)"])]

    sum_sqs = [float(row["sum_sq"]) for _, row in anova_results.iterrows()]
    pvals = [float(row["PR(>F)"]) for _, row in anova_results.iterrows()]

    cond_list = experiment.condition_list
    groups = [exp_df[exp_df["Condition"] == cond.name][column].dropna() for cond in cond_list]
    tukey_results = _run_tukey(*groups)
    statistics, pairwise_pvalues = extract_p_and_stats_from_results(tukey_results, comparisons)
    results_dict["Tukey"] = [statistics, pairwise_pvalues]
    annotations = [get_annotation(result, ns) for result in pairwise_pvalues]
    return pairwise_pvalues, annotations, (sum_sqs, pvals), results_dict, "Tukey"

def test_normality(df_list, make_plot=True):
    groups = _coerce_groups(df_list)
    if len(groups) == 0:
        fig = None
        if make_plot:
            fig, _ = plt.subplots(1, 2, layout="constrained", figsize=(10, 5))
        return False, {}, fig
    all_data = pd.concat(groups).dropna()
    if len(all_data) < 3:
        fig = None
        if make_plot:
            fig, _ = plt.subplots(1, 2, layout="constrained", figsize=(10, 5))
        return False, {}, fig
    results_dict = {}

    norm_fig = None
    norm_ax = None
    if make_plot:
        norm_fig, norm_ax = plt.subplots(1, 2, layout="constrained", figsize=(10, 5))
        n = max(1, int(len(all_data)))
        n_bins = max(8, min(32, int(np.sqrt(n) * 2)))
        lo = float(np.nanmin(all_data))
        hi = float(np.nanmax(all_data))
        if not np.isfinite(lo) or not np.isfinite(hi):
            lo, hi = 0.0, 1.0
        if hi <= lo:
            hi = lo + 1.0
        sns.histplot(all_data, bins=n_bins, binrange=(lo, hi), ax=norm_ax[0])
        sm.qqplot(all_data, ax=norm_ax[1], fit=True, line="45")

    # D'Agostino-Pearson requires at least 8 samples.
    if len(all_data) >= 8:
        stat_k2, p_k2 = normaltest(all_data)
        results_dict["DA"] = [float(stat_k2), float(p_k2)]
    else:
        p_k2 = float("nan")
        results_dict["DA"] = [float("nan"), float("nan")]

    stat_a, p_a = modified_anderson(all_data)
    stat_ks, p_ks = kstest(all_data, "norm")
    stat_sw, p_sw = stats.shapiro(all_data)
    results_dict["A"] = [float(stat_a), float(p_a)]
    results_dict["KS"] = [float(stat_ks), float(p_ks)]
    results_dict["SW_all"] = [float(stat_sw), float(p_sw)]

    if make_plot and norm_ax is not None:
        pval_string = (
            f"K2: {round(p_k2, 2) if not np.isnan(p_k2) else 'n<8'}\n"
            f"A: {round(p_a, 2)}\n"
            f"KS: {round(p_ks, 2)}\n"
            f"W: {round(p_sw, 2)}"
        )
        norm_ax[0].annotate(pval_string, xy=(0.8, 0.8), size=10, xycoords="axes fraction")

    valid_pvals = [value[1] for value in results_dict.values() if not np.isnan(value[1])]
    normality_count = sum(1 for p in valid_pvals if p > 0.05)
    if len(valid_pvals) == 0:
        normality = False
    else:
        normality = normality_count >= max(1, (len(valid_pvals) // 2) + (len(valid_pvals) % 2))
    return normality, results_dict, norm_fig


def _default_comparisons(num_groups):
    comps = []
    for gap in range(1, num_groups):
        for first in range(1, num_groups - gap + 1):
            second = first + gap
            comps.append(f"{first}-{second}")
    return comps


def _sanitize_comparisons(comparisons, n_groups):
    """Keep only well-formed comparisons inside 1..n_groups."""
    if comparisons is None:
        return []
    valid = []
    seen = set()
    for comp in comparisons:
        try:
            first, second = [int(part) for part in str(comp).split("-")]
        except Exception:
            continue
        if first == second:
            continue
        if not (1 <= first <= n_groups and 1 <= second <= n_groups):
            continue
        norm = f"{min(first, second)}-{max(first, second)}"
        if norm in seen:
            continue
        seen.add(norm)
        valid.append(norm)
    return valid


def _fmt_p(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "n/a"
    if np.isnan(p):
        return "n/a"
    if p < 0.0001:
        return f"{p:.2e}"
    return f"{p:.4f}".rstrip("0").rstrip(".")


def _fmt_es(v):
    """Format an effect size / CI bound (not a p-value): fixed 2 decimals."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "n/a"
    if np.isnan(v):
        return "n/a"
    return f"{v:.2f}"


def _name_of(item):
    return item.name if hasattr(item, "name") else str(item)


STATS_ANNOTATION_X = 1.08
STATS_ANNOTATION_Y = 1.0


def _annotate_stats_summary(ax, test, post_hoc, overall, comparisons, pairwise_pvalues, condition_list, factor_list=None, effect_strings=None):
    """Draw a compact statistics summary to the right of the plot."""
    lines = [f"Test: {test}", f"Post-hoc: {post_hoc}"]

    overall_p = overall[1] if isinstance(overall, tuple) and len(overall) > 1 else None
    if isinstance(overall_p, list):
        labels = factor_list or ["Factor 1", "Factor 2", "Interaction", "Residual"]
        for i, p in enumerate(overall_p):
            name = labels[i] if i < len(labels) else f"Term {i+1}"
            lines.append(f"{name} p={_fmt_p(p)}")
    elif overall_p is not None:
        lines.append(f"Group p={_fmt_p(overall_p)}")

    for i, p in enumerate(pairwise_pvalues):
        if i >= len(comparisons):
            break
        comp = comparisons[i]
        try:
            a, b = [int(x) - 1 for x in comp.split("-")]
            if 0 <= a < len(condition_list) and 0 <= b < len(condition_list):
                label = f"{_name_of(condition_list[a])} vs {_name_of(condition_list[b])}"
            else:
                label = comp
        except Exception:
            label = comp
        lines.append(f"{label}: p={_fmt_p(p)}")

    if effect_strings:
        lines.append("")
        lines.extend(str(s) for s in effect_strings)

    ax.text(
        STATS_ANNOTATION_X, STATS_ANNOTATION_Y, "\n".join(lines),
        transform=ax.transAxes,
        ha="left", va="top",
        fontsize=10,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85},
        clip_on=False,
    )


def _annotate_stats_error(ax, error_message):
    """Draw a compact error annotation to the right of the plot."""
    msg = str(error_message)
    if len(msg) > 140:
        msg = msg[:137] + "..."
    ax.text(
        STATS_ANNOTATION_X, STATS_ANNOTATION_Y, f"Stats error:\n{msg}",
        transform=ax.transAxes,
        ha="left", va="top",
        fontsize=10,
        color="crimson",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9},
        clip_on=False,
    )


def print_comparison_results(comparisons, condition_list, individual_results, overall_f, overall_p, normality, test, post_hoc, experiment_name, factor_list=None):
    """Build readable summary strings for group and pairwise results."""
    _ = experiment_name, factor_list  # retained for notebook compatibility
    if not isinstance(overall_p, list):
        group_comparison_string = {"Group difference": get_annotation(overall_p, "ns")}
    else:
        labels = factor_list or ["Factor 1", "Factor 2", "Interaction", "Residual"]
        group_comparison_string = {
            labels[i] if i < len(labels) else f"Term {i+1}": get_annotation(p, "ns")
            for i, p in enumerate(overall_p)
        }

    comparison_strings = []
    for i, comparison in enumerate(comparisons):
        if i >= len(individual_results):
            break
        first, second = [int(part) - 1 for part in comparison.split("-")]
        comparison_strings.append(
            f"{_name_of(condition_list[first])} vs {_name_of(condition_list[second])} {get_annotation(individual_results[i], 'ns')}"
        )
    return group_comparison_string, comparison_strings


def draw_comparison_brackets(ax, centers, comparisons, annotations, *,
                             base_height, pad_height, handles, visible_y_span,
                             lw=2, offset=0.1, floor=None, color="black",
                             star_y_offset_frac=None):
    """Draw PyFLASH's house comparison brackets on ``ax``.

    This is the single bracket renderer shared by every plot that marks
    between-group comparisons (``plot_mean_bars`` via
    :func:`plot_comparison_lines_from_figdata`, and the ``*_contrast``
    slopegraphs), so the geometry cannot drift between them.

    ``centers`` are the x positions of the groups; ``comparisons`` are
    ``"<start>-<end>"`` strings using **1-based** group indices; ``annotations``
    are the matching labels (stars, ``ns``, or numeric p-values).

    Brackets are tiered: one is lifted above an earlier bracket only when their
    horizontal spans genuinely overlap, so adjacent comparisons that merely
    share an endpoint stay on the same tier. Non-significant / numeric labels sit
    **above** the line while stars sit tight against it, which is what keeps an
    ``ns`` from colliding with its own bracket.

    Returns ``(top_drawn, top_line_height)``; ``top_line_height`` is ``None``
    when nothing was drawn.
    """
    n = len(centers)
    annotations = list(annotations or [])
    comparisons = list(comparisons or [])
    line_kws = {"lw": lw, "color": color, "zorder": 1, "clip_on": False}
    updated_x_heights = {}
    top_drawn = float(floor) if floor is not None else float(base_height)
    top_line_height = None

    for i, comparison in enumerate(comparisons):
        if i >= len(annotations):
            break
        try:
            start_index, end_index = [int(v) - 1 for v in str(comparison).split("-")]
        except (TypeError, ValueError):
            continue
        if start_index < 0 or end_index < 0 or start_index >= n or end_index >= n:
            continue
        lo, hi = min(start_index, end_index), max(start_index, end_index)
        xs_cov = centers[lo:hi + 1]
        present = [x for x in xs_cov if x in updated_x_heights]
        height = (
            max(updated_x_heights[x] for x in present)
            if len(present) >= 2
            else base_height
        )

        x_left = centers[lo] + offset
        x_right = centers[hi] - offset
        ax.plot([x_left, x_left], [height, height + handles], **line_kws)
        ax.plot([x_right, x_right], [height, height + handles], **line_kws)
        line_height = height + handles
        ax.plot([x_left, x_right], [line_height, line_height], **line_kws)
        top_line_height = (
            line_height if top_line_height is None
            else max(top_line_height, line_height)
        )
        x_mid = (x_left + x_right) / 2
        annot = annotations[i]
        # Keep text-to-line spacing fixed in axes-relative visual units.  These
        # fractions reproduce the original 0..20 Acrophase placement exactly.
        text_lift = visible_y_span * 0.022
        is_nonsig = _is_nonsignificant_annotation(annot)
        if is_nonsig:
            annot_y = line_height + visible_y_span * 0.0165 + text_lift
        else:
            if star_y_offset_frac is None:
                star_offset = 0.0022
            else:
                try:
                    star_offset = float(star_y_offset_frac)
                except (TypeError, ValueError):
                    star_offset = 0.0022
            annot_y = line_height + visible_y_span * star_offset
        ax.text(
            x_mid, annot_y, annot,
            ha="center",
            va="center",
            size=18 if is_nonsig else 35,
            clip_on=False,
            weight="normal" if is_nonsig else "bold",
            color=color,
        )

        new_height = height + pad_height + handles
        updated_x_heights.update({x: new_height for x in xs_cov})
        top_drawn = max(top_drawn, new_height + handles)

    return top_drawn, top_line_height


def plot_comparison_lines_from_figdata(
    scatter, bar, ax,
    annotations=None, comparisons=None,
    errobar_width=0.12, lw=2, pad=10, handles_fraction=0.3,
    max_override=None,
    group_values=None, group_positions=None, group_colors=None,
    draw_error_bars=True,
):
    if scatter is None:
        return None
    annotations = annotations or []
    comparisons = comparisons or []
    if not hasattr(scatter, "collections") or not scatter.collections:
        return None
    if group_positions is not None and len(group_positions) > 0:
        bar_xs = [float(x) for x in group_positions]
    elif bar is not None:
        bar_xs = sorted({patch.get_x() + patch.get_width() / 2 for patch in bar.patches})
    else:
        return None
    if len(bar_xs) == 0:
        return None

    # Use provided numeric groups when available (most reliable for SEM/error bar placement).
    if group_values is not None and len(group_values) > 0:
        y_by_center = {}
        centers_with_data = []
        for i, vals in enumerate(group_values):
            if i >= len(bar_xs):
                break
            y = pd.to_numeric(pd.Series(vals), errors="coerce").dropna().to_numpy(dtype=float)
            if len(y) == 0:
                continue
            c = bar_xs[i]
            y_by_center[c] = y.tolist()
            centers_with_data.append(c)
        if group_colors is not None and len(group_colors) > 0:
            color_by_center = {}
            for i, cx in enumerate(centers_with_data):
                color_by_center[cx] = group_colors[i] if i < len(group_colors) else "black"
        else:
            color_by_center = {x: "black" for x in centers_with_data}
    else:
        # Fallback: infer groups from plotted swarm points.
        y_by_center = {x: [] for x in bar_xs}
        color_by_center = {x: "black" for x in bar_xs}
        for coll in scatter.collections:
            offsets = coll.get_offsets()
            if offsets is None or len(offsets) == 0:
                continue
            edge = coll.get_edgecolor()
            edge_color = edge[0] if edge is not None and len(edge) > 0 else "black"
            for x, y in np.asarray(offsets, dtype=float):
                if not np.isfinite(y):
                    continue
                nearest = min(bar_xs, key=lambda c: abs(c - x))
                y_by_center[nearest].append(float(y))
                color_by_center[nearest] = edge_color
        centers_with_data = [x for x in bar_xs if len(y_by_center[x]) > 0]
    n = len(centers_with_data)
    if n == 0:
        return None

    means = [float(np.mean(y_by_center[x])) for x in centers_with_data]
    sems = [
        float(np.std(y_by_center[x], ddof=1) / np.sqrt(len(y_by_center[x])))
        if len(y_by_center[x]) > 1 else 0.0
        for x in centers_with_data
    ]
    max_height = max(float(np.max(y_by_center[x])) for x in centers_with_data)
    upper_error_heights = np.add(means, sems)
    # Preserve the original one-sided SEM glyph for positive bars. For negative
    # bars only, point the same glyph downward so it remains outside the bar.
    error_heights = np.asarray([
        mean + sem if mean >= 0 else mean - sem
        for mean, sem in zip(means, sems)
    ], dtype=float)
    max_all = max(max_height, float(np.max(upper_error_heights)))
    if max_override is not None:
        max_all = max(max_all, float(max_override))

    # Preserve the original upper-limit behavior and extend the lower limit only
    # when a signed bar's outward SEM would otherwise be clipped.
    cur_ymin, cur_ymax = ax.get_ylim()
    min_required_top = float(np.max(upper_error_heights)) * 1.03 if len(upper_error_heights) > 0 else cur_ymax
    if cur_ymax < min_required_top:
        ax.set_ylim(cur_ymin, min_required_top)
        cur_ymin, cur_ymax = ax.get_ylim()
    if len(error_heights) > 0 and float(np.min(error_heights)) < cur_ymin:
        ax.set_ylim(float(np.min(error_heights)) * 1.03, cur_ymax)

    # Comparison geometry must be independent of the metric's numeric scale.
    # The axes have a fixed visual height, so express the first-tier gap and
    # handle height as fractions of the visible y span.  With the historical
    # 0..20 Acrophase axis this is numerically identical to the original code
    # (pad_height=2, handles=0.6), while signed axes now render at the same
    # physical size instead of shrinking their brackets.
    cur_ymin, cur_ymax = ax.get_ylim()
    visible_y_span = float(cur_ymax - cur_ymin)
    if not np.isfinite(visible_y_span) or visible_y_span <= 0:
        visible_y_span = max(abs(float(cur_ymax)), abs(float(cur_ymin)), 1.0)
    pad_height = visible_y_span / pad
    handles = pad_height * handles_fraction
    base_height = float(cur_ymax) + pad_height
    line_kws = {"lw": lw, "color": "black", "zorder": 1, "clip_on": False}

    # Plot SEM lines at each bar center. Callers that already draw their own
    # interval glyphs can suppress these while still using the bracket logic.
    if draw_error_bars:
        for i in range(n):
            cx = centers_with_data[i]
            c = color_by_center[cx]
            ax.plot([cx, cx], [means[i], error_heights[i]], color=c, zorder=2.5, lw=2.5)
            ax.plot([cx - errobar_width, cx + errobar_width], [error_heights[i], error_heights[i]], color=c, zorder=2.6, lw=2.5)

    # Default comparisons if none given.
    if comparisons == []:
        pair_iter = itertools.combinations(range(1, n + 1), 2)
        sorted_pairs = sorted(pair_iter, key=lambda x: (x[1] - x[0], x[0]))
        comparisons = [f"{a}-{b}" for a, b in sorted_pairs]

    # Plot comparison brackets.
    top_drawn, top_line_height = draw_comparison_brackets(
        ax, centers_with_data, comparisons, annotations,
        base_height=base_height, pad_height=pad_height, handles=handles,
        visible_y_span=visible_y_span, lw=lw, floor=max_all,
    )

    if top_line_height is not None:
        # Tight SVG export normally sizes itself to the exact glyph bounds, so
        # an ``ns`` top label and a larger ``*`` top label produce slightly
        # different outer canvas heights.  Reserve one fixed visual envelope
        # above the highest tier.  The patch is fully transparent but remains
        # part of Matplotlib's tight-bounding-box calculation.
        x_min, x_max = ax.get_xlim()
        x_epsilon = max(abs(float(x_max - x_min)), 1.0) * 1e-9
        y_epsilon = visible_y_span * 1e-9
        height_anchor = Rectangle(
            (centers_with_data[0], top_line_height + visible_y_span * 0.07),
            x_epsilon,
            y_epsilon,
            facecolor="none",
            edgecolor="none",
            linewidth=0,
            clip_on=False,
        )
        height_anchor.set_gid("pyflash-comparison-height-anchor")
        ax.add_patch(height_anchor)

    return max_all

def plot_comparison_lines_from_fig_data(*args, **kwargs):
    """Backward-compatible alias for alternative function naming."""
    return plot_comparison_lines_from_figdata(*args, **kwargs)


def _effects_to_results_dict(effects, results_dict):
    """Record computed effect sizes into the results dict written to CSV."""
    for key, value in (effects.get("overall") or {}).items():
        results_dict[f"Effect overall ({key})"] = [
            float(value) if value is not None else np.nan, np.nan,
        ]
    for row in effects.get("pairwise", []):
        results_dict[f"Effect {row['comparison']} ({row['metric']})"] = [
            float(row["value"]) if row.get("value") is not None else np.nan,
            [row.get("ci_low"), row.get("ci_high")],
        ]
    return results_dict


def _format_effect_strings(effects, condition_list):
    """Build compact, human-readable effect-size lines for figure/CSV."""
    if not effects:
        return []
    out = []
    for key, value in (effects.get("overall") or {}).items():
        out.append(f"{key.replace('_', ' ')}={_fmt_es(value)}")
    for row in effects.get("pairwise", []):
        comp = row.get("comparison", "")
        try:
            a, b = [int(x) - 1 for x in str(comp).split("-")]
            if 0 <= a < len(condition_list) and 0 <= b < len(condition_list):
                label = f"{_name_of(condition_list[a])} vs {_name_of(condition_list[b])}"
            else:
                label = comp
        except Exception:
            label = comp
        metric = row.get("metric", "effect")
        short = {"hedges_g": "g", "rank_biserial_r": "r"}.get(metric, metric)
        lo, hi = row.get("ci_low"), row.get("ci_high")
        if lo is not None and hi is not None and np.isfinite(lo) and np.isfinite(hi):
            ci_txt = f" [{_fmt_es(lo)}, {_fmt_es(hi)}]"
        else:
            ci_txt = ""
        interp = row.get("interpretation", "")
        interp_txt = f" {interp}" if interp and interp != "n/a" else ""
        out.append(f"{label}: {short}={_fmt_es(row.get('value'))}{ci_txt}{interp_txt}")
    return (["Effect sizes:"] + out) if out else []


def _emit_comparison_record(
    valid_groups, group_labels, cond_list, test, post_hoc,
    overall, comparisons, results, effect_strings, results_dict, normal,
    fallback_metric=None, valid_indices=None, factor_list=None, figure=None,
):
    """Push a structured comparison record to the report collector, if armed.

    Captures the descriptive + inferential numbers ``multipleComparisons`` already
    computed (per-group n/mean/sd, test, p-values, effect sizes) so an agent can
    read them instead of OCR-ing the figure. Fully guarded — never raises into the
    plotting path, and a no-op unless a caller has armed ``PyFLASH.report``.

    ``valid_indices`` aligns the (full-length) ``group_labels``/``cond_list`` to the
    ``valid_groups`` actually tested — ``multipleComparisons`` drops empty groups, so
    without this the labels would pair positionally with the wrong groups' values.
    """
    try:
        import PyFLASH.report as report
    except Exception:
        return
    if not report.is_active():
        return
    try:
        # _name_of unwraps Condition objects to their .name (str() would give an
        # object repr); it passes plain strings through unchanged.
        label_source = group_labels if group_labels is not None else cond_list
        try:
            names = [_name_of(c) for c in label_source]
        except Exception:
            names = []
        if valid_indices is not None:
            try:
                names = [names[i] for i in valid_indices if 0 <= i < len(names)]
            except Exception:
                pass
        metric = fallback_metric
        for g in valid_groups:
            nm = getattr(g, "name", None)
            if nm is not None and str(nm) != "":
                metric = nm
                break
        # For Two-Way ANOVA the overall p is a list [Factor1, Factor2, Interaction,
        # Residual]; extend the factor names so the trailing terms aren't anonymous
        # "term3"/"term4". Mirrors PyFLASH's own annotation label convention.
        if isinstance(factor_list, (list, tuple)):
            term_labels = list(factor_list) + ["Interaction", "Residual"]
        else:
            term_labels = None
        record = report.build_comparison_record(
            metric=metric,
            group_names=names,
            group_values=valid_groups,
            test=test,
            post_hoc=post_hoc,
            overall=overall,
            comparisons=comparisons,
            pairwise_pvalues=results,
            effect_strings=effect_strings,
            raw_stats=results_dict,
            normal=normal,
            factor_terms=term_labels,
        )
        plot_rows = []
        for group_index, group_values in enumerate(valid_groups):
            group_name = names[group_index] if group_index < len(names) else f"G{group_index + 1}"
            try:
                entries = group_values.items()
            except AttributeError:
                entries = enumerate(group_values)
            for observation_id, value in entries:
                plot_rows.append({
                    "group": group_name,
                    "metric": metric,
                    "value": value,
                    "observation_id": str(observation_id),
                })
        plotted_data = pd.DataFrame(plot_rows)
        report.emit(
            record,
            figure=figure,
            plotted_data=plotted_data,
            analysis={"independent_unit": "animal"},
        )
        if figure is not None:
            report.attach(
                figure,
                column_classification={
                    "group": "safe",
                    "metric": "safe",
                    "value": "safe",
                    "observation_id": "private",
                },
                column_roles={
                    "group": "group",
                    "metric": "metric",
                    "value": "value",
                    "observation_id": "independent_unit",
                },
                data_status="complete",
                statistics_status="complete",
            )
    except Exception:
        pass


def multipleComparisons(
    experiment,
    dfs,
    ax,
    fig,
    scatter,
    bar,
    multiple_comparison="Two-Way",
    save_name=None,
    comparisons=None,
    force_nonparametric=False,
    posthoc="Conover",
    posthoc_correction="auto",
    stats_test="auto",
    variance_test="brown-forsythe",
    variance_alpha=0.05,
    auto_welch=True,
    model_df=None,
    model_group_col=None,
    model_value_col=None,
    covariates=None,
    categorical_covariates=None,
    cov_type="HC3",
    cov_kwds=None,
    max_override=None,
    ns="ns",
    annotate_summary=True,
    group_labels=None,
    group_positions=None,
    group_colors=None,
    verbose=False,
    save_normality=False,
    normality_dpi=120,
    draw=True,
    cache_key=None,
    output_dir=None,
):
    """Run group and post-hoc tests, save stats CSV, and optionally annotate.

    When *draw* is False the computation runs but no annotations are added
    to the axes.  The fourth return element is the results dict.

    When *cache_key* is provided and ``Config.STATS_CACHE`` is True,
    previously computed results are reused (draw still runs if requested).
    """
    from PyFLASH.config import Config

    if not dfs:
        return "N/A", "N/A", None, {}
    clean_dfs = [pd.to_numeric(pd.Series(g), errors="coerce").dropna() for g in dfs]
    valid_groups = [g for g in clean_dfs if len(g) > 0]
    # Original-order indices of the surviving groups, so the report layer can map
    # full-length group labels back onto the (possibly shorter) valid_groups.
    valid_indices = [i for i, g in enumerate(clean_dfs) if len(g) > 0]
    if len(valid_groups) < 2:
        return "N/A", "N/A", None, {}

    # ── Cache lookup ────────────────────────────────────────────────
    cached = None
    if cache_key is not None and Config.STATS_CACHE:
        cached = _stats_cache.get(cache_key)
    if cached is not None:
        test = cached['test']
        post_hoc = cached['post_hoc']
        annotations = cached['annotations']
        results = cached['results']
        overall = cached['overall']
        results_dict = cached['results_dict']
        comparisons = cached['comparisons']
        cond_list = group_labels if group_labels is not None else experiment.condition_list
        results_strings = cached.get('results_strings', {})
        effect_strings = cached.get('effect_strings', [])
        if save_name:
            results_to_excel(
                results_dict, results_strings, experiment.data_path, save_name,
                verbose=verbose, output_dir=output_dir)
        annotation_objects = None
        if draw:
            annotation_objects = plot_comparison_lines_from_figdata(
                scatter, bar, ax,
                annotations=annotations,
                comparisons=comparisons,
                errobar_width=0.12, lw=2,
                max_override=max_override,
                group_values=valid_groups,
                group_positions=group_positions,
                group_colors=group_colors,
            )
            if annotate_summary:
                _annotate_stats_summary(
                    ax=ax, test=test, post_hoc=post_hoc, overall=overall,
                    comparisons=comparisons, pairwise_pvalues=results,
                    condition_list=cond_list,
                    factor_list=experiment.factor if hasattr(experiment, "factor") else None,
                    effect_strings=effect_strings,
                )
        _emit_comparison_record(
            valid_groups, group_labels, cond_list, test, post_hoc,
            overall, comparisons, results, effect_strings, results_dict,
            cached.get('normal'),
            fallback_metric=save_name, valid_indices=valid_indices,
            factor_list=getattr(experiment, "factor", None), figure=fig,
        )
        return test, post_hoc, annotation_objects, results_dict

    if comparisons is None:
        default_from_conditions = getattr(experiment.condition_list, "comparisons", None)
        comparisons = default_from_conditions if default_from_conditions is not None else _default_comparisons(len(valid_groups))
    comparisons = _sanitize_comparisons(comparisons, len(valid_groups))
    if len(comparisons) == 0 and len(valid_groups) >= 2:
        comparisons = _default_comparisons(len(valid_groups))
    cond_list = group_labels if group_labels is not None else experiment.condition_list
    normal, results_dict, norm_fig = test_normality(valid_groups, make_plot=save_normality)
    if save_name and save_normality and norm_fig is not None:
        fname = f"{strip_name(save_name)}_normality.png"
        normality_dir = output_dir or experiment.data_path
        os.makedirs(normality_dir, exist_ok=True)
        out_path = os.path.join(normality_dir, fname)
        save_fig(
            norm_fig,
            normality_dir,
            os.path.splitext(fname)[0],
            figure_formats=("png",),
            dpi=normality_dpi,
            rasterize=False,
            transparent=False,
            verbose=False,
        )
        if verbose:
            _log.confirm(f"Normality figure saved to {out_path}")
    if norm_fig is not None:
        plt.close(norm_fig)
    if force_nonparametric:
        normal = False
    variance_info = test_equal_variance(
        valid_groups,
        results_dict,
        method=variance_test,
        alpha=variance_alpha,
    )
    equal_variance = variance_info.get("equal_var")
    selected_test = _normalize_group_stats_test(stats_test)

    try:
        if selected_test == "linear_model":
            if model_df is None:
                raise ValueError("stats_test='linear_model' requires model_df/model_group_col/model_value_col.")
            model_group_col = model_group_col or "Condition"
            model_value_col = model_value_col or pd.Series(valid_groups[0]).name
            results, annotations, overall, results_dict, post_hoc = runLinearModel(
                model_df,
                model_value_col,
                model_group_col,
                comparisons,
                results_dict,
                ns=ns,
                covariates=covariates,
                categorical_covariates=categorical_covariates,
                posthoc_correction=posthoc_correction,
                cov_type=cov_type,
                cov_kwds=cov_kwds,
                group_order=[
                    _name_of(g) if not isinstance(g, str) else g
                    for g in (group_labels or [])
                ] or None,
            )
            test = "Linear Model"
        elif len(valid_groups) == 2:
            # If either group is too small for t-test assumptions, fall back to MWU.
            if selected_test in {"anova", "welch_anova", "kruskal", "two_way"}:
                raise ValueError(f"stats_test={stats_test!r} needs at least three groups.")
            if selected_test == "mannwhitney" or (
                selected_test in {"auto", "auto_t"} and ((not normal) or any(len(g) <= 1 for g in valid_groups))
            ):
                results, annotations, overall, results_dict, post_hoc = mwu_multiple_comparisons(
                    valid_groups, ["1-2"], results_dict, ns
                )
                test = "Mann-Whitney U"
                comparisons = ["1-2"]
            else:
                if selected_test == "student_t":
                    t_equal_var = True
                elif selected_test == "welch_t":
                    t_equal_var = False
                else:
                    t_equal_var = True if equal_variance is True else False
                results, annotations, overall, results_dict, post_hoc = runITTest(
                    valid_groups[0],
                    valid_groups[1],
                    results_dict,
                    ns,
                    equal_var=t_equal_var,
                    variance_test=variance_test,
                    variance_alpha=variance_alpha,
                )
                test = "Student's T-Test" if t_equal_var else "Welch's T-Test"
                comparisons = ["1-2"]
        else:
            if selected_test in {"student_t", "welch_t", "mannwhitney", "auto_t"}:
                raise ValueError(f"stats_test={stats_test!r} supports exactly two groups.")
            use_nonparametric = (
                selected_test == "kruskal"
                or (selected_test == "auto" and ((not normal) or any(len(g) <= 1 for g in valid_groups)))
            )
            use_welch_anova = (
                selected_test == "welch_anova"
                or (
                    selected_test == "auto"
                    and normal
                    and bool(auto_welch)
                    and equal_variance is False
                    and multiple_comparison == "One-Way"
                )
            )
            if use_nonparametric:
                results, annotations, overall, results_dict, post_hoc = runKW(
                    valid_groups,
                    comparisons,
                    results_dict,
                    posthoc=posthoc,
                    posthoc_correction=posthoc_correction,
                    ns=ns,
                )
                test = "Kruskal-Wallis"
            elif use_welch_anova:
                welch_posthoc = posthoc
                if _normalize_kw_correction_key(posthoc or "auto") in {
                    "auto", "default", "conover", "conover_test", "dunn", "dunns",
                    "dunns_test", "dunn_test", "tukey", "tukey_hsd", "hsd",
                }:
                    welch_posthoc = "Tamhane T2"
                results, annotations, overall, results_dict, post_hoc = runWelchOWA(
                    valid_groups,
                    comparisons,
                    results_dict,
                    ns=ns,
                    posthoc=welch_posthoc,
                )
                test = "Welch ANOVA"
            elif selected_test == "anova" or (selected_test == "auto" and multiple_comparison == "One-Way"):
                results, annotations, overall, results_dict, post_hoc = runOWA(
                    valid_groups,
                    comparisons,
                    results_dict,
                    ns,
                    posthoc=posthoc,
                    posthoc_correction=posthoc_correction,
                )
                test = "One-Way ANOVA"
            else:
                results, annotations, overall, results_dict, post_hoc = runTWA(
                    experiment,
                    pd.Series(valid_groups[0]).name,
                    comparisons=comparisons,
                    results_dict=results_dict,
                    ns=ns,
                )
                test = "Two-Way ANOVA"
    except Exception as e:
        err = str(e)
        results_dict["Stats_error"] = [err, np.nan]
        if draw and annotate_summary:
            _annotate_stats_error(ax, err)
        if save_name:
            results_to_excel(
                results_dict,
                {"Group Test Used": "Error", "Post-Hoc Test Used": f"Error: {err}", "Comparisons": []},
                experiment.data_path,
                save_name,
                verbose=verbose,
                output_dir=output_dir,
            )
        return "Error", f"Error: {err}", None, results_dict

    group_strings, comp_strings = print_comparison_results(
        comparisons,
        cond_list,
        results,
        overall[0],
        overall[1],
        normal,
        test,
        post_hoc,
        save_name or "Comparison",
        experiment.factor if hasattr(experiment, "factor") else None,
    )

    results_strings = {
        "Group Test Used": test,
        **group_strings,
        "Post-Hoc Test Used": post_hoc,
        "Comparisons": comp_strings,
    }
    if isinstance(variance_info, dict) and variance_info.get("method") != "Not checked":
        results_strings["Variance Test"] = (
            f"{variance_info.get('method')}: p={_fmt_p(variance_info.get('pvalue'))}; "
            f"equal_var={variance_info.get('equal_var')}"
        )

    # ── Effect sizes ────────────────────────────────────────────────
    effects = {}
    effect_strings = []
    if getattr(Config, "EFFECT_SIZES", True):
        try:
            from PyFLASH import stats_extra as _se
            effects = _se.effect_sizes_for_test(
                valid_groups, test, comparisons,
                ci=getattr(Config, "EFFECT_CI", True),
                n_resamples=getattr(Config, "EFFECT_CI_RESAMPLES", 5000),
            )
            _effects_to_results_dict(effects, results_dict)
            effect_strings = _format_effect_strings(effects, cond_list)
            if effect_strings:
                results_strings["Effect sizes"] = effect_strings[1:]  # drop header for CSV
        except Exception as e:
            results_dict["Effect_error"] = [str(e), np.nan]

    if save_name:
        results_to_excel(
            results_dict, results_strings, experiment.data_path, save_name,
            verbose=verbose, output_dir=output_dir)
    annotation_objects = None
    if draw:
        annotation_objects = plot_comparison_lines_from_figdata(
            scatter,
            bar,
            ax,
            annotations=annotations,
            comparisons=comparisons,
            errobar_width=0.12,
            lw=2,
            max_override=max_override,
            group_values=valid_groups,
            group_positions=group_positions,
            group_colors=group_colors,
        )
        if annotate_summary:
            _annotate_stats_summary(
                ax=ax,
                test=test,
                post_hoc=post_hoc,
                overall=overall,
                comparisons=comparisons,
                pairwise_pvalues=results,
                condition_list=cond_list,
                factor_list=experiment.factor if hasattr(experiment, "factor") else None,
                effect_strings=effect_strings,
            )

    # ── Cache store ──────────────────────────────────────────────────
    if cache_key is not None and Config.STATS_CACHE:
        _stats_cache[cache_key] = {
            'test': test,
            'post_hoc': post_hoc,
            'annotations': annotations,
            'results': results,
            'overall': overall,
            'results_dict': results_dict,
            'comparisons': comparisons,
            'results_strings': results_strings,
            'effect_strings': effect_strings,
            'normal': normal,
        }

    _emit_comparison_record(
        valid_groups, group_labels, cond_list, test, post_hoc,
        overall, comparisons, results, effect_strings, results_dict, normal,
        fallback_metric=save_name, valid_indices=valid_indices,
        factor_list=getattr(experiment, "factor", None), figure=fig,
    )
    return test, post_hoc, annotation_objects, results_dict
