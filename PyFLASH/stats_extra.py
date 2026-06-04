"""
Effect sizes, confidence intervals, multiplicity control, power, and
reliability metrics that complement :mod:`PyFLASH.stats`.

Everything here is pure computation (returns plain dicts / floats) and depends
only on the mandatory stack (numpy / scipy / statsmodels), so importing this
module never requires an optional dependency.  Figure-producing analyses that
need an optional package live in :mod:`PyFLASH.plotting` and use
:mod:`PyFLASH._optional`.

Design notes
------------
PyFLASH's ``batch.summary`` is already aggregated to one row per animal
(``Experiment.createSummary`` groups ROI-level rows by ``AnimalName``), so the
group lists handed to :func:`effect_sizes_for_test` are animal-level: N is the
number of animals, and the bootstrap CI in :func:`effect_ci` resamples animals,
respecting the true experimental unit for free.

This module deliberately reimplements the handful of effect-size / power
formulae it needs rather than taking a dependency on ``pingouin`` (GPL-3.0),
keeping PyFLASH BSD-3-Clause.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as _sps


# ── Effect sizes ─────────────────────────────────────────────────────
def cohens_d(a, b) -> float:
    """Cohen's d with pooled SD (two independent groups)."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan")
    sp = np.sqrt(((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2))
    return float((a.mean() - b.mean()) / sp) if sp > 0 else float("nan")


def hedges_g(a, b) -> float:
    """Cohen's d with the small-sample (Hedges) bias correction."""
    d = cohens_d(a, b)
    na, nb = len(a), len(b)
    if not np.isfinite(d) or (na + nb) <= 2:
        return float("nan")
    j = 1.0 - 3.0 / (4.0 * (na + nb) - 9.0)
    return float(d * j)


def rank_biserial(a, b) -> float:
    """Rank-biserial correlation: effect size for Mann-Whitney U (range -1..1).

    Signed (Kerby 2014) so that positive means group *a* tends to exceed group
    *b* — consistent with the sign of :func:`cohens_d`/:func:`hedges_g`.
    """
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na, nb = len(a), len(b)
    if na == 0 or nb == 0:
        return float("nan")
    try:
        u, _ = _sps.mannwhitneyu(a, b, alternative="two-sided")
    except ValueError:
        return float("nan")
    return float((2.0 * u) / (na * nb) - 1.0)


def anova_effect_sizes(groups) -> dict:
    """eta-squared and (less biased) omega-squared for a one-way layout."""
    groups = [np.asarray(g, float) for g in groups if len(g) > 0]
    k = len(groups)
    if k < 2:
        return {}
    allv = np.concatenate(groups)
    n = len(allv)
    grand = allv.mean()
    ss_b = sum(len(g) * (g.mean() - grand) ** 2 for g in groups)
    ss_w = sum(((g - g.mean()) ** 2).sum() for g in groups)
    ss_t = ss_b + ss_w
    ms_w = ss_w / (n - k) if n > k else float("nan")
    eta2 = ss_b / ss_t if ss_t > 0 else float("nan")
    if np.isfinite(ms_w) and (ss_t + ms_w) > 0:
        omega2 = (ss_b - (k - 1) * ms_w) / (ss_t + ms_w)
    else:
        omega2 = float("nan")
    return {"eta_squared": float(eta2), "omega_squared": float(omega2)}


def kw_epsilon_squared(groups) -> float:
    """Epsilon-squared effect size for the Kruskal-Wallis test."""
    groups = [np.asarray(g, float) for g in groups if len(g) > 0]
    n = sum(len(g) for g in groups)
    k = len(groups)
    if n <= k or k < 2:
        return float("nan")
    try:
        h, _ = _sps.kruskal(*groups)
    except ValueError:
        return float("nan")
    return float((h - k + 1) / (n - k))


def interpret_magnitude(value, kind="d") -> str:
    """Plain-English magnitude band for an effect size (Cohen benchmarks)."""
    try:
        v = abs(float(value))
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(v):
        return "n/a"
    if kind == "d":  # Cohen's d / Hedges' g / |rank-biserial|
        return ("negligible" if v < 0.2 else "small" if v < 0.5
                else "medium" if v < 0.8 else "large")
    if kind in ("eta2", "omega2", "eps2"):
        return "small" if v < 0.06 else "medium" if v < 0.14 else "large"
    return "n/a"


def effect_ci(a, b, eftype="hedges", n_resamples=5000, confidence=0.95):
    """Animal-level BCa bootstrap CI for a two-group effect size.

    Returns ``(low, high)``; ``(nan, nan)`` when the groups are too small or
    the resampling fails (e.g. degenerate variance).
    """
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return (float("nan"), float("nan"))
    fn = hedges_g if eftype == "hedges" else cohens_d
    try:
        res = _sps.bootstrap(
            (a, b),
            lambda x, y: fn(x, y),
            vectorized=False,
            paired=False,
            method="BCa",
            n_resamples=int(n_resamples),
            confidence_level=confidence,
        )
        ci = res.confidence_interval
        lo, hi = float(ci.low), float(ci.high)
        if not (np.isfinite(lo) and np.isfinite(hi)):
            return (float("nan"), float("nan"))
        return (lo, hi)
    except Exception:
        return (float("nan"), float("nan"))


_PARAMETRIC_TESTS = {"Independent T-Test", "One-Way ANOVA", "Two-Way ANOVA"}


def effect_sizes_for_test(groups, test, comparisons, ci=True, n_resamples=5000) -> dict:
    """Compute the effect-size family matching the test that was run.

    Parameters
    ----------
    groups : list of array-like
        Animal-level values per group, in the same 1-based order the
        ``comparisons`` strings (e.g. ``"1-2"``) index into.
    test : str
        The test name chosen by :func:`PyFLASH.stats.multipleComparisons`.
    comparisons : list[str]
        Pairwise comparison tokens like ``"1-2"``.
    ci : bool
        Compute bootstrap CIs for parametric pairwise effects.

    Returns
    -------
    dict with keys ``overall`` (dict), ``pairwise`` (list of dicts) and
    ``family`` (str | None).
    """
    groups = [np.asarray(pd.to_numeric(pd.Series(g), errors="coerce").dropna(), float) for g in groups]
    parametric = test in _PARAMETRIC_TESTS
    out: dict = {"overall": {}, "pairwise": [], "family": None}

    # Overall (omnibus) effect size — only where it is unambiguous.
    if test == "One-Way ANOVA":
        out["overall"] = anova_effect_sizes(groups)
        out["family"] = "omega_squared"
    elif test == "Kruskal-Wallis":
        out["overall"] = {"epsilon_squared": kw_epsilon_squared(groups)}
        out["family"] = "epsilon_squared"
    # Two-Way ANOVA: partial eta-squared per factor needs the full ANOVA table,
    # so we report only the (always valid) pairwise effects below.

    for comp in comparisons or []:
        try:
            i, j = [int(p) - 1 for p in str(comp).split("-")]
        except (ValueError, AttributeError):
            continue
        if not (0 <= i < len(groups) and 0 <= j < len(groups)):
            continue
        a, b = groups[i], groups[j]
        if parametric:
            val = hedges_g(a, b)
            lo, hi = effect_ci(a, b, "hedges", n_resamples=n_resamples) if ci else (float("nan"), float("nan"))
            out["pairwise"].append({
                "comparison": comp, "metric": "hedges_g", "value": val,
                "ci_low": lo, "ci_high": hi, "interpretation": interpret_magnitude(val, "d"),
            })
        else:
            val = rank_biserial(a, b)
            out["pairwise"].append({
                "comparison": comp, "metric": "rank_biserial_r", "value": val,
                "ci_low": float("nan"), "ci_high": float("nan"),
                "interpretation": interpret_magnitude(val, "d"),
            })
    return out


# ── Multiplicity control ─────────────────────────────────────────────
def adjust_pvalues(pvalues, method="fdr_bh"):
    """Adjust a set of p-values; NaNs pass through untouched.

    ``method`` is any accepted by ``statsmodels.stats.multitest.multipletests``
    (``'fdr_bh'``, ``'fdr_by'``, ``'holm'``, ``'bonferroni'``, ``'sidak'``...).
    Returns ``(reject_list, adjusted_list)``.
    """
    from statsmodels.stats.multitest import multipletests

    p = np.asarray([float(x) for x in pvalues], float)
    mask = np.isfinite(p)
    adj = np.full(p.shape, np.nan)
    rej = np.zeros(p.shape, bool)
    if mask.sum() > 0:
        r, a, *_ = multipletests(p[mask], method=method)
        adj[mask] = a
        rej[mask] = r
    return rej.tolist(), adj.tolist()


# ── Power ────────────────────────────────────────────────────────────
def achieved_power(effect_size, n1, n2=None, alpha=0.05) -> float:
    """Post-hoc power of a two-group t-test for a given standardized effect."""
    from statsmodels.stats.power import TTestIndPower

    if not np.isfinite(effect_size) or n1 < 2:
        return float("nan")
    ratio = (n2 / n1) if n2 else 1.0
    try:
        return float(TTestIndPower().power(
            effect_size=abs(effect_size), nobs1=int(n1), alpha=alpha, ratio=ratio))
    except Exception:
        return float("nan")


def required_n(effect_size, alpha=0.05, power=0.8) -> float:
    """Per-group n needed to detect *effect_size* at the target power."""
    from statsmodels.stats.power import TTestIndPower

    if not np.isfinite(effect_size) or effect_size == 0:
        return float("nan")
    try:
        return float(TTestIndPower().solve_power(
            effect_size=abs(effect_size), alpha=alpha, power=power))
    except Exception:
        return float("nan")


# ── Reliability / design diagnostic ──────────────────────────────────
def icc1(roi_df, value_col, group_col="AnimalName") -> float:
    """ICC(1): fraction of total variance that is between animals.

    Operates on **ROI-level** rows (e.g. ``experiment.data[marker].df``), not the
    animal-level summary.  High ICC (>0.3) means ROIs within an animal are
    strongly correlated, which justifies PyFLASH's aggregate-to-animal approach;
    near-zero ICC means ROI-level variation dominates.
    """
    df = roi_df[[group_col, value_col]].copy()
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna()
    groups = [g[value_col].to_numpy() for _, g in df.groupby(group_col)]
    groups = [g for g in groups if len(g) > 0]
    k = len(groups)
    if k < 2:
        return float("nan")
    n_i = [len(g) for g in groups]
    n = sum(n_i)
    if n <= k:
        return float("nan")
    grand = np.concatenate(groups).mean()
    msb = sum(ni * (g.mean() - grand) ** 2 for g, ni in zip(groups, n_i)) / (k - 1)
    msw = sum(((g - g.mean()) ** 2).sum() for g in groups) / (n - k)
    k0 = (n - sum(ni ** 2 for ni in n_i) / n) / (k - 1)  # corrected mean group size
    denom = msb + (k0 - 1) * msw
    return float((msb - msw) / denom) if np.isfinite(denom) and denom > 0 else float("nan")
