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


# ── Batch multiplicity control ───────────────────────────────────────
def apply_fdr(pvalues, labels=None, families=None, method="fdr_bh", alpha=0.05):
    """Adjust a collection of p-values, optionally within families.

    Use this across a whole multi-marker sweep (Bonferroni/Sidak in the
    per-figure path are too conservative for dozens of comparisons).  Pass a
    dict ``{label: p}``, a ``pd.Series``, or a list (plus optional ``labels``).
    ``families`` (dict ``{label: family}`` or list) applies the correction
    within each family separately, e.g. all Abeta markers vs all glial markers.

    Returns a tidy DataFrame: ``label, family, p_value, p_adjusted, reject``.
    """
    if isinstance(pvalues, dict):
        labels = list(pvalues.keys())
        pv = list(pvalues.values())
    elif isinstance(pvalues, pd.Series):
        labels = list(pvalues.index) if labels is None else labels
        pv = list(pvalues.values)
    else:
        pv = list(pvalues)
        if labels is None:
            labels = list(range(len(pv)))

    n = len(pv)
    if families is None:
        fam = ["all"] * n
    elif isinstance(families, dict):
        fam = [families.get(lab, "all") for lab in labels]
    else:
        fam = list(families)

    out = pd.DataFrame({
        "label": labels,
        "family": fam,
        "p_value": [float(x) for x in pv],
    })
    out["p_adjusted"] = np.nan
    for fam_name in out["family"].unique():
        mask = out["family"] == fam_name
        _, adj = adjust_pvalues(out.loc[mask, "p_value"].tolist(), method=method)
        out.loc[mask, "p_adjusted"] = adj
    out["reject"] = out["p_adjusted"] <= float(alpha)
    return out.reset_index(drop=True)


# ── Many-to-one (treatment vs control) ───────────────────────────────
def dunnett_vs_control(groups, labels=None, control=0, alternative="two-sided"):
    """Dunnett's test: each treatment group vs a single control.

    More powerful and appropriate than all-pairwise Tukey for genotype x drug
    designs where the question is "does each treatment differ from vehicle/WT?"

    Requires SciPy >= 1.11 (``scipy.stats.dunnett``); raises a clear ImportError
    otherwise.  ``control`` is an index or a value in ``labels``.
    Returns a DataFrame: ``comparison, statistic, p_value``.
    """
    dunnett = getattr(_sps, "dunnett", None)
    if dunnett is None:
        raise ImportError(
            "Dunnett's test requires SciPy >= 1.11 (scipy.stats.dunnett); "
            "the installed SciPy is older."
        )
    groups = [np.asarray(pd.to_numeric(pd.Series(g), errors="coerce").dropna(), float) for g in groups]
    if labels is None:
        labels = [str(i + 1) for i in range(len(groups))]
    labels = [str(x) for x in labels]
    if len(labels) != len(groups):
        raise ValueError("labels and groups must be the same length.")

    if isinstance(control, str):
        if control not in labels:
            raise ValueError(f"control '{control}' not found in labels {labels}.")
        ci = labels.index(control)
    else:
        ci = int(control)
    if not (0 <= ci < len(groups)):
        raise ValueError("control index out of range.")

    treatment_idx = [i for i in range(len(groups)) if i != ci]
    if len(treatment_idx) < 1:
        raise ValueError("Need at least one treatment group besides the control.")
    treatments = [groups[i] for i in treatment_idx]
    res = dunnett(*treatments, control=groups[ci], alternative=alternative)

    stats_arr = np.atleast_1d(res.statistic)
    pvals_arr = np.atleast_1d(res.pvalue)
    rows = []
    for k, i in enumerate(treatment_idx):
        rows.append({
            "comparison": f"{labels[i]} vs {labels[ci]}",
            "statistic": float(stats_arr[k]),
            "p_value": float(pvals_arr[k]),
        })
    return pd.DataFrame(rows)


# ── Proportions / counts ─────────────────────────────────────────────
def proportion_test(table, force=None):
    """Chi-square test of independence, with automatic Fisher's exact fallback.

    For comparing proportions (e.g. % marker-positive cells, fraction of animals
    with plaques) across conditions.  ``table`` is a contingency table of counts
    (DataFrame or 2D array).  Fisher's exact is used for a 2x2 table when any
    expected cell < 5 (or ``force='fisher'``); ``force='chi2'`` keeps chi-square.

    Returns ``{test, statistic, p_value, dof, expected}``.
    """
    arr = np.asarray(pd.DataFrame(table).to_numpy() if not isinstance(table, np.ndarray) else table, float)
    arr = np.atleast_2d(arr)
    if arr.ndim != 2 or arr.shape[0] < 2 or arr.shape[1] < 2:
        raise ValueError("Contingency table must be at least 2x2.")

    is_2x2 = arr.shape == (2, 2)
    chi2, p, dof, expected = _sps.chi2_contingency(arr, correction=is_2x2)
    use_fisher = (force == "fisher") or (force is None and is_2x2 and expected.min() < 5)
    if use_fisher and is_2x2:
        odds, p_f = _sps.fisher_exact(arr)
        return {"test": "Fisher exact", "statistic": float(odds), "p_value": float(p_f),
                "dof": None, "expected": expected}
    return {"test": "Chi-square", "statistic": float(chi2), "p_value": float(p),
            "dof": int(dof), "expected": expected}


# ── Longitudinal helpers ─────────────────────────────────────────────
def _resolve_numeric_time(series, time_map=None):
    """Coerce a time factor to numbers: explicit map -> numeric -> trailing digits."""
    s = pd.Series(series)
    if time_map:
        mapped = s.map(time_map)
        if mapped.notna().any():
            return pd.to_numeric(mapped, errors="coerce")
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().any():
        return num
    digits = s.astype(str).str.extract(r"(\d+\.?\d*)")[0]
    return pd.to_numeric(digits, errors="coerce")


def timecourse_auc(df, time_col, value_col, animal_col="AnimalName",
                   group_col=None, time_map=None, baseline=None):
    """Trapezoidal area under the time-course, one value per animal.

    Collapses a longitudinal series to a single scalar per animal (total
    exposure), sidestepping pseudoreplication for the downstream group test.
    ``time_map`` (e.g. ``{'WeekTwo': 2, 'WeekEight': 8}``) maps a categorical
    time factor to numbers; otherwise numeric values or trailing digits are used.

    Returns a DataFrame with ``[group_col,] AnimalName, auc``.
    """
    work = df.copy()
    work["_t"] = _resolve_numeric_time(work[time_col], time_map)
    work["_v"] = pd.to_numeric(work[value_col], errors="coerce")
    if baseline is not None:
        work["_v"] = work["_v"] - float(baseline)
    work = work.dropna(subset=["_t", "_v"])

    keys = [animal_col] + ([group_col] if group_col else [])
    rows = []
    grouped = work.groupby(keys) if len(keys) > 1 else work.groupby(animal_col)
    for key, g in grouped:
        g = g.sort_values("_t")
        if len(g) < 2:
            continue
        _trapz = getattr(np, "trapezoid", np.trapz)
        auc = float(_trapz(g["_v"].to_numpy(), g["_t"].to_numpy()))
        rec = {}
        key_tuple = key if isinstance(key, tuple) else (key,)
        for kcol, kval in zip(keys, key_tuple):
            rec[kcol] = kval
        rec["auc"] = auc
        rows.append(rec)
    return pd.DataFrame(rows)


def _growth_models():
    """name -> (model function, n_params, requires_positive_x)."""
    def linear(x, slope, intercept):
        return slope * x + intercept

    def exponential(x, amplitude, rate, offset):
        return amplitude * np.exp(rate * x) + offset

    def logistic(x, bottom, top, ec50, hill):
        return bottom + (top - bottom) / (1.0 + (ec50 / x) ** hill)

    return {
        "linear": (linear, 2, False),
        "exponential": (exponential, 3, False),
        "logistic": (logistic, 4, True),
    }


def _growth_p0_bounds(name, x, y):
    """Initial guesses and parameter bounds for each growth model."""
    ymin, ymax = float(np.min(y)), float(np.max(y))
    xmin, xmax = float(np.min(x)), float(np.max(x))
    if name == "linear":
        slope0 = (y[-1] - y[0]) / (x[-1] - x[0]) if x[-1] != x[0] else 0.0
        return [slope0, ymin], (-np.inf, np.inf)
    if name == "exponential":
        return [(ymax - ymin) or 1.0, 0.1, ymin], (-np.inf, np.inf)
    if name == "logistic":
        p0 = [ymin, ymax if ymax > ymin else ymin + 1.0, ((xmin + xmax) / 2.0) or 1.0, 1.0]
        lb = [-np.inf, -np.inf, 1e-9, 0.1]
        ub = [np.inf, np.inf, np.inf, 10.0]
        return p0, (lb, ub)
    return None, (-np.inf, np.inf)


def _aic_least_squares(sse, n, k):
    """AIC for a least-squares fit (Gaussian errors)."""
    if sse <= 0 or n <= 0:
        return -np.inf
    return float(n * np.log(sse / n) + 2 * k)


def fit_growth_curve(x, y, model="auto"):
    """Fit a growth/decay curve to (x, y) with parameter uncertainties.

    Models: ``'linear'``, ``'exponential'``, ``'logistic'`` (4-parameter), or
    ``'auto'`` (best by AIC among models with enough residual degrees of
    freedom).  Uses ``scipy.optimize.curve_fit``; parameter standard errors come
    from the covariance matrix.

    Returns ``{model, params:{name:{value,stderr}}, r_squared, aic, n,
    predict(callable), all_models}``.
    """
    import inspect
    from scipy.optimize import curve_fit

    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    order = np.argsort(x)
    x, y = x[order], y[order]
    n = len(x)
    if n < 3:
        raise ValueError("Need >= 3 finite (x, y) points to fit a growth curve.")

    models = _growth_models()
    if model == "auto":
        candidates = [
            name for name, (_, npar, pos) in models.items()
            if npar <= n - 1 and not (pos and np.min(x) <= 0)
        ]
    else:
        if model not in models:
            raise ValueError(f"model must be one of {list(models)} or 'auto'.")
        func, npar, pos = models[model]
        if pos and np.min(x) <= 0:
            raise ValueError(f"model '{model}' requires strictly positive x values.")
        candidates = [model]

    sst = float(np.sum((y - y.mean()) ** 2))
    results = {}
    for name in candidates:
        func, npar, _ = models[name]
        names = [p for p in inspect.signature(func).parameters if p != "x"]
        p0, bounds = _growth_p0_bounds(name, x, y)
        try:
            popt, pcov = curve_fit(func, x, y, p0=p0, bounds=bounds, maxfev=20000)
        except Exception:
            continue
        yhat = func(x, *popt)
        sse = float(np.sum((y - yhat) ** 2))
        if not np.isfinite(sse):
            continue
        perr = (np.sqrt(np.diag(pcov)) if pcov is not None and np.all(np.isfinite(pcov))
                else np.full(npar, np.nan))
        results[name] = {
            "func": func, "names": names, "popt": popt, "perr": perr,
            "r2": (1.0 - sse / sst) if sst > 0 else float("nan"),
            "aic": _aic_least_squares(sse, n, npar),
        }
    if not results:
        raise RuntimeError("All growth-curve fits failed for the given data.")

    best_name = min(results, key=lambda k: results[k]["aic"]) if model == "auto" else candidates[0]
    best = results[best_name]
    params_out = {
        nm: {"value": float(v), "stderr": float(e)}
        for nm, v, e in zip(best["names"], best["popt"], best["perr"])
    }
    func = best["func"]
    popt = best["popt"]
    return {
        "model": best_name,
        "params": params_out,
        "r_squared": float(best["r2"]),
        "aic": float(best["aic"]),
        "n": int(n),
        "predict": (lambda xx, _f=func, _p=popt: np.asarray(_f(np.asarray(xx, float), *_p), float)),
        "all_models": {k: {"aic": float(v["aic"])} for k, v in results.items()},
    }


# ── Outlier detection ────────────────────────────────────────────────
def iqr_bounds(values, k=1.5):
    """Tukey IQR fence ``(lower, upper)``; ``(nan, nan)`` for <4 finite values.

    A value below ``lower`` or above ``upper`` is an IQR outlier. ``k=1.5`` is the
    classic Tukey fence; ``k=3`` flags only "far" outliers.
    """
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(float)
    if arr.size < 4:
        return float("nan"), float("nan")
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    return float(q1 - float(k) * iqr), float(q3 + float(k) * iqr)


def mad_modified_z(values):
    """Iglewicz-Hoaglin modified z-scores ``0.6745*(x-median)/MAD``.

    Returns a float array aligned to ``values`` (NaN where the input is non-finite
    or the median absolute deviation is zero). Uses median/MAD rather than
    mean/SD, so a single gross outlier does not mask itself. ``|z| > 3.5`` is the
    conventional flag threshold.
    """
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.full(arr.shape, np.nan)
    med = float(np.median(finite))
    mad = float(np.median(np.abs(finite - med)))
    if mad <= 0:
        return np.full(arr.shape, np.nan)
    return 0.6745 * (arr - med) / mad


def _rout_robust_center_and_rsdr(arr, *, n_params=1):
    """ROUT-style robust constant fit and robust SD of residuals."""
    arr = np.asarray(arr, float)
    arr = arr[np.isfinite(arr)]
    if arr.size <= int(n_params):
        return float("nan"), float("nan")

    center = float(np.median(arr))

    def _rsdr(residuals):
        finite = np.abs(np.asarray(residuals, float))
        finite = finite[np.isfinite(finite)]
        if finite.size <= int(n_params):
            return float("nan")
        p68 = float(np.percentile(finite, 68.27))
        df = finite.size - int(n_params)
        if df <= 0 or not np.isfinite(p68) or p68 <= 0:
            return float("nan")
        return float(p68 * finite.size / df)

    rsdr = _rsdr(arr - center)
    for _ in range(50):
        if not np.isfinite(rsdr) or rsdr <= 0:
            break
        rr = (arr - center) / rsdr
        weights = 1.0 / (1.0 + rr * rr)
        total = float(np.sum(weights))
        if not np.isfinite(total) or total <= 0:
            break
        new_center = float(np.sum(weights * arr) / total)
        if abs(new_center - center) <= 1e-10 * max(1.0, abs(center)):
            center = new_center
            break
        center = new_center
        rsdr = _rsdr(arr - center)

    return center, _rsdr(arr - center)


def rout_outlier_stats(values, *, q=1.0, n_params=1, max_fraction=0.30):
    """ROUT-style outlier flags for a one-column animal-summary vector.

    ``q`` is the maximum desired false discovery rate in percent; GraphPad
    Prism's recommended/default setting is 1%.
    """
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(float)
    flags = np.zeros(arr.shape, dtype=bool)
    pvals = np.full(arr.shape, np.nan)
    thresholds = np.full(arr.shape, np.nan)
    tvals = np.full(arr.shape, np.nan)

    finite_mask = np.isfinite(arr)
    finite = arr[finite_mask]
    n = finite.size
    if n < 3:
        return flags, pvals, thresholds, tvals, float("nan"), float("nan")

    center, rsdr = _rout_robust_center_and_rsdr(finite, n_params=n_params)
    if not np.isfinite(rsdr) or rsdr <= 0:
        return flags, pvals, thresholds, tvals, center, rsdr

    df = max(int(n - n_params), 1)
    q_fraction = max(float(q), 0.0) / 100.0
    local_t = np.abs(finite - center) / rsdr
    local_p = 2.0 * _sps.t.sf(local_t, df=df)
    local_thresholds = np.full(n, np.nan)

    order = np.argsort(local_p)
    max_candidates = max(1, int(np.floor(float(max_fraction) * n)))
    max_candidates = min(max_candidates, n)
    cutoff_rank = 0
    for rank, pos in enumerate(order[:max_candidates], start=1):
        threshold = q_fraction * rank / n
        local_thresholds[pos] = threshold
        if local_p[pos] <= threshold:
            cutoff_rank = rank

    local_flags = np.zeros(n, dtype=bool)
    if cutoff_rank:
        local_flags[order[:cutoff_rank]] = True

    finite_positions = np.flatnonzero(finite_mask)
    flags[finite_positions] = local_flags
    pvals[finite_positions] = local_p
    thresholds[finite_positions] = local_thresholds
    tvals[finite_positions] = local_t
    return flags, pvals, thresholds, tvals, center, rsdr


def flag_outliers(df, columns, *, group_labels=None, methods=("rout",),
                  iqr_k=1.5, mad_threshold=3.5, rout_q=1.0, min_rows=4):
    """Flag per-(group, column) outliers by IQR, modified-z (MAD), and/or ROUT.

    Operates on the *experimental-unit* rows of ``df`` — PyFLASH summaries are one
    row per animal, so flags are animal-level. ``group_labels`` is an optional
    mapping (df-index -> group label, e.g. a Series) so outliers are judged within
    each group; ``None`` pools all rows. IQR/MAD use ``min_rows`` finite values;
    ROUT can run with three finite values.

    Returns a tidy DataFrame, one row per flagged (group, column, df-index):
    ``group, column, row, value, iqr_outlier, mad_outlier, modified_z,
    iqr_lower, iqr_upper, rout_outlier, rout_p, rout_threshold, rout_t,
    rout_center, rout_rsdr`` (``row`` is the original df index label). Empty
    (with those columns) when nothing is flagged.
    """
    methods = [str(m).lower() for m in (methods or ())]
    use_iqr = "iqr" in methods
    use_mad = "mad" in methods
    use_rout = "rout" in methods
    if group_labels is None:
        group_labels = pd.Series("all", index=df.index)
    else:
        group_labels = pd.Series(group_labels).reindex(df.index)

    out_cols = ["group", "column", "row", "value", "iqr_outlier",
                "mad_outlier", "modified_z", "iqr_lower", "iqr_upper",
                "rout_outlier", "rout_p", "rout_threshold", "rout_t",
                "rout_center", "rout_rsdr"]
    rows = []
    for glabel in pd.unique(group_labels.dropna()):
        gidx = group_labels.index[group_labels == glabel]
        for col in columns:
            if col not in df.columns:
                continue
            s = pd.to_numeric(df.loc[gidx, col], errors="coerce").dropna()
            active_iqr = use_iqr and len(s) >= int(min_rows)
            active_mad = use_mad and len(s) >= int(min_rows)
            active_rout = use_rout and len(s) >= 3
            if not (active_iqr or active_mad or active_rout):
                continue
            arr = s.to_numpy(float)
            lower, upper = iqr_bounds(arr, iqr_k) if active_iqr else (np.nan, np.nan)
            med = float(np.median(arr))
            mad = float(np.median(np.abs(arr - med)))
            if active_rout:
                rout_flags, rout_p, rout_threshold, rout_t, rout_center, rout_rsdr = (
                    rout_outlier_stats(arr, q=rout_q)
                )
            else:
                rout_flags = np.zeros(arr.shape, dtype=bool)
                rout_p = np.full(arr.shape, np.nan)
                rout_threshold = np.full(arr.shape, np.nan)
                rout_t = np.full(arr.shape, np.nan)
                rout_center = np.nan
                rout_rsdr = np.nan
            for pos, (idx, val) in enumerate(s.items()):
                v = float(val)
                flag_iqr = bool(active_iqr and np.isfinite(lower)
                                and (v < lower or v > upper))
                mz = (0.6745 * (v - med) / mad) if (active_mad and mad > 0) else np.nan
                flag_mad = bool(active_mad and np.isfinite(mz)
                                and abs(mz) > float(mad_threshold))
                flag_rout = bool(rout_flags[pos])
                if not (flag_iqr or flag_mad or flag_rout):
                    continue
                rows.append({
                    "group": str(glabel), "column": col, "row": idx, "value": v,
                    "iqr_outlier": flag_iqr, "mad_outlier": flag_mad,
                    "modified_z": (float(mz) if np.isfinite(mz) else np.nan),
                    "iqr_lower": lower, "iqr_upper": upper,
                    "rout_outlier": flag_rout,
                    "rout_p": float(rout_p[pos]) if np.isfinite(rout_p[pos]) else np.nan,
                    "rout_threshold": (
                        float(rout_threshold[pos])
                        if np.isfinite(rout_threshold[pos]) else np.nan
                    ),
                    "rout_t": float(rout_t[pos]) if np.isfinite(rout_t[pos]) else np.nan,
                    "rout_center": (
                        float(rout_center) if np.isfinite(rout_center) else np.nan
                    ),
                    "rout_rsdr": float(rout_rsdr) if np.isfinite(rout_rsdr) else np.nan,
                })
    return pd.DataFrame(rows, columns=out_cols)
