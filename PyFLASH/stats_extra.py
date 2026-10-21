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
PyFLASH's ``batch.summary`` is already aggregated to one row per subject
(``Experiment.createSummary`` groups ROI-level rows by ``AnimalName``), so the
group lists handed to :func:`effect_sizes_for_test` are subject-level: N is the
number of subjects, and the bootstrap CI in :func:`effect_ci` resamples subjects,
respecting the true experimental unit for free.

This module deliberately reimplements the handful of effect-size / power
formulae it needs rather than taking a dependency on ``pingouin`` (GPL-3.0),
keeping PyFLASH BSD-3-Clause.
"""
from __future__ import annotations

import itertools as _itertools
import math as _math
from PyFLASH._cache import bounded_lru_cache as _lru_cache

import numpy as np
import pandas as pd
from scipy import stats as _sps


# ── Effect sizes ─────────────────────────────────────────────────────
def _standardized_effect(a, b, *, axis=None, hedges=False):
    import math
    from fractions import Fraction
    from PyFLASH._numeric_scaling import _rational_sqrt
    a, b = np.asarray(a, float), np.asarray(b, float)
    if axis is None and (a.ndim != 1 or b.ndim != 1):
        raise ValueError('Independent samples must each be one-dimensional.')
    na, nb = (len(a), len(b)) if axis is None else (a.shape[axis], b.shape[axis])
    if na < 2 or nb < 2:
        return float('nan')
    ratios = {}
    def ratio(value):
        value = float(value)
        result = ratios.get(value)
        if result is None:
            numerator, denominator = value.as_integer_ratio()
            result = numerator, denominator.bit_length()-1
            if len(ratios) < 4096:
                ratios[value] = result
        return result
    def effect(x, y):
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            return float('nan')
        rx, ry = [ratio(value) for value in x], [ratio(value) for value in y]
        exponent = max(power for _,power in rx+ry)
        ix, iy = ([numerator << (exponent-power) for numerator,power in group] for group in (rx,ry))
        sx, sy = sum(ix), sum(iy)
        within = nb*(na*sum(value*value for value in ix)-sx*sx)+na*(nb*sum(value*value for value in iy)-sy*sy)
        if not within:
            return float('nan')
        difference = nb*sx-na*sy
        numerator = difference*difference*(na+nb-2)
        denominator = na*nb*within
        if hedges:
            numerator *= (4*(na+nb)-12)**2
            denominator *= (4*(na+nb)-9)**2
        value = _rational_sqrt(Fraction(numerator,denominator))
        value = -value if difference < 0 else value
        return float('nan') if hedges and not math.isfinite(value) else value
    if axis is None:
        return effect(a,b)
    a,b=np.moveaxis(a,axis,-1),np.moveaxis(b,axis,-1)
    shape=np.broadcast_shapes(a.shape[:-1],b.shape[:-1])
    a,b=np.broadcast_to(a,shape+(na,)),np.broadcast_to(b,shape+(nb,))
    result=[effect(x,y) for x,y in zip(a.reshape(-1,na),b.reshape(-1,nb))]
    return np.asarray(result).reshape(shape)



def cohens_d(a, b) -> float:
    """Cohen's d with pooled SD for two ordered one-dimensional samples."""
    return float(_standardized_effect(a, b))


def hedges_g(a, b) -> float:
    """Small-sample corrected d for two ordered one-dimensional samples."""
    return float(_standardized_effect(a, b, hedges=True))


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
    """Exact group sums keep dimensionless effects independent of measurement scale."""
    from fractions import Fraction
    groups = [np.asarray(g, float) for g in groups if len(g) > 0]
    k = len(groups)
    if k < 2:
        return {}
    if any(group.ndim != 1 for group in groups):
        raise ValueError('Independent samples must each be one-dimensional.')
    if any(not np.isfinite(group).all() for group in groups):
        return {'eta_squared':float('nan'), 'omega_squared':float('nan')}
    groups = [list(map(Fraction, group)) for group in groups]
    n = sum(map(len, groups))
    means = [sum(group)/len(group) for group in groups]
    grand = sum(sum(group) for group in groups)/n
    between = sum(len(group)*(mean-grand)**2 for group,mean in zip(groups,means))
    within = sum(sum((value-mean)**2 for value in group) for group,mean in zip(groups,means))
    total = between+within
    eta = float(between/total) if total else float('nan')
    mean_within = within/(n-k) if n>k else None
    omega = (float((between-(k-1)*mean_within)/(total+mean_within))
             if mean_within is not None and total+mean_within else float('nan'))
    return {'eta_squared':eta, 'omega_squared':omega}


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
    """Return a conventional magnitude band for one effect size.

    ``d`` uses Cohen's (1988) standardized-difference cutoffs 0.2/0.5/0.8;
    ``r`` uses the correlation cutoffs 0.1/0.3/0.5, including rank-biserial r.
    ``eta2``, ``omega2`` and ``eps2`` use Field's (2013) 0.01/0.06/0.14.
    Negative squared-effect estimates belong in the lowest band. These are
    descriptive conventions; nonfinite values or unknown kinds return ``n/a``.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(v):
        return "n/a"
    if kind == "d":  # Cohen's d / Hedges' g
        v = abs(v)
        return ("negligible" if v < 0.2 else "small" if v < 0.5
                else "medium" if v < 0.8 else "large")
    if kind == "r":
        v = abs(v)
        return ("negligible" if v < 0.1 else "small" if v < 0.3
                else "medium" if v < 0.5 else "large")
    if kind in ("eta2", "omega2", "eps2"):
        return ("negligible" if v < 0.01 else "small" if v < 0.06
                else "medium" if v < 0.14 else "large")
    return "n/a"


def _validated_random_state(random_state):
    from numbers import Integral
    if not isinstance(random_state, (np.random.RandomState, np.random.Generator)):
        if (isinstance(random_state, (bool, np.bool_)) or not isinstance(random_state, Integral)
                or not 0 <= random_state < 2**32):
            raise ValueError("random_state must be a valid integer seed, RandomState or Generator.")
        random_state = int(random_state)
    return random_state


def _validated_effect_interval_options(eftype,n_resamples,confidence,random_state):
    from numbers import Integral, Real
    if not isinstance(eftype, str) or eftype not in {"hedges", "cohen"}:
        raise ValueError("eftype must be 'hedges' or 'cohen'.")
    if isinstance(n_resamples, (bool, np.bool_)) or not isinstance(n_resamples, Integral) or n_resamples < 1:
        raise ValueError("n_resamples must be a positive integer.")
    if (isinstance(confidence, (bool, np.bool_)) or not isinstance(confidence, Real)
            or not np.isfinite(confidence) or not 0 <= confidence <= 1):
        raise ValueError("confidence must be a finite number between zero and one.")
    if random_state is None:
        from PyFLASH.config import Config
        random_state = Config.EFFECT_CI_RANDOM_STATE
    return _validated_random_state(random_state)


def effect_ci(a, b, eftype="hedges", n_resamples=5000, confidence=0.95, *, random_state=None):
    """Animal-level BCa bootstrap CI for a two-group effect size.

    Returns ``(low, high)``; ``(nan, nan)`` when the groups are too small or
    the interval is undefined (e.g. degenerate variance or nonfinite samples).
    ``random_state`` overrides ``Config.EFFECT_CI_RANDOM_STATE`` (default 0).
    Identical inputs and settings reproduce the same subject-level draws.
    Groups must be one-dimensional. The estimator is ``hedges`` or ``cohen``;
    resample counts are positive integers and confidence lies in [0, 1].
    Integer seeds, NumPy RandomState and Generator objects are supported.
    Invalid requests raise ValueError before sampling, even for empty groups.
    """
    random_state = _validated_effect_interval_options(eftype,n_resamples,confidence,random_state)
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    if a.ndim != 1 or b.ndim != 1:
        raise ValueError("Bootstrap groups must be one-dimensional.")
    if len(a) < 2 or len(b) < 2 or not (np.isfinite(a).all() and np.isfinite(b).all()):
        return (float("nan"), float("nan"))
    try:
        res = _sps.bootstrap(
            (a, b),
            lambda x, y, axis: _standardized_effect(x, y, axis=axis, hedges=eftype == "hedges"),
            vectorized=True,
            paired=False,
            method="BCa",
            n_resamples=int(n_resamples),
            confidence_level=confidence,
            random_state=random_state,
        )
        ci = res.confidence_interval
        lo, hi = float(ci.low), float(ci.high)
        if not (np.isfinite(lo) and np.isfinite(hi)):
            return (float("nan"), float("nan"))
        return (lo, hi)
    except (ValueError, FloatingPointError):
        return (float("nan"), float("nan"))


_PARAMETRIC_TESTS = {
    "Independent T-Test",
    "Student's T-Test",
    "Welch's T-Test",
    "One-Way ANOVA",
    "Welch ANOVA",
    "Two-Way ANOVA",
}


def effect_sizes_for_test(groups, test, comparisons, ci=True, n_resamples=5000, *, random_state=None) -> dict:
    """Complete animal-level effects matching an explicitly named test.

    Parametric group tests report Hedges g; Mann-Whitney U and Kruskal-Wallis
    report rank-biserial effects. A one-way ANOVA additionally reports eta and
    omega squared, and Kruskal-Wallis reports epsilon squared. Raw groups cannot
    identify a fitted linear model's adjusted effects: that test returns empty
    overall/pairwise results with no inferred family. Comparisons are one-based
    pairs, supplied as text or an ordered sequence. Reversed and repeated pairs
    keep their requested order. Invalid test names, shapes or pairs fail before
    sampling. Nonfinite/nonnumeric observations are omitted consistently.
    CI options apply only to requested parametric bootstrap intervals.
    """
    from collections.abc import Mapping
    from PyFLASH._comparison_tokens import parse_pairs
    if isinstance(test, str) and test == "Mann-Whitney":
        test = "Mann-Whitney U"
    allowed = _PARAMETRIC_TESTS | {"Mann-Whitney U", "Kruskal-Wallis", "Linear Model"}
    if not isinstance(test, str) or test not in allowed:
        raise ValueError("test must name a supported parametric, rank or linear-model test.")
    if not isinstance(ci, (bool, np.bool_)):
        raise ValueError("ci must be a Boolean.")
    if isinstance(groups, (str, bytes, Mapping)):
        raise ValueError("groups must be an ordered sequence of one-dimensional samples.")
    try:
        raw_groups = list(groups)
    except TypeError as error:
        raise ValueError("groups must be an ordered sequence of one-dimensional samples.") from error
    normalized = []
    for group in raw_groups:
        if np.asarray(group, dtype=object).ndim != 1:
            raise ValueError("Effect groups must be one-dimensional.")
        values = pd.to_numeric(pd.Series(group), errors="coerce").to_numpy(dtype=float)
        normalized.append(values[np.isfinite(values)])
    groups = normalized
    pairs = parse_pairs(comparisons,len(groups),allow_none=True,allow_single=True,allow_self=False)
    parametric = test in _PARAMETRIC_TESTS
    if ci and parametric:
        random_state = _validated_effect_interval_options("hedges",n_resamples,.95,random_state)
    out = {"overall": {}, "pairwise": [], "family": None}
    if test == "Linear Model":
        return out
    if test == "One-Way ANOVA":
        out["overall"] = anova_effect_sizes(groups)
        out["family"] = "omega_squared"
    elif test == "Kruskal-Wallis":
        out["overall"] = {"epsilon_squared": kw_epsilon_squared(groups)}
        out["family"] = "epsilon_squared"
    for comparison,i,j in pairs:
        a,b=groups[i],groups[j]
        if parametric:
            value=hedges_g(a,b)
            low,high=(effect_ci(a,b,"hedges",n_resamples=n_resamples,random_state=random_state)
                      if ci else (float("nan"),float("nan")))
            metric,kind="hedges_g","d"
        else:
            value=rank_biserial(a,b);low=high=float("nan");metric,kind="rank_biserial_r","r"
        out["pairwise"].append({"comparison":comparison,"metric":metric,"value":value,
            "ci_low":low,"ci_high":high,"interpretation":interpret_magnitude(value,kind)})
    return out



# ── Multiplicity control ─────────────────────────────────────────────
def adjust_pvalues(pvalues, method="fdr_bh"):
    """Adjust a set of probabilities at alpha 0.05.

    ``method`` is any accepted by ``statsmodels.stats.multitest.multipletests``
    (``'fdr_bh'``, ``'fdr_by'``, ``'holm'``, ``'bonferroni'``, ``'sidak'``...).
      Returns ``(reject_list, adjusted_list)``.
    Nonfinite values remain missing and are excluded from the correction
    family. Finite probabilities must be in [0, 1]. Rejection is determined
    by the returned adjusted probability <= 0.05, including the boundary.
    """
    return _adjust_probabilities(pvalues,method,0.05)


def _adjust_probabilities(pvalues,method,alpha):
    """Shared validation and correction at the actual requested threshold."""
    from numbers import Real
    from statsmodels.stats.multitest import multipletests
    if (isinstance(alpha,(bool,np.bool_)) or not isinstance(alpha,Real)
            or not np.isfinite(alpha) or not 0<=alpha<=1):
        raise ValueError('alpha must be a finite probability in [0, 1].')

    p = np.asarray([np.nan if x is None or x is pd.NA else float(x) for x in pvalues], float)
    mask = np.isfinite(p)
    if np.any((p[mask] < 0) | (p[mask] > 1)):
        raise ValueError('Finite probabilities must lie in [0, 1].')
    adj = np.full(p.shape, np.nan)
    rej = np.zeros(p.shape, bool)
    if mask.sum() > 0:
        # Valid probability-one endpoints have log1p(-1)/division-by-zero
        # limits in upstream Sidak/GBS formulas. Suppress only that local,
        # verified endpoint warning; package-wide warnings remain enabled.
        with np.errstate(divide='ignore'):
            _, a, *_ = multipletests(p[mask], method=method,alpha=alpha)
            normalized = method.lower()
            if normalized in {'s','sidak'} and mask.sum()==1:
                a = p[mask].copy()  # A one-test correction is exactly identity.
            elif normalized in {'hs','holm-sidak'}:
                order = np.argsort(p[mask])
                ordered = p[mask][order]
                bounds = -np.expm1(np.arange(len(ordered),0,-1)*np.log1p(-ordered))
                bounds[-1] = ordered[-1]  # Preserve the exact one-test endpoint.
                a = np.empty(len(ordered))
                a[order] = np.minimum(np.maximum.accumulate(bounds),1)
            if method.lower()=='fdr_gbs':
                # Keep integer factors together before division. Splitting
                # (m+1-i)/i introduces a verified one-ulp false non-rejection
                # at adjusted p=.1 (p=.2, i=5, m=6).
                order = np.argsort(p[mask])
                ordered = p[mask][order]
                m = len(ordered)
                rank = np.arange(1,m+1)
                bounds = (m+1-rank)*ordered/(rank*(1-ordered))
                q = np.minimum.accumulate(np.maximum.accumulate(bounds)[::-1])[::-1]
                a = np.empty(m)
                a[order] = np.minimum(q,1)
        adj[mask] = a
        rej[mask] = a <= alpha
    else:
        with np.errstate(divide='ignore'):
            multipletests([0.5], method=method,alpha=alpha)  # Validate empty families too.
    return rej.tolist(), adj.tolist()


# ── Power ────────────────────────────────────────────────────────────
def achieved_power(effect_size, n1, n2=None, alpha=0.05) -> float:
    """Two-sided independent-t power at observed integer sample counts.

    ``n1`` is at least two; explicit ``n2`` is a positive integer. ``n2=None``
    requests equal groups; numeric zero retains the legacy equal-group alias
    (it never denotes an empty observed group). Invalid counts return NaN, retaining
    this function's undefined-result convention without rounding counts.
    """
    from numbers import Real
    try:
        if isinstance(n2,(bool,np.bool_)):
            return float('nan')
        second = n1 if n2 is None or isinstance(n2,Real) and n2 == 0 else n2
        for count, minimum in ((n1,2),(second,1)):
            if (isinstance(count,(bool,np.bool_)) or not isinstance(count,Real)
                    or not np.isfinite(count) or count < minimum or count != int(count)):
                return float('nan')
        if not np.isfinite(effect_size):
            return float('nan')
        return _independent_t_power(abs(effect_size), int(n1), int(second), alpha)
    except Exception:
        return float("nan")


def _independent_t_power(effect, first, second, alpha):
    """Both rejection tails using SciPy's public noncentral-t distribution."""
    degrees = first+second-2
    if first <= 0 or second <= 0 or degrees <= 0 or not 0 <= alpha <= 1:
        return float('nan')
    critical = _sps.t.isf(alpha/2, degrees)
    noncentral = effect*_math.sqrt(first*second/(first+second))
    return float(_sps.nct.sf(critical, degrees, noncentral)+
                 _sps.nct.cdf(-critical, degrees, noncentral))


def required_n(effect_size, alpha=0.05, power=0.8) -> float:
    """Fractional per-group sample-size root for a two-sided independent t-test.

    Both rejection tails count. Round the returned root up for an integer
    design. A bracketed solver checks convergence rather than returning its
    initial guess when a large effect requires fewer than two observations.
    """
    if not np.isfinite(effect_size) or effect_size == 0:
        return float("nan")
    if not 0 < alpha < power < 1:
        return float('nan')
    try:
        from scipy.optimize import brentq
        def objective(n):
            return _independent_t_power(abs(effect_size), n, n, alpha)-power
        low, high = 2.0, 2.0
        for _ in range(48):
            value = objective(low)
            if np.isfinite(value) and value <= 0:
                break
            low = 1+(low-1)/2
        else:
            return float('nan')
        for _ in range(64):
            value = objective(high)
            if np.isfinite(value) and value >= 0:
                break
            high *= 2
        else:
            return float('nan')
        result = brentq(objective, low, high, xtol=1e-11, rtol=1e-13)
        if abs(objective(result)) > 1e-10:
            return float('nan')
        return float(result)
    except Exception:
        return float("nan")


# ── Reliability / design diagnostic ──────────────────────────────────
def icc1(roi_df, value_col, group_col="AnimalName") -> float:
    """ICC(1): fraction of total variance that is between subjects.

    Operates on **ROI-level** rows (e.g. ``experiment.data[marker].df``), not the
    subject-level summary.  High ICC (>0.3) means ROIs within a subject are
    strongly correlated, which justifies PyFLASH's aggregate-to-subject approach;
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
    Missing family names form one family rather than being skipped. Nonfinite
    probabilities remain missing and do not enter a family's size. ``alpha``
    controls both rejection and the alpha-dependent two-stage corrections.

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

    if len(labels)!=n or len(fam)!=n:
        raise ValueError('Each probability needs one label and one family.')
    _adjust_probabilities([],method,alpha)  # Validate even an empty collection.
    out = pd.DataFrame({
        "label": labels,
        "family": fam,
        "p_value": [np.nan if x is None or x is pd.NA else float(x) for x in pv],
    })
    out["p_adjusted"] = np.nan
    for indices in out.groupby('family',sort=False,dropna=False).indices.values():
        _, adj = _adjust_probabilities(out.loc[indices, "p_value"].tolist(),method,alpha)
        out.loc[indices, "p_adjusted"] = adj
    out["reject"] = out["p_adjusted"] <= float(alpha)
    return out.reset_index(drop=True)


# ── Correction calibration ───────────────────────────────────────────
# What multiple-comparison correction actually costs on one design, and a
# permutation-calibrated alternative to the closed-form conventions.
#
# The load-bearing observation: under the complete null a rank statistic
# depends only on the group sizes and the multiset of ranks, never on the
# data.  One cached computation per design signature therefore serves every
# marker, metric and figure in a batch.  Untied data always ranks 1..N, so a
# whole batch usually collapses to a single cache entry; a tied column (Count
# with repeated zeros, say) gets its own entry and is still computed once.
#
# Nothing here decides anything.  These functions report what each convention
# would say; choosing between them is left to the caller.

_CORRECTION_CONVENTIONS = (
    "uncorrected", "holm", "bh_q", "bonferroni", "sidak", "westfall_young",
)

_LADDER_METHODS = (
    ("holm", "holm"),
    ("bh_q", "fdr_bh"),
    ("bonferroni", "bonferroni"),
    ("sidak", "sidak"),
)


def _ordered_partitions(indices, sizes):
    """Every way of splitting *indices* into groups of the given *sizes*.

    Yields ``N! / prod(n_i!)`` tuples-of-tuples.  The final group is whatever
    is left over, so it is never enumerated separately.
    """
    if len(sizes) == 1:
        yield (tuple(indices),)
        return
    head, rest = sizes[0], sizes[1:]
    for first in _itertools.combinations(indices, head):
        chosen = set(first)
        remaining = [i for i in indices if i not in chosen]
        for tail in _ordered_partitions(remaining, rest):
            yield (first,) + tail


def _exact_mean_ranks(ranks, ns):
    """Mean rank per group for every possible assignment. Shape (total, k)."""
    idx = tuple(range(len(ranks)))
    rows = [
        [ranks[list(part)].sum() / n for part, n in zip(parts, ns)]
        for parts in _ordered_partitions(idx, tuple(ns))
    ]
    return np.asarray(rows, float)


def _sampled_mean_ranks(ranks, ns, n_resamples, seed):
    """Mean rank per group for *n_resamples* random assignments."""
    rng = np.random.default_rng(seed)
    perm = np.argsort(rng.random((int(n_resamples), len(ranks))), axis=1)
    drawn = ranks[perm]
    cuts = np.cumsum(ns)[:-1]
    return np.stack(
        [blk.sum(axis=1) / n for blk, n in zip(np.split(drawn, cuts, axis=1), ns)],
        axis=1,
    )


def _rank_multiset_constants(ranks):
    """Quantities the post-hoc statistics need that depend only on the ranks.

    All three are invariant under permutation - they are properties of the rank
    multiset, not of how it is split - so they are computed once per design
    rather than once per arrangement.
    """
    n = len(ranks)
    _, counts = np.unique(ranks, return_counts=True)
    tied = counts[counts > 1]
    tie_sum = float(np.sum(tied ** 3 - tied)) if tied.size else 0.0
    # scikit_posthocs uses two different tie factors, one subtractive (Dunn)
    # and one multiplicative (Conover / Nemenyi). Reproduce both exactly.
    dunn_tie = tie_sum / (12.0 * (n - 1)) if n > 1 else 0.0
    scale_tie = min(1.0, 1.0 - tie_sum / (n ** 3 - n)) if n > 1 else 1.0
    if scale_tie == 1.0:
        s_squared = n * (n + 1.0) / 12.0
    else:
        s_squared = (1.0 / (n - 1.0)) * (
            float(np.sum(np.asarray(ranks, float) ** 2))
            - n * ((n + 1.0) ** 2) / 4.0
        )
    return {"n": n, "tie_sum": tie_sum, "dunn_tie": dunn_tie,
            "scale_tie": scale_tie, "s_squared": s_squared,
            # Valid pooled midranks are half-integral. Keep their exact total
            # spread for arrangements at the zero-residual-variance boundary.
            "rank_ss_quarters": sum((int(2 * rank) - (n + 1)) ** 2 for rank in ranks)}


def _pairwise_b(ns, pairs):
    """The ``1/n_i + 1/n_j`` term, one per pair."""
    return np.array([1.0 / ns[i] + 1.0 / ns[j] for i, j in pairs], float)


def _dunn_null_pvalues(mean_ranks, ns, const, pairs):
    """Two-sided Dunn p-values, matching ``scikit_posthocs.posthoc_dunn``.

    ``z = |Rbar_i - Rbar_j| / sqrt((n(n+1)/12 - tie) * (1/n_i + 1/n_j))``
    """
    n = const["n"]
    a = n * (n + 1.0) / 12.0 - const["dunn_tie"]
    diff = np.stack([np.abs(mean_ranks[:, i] - mean_ranks[:, j])
                     for i, j in pairs], axis=1)
    sigma = np.sqrt(a * _pairwise_b(ns, pairs))[None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        z = diff / sigma
    return 2.0 * _sps.norm.sf(z)


def _conover_null_pvalues(mean_ranks, ns, const, pairs):
    """Two-sided Conover p-values, matching ``scikit_posthocs.posthoc_conover``.

    Unlike Dunn, the denominator moves with the arrangement: it carries the
    Kruskal-Wallis statistic of that same permutation, which is what makes
    Conover more powerful and what makes a Dunn null wrong for it.
    """
    n = const["n"]
    k = len(ns)
    if const['scale_tie'] == 0:
        # Every observation is tied: both the rank variance and corrected
        # omnibus statistic are undefined, as in the published post-hoc.
        return np.full((len(mean_ranks),len(pairs)),np.nan)
    ns_arr = np.asarray(ns, float)
    rank_sums = mean_ranks * ns_arr[None, :]
    # s_squared * (n - 1 - H_corrected) is the within-group rank sum
    # of squares. Center before evaluating between-group spread, avoiding
    # subtraction of the large uncentered Kruskal-Wallis terms.
    total_ss = const['rank_ss_quarters'] / 4.0
    between_ss = np.sum(ns_arr[None, :] * (mean_ranks - (n + 1.0) / 2) ** 2, axis=1)
    within_ss = total_ss - between_ss
    uncertain = np.abs(within_ss) <= 64 * np.finfo(float).eps * np.maximum(total_ss, between_ss)
    if np.any(uncertain):
        from fractions import Fraction
        for row in np.flatnonzero(uncertain):
            # Reconstruct known half-integral rank sums, then calculate the
            # residual exactly. This does not round a probability or force
            # an arbitrarily small positive residual to zero.
            exact = Fraction(const['rank_ss_quarters'], 4)
            for column, size in enumerate(ns):
                twice_sum = int(round(2 * rank_sums[row, column]))
                deviation = twice_sum - size * (n + 1)
                exact -= Fraction(deviation ** 2, 4 * size)
            within_ss[row] = float(exact)
    residual_variance = np.maximum(within_ss, 0.0) / (n - k)
    diff = np.stack([np.abs(mean_ranks[:, i] - mean_ranks[:, j])
                     for i, j in pairs], axis=1)
    denom = np.sqrt(residual_variance[:, None] * _pairwise_b(ns, pairs)[None, :])
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(denom > 0, diff / denom, np.inf)
    p = 2.0 * _sps.t.sf(np.abs(t), df=n - k)
    # A zero denominator with a zero difference is "no evidence", not "certain".
    return np.where((denom <= 0) & (diff <= 0), 1.0, p)


_NULL_STATISTICS = {
    "dunn": _dunn_null_pvalues,
    "conover": _conover_null_pvalues,
}


@_lru_cache(maxsize=64)
def _mean_rank_null_cached(group_sizes, ranks, n_resamples, exact_max, seed):
    """The expensive half: every arrangement's per-group mean rank.

    Shared across statistics, so asking for Conover after Dunn on the same
    design costs only the closed-form transform.
    """
    ns = list(group_sizes)
    rank_array = np.asarray(ranks, float)
    n_total = int(sum(ns))
    total = _math.factorial(n_total) // _math.prod(_math.factorial(n) for n in ns)
    if total <= exact_max:
        mean_ranks = _exact_mean_ranks(rank_array, ns)
        mode = "exact"
    else:
        mean_ranks = _sampled_mean_ranks(rank_array, ns, n_resamples, seed)
        mode = "sampled"
    return mean_ranks, mode, int(total)


@_lru_cache(maxsize=64)
def _permutation_null_cached(group_sizes, ranks, n_resamples, exact_max, seed,
                             statistic):
    """Cached core.  All arguments are hashable; *ranks* is a sorted tuple.

    A ``(20000, 6)`` float array is ~960 KB, so ``maxsize`` is deliberately
    small: this cache sits alongside a 288 MB batch pickle.
    """
    ns = list(group_sizes)
    mean_ranks, mode, total = _mean_rank_null_cached(
        group_sizes, ranks, n_resamples, exact_max, seed)
    pairs = [(i, j) for i in range(len(ns)) for j in range(i + 1, len(ns))]
    const = _rank_multiset_constants(np.asarray(ranks, float))
    p_null = _NULL_STATISTICS[statistic](mean_ranks, ns, const, pairs)
    p_null = np.clip(np.asarray(p_null, float), 0.0, 1.0)
    p_null.flags.writeable = False        # the cache hands out one shared array
    return {
        "p": p_null,
        "pairs": pairs,
        "mode": mode,
        "statistic": statistic,
        "n_perm": int(p_null.shape[0]),
        "n_arrangements": int(total),
    }


def permutation_null(group_sizes, ranks=None, *, statistic="dunn",
                     n_resamples=20000, exact_max=10_000, seed=0):
    """Null distribution of the pairwise rank statistics for one design.

    Returns a dict with ``p`` (an ``(n_perm, n_pairs)`` array of two-sided null
    p-values), ``pairs``, ``mode`` (``"exact"`` or ``"sampled"``),
    ``statistic``, ``n_perm`` and ``n_arrangements``.

    *statistic* must name the post-hoc that produced the observed p-values -
    ``"dunn"`` or ``"conover"``.  They do not share a denominator, and
    comparing one against the other's null would be comparing unlike things.
    Nemenyi and DSCF are unsupported: Nemenyi's p-values come from a clipped
    studentised-range approximation, and DSCF re-ranks within each pair, so
    neither is recoverable from the pooled mean ranks.

    Exhaustive enumeration is used at or below *exact_max* arrangements and
    Monte Carlo above it.  The crossover is a measured one: enumerating 34,650
    arrangements costs ~970 ms where 20,000 random draws cost ~30 ms at any
    size, so exactness is only worth buying on the small designs where
    discreteness actually bites.

    The result is cached on ``(group_sizes, sorted ranks, ...)``.  Only the
    multiset of ranks matters under the null, so every untied column of a batch
    shares one entry. Returned metadata and arrays are owned copies; the array
    is read-only. Group sizes and resample counts are positive integers;
    ``exact_max`` and ``seed`` are nonnegative integers. Explicit ranks must be
    the finite pooled midranks (including ties), not raw measurements or scaled
    scores. All-tied designs have undefined p-values, represented by NaN.
    """
    if not isinstance(statistic,str) or statistic not in _NULL_STATISTICS:
        raise ValueError(
            f"statistic must be one of {sorted(_NULL_STATISTICS)}, "
            f"not {statistic!r}")
    import operator
    def integer(value,name,minimum):
        try:
            if isinstance(value,(bool,np.bool_)):
                raise TypeError
            result = operator.index(value)
        except TypeError as exc:
            raise ValueError(f'{name} must be an integer at least {minimum}.') from exc
        if result < minimum:
            raise ValueError(f'{name} must be an integer at least {minimum}.')
        return result
    try:
        ns = tuple(integer(n,'Group size',1) for n in group_sizes)
    except TypeError as exc:
        raise ValueError('Group sizes must be an iterable of positive integers.') from exc
    if len(ns)<2:
        raise ValueError('A rank comparison requires at least two groups.')
    n_resamples = integer(n_resamples,'n_resamples',1)
    exact_max = integer(exact_max,'exact_max',0)
    seed = integer(seed,'seed',0)
    n_total = sum(ns)
    if statistic=='conover' and n_total<=len(ns):
        raise ValueError('Conover inference requires positive residual degrees of freedom.')
    if ranks is None:
        rk = tuple(float(i) for i in range(1, n_total + 1))
    else:
        try:
            values = np.asarray(tuple(ranks),dtype=float)
        except (ValueError,TypeError,OverflowError) as exc:
            raise ValueError('Ranks must be a finite one-dimensional midrank sequence.') from exc
        if values.ndim!=1 or not np.isfinite(values).all():
            raise ValueError('Ranks must be a finite one-dimensional midrank sequence.')
        rk = tuple(sorted(values.tolist()))
    if len(rk) != n_total:
        raise ValueError(
            f"ranks has {len(rk)} entries but the group sizes sum to {n_total}")
    if ranks is not None:
        position = 0
        for rank,count in _itertools.groupby(rk):
            size = sum(1 for _ in count)
            expected = position+(size+1)/2
            if rank!=expected:
                raise ValueError('Ranks must contain the pooled midranks implied by their ties.')
            position += size
    cached = _permutation_null_cached(ns,rk,n_resamples,exact_max,seed,statistic)
    result = {**cached,'pairs':list(cached['pairs']),'p':cached['p'].copy()}
    result['p'].flags.writeable = False
    return result


def attainable_p_floor(group_sizes, ranks=None, **kw):
    """Smallest p-value this design is physically capable of producing.

    Measured on the same scale the chosen post-hoc reports (Dunn's normal
    approximation by default), not on the exact permutation scale. The two differ, and
    the difference decides cases: a 3-vs-3 comparison has only 20 possible
    arrangements, so its *exact* two-sided floor is 0.10, but the Dunn p for
    that most extreme arrangement is 0.0495.  Uncorrected it can therefore just
    reach significance; under Bonferroni at 0.0167 it cannot, whatever the
    biology.

    A floor above the threshold in force means a non-significant result is
    uninformative rather than negative.
    """
    return float(permutation_null(group_sizes, ranks, **kw)["p"].min())


def correction_ladder(pvalues):
    """Every closed-form correction convention for one family of p-values.

    No permutations, so this is free and valid on every test path regardless of
    how the p-values were produced.  Delegates to :func:`adjust_pvalues`.
    """
    p = [float(x) for x in pvalues]
    out = {"uncorrected": p}
    for key, method in _LADDER_METHODS:
        _, adj = adjust_pvalues(p, method=method)
        out[key] = [float(v) for v in adj]
    return out


def westfall_young(pvalues,null):
    """Westfall-Young step-down minP over a supplied finite null distribution.

    Return the ordered step-down empirical probabilities from the same joint
    permutations for all tests. This uses probability minima, not maxT test
    statistics. Missing observed tests remain missing and are excluded from the
    retained family; each retained test requires finite null probabilities.
    The null must have matching columns and at least one permutation.

    Valid family-wise inference additionally needs an exchangeable sampling
    design and the relevant subset-pivotality assumptions. This calculation
    alone does not establish either. With ``mode='sampled'``, include the
    observed arrangement: probabilities are ``(count + 1) / (rows + 1)``.
    ``mode='exact'`` and an omitted mode use the supplied finite distribution
    directly. A sampled tail never establishes a zero underlying probability.
    """
    try:
        p=np.asarray(list(pvalues),float)
        p_null=np.asarray(null['p'],float)
    except (TypeError,ValueError,KeyError) as exc:
        raise ValueError('Provide observed probabilities and a numeric null matrix.') from exc
    if p.ndim!=1 or p_null.ndim!=2 or p_null.shape[1]!=len(p):
        raise ValueError('Observed probabilities and null columns must have matching dimensions.')
    if np.any(np.isinf(p)) or np.any(np.isfinite(p)&((p<0)|(p>1))):
        raise ValueError('Observed probabilities must be in [0, 1] or missing.')
    mode = null.get('mode', 'empirical')
    if mode not in ('empirical', 'exact', 'sampled'):
        raise ValueError('Null mode must be empirical, exact or sampled.')
    if not len(p): return []
    if not p_null.shape[0]: raise ValueError('The null must contain at least one permutation.')
    valid=np.isfinite(p)
    selected=p_null[:,valid]
    if not np.all(np.isfinite(selected)) or np.any((selected<0)|(selected>1)):
        raise ValueError('Every retained test needs finite null probabilities in [0, 1].')
    adj=np.full(len(p),np.nan)
    order=np.flatnonzero(valid)[np.argsort(p[valid],kind='stable')]
    running=0.
    for step,idx in enumerate(order):
        remaining=order[step:]
        count=np.count_nonzero(p_null[:,remaining].min(axis=1)<=p[idx])
        plus=int(mode=='sampled')
        raw=float((count+plus)/(p_null.shape[0]+plus))
        running=max(running,raw)
        adj[idx]=running
    return adj.tolist()


def _align_null_columns(p_null, null_pairs, pairs):
    """Reorder null columns onto the observed comparison order.

    The null is built in a fixed pair order; the caller reports comparisons in
    whatever order the figure uses.  With equal group sizes the columns are
    exchangeable and this is a no-op, but with unequal sizes each pair has its
    own standard error, so a mismatch would quietly compare one pair against
    another pair's null.  Returns ``None`` when the two sets do not correspond.
    """
    def canonical_pair(pair):
        indices = list(pair)
        if len(indices) != 2 or any(
                isinstance(i, (bool, np.bool_)) or
                not isinstance(i, (int, np.integer)) or i < 0 for i in indices):
            raise ValueError('Comparison indices must be nonnegative integers.')
        if indices[0] == indices[1]:
            raise ValueError('A comparison needs two distinct groups.')
        return tuple(sorted(int(i) for i in indices))
    try:
        declared = [canonical_pair(pair) for pair in null_pairs]
        wanted = declared if pairs is None else [canonical_pair(pair) for pair in pairs]
    except (TypeError, ValueError):
        return None
    if p_null.ndim != 2 or len(declared) != p_null.shape[1] or len(set(declared)) != len(declared):
        return None
    available = {pair: col for col, pair in enumerate(declared)}
    if len(set(wanted)) != len(wanted) or any(p not in available for p in wanted):
        return None
    return p_null[:, [available[p] for p in wanted]]


def value_permutation_null(groups, *, statistic="lsd", n_resamples=10000,
                           seed=0):
    """Permutation null for the pairwise ANOVA post-hocs, on observed values.

    Not cached: unlike the rank null this depends on the data, so it is one
    computation per column rather than one per design.  That is why the
    parametric paths are gated behind ``Config.CORRECTION_AUDIT = "full"`` or
    an explicit request, while the rank path is always on.

    *statistic* selects the denominator, and it must match the post-hoc that
    produced the observed p-values:

    ``"lsd"``
        Fisher LSD - ``t = |m_i - m_j| / sqrt(MSE * (1/n_i + 1/n_j))``,
        two-sided t on ``N - k`` degrees of freedom.

    Tukey and Dunnett are not offered, and the reason is cost rather than
    principle.  Reproducing Tukey means evaluating ``studentized_range.sf``
    once per draw, which is a numerical double integral costing on the order of
    a second for a handful of values - thousands of times over is out of the
    question.  Dunnett needs a multivariate-t integral with the same problem.
    Neither loses much: the studentised range and the multivariate t already
    account for comparisons that share a group, which is most of what
    Westfall-Young would add.  Fisher LSD is the path that genuinely needs it,
    because it applies no correction of its own.

    Valid only under exchangeability.  Do not use it where the groups may have
    unequal variance: permuting across groups imposes the equal variance the
    analysis was trying to avoid, which makes the null wrong rather than
    merely approximate.

    Supply at least two nonempty, finite, one-dimensional groups with positive
    residual degrees of freedom. Counts and seeds are integers. A zero pooled
    variance with equal means gives an undefined probability; distinct means
    with zero pooled variance give zero. No missing-value omission is implicit.
    """
    if statistic not in _VALUE_STATISTICS:
        raise ValueError(
            f"statistic must be one of {sorted(_VALUE_STATISTICS)}, "
            f"not {statistic!r}")
    if (isinstance(n_resamples, (bool, np.bool_)) or
            not isinstance(n_resamples, (int, np.integer)) or n_resamples < 1):
        raise ValueError('n_resamples must be a positive integer.')
    if (isinstance(seed, (bool, np.bool_)) or
            not isinstance(seed, (int, np.integer)) or seed < 0):
        raise ValueError('seed must be a nonnegative integer.')
    try:
        arrays = [np.asarray(g, float) for g in groups]
    except (TypeError, ValueError) as exc:
        raise ValueError('Provide numeric one-dimensional groups.') from exc
    if any(a.ndim != 1 or not a.size or not np.isfinite(a).all() for a in arrays):
        raise ValueError('Each group must be a nonempty finite one-dimensional vector.')
    ns = [len(a) for a in arrays]
    k = len(ns)
    if k < 2:
        raise ValueError('At least two groups are required for a value permutation null.')
    pooled = np.concatenate(arrays)
    n_total = pooled.size
    df_error = n_total - k
    if df_error <= 0 or k < 2:
        raise ValueError("not enough data for a value permutation null")

    rng = np.random.default_rng(seed)
    order = np.argsort(rng.random((int(n_resamples), n_total)), axis=1)
    draws = pooled[order]
    cuts = np.cumsum(ns)[:-1]
    blocks = np.split(draws, cuts, axis=1)
    means = np.stack([b.mean(axis=1) for b in blocks], axis=1)
    ss_within = np.sum(
        [((b - b.mean(axis=1, keepdims=True)) ** 2).sum(axis=1) for b in blocks],
        axis=0,
    )
    mse = ss_within / df_error

    pairs = [(i, j) for i in range(k) for j in range(i + 1, k)]
    b_term = np.array([1.0 / ns[i] + 1.0 / ns[j] for i, j in pairs])
    diff = np.stack([np.abs(means[:, i] - means[:, j]) for i, j in pairs],
                    axis=1)
    p_null = _VALUE_STATISTICS[statistic](diff, mse, b_term, k, df_error)
    p_null = np.clip(np.asarray(p_null, float), 0.0, 1.0)
    return {
        "p": p_null,
        "pairs": pairs,
        "mode": "sampled",
        "statistic": statistic,
        "n_perm": int(p_null.shape[0]),
        "n_arrangements": None,
    }


def _lsd_value_pvalues(diff, mse, b_term, k, df_error):
    """Fisher LSD: the pooled-MSE t-test PyFLASH's ``_run_fisher_lsd`` uses."""
    se = np.sqrt(mse[:, None] * b_term[None, :])
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, diff / se, np.where(diff > 0, np.inf, np.nan))
    return 2.0 * _sps.t.sf(np.abs(t), df_error)


_VALUE_STATISTICS = {
    "lsd": _lsd_value_pvalues,
}


def westfall_young_from_null(pvalues, null, pairs=None):
    """Adjust *pvalues* against an already-built null, aligning its columns.

    The one place either null kind - rank or value - turns into adjusted
    p-values, so the alignment rule cannot drift between them.
    """
    p_null = _align_null_columns(
        np.asarray(null["p"], float), null["pairs"], pairs)
    if p_null is None or p_null.shape[1] != len(pvalues):
        raise ValueError(
            "the permutation null does not correspond to the reported "
            "comparisons, so it cannot be used to adjust them")
    return westfall_young(pvalues, {**null, "p": p_null})


def value_westfall_young_adjusted(pvalues, groups, *, pairs=None,
                                  statistic="lsd", **kw):
    """Westfall-Young adjusted p-values from a value-permutation null."""
    null = value_permutation_null(groups, statistic=statistic, **kw)
    return westfall_young_from_null(pvalues, null, pairs)


def westfall_young_adjusted(pvalues, group_sizes, *, ranks=None, pairs=None,
                            statistic="dunn", **kw):
    """Westfall-Young adjusted p-values for a rank post-hoc.

    Builds (or reuses) the cached null for the design, aligns its columns onto
    *pairs* - the ``(i, j)`` group indices behind each reported p-value - and
    adjusts.  Raises ``ValueError`` rather than returning a number when the
    null cannot be made to correspond to the reported comparisons.
    """
    null = permutation_null(group_sizes, ranks, statistic=statistic, **kw)
    return westfall_young_from_null(pvalues, null, pairs)


def _calibration_threshold(min_p, alpha, *, sampled=False):
    """Largest representable cutoff whose finite-null CDF does not exceed alpha.

    Sampled inference includes the observed arrangement. ``None`` means no
    nonnegative cutoff is attainable. Never interpolate across a CDF jump.
    """
    plus = int(sampled)
    denominator = len(min_p) + plus
    if plus / denominator > alpha:
        return None
    boundaries, counts = np.unique(min_p, return_counts=True)
    probabilities = (np.cumsum(counts) + plus) / denominator
    failures = np.flatnonzero(probabilities > alpha)
    if not len(failures):
        return 1.0
    boundary = float(boundaries[failures[0]])
    return float(np.nextafter(boundary, -np.inf)) if boundary > 0 else None


def _validated_correction_alpha(alpha):
    """One threshold boundary for correction audits and verdict reports."""
    try:
        alpha = float(alpha)
    except (TypeError, ValueError) as exc:
        raise ValueError('alpha must be finite and in [0, 1].') from exc
    if not np.isfinite(alpha) or not 0 <= alpha <= 1:
        raise ValueError('alpha must be finite and in [0, 1].')
    return alpha


def correction_audit(pvalues, group_sizes=None, *, ranks=None, alpha=0.05,
                     null=None, pairs=None, want_permutation=True, **kw):
    """Every correction convention for one family, plus what correction costs.

    Always returns the closed-form ladder.  Adds the permutation block when a
    null is supplied or computable - the caller decides, because on the
    parametric paths the null is per-column rather than cached per design.

    *pairs* is the 0-based ``(i, j)`` group indices behind each reported
    p-value, in reported order.  Pass it whenever the comparison order might
    differ from the null's, which is the only thing keeping unequal-sized
    groups honest.

    The permutation block reports ``alpha_star`` (the *uncorrected* p threshold
    whose supplied-distribution family-wise error rate does not exceed *alpha*),
    what Bonferroni uses instead, their empirical error rates, and the raw p
    floor. Cutoffs use ``p <= threshold``. Sampling includes the observed
    arrangement; ``alpha_star=None`` means no attainable nonnegative cutoff.
    These are properties of the supplied null, not a proof of its sampling
    assumptions or its error rate in the underlying population.
    """
    alpha = _validated_correction_alpha(alpha)
    audit = {"alpha": alpha, **correction_ladder(pvalues)}
    if want_permutation and null is None and group_sizes is not None:
        null = permutation_null(group_sizes, ranks, **kw)
    if null is None:
        audit["permutation"] = None
        return audit

    p_null = np.asarray(null["p"], float)
    if p_null.ndim != 2 or not p_null.shape[0]:
        raise ValueError('Provide a nonempty two-dimensional null matrix.')
    k = p_null.shape[1]
    if k != len(audit["uncorrected"]):
        # The null covers a different family than the one reported; publishing
        # its numbers here would silently compare unlike things.
        audit["permutation"] = None
        audit["skipped"] = (
            f"null covers {k} comparisons but "
            f"{len(audit['uncorrected'])} were reported"
        )
        return audit

    aligned = _align_null_columns(p_null, null["pairs"], pairs)
    if aligned is None:
        audit["permutation"] = None
        audit["skipped"] = "reported comparisons do not match the null design"
        return audit
    p_null = aligned
    null = {**null, "p": p_null}

    audit["westfall_young"] = westfall_young(audit['uncorrected'], null)
    valid = np.isfinite(audit['uncorrected'])
    if not np.any(valid):
        audit['permutation'] = None
        audit['skipped'] = 'no finite observed comparisons to calibrate'
        return audit
    p_null = p_null[:, valid]
    k = p_null.shape[1]
    min_p = p_null.min(axis=1)
    mode = null.get('mode', 'empirical')
    n_perm = p_null.shape[0]
    declared_count = null.get('n_perm', n_perm)
    if (isinstance(declared_count, (bool, np.bool_)) or
            not isinstance(declared_count, (int, np.integer)) or declared_count != n_perm):
        raise ValueError('n_perm must equal the number of supplied null rows.')
    sampled = mode == 'sampled'
    audit["permutation"] = {
        "mode": mode,
        "n_perm": n_perm,
        "n_arrangements": null.get("n_arrangements"),
        # Spacing of the finite-null probability grid. Sampled inference has
        # this strictly positive floor because the observed arrangement is
        # included; an empirical/exact CDF may also evaluate to zero off-support.
        "p_resolution": 1.0 / (n_perm + int(sampled)),
        "p_floor": float(p_null.min()),
        "fwer_if_uncorrected": float((min_p <= alpha).mean()),
        "fwer_of_bonferroni": float((min_p <= alpha / k).mean()),
        "alpha_star": _calibration_threshold(min_p, alpha, sampled=sampled),
        "alpha_bonferroni": float(alpha / k),
    }
    return audit



def verdict_changes(audit, comparisons=None, alpha=0.05):
    """Which correction conventions call each comparison significant.

    An empty list means the design never reached significance under any
    convention; a full list means the choice of correction was irrelevant.
    Anything in between is a result that depends on a convention rather than on
    the data, which is the case worth flagging.

    Compares each adjusted p against *alpha*, never against ``alpha_star`` -
    ``alpha_star`` is a threshold for *uncorrected* p, and mixing the two is the
    easiest mistake available here.  The calibrated verdict is reported
    separately as its own ``calibrated`` convention.

    Return one entry per comparison. Display labels, including generated
    defaults, must be unique; ``alpha`` must be finite and in [0, 1].
    """
    alpha = _validated_correction_alpha(alpha)
    keys = [k for k in _CORRECTION_CONVENTIONS if audit.get(k)]
    n = len(audit.get("uncorrected") or [])
    labels = list(comparisons) if comparisons is not None else []
    output_labels = [str(labels[i]) if i < len(labels) else str(i + 1) for i in range(n)]
    if len(set(output_labels)) != n:
        raise ValueError('Comparison display labels must be unique in a verdict report.')
    perm = audit.get("permutation") or {}
    alpha_star = perm.get("alpha_star")
    out = {}
    for i in range(n):
        label = output_labels[i]
        names = [k for k in keys
                 if np.isfinite(float(audit[k][i])) and float(audit[k][i]) <= alpha]
        if alpha_star is not None:
            raw = float(audit["uncorrected"][i])
            if np.isfinite(raw) and raw <= float(alpha_star):
                names.append("calibrated")
        out[label] = names
    return out


# ── Many-to-one (treatment vs control) ───────────────────────────────
def dunnett_vs_control(groups, labels=None, control=0, alternative="two-sided", *, random_state=0):
    """Complete Dunnett single-step comparisons of treatments with one control.

    Uses the pooled within-group variance and the common-control multivariate-t
    distribution. Adaptive Gaussian/chi conditional integration avoids seeded
    randomized quadrature error. ``random_state`` remains accepted and validated
    for compatibility; deterministic integration does not consume its draws.
    Groups are one-dimensional ordered samples; nonfinite/nonnumeric observations
    are omitted. Every group must retain an observation and pooled residual degrees
    of freedom must be positive. Labels must be unique after display conversion.
    Control is a zero-based integer index or a display label. Returns the ordered
    DataFrame ``comparison, statistic, p_value``. Zero residual-variance statistics
    retain the signed-infinite/undefined limits of the declared pooled test.
    """
    import math
    from numbers import Integral
    from collections.abc import Mapping
    from PyFLASH._dunnett import _probability
    if not isinstance(alternative,str) or alternative not in {"two-sided","greater","less"}:
        raise ValueError("alternative must be two-sided, greater or less.")
    _validated_random_state(0 if random_state is None else random_state)
    if isinstance(groups,(str,bytes,Mapping)):
        raise ValueError("groups must be an ordered sequence of one-dimensional samples.")
    try:raw=list(groups)
    except TypeError as error:raise ValueError("groups must be an ordered sequence of samples.") from error
    if len(raw)<2:raise ValueError("Need a control and at least one treatment group.")
    normalized=[]
    for group in raw:
        if np.asarray(group,dtype=object).ndim!=1:raise ValueError("Dunnett groups must be one-dimensional.")
        values=pd.to_numeric(pd.Series(group),errors="coerce").to_numpy(dtype=float)
        values=values[np.isfinite(values)]
        if not len(values):raise ValueError("Every Dunnett group must retain a finite observation.")
        normalized.append(values)
    groups=normalized
    if labels is None:labels=[str(i+1) for i in range(len(groups))]
    else:
        if isinstance(labels,(str,bytes,Mapping)):raise ValueError("labels must be an ordered sequence.")
        try:labels=list(labels)
        except TypeError as error:raise ValueError("labels must be an ordered sequence.") from error
        if np.asarray(labels,dtype=object).ndim!=1:raise ValueError("labels must be one-dimensional.")
        labels=[str(label) for label in labels]
    if len(labels)!=len(groups):raise ValueError("labels and groups must have the same length.")
    if len(set(labels))!=len(labels):raise ValueError("Dunnett display labels must be unique.")
    if isinstance(control,str):
        if control not in labels:raise ValueError("Control label is absent from groups.")
        ci=labels.index(control)
    elif isinstance(control,(bool,np.bool_)) or not isinstance(control,Integral):
        raise ValueError("control must be an integer index or display label.")
    else:ci=int(control)
    if not 0<=ci<len(groups):raise ValueError("Control index is out of range.")
    sizes=[len(group) for group in groups];df=sum(sizes)-len(groups)
    if df<=0:raise ValueError("Dunnett needs positive pooled residual degrees of freedom.")
    from PyFLASH._numeric_scaling import _power_of_two_scale
    groups = list(_power_of_two_scale(*groups))
    means=[math.fsum(float(value) for value in group)/len(group) for group in groups]
    error=math.fsum((float(value)-mean)**2 for group,mean in zip(groups,means) for value in group)
    residual_sd=math.sqrt(error/df)
    treatment=[i for i in range(len(groups)) if i!=ci]
    treatment_sizes=tuple(sizes[i] for i in treatment)
    rows=[]
    for i in treatment:
        difference=means[i]-means[ci]
        statistic=(difference/(residual_sd*math.sqrt(1/sizes[i]+1/sizes[ci]))
            if residual_sd>0 else math.copysign(math.inf,difference) if difference else math.nan)
        probability=_probability(float(statistic),treatment_sizes,sizes[ci],df,alternative)
        if math.isfinite(probability):probability=min(1.,max(0.,probability))
        rows.append({"comparison":labels[i]+" vs "+labels[ci],
                     "statistic":float(statistic),"p_value":float(probability)})
    return pd.DataFrame(rows,columns=["comparison","statistic","p_value"])



# ── Proportions / counts ─────────────────────────────────────────────
def proportion_test(table, force=None):
    """Chi-square test of independence, with automatic Fisher's exact fallback.

    For comparing proportions (e.g. % marker-positive cells, fraction of subjects
    with plaques) across conditions.  ``table`` is a contingency table of counts
    (DataFrame or 2D array).  Fisher's exact is used for a 2x2 table when any
    expected cell < 5 (or ``force='fisher'``); ``force='chi2'`` keeps chi-square.

    Counts must be finite, nonnegative integers, with positive row and column
    totals. Invalid counts or an unknown ``force`` raise ``ValueError`` rather
    than silently truncating a fractional count or selecting another method.
    Returns ``{test, statistic, p_value, dof, expected}``.
    """
    if force not in (None, 'chi2', 'fisher'):
        raise ValueError("force must be None, 'chi2' or 'fisher'.")
    arr = np.asarray(pd.DataFrame(table).to_numpy() if not isinstance(table, np.ndarray) else table, float)
    arr = np.atleast_2d(arr)
    if arr.ndim != 2 or arr.shape[0] < 2 or arr.shape[1] < 2:
        raise ValueError("Contingency table must be at least 2x2.")
    if not np.isfinite(arr).all() or (arr < 0).any() or (arr != np.floor(arr)).any():
        raise ValueError('Contingency counts must be finite nonnegative integers.')
    if (arr.sum(axis=0) == 0).any() or (arr.sum(axis=1) == 0).any():
        raise ValueError('Contingency rows and columns must have positive totals.')

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
    """Trapezoidal area under the time-course, one value per subject.

    Collapses a longitudinal series to a single scalar per subject (total
    exposure), sidestepping pseudoreplication for the downstream group test.
    ``time_map`` (e.g. ``{'WeekTwo': 2, 'WeekEight': 8}``) maps a categorical
    time factor to numbers; otherwise numeric values or the first numeric
    substring are used. Unresolved or nonfinite times/values and missing subject
    or group keys are omitted. Subjects with fewer than two usable measurements
    produce no row. Duplicate times retain the original measurement order;
    their zero-width intervals contribute zero. ``baseline`` must be finite.

    Returns a DataFrame with ``animal_col, [group_col,] auc``, preserving these
    columns even when no subject has enough usable measurements.
    """
    work = df.copy()
    work["_t"] = _resolve_numeric_time(work[time_col], time_map)
    work["_v"] = pd.to_numeric(work[value_col], errors="coerce")
    if baseline is not None:
        if not np.isfinite(float(baseline)):
            raise ValueError("baseline must be finite")
        work["_v"] = work["_v"] - float(baseline)
    work = work.loc[np.isfinite(work["_t"]) & np.isfinite(work["_v"])]

    keys = [animal_col] + ([group_col] if group_col else [])
    rows = []
    grouped = work.groupby(keys) if len(keys) > 1 else work.groupby(animal_col)
    for key, g in grouped:
        g = g.sort_values("_t", kind="stable")
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
    return pd.DataFrame(rows, columns=keys + ["auc"])


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
        # Increasing signals may accelerate or approach a plateau; direction
        # alone cannot determine the exponential rate. Estimate curvature from
        # neighbouring slopes, then initialize amplitude with its proper sign.
        widths = np.diff(x)
        changes = np.diff(y)
        usable = widths > 0
        slopes = changes[usable]/widths[usable]
        centres = ((x[1:]+x[:-1])/2)[usable]
        direction = np.sign(y[-1]-y[0]) or 1.0
        coherent = np.isfinite(slopes) & (direction*slopes > 0)
        span = xmax-xmin
        rate = direction/max(span, 1.0)
        if np.count_nonzero(coherent) >= 2 and np.ptp(centres[coherent]) > 0:
            centre = centres[coherent]
            log_slope = np.log(np.abs(slopes[coherent]))
            centred = centre-centre.mean()
            estimate = float(centred@(log_slope-log_slope.mean())/(centred@centred))
            if np.isfinite(estimate) and abs(estimate)*max(span, 1.0) > 1e-3:
                rate = estimate
        slope = float(np.median(slopes[coherent])) if np.any(coherent) else direction
        amplitude = slope/rate * np.exp(-rate*float(np.median(x)))
        offset = float(np.median(y))-amplitude*np.exp(rate*float(np.median(x)))
        return [amplitude, rate, offset], (-np.inf, np.inf)
    if name == "logistic":
        p0 = [float(y[0]), float(y[-1]) if ymax > ymin else ymin + 1.0, max(1e-9, ((xmin + xmax) / 2.0) or 1.0), 1.0]
        lb = [-np.inf, -np.inf, 1e-9, 0.1]
        ub = [np.inf, np.inf, np.inf, 10.0]
        return p0, (lb, ub)
    return None, (-np.inf, np.inf)


def _aic_least_squares(sse, n, k):
    """AIC for a least-squares fit (Gaussian errors)."""
    if sse <= 0 or n <= 0:
        return -np.inf
    return float(n * np.log(sse / n) + 2 * k)


def _growth_jacobian(model, x, parameters):
    """Exact first derivatives in the public parameter order."""
    x = np.asarray(x, float)
    if model == "exponential":
        amplitude, rate, offset = parameters
        exponential = np.exp(rate*x)
        return np.column_stack([exponential, amplitude*x*exponential, np.ones_like(x)])
    bottom, top, ec50, hill = parameters
    q = (ec50/x)**hill
    fraction = 1/(1+q)
    scale = (top-bottom)*q/(1+q)**2
    return np.column_stack([1-fraction, fraction, -scale*hill/ec50,
                            -scale*np.log(ec50/x)])


def fit_growth_curve(x, y, model="auto"):
    """Fit a growth/decay curve to (x, y) with parameter uncertainties.

    Models: ``'linear'``, ``'exponential'``, ``'logistic'`` (4-parameter), or
    ``'auto'`` (best by AIC among models with enough residual degrees of
    freedom).  Uses ``scipy.optimize.curve_fit``; parameter standard errors come
    from the local unconstrained covariance matrix. When a parameter reaches
    a bound, these standard errors are undefined. An explicitly requested
    saturated model can return identified parameters, with undefined standard
    errors and AIC because residual variance has no remaining degrees of freedom.

    Returns ``{model, params:{name:{value,stderr}}, r_squared, aic, n,
    predict(callable), all_models}``.
    """
    import inspect
    from scipy.optimize import curve_fit, least_squares

    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if x.ndim != 1 or y.ndim != 1 or len(x) != len(y):
        raise ValueError("Growth inputs must be equal-length one-dimensional arrays.")
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    order = np.argsort(x)
    x, y = x[order], y[order]
    n = len(x)
    if n < 3:
        raise ValueError("Need >= 3 finite (x, y) points to fit a growth curve.")

    models = _growth_models()
    if not isinstance(model, str):
        raise ValueError("Growth model must be a model name.")
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
        if len(np.unique(x)) < npar:
            continue
        names = [p for p in inspect.signature(func).parameters if p != "x"]
        p0, bounds = _growth_p0_bounds(name, x, y)
        try:
            if name == "linear":
                # This model is linear in its parameters. Solving it directly
                # avoids approximate finite-difference covariance estimates.
                design = np.column_stack([x, np.ones(n)])
                popt, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
                if rank < 2:
                    continue
                # An exact affine witness is checked in rational arithmetic:
                # zero residuals must not become a finite AIC through solver noise.
                from fractions import Fraction
                xx = [Fraction(float(value)) for value in x]
                yy = [Fraction(float(value)) for value in y]
                other = next(i for i in range(1, n) if xx[i] != xx[0])
                slope = (yy[other] - yy[0])/(xx[other] - xx[0])
                intercept = yy[0] - slope*xx[0]
                exact_affine = all(value == slope*time + intercept for time,value in zip(xx,yy))
                if exact_affine:
                    popt = np.asarray([float(slope),float(intercept)])
                    residual = np.zeros(n)
                else:
                    residual = y - design @ popt
                pcov = (residual @ residual)/(n-2) * np.linalg.inv(design.T @ design)
            else:
                jac = lambda xx, *theta: _growth_jacobian(name, xx, theta)
                starts = [p0]
                fits = []
                for initial in starts:
                    try:
                        parameters, _ = curve_fit(func, x, y, p0=initial, bounds=bounds,
                            jac=jac, maxfev=20000, ftol=1e-13, xtol=1e-13, gtol=1e-13)
                        error = float(np.sum((y-func(x, *parameters))**2))
                        # Bounded solvers can stop when the change in cost is
                        # below floating-point resolution, before parameters
                        # are stationary. Polish interior fits with their exact
                        # Jacobian; never accept a bound violation or worse fit.
                        lower, upper = (np.broadcast_to(np.asarray(bound, float), parameters.shape)
                                        for bound in bounds)
                        # Only coordinates indistinguishable from a finite bound
                        # at machine precision are treated as constrained.
                        active_lower = np.isfinite(lower) & np.isclose(parameters, lower, rtol=8*np.finfo(float).eps, atol=0.)
                        active_upper = np.isfinite(upper) & np.isclose(parameters, upper, rtol=8*np.finfo(float).eps, atol=0.)
                        active = active_lower | active_upper
                        parameters[active_lower] = lower[active_lower]
                        parameters[active_upper] = upper[active_upper]
                        free = np.flatnonzero(~active)
                        if not np.any(active) and np.all(parameters > lower) and np.all(parameters < upper):
                            polished = least_squares(lambda theta: func(x, *theta)-y,
                                parameters, jac=lambda theta: jac(x, *theta), method="lm",
                                max_nfev=100, ftol=1e-15, xtol=1e-15, gtol=1e-15)
                            trial = polished.x
                            trial_error = float(np.sum((y-func(x, *trial))**2))
                            original_gradient = np.linalg.norm(jac(x, *parameters).T@(func(x, *parameters)-y))
                            trial_gradient = np.linalg.norm(jac(x, *trial).T@(func(x, *trial)-y))
                            resolution = 16*np.finfo(float).eps*max(1.0, error)
                            if (np.all(trial >= lower) and np.all(trial <= upper)
                                    and trial_error <= error + resolution
                                    and trial_gradient <= original_gradient):
                                parameters, error = trial, trial_error
                        # Cost changes can round away before the parameters
                        # become stationary. Complex-step derivatives of the
                        # analytic residual score give a stable local Hessian.
                        for _ in range(12):
                            residual = func(x, *parameters) - y
                            matrix = jac(x, *parameters)
                            gradient = matrix.T @ residual
                            hessian = np.empty((npar, npar))
                            for column in range(npar):
                                shifted = np.asarray(parameters, dtype=complex)
                                shifted[column] += 1j * 1e-20
                                shifted_gradient = jac(x, *shifted).T @ (func(x, *shifted) - y)
                                hessian[:, column] = shifted_gradient.imag / 1e-20
                            hessian = (hessian + hessian.T) / 2
                            try:
                                restricted = hessian[np.ix_(free, free)]
                                np.linalg.cholesky(restricted)
                                step = np.zeros(npar)
                                step[free] = np.linalg.solve(restricted, gradient[free])
                            except np.linalg.LinAlgError:
                                break
                            trial = parameters - step
                            if not (np.all(trial >= lower) and np.all(trial <= upper)):
                                break
                            trial_error = float(np.sum((y - func(x, *trial)) ** 2))
                            trial_gradient = jac(x, *trial).T @ (func(x, *trial) - y)
                            if (not np.isfinite(trial_error)
                                    or trial_error > error + 16*np.finfo(float).eps*max(1.0, error)
                                    or np.linalg.norm(trial_gradient[free]) > np.linalg.norm(gradient[free])):
                                break
                            parameters, error = trial, trial_error
                            if np.max(np.abs(step)/(1 + np.abs(parameters))) <= 8*np.finfo(float).eps:
                                break
                        if np.isfinite(error):
                            fits.append((error, parameters, bool(np.any(active))))
                    except (RuntimeError, ValueError, FloatingPointError):
                        continue
                if not fits:
                    continue
                error, popt, bound_active = min(fits, key=lambda entry: entry[0])
                matrix = jac(x, *popt)
                inverse, _, rank, _ = np.linalg.lstsq(matrix, np.eye(n), rcond=None)
                if rank < npar:
                    continue
                pcov = ((inverse @ inverse.T)*error/(n-npar)
                        if n > npar and not bound_active else None)
        except (RuntimeError, ValueError, FloatingPointError, np.linalg.LinAlgError):
            continue
        yhat = func(x, *popt)
        sse = 0.0 if name == "linear" and exact_affine else float(np.sum((y - yhat) ** 2))
        if not np.isfinite(sse):
            continue
        perr = (np.sqrt(np.diag(pcov)) if pcov is not None and np.all(np.isfinite(pcov))
                else np.full(npar, np.nan))
        results[name] = {
            "func": func, "names": names, "popt": popt, "perr": perr,
            "r2": (1.0 - sse / sst) if sst > 0 else float("nan"),
            "aic": _aic_least_squares(sse, n, npar) if n > npar else float("nan"),
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
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(float)
    arr = arr[np.isfinite(arr)]
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
    result = np.full(arr.shape, np.nan)
    valid = np.isfinite(arr)
    result[valid] = 0.6745 * (arr[valid] - med) / mad
    return result


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


def _validated_outlier_parameters(**parameters):
    """Validate explicit outlier settings before inspecting or fitting data."""
    from numbers import Integral, Real
    checked = {}
    for name, value in parameters.items():
        if name in {"n_params", "min_rows"}:
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
            checked[name] = int(value)
            continue
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not _math.isfinite(value):
            raise ValueError(f"{name} must be a finite real number.")
        if name == "q" and not 0 <= value <= 100:
            raise ValueError("q must be between zero and 100 percent.")
        if name == "max_fraction" and not 0 < value <= 1:
            raise ValueError("max_fraction must be greater than zero and at most one.")
        if name in {"iqr_k", "mad_threshold"} and value < 0:
            raise ValueError(f"{name} must be nonnegative.")
        checked[name] = float(value)
    return checked


def rout_outlier_stats(values, *, q=1.0, n_params=1, max_fraction=0.30):
    """ROUT-style outlier flags for a one-column animal-summary vector.

    ``q`` is the maximum desired false discovery rate in percent; GraphPad
    Prism's recommended/default setting is 1%. This constant-fit IRLS variant
    is not an implementation of Prism's nonlinear robust fitting procedure.
    The candidate count is floor(max_fraction * N), with at least one.
    Equal-probability candidates keep their input order. All six output fields
    retain the original input positions, including omitted observations.
    Invalid settings raise ValueError even when the data are empty.
    """
    settings = _validated_outlier_parameters(q=q, n_params=n_params, max_fraction=max_fraction)
    q, n_params, max_fraction = (settings[name] for name in ("q", "n_params", "max_fraction"))
    if np.asarray(values, dtype=object).ndim != 1:
        raise ValueError("Outlier values must be one-dimensional.")
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
    q_fraction = q / 100.0
    local_t = np.abs(finite - center) / rsdr
    local_p = 2.0 * _sps.t.sf(local_t, df=df)
    local_thresholds = np.full(n, np.nan)

    order = np.argsort(local_p, kind="stable")
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
    row per subject, so flags are subject-level. ``group_labels`` is an optional
    mapping (df-index -> group label, e.g. a Series), or a positional sequence,
    so outliers are judged within each group; ``None`` pools all rows. IQR/MAD use ``min_rows`` finite values;
    ROUT can run with three finite values.

    Returns a tidy DataFrame, one row per flagged (group, column, df-index):
    ``group, column, row, value, iqr_outlier, mad_outlier, modified_z,
    iqr_lower, iqr_upper, rout_outlier, rout_p, rout_threshold, rout_t,
    rout_center, rout_rsdr`` (``row`` is the original df index label). Empty
    (with those columns) when nothing is flagged. A single column or method
    may be supplied as text. Invalid settings, missing selected columns,
    duplicate subject identities and ambiguous group labels raise ValueError.
    """
    from collections.abc import Mapping
    if not isinstance(df, pd.DataFrame) or not df.index.is_unique or not df.columns.is_unique:
        raise ValueError("Outlier data must be a DataFrame with unique subject rows and columns.")
    if isinstance(columns, str):
        columns = [columns]
    else:
        try:
            columns = list(columns)
        except TypeError as error:
            raise ValueError("columns must be a column name or a sequence of names.") from error
    try:
        invalid_columns = len(set(columns)) != len(columns) or any(col not in df.columns for col in columns)
    except TypeError as error:
        raise ValueError("Selected outlier columns must be valid column names.") from error
    if invalid_columns:
        raise ValueError("Selected outlier columns must exist and occur only once.")
    from PyFLASH.aliases import _normalize_outlier_methods
    methods = _normalize_outlier_methods(methods)
    if any(not isinstance(method, str) or method.lower() not in {"iqr", "mad", "rout"} for method in methods):
        raise ValueError("methods must name IQR, MAD or ROUT.")
    methods = [method.lower() for method in methods]
    settings = _validated_outlier_parameters(iqr_k=iqr_k, mad_threshold=mad_threshold, q=rout_q, min_rows=min_rows)
    iqr_k, mad_threshold, rout_q, min_rows = (settings[name] for name in ("iqr_k", "mad_threshold", "q", "min_rows"))
    use_iqr = "iqr" in methods
    use_mad = "mad" in methods
    use_rout = "rout" in methods
    if group_labels is None:
        group_labels = pd.Series("all", index=df.index)
    elif isinstance(group_labels, (pd.Series, Mapping)):
        group_labels = pd.Series(group_labels)
        if not group_labels.index.is_unique:
            raise ValueError("Group mapping keys must be unique.")
        group_labels = group_labels.reindex(df.index)
    else:
        if np.asarray(group_labels, dtype=object).ndim != 1 or len(group_labels) != len(df):
            raise ValueError("Positional group labels must match the subject rows.")
        group_labels = pd.Series(list(group_labels), index=df.index)
    labels = pd.unique(group_labels.dropna())
    if len({str(label) for label in labels}) != len(labels):
        raise ValueError("Different groups must have different display labels.")

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
            s = s[np.isfinite(s)]
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


# ── Cosinor / rhythm analysis ────────────────────────────────────────
# A single-component cosinor is the periodic sibling of ``fit_growth_curve``:
# y = MESOR + amplitude * cos(2*pi/period * (t - acrophase)). It is period-generic
# — period=24 for a daily rhythm, 12 for a circannual (seasonal) one, or fitted
# freely for a free-running tau. Rhythm presence is the zero-amplitude F-test.
def fit_cosinor(t,y,period=24.,period_free=False,free_bounds=None):
    """Fit a single cosine; return parameters, uncertainty and predictions.

    The fixed-period fit is linear least squares with an exact F(2, n-3)
    zero-amplitude test. The free fit profiles linear coefficients over positive
    period bounds and searches all resolved minima; its F(3, n-4) test is an
    approximate omnibus test because period is unidentified under zero amplitude.
    Use fixed-period inference for an exact rhythmicity test.

    Peak time is in [0, period); a numerically absent harmonic has no peak or
    amplitude/peak standard error. Constant signals have undefined rhythmicity.
    Fits indistinguishable from exact at the least-squares backward-error bound
    have zero residual variance. At a binding period limit free-fit symmetric
    standard errors are undefined. Free bounds default to 2/3..3/2 of period.

    Requires paired one-dimensional arrays, a finite positive period, an
    identifiable sampling design, and four fixed or five free finite pairs.
    Nonfinite pairs are omitted together. Free bounds require period_free=True
    and finite positive increasing endpoints containing the initial period.
    Every params value matches its corresponding top-level field.
    """
    t=np.asarray(t,float); y=np.asarray(y,float)
    if t.ndim!=1 or y.ndim!=1 or t.shape!=y.shape:
        raise ValueError('t and y must be one-dimensional arrays of equal length.')
    if not isinstance(period_free,(bool,np.bool_)):
        raise ValueError('period_free must be a boolean.')
    period=float(period)
    if not np.isfinite(period) or period<=0:
        raise ValueError('period must be finite and positive.')
    if not period_free and free_bounds is not None:
        raise ValueError('free_bounds requires period_free=True.')
    mask=np.isfinite(t)&np.isfinite(y); t,y=t[mask],y[mask]
    k=4 if period_free else 3; n=len(t)
    if n<=k: raise ValueError(f'Need >= {k+1} finite (t, y) points to fit this cosinor.')
    # Sorting makes the estimator independent of row order at floating precision.
    order=np.argsort(t,kind='stable'); t,y=t[order],y[order]
    def profile(per):
        w=2*np.pi/per
        X=np.column_stack([np.ones(n),np.cos(w*t),np.sin(w*t)])
        beta,_,rank,_=np.linalg.lstsq(X,y,rcond=None)
        if rank!=3: raise ValueError('Sampling times do not identify both harmonic coefficients.')
        residual=y-X@beta
        derivative=(2*np.pi*t/per**2)*(beta[1]*np.sin(w*t)-beta[2]*np.cos(w*t))
        return float(residual@residual),float(-2*residual@derivative),X,beta,residual,derivative
    boundary=False
    if period_free:
        from scipy.optimize import brentq
        if free_bounds is None: lo,hi=period*2/3,period*1.5
        else:
            bounds=np.asarray(free_bounds,float)
            if bounds.shape!=(2,): raise ValueError('free_bounds must contain exactly two endpoints.')
            lo,hi=map(float,bounds)
        if not np.isfinite(lo) or not np.isfinite(hi) or not 0<lo<hi:
            raise ValueError('free_bounds must be finite, positive and increasing.')
        if not lo<=period<=hi: raise ValueError('Starting period must lie within free_bounds.')
        if np.ptp(y)==0: raise ValueError('A constant signal does not identify a free period.')
        subdivisions=max(160,int(np.ceil(16*np.ptp(t)*(1/lo-1/hi))))
        # Equal frequency steps resolve the fastest oscillations in the search.
        grid=1/np.linspace(1/hi,1/lo,subdivisions+1)[::-1]
        gradients=[profile(v)[1] for v in grid]
        candidates=[lo,hi]
        for i,(a,b) in enumerate(zip(grid,grid[1:])):
            if gradients[i]==0: candidates.append(a)
            if gradients[i]<0<gradients[i+1]:
                candidates.append(brentq(lambda v:profile(v)[1],a,b,xtol=1e-13,rtol=1e-15))
        period=min(candidates,key=lambda v:profile(v)[0])
        boundary=period in (lo,hi)
    sse,_,X,beta,residual,derivative=profile(period)
    M,b,g=map(float,beta)
    # The least-squares backward-error bound distinguishes a harmonic from
    # floating-point noise; it is relative to the supplied signal and design.
    resolution=np.finfo(float).eps*max(X.shape)*np.linalg.norm(y)*np.linalg.cond(X)
    if abs(b)<=resolution: b=0.
    if abs(g)<=resolution: g=0.
    if np.linalg.norm(residual)<=resolution: sse=0.
    if np.ptp(y)==0:
        M=float(y[0]); b=g=0.; sse=0.
    amplitude=float(np.hypot(b,g)); w=2*np.pi/period
    acrophase=float((np.arctan2(g,b)%(2*np.pi))/w) if amplitude else float('nan')
    tss=float(np.sum((y-y.mean())**2)); df=n-k
    r2=1-sse/tss if tss else float('nan')
    if tss:
        F=(max(tss-sse,0.)/(k-1))/(sse/df) if sse else float('inf')
        p=float(_sps.f.sf(F,k-1,df))
    else: F=p=float('nan')
    J=np.column_stack([X,derivative]) if period_free else X
    cov=np.full((k,k),np.nan)
    if not boundary and np.linalg.matrix_rank(J)==k:
        # SVD avoids squaring the condition number in the normal equations.
        inverse=np.linalg.pinv(J)
        cov=(sse/df)*(inverse@inverse.T)
    seM=float(np.sqrt(cov[0,0])); seA=sePhi=float('nan')
    if amplitude and np.all(np.isfinite(cov)):
        jac_amp=np.array([0,b/amplitude,g/amplitude]+([0] if period_free else []))
        jac_phase=np.array([0,-g/(amplitude**2*w),b/(amplitude**2*w)]+([acrophase/period] if period_free else []))
        seA=float(np.sqrt(max(float(jac_amp@cov@jac_amp),0.)))
        sePhi=float(np.sqrt(max(float(jac_phase@cov@jac_phase),0.)))
    def predict(tt):
        tt=np.asarray(tt,float)
        return M+b*np.cos(w*tt)+g*np.sin(w*tt)
    params={'mesor':{'value':M,'stderr':seM},'amplitude':{'value':amplitude,'stderr':seA},
            'acrophase':{'value':acrophase,'stderr':sePhi}}
    if period_free: params['period']={'value':period,'stderr':float(np.sqrt(cov[3,3]))}
    return {'model':'cosinor_free' if period_free else 'cosinor','period':period,
            'mesor':M,'amplitude':amplitude,'acrophase':acrophase,'coef_cos':b,'coef_sin':g,
            'params':params,'r_squared':float(r2),'f_stat':float(F),'p':float(p),'p_rhythm':float(p),'n':n,'predict':predict}


def _fit_cosinor_free(t, y, period0, free_bounds=None):
    """Compatibility helper; the public function owns both fitting paths."""
    return fit_cosinor(t, y, period=period0, period_free=True, free_bounds=free_bounds)


def cosinor_table(df, time_col, value_col, group_col=None, animal_col=None,
                  period=24.0, period_free=False, method="pooled", time_map=None):
    """Fit one rhythm row per group, preserving the requested sampling method.

    ``pooled`` fits all retained measurements and supports a fixed or estimated
    period. ``population_mean`` averages identifiable per-subject fixed-period
    coefficients and uses a Hotelling test; at least two subjects with four
    measurements are required. Its amplitude uncertainty includes the full
    between-subject coefficient covariance. ``mixed`` fits Gaussian maximum
    likelihood with a subject random intercept and an asymptotic joint Wald
    test. At zero random variance it uses the active fixed-model covariance;
    a design with zero within-subject noise has no finite variance solution.
    Both repeated-measure methods require ``animal_col`` and a shared fixed
    period. They never fall back to pooled sampling.

    Nonfinite time/value pairs, missing group identities, and (for repeated
    measures) missing subject identities are omitted. ``n`` counts the retained
    measurements. Distinct identities sharing a display label are rejected.
    Input rows and column labels, including numeric and scratch-like labels,
    are preserved. Every table has ``group, n, method, mesor, amplitude,
    acrophase, period, r_squared, p_rhythm, amplitude_se, acrophase_se, error``;
    population tables also have ``n_subjects``. Empty and failed tables retain
    that schema; an individual fit failure records its error and undefined
    estimates without losing other groups.

    Time conversion uses a supplied map if any label maps, otherwise numeric
    values if any convert, otherwise the first unsigned number in each label.
    Unmapped/unconvertible labels remain missing within the chosen conversion.
    """
    _validate_circular_period(period)
    if not isinstance(period_free, (bool, np.bool_)):
        raise ValueError("period_free must be a boolean.")
    if method not in ("pooled", "population_mean", "mixed"):
        raise ValueError(f"unknown method {method!r}")
    repeated = method != "pooled"
    if repeated and animal_col is None:
        raise ValueError(f"{method} requires animal_col.")
    required = [time_col, value_col]
    if group_col is not None:
        required.append(group_col)
    if repeated:
        required.append(animal_col)
    labels = list(df.columns)
    for column in required:
        if labels.count(column) != 1:
            raise ValueError(f"Required column {column!r} must occur exactly once.")
    # Read original columns before creating scratch fields. User column labels
    # may themselves be _t, _v, _grp or _animal, or a valid numeric label.
    t = _resolve_numeric_time(df[time_col], time_map).to_numpy(float, na_value=np.nan)
    y = pd.to_numeric(df[value_col], errors="coerce").to_numpy(float, na_value=np.nan)
    groups = df[group_col].to_numpy() if group_col is not None else np.repeat("all", len(df))
    animals = df[animal_col].to_numpy() if repeated else np.repeat(None, len(df))
    keep = np.isfinite(t) & np.isfinite(y) & pd.notna(groups)
    if repeated:
        keep &= pd.notna(animals)
    work = pd.DataFrame({"_t": t[keep], "_v": y[keep],
                         "_identity": groups[keep], "_animal": animals[keep]})
    work["_grp"] = work["_identity"].astype(str)
    for _, sub in work.groupby("_grp", sort=False):
        if sub["_identity"].nunique() > 1:
            raise ValueError("Distinct group identities have the same display label.")
        if repeated:
            for _, subject in sub.groupby(sub["_animal"].astype(str), sort=False):
                if subject["_animal"].nunique() > 1:
                    raise ValueError("Distinct subject identities have the same display label.")
    columns = ["group", "n", "method", "mesor", "amplitude", "acrophase", "period",
               "r_squared", "p_rhythm", "amplitude_se", "acrophase_se", "error"]
    if method == "population_mean":
        columns.append("n_subjects")
    rows = []
    for group, sub in work.groupby("_grp", sort=False):
        rec = {key: np.nan for key in columns}
        rec.update(group=group, n=int(len(sub)), method=method, period=float(period), error=None)
        try:
            if repeated and period_free:
                raise ValueError(f"{method} requires a shared fixed period.")
            if method == "pooled":
                fit = fit_cosinor(sub["_t"].to_numpy(), sub["_v"].to_numpy(), period, period_free)
                rec.update(mesor=fit["mesor"], amplitude=fit["amplitude"],
                           acrophase=fit["acrophase"], period=fit["period"],
                           r_squared=fit["r_squared"], p_rhythm=fit["p"],
                           amplitude_se=fit["params"]["amplitude"]["stderr"],
                           acrophase_se=fit["params"]["acrophase"]["stderr"])
            elif method == "population_mean":
                rec.update(_population_mean_cosinor(sub, "_animal", period, False))
            else:
                rec.update(_mixed_cosinor(sub, "_animal", period))
        except Exception as exc:
            rec["error"] = str(exc)
        rows.append(rec)
    return pd.DataFrame(rows, columns=columns)


def _population_mean_cosinor(sub, animal_col, period, period_free):
    """Per-subject cosinor fits averaged; Hotelling T^2 rhythmicity (Bingham 1982)."""
    if period_free:
        raise ValueError("population_mean requires a shared fixed period.")
    coefs = []
    for _, a in sub.groupby(animal_col):
        if len(a) < 4:
            continue
        try:
            f = fit_cosinor(a["_t"].to_numpy(), a["_v"].to_numpy(), period, period_free)
            coefs.append((f["mesor"], f["coef_cos"], f["coef_sin"]))
        except ValueError:
            continue
    m = len(coefs)
    if m < 2:
        raise ValueError("population_mean needs >= 2 subjects with >= 4 timepoints each")
    arr = np.asarray(coefs, float)
    mesor = float(arr[:, 0].mean())
    bg = arr[:, 1:]
    mean_bg = bg.mean(axis=0)
    b, g = float(mean_bg[0]), float(mean_bg[1])
    amp = float(np.hypot(b, g))
    w = 2.0 * np.pi / period
    acro = float((np.arctan2(g, b) / w) % period) if amp else np.nan
    p = np.nan
    S = np.cov(bg, rowvar=False)
    if m > 2 and np.linalg.matrix_rank(S) == 2:
        T2 = m * mean_bg @ np.linalg.solve(S, mean_bg)
        F = (m - 2) / (2.0 * (m - 1)) * T2
        p = float(_sps.f.sf(F, 2, m - 2))
    amp_se = np.nan
    if amp:
        direction = mean_bg / amp
        amp_se = float(np.sqrt(max(float(direction @ S @ direction) / m, 0.)))
    return {"mesor": mesor, "amplitude": amp, "acrophase": acro, "period": float(period),
            "r_squared": np.nan, "p_rhythm": p, "amplitude_se": amp_se,
            "acrophase_se": np.nan, "n_subjects": m}


def _mixed_cosinor(sub, animal_col, period):
    """Gaussian ML random intercept; approximate observed-information Wald test."""
    import statsmodels.formula.api as smf
    from statsmodels.regression.mixed_linear_model import MixedLMParams
    from scipy.optimize import brentq

    _validate_circular_period(period)
    w = 2.0 * np.pi / period
    d = pd.DataFrame({
        "_v": sub["_v"].to_numpy(float),
        "_cos": np.cos(w * sub["_t"].to_numpy(float)),
        "_sin": np.sin(w * sub["_t"].to_numpy(float)),
        "_g": sub[animal_col].astype(str).to_numpy(),
    })
    if len(d) <= 3 or d["_g"].nunique() < 2:
        raise ValueError("mixed cosinor needs at least two subjects and four measurements.")
    X = np.column_stack([np.ones(len(d)), d["_cos"], d["_sin"]])
    if np.linalg.matrix_rank(X) != 3:
        raise ValueError("Sampling times do not identify both harmonic coefficients.")
    # A zero within-noise design has an unbounded Gaussian likelihood, rather
    # than a finite variance estimate with an extremely significant Wald test.
    D = pd.get_dummies(d["_g"]).to_numpy(float)
    full = np.column_stack([D, X[:, 1:]])
    y = d["_v"].to_numpy(float)
    beta_full, _, rank, singular_values = np.linalg.lstsq(full, y, rcond=None)
    resolution = (np.finfo(float).eps * max(full.shape) * np.linalg.norm(y)
                  * singular_values[0] / singular_values[rank - 1])
    if np.linalg.norm(y - full @ beta_full) <= resolution:
        raise ValueError("mixed cosinor needs positive residual variance for a finite ML fit.")
    model = smf.mixedlm("_v ~ _cos + _sin", d, groups=d["_g"])
    import warnings as _warnings
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        # Initialize the owner's ML configuration through its public fit API.
        # A singular boundary covariance does not preclude the fixed model.
        try:
            model.fit(reml=False, method="bfgs", gtol=1e-10, maxiter=2000)
        except np.linalg.LinAlgError:
            pass
        # Refine the scalar variance score: default stopping criteria can lose
        # relative accuracy in small positive significance probabilities.
        def variance_parameters(x):
            beta, singular = model.get_fe_params(np.array([[x*x]]), np.empty(0), tol=0.)
            return MixedLMParams.from_components(fe_params=beta, cov_re=np.array([[x*x]]))
        def variance_score(x):
            return float(model.score(variance_parameters(x), profile_fe=False)[model.k_fe])
        def variance_likelihood(x):
            return float(model.loglike(variance_parameters(x), profile_fe=False))
        grid = np.r_[np.sqrt(np.finfo(float).eps), 10. ** np.linspace(-3, 4, 141)]
        scores = [variance_score(x) for x in grid]
        roots = []
        for i, (a, upper) in enumerate(zip(grid, grid[1:])):
            if scores[i] > 0 > scores[i + 1]:
                roots.append(brentq(lambda x: variance_score(x),
                                    a, upper, xtol=1e-13, rtol=1e-14))
        if not np.all(np.isfinite(scores)) or scores[-1] > 0:
            raise ValueError("Mixed rhythm variance has no resolved finite maximum.")
        fixed = smf.ols("_v ~ _cos + _sin", d).fit()
        optimum = max(roots, key=lambda x: variance_likelihood(x)) if roots else None
        if optimum is None or (scores[0] <= 0 and fixed.llf >= variance_likelihood(optimum)):
            beta = np.asarray(fixed.params, float)
            # OLS reports residual-df scale; the Gaussian ML scale uses N.
            covariance = np.asarray(fixed.cov_params(), float) * (fixed.df_resid / fixed.nobs)
        else:
            ratio = optimum ** 2
            beta, singular = model.get_fe_params(np.array([[ratio]]), np.empty(0), tol=0.)
            if singular:
                raise ValueError("Mixed rhythm coefficients are not identified.")
            parameters = MixedLMParams.from_components(fe_params=beta, cov_re=np.array([[ratio]]))
            hessian, singular = model.hessian(parameters)
            covariance = np.linalg.inv(-hessian)[:3, :3]
    if not np.all(np.isfinite(covariance)) or np.any(np.linalg.eigvalsh(covariance) <= 0):
        raise ValueError("Mixed rhythm covariance is not positive definite.")
    mean_bg = beta[1:]
    statistic = float(mean_bg @ np.linalg.solve(covariance[1:, 1:], mean_bg))
    mesor, b, g = map(float, beta)
    amp = float(np.hypot(b, g))
    acro = float((np.arctan2(g, b) / w) % period) if amp else np.nan
    p = float(_sps.chi2.sf(statistic, 2))
    return {"mesor": mesor, "amplitude": amp, "acrophase": acro, "period": float(period),
            "r_squared": np.nan, "p_rhythm": p, "amplitude_se": np.nan,
            "acrophase_se": np.nan}


def cosinor_group_test(df, time_col, value_col, group_col, period=24.0, time_map=None):
    """Test whether rhythm parameters (amplitude/acrophase) differ between groups.

    An F-test comparing a **full** model (a separate cos/sin pair per group, i.e.
    group-specific rhythms) against a **reduced** model (one common cos/sin shared
    by all groups), each allowing a group-specific MESOR. A significant result
    means at least one group's rhythm (amplitude and/or acrophase) differs. Returns
    ``{F, p, df1, df2, n, groups}``. Nonfinite paired measurements and missing
    group identities are omitted. A common exact fit has undefined significance;
    exact different rhythms have infinite F and zero p. Invalid periods and
    distinct group identities sharing one display label are rejected.
    """
    _validate_circular_period(period)
    work = df.copy()
    work["_t"] = _resolve_numeric_time(work[time_col], time_map)
    work["_v"] = pd.to_numeric(work[value_col], errors="coerce")
    keep = (np.isfinite(work["_t"].to_numpy(float))
            & np.isfinite(work["_v"].to_numpy(float))
            & work[group_col].notna().to_numpy())
    work = work.loc[keep].copy()
    work["_g"] = work[group_col].astype(str)
    for _, sub in work.groupby("_g", sort=False):
        if sub[group_col].nunique() > 1:
            raise ValueError("Distinct group identities have the same display label.")
    groups = list(dict.fromkeys(work["_g"]))
    k = len(groups)
    n = len(work)
    if k < 2 or n < (3 * k + 1):
        return {"F": float("nan"), "p": float("nan"), "df1": 0, "df2": 0,
                "n": int(n), "groups": groups}

    w = 2.0 * np.pi / period
    cos = np.cos(w * work["_t"].to_numpy(float))
    sin = np.sin(w * work["_t"].to_numpy(float))
    D = pd.get_dummies(work["_g"], prefix="g").to_numpy(float)   # per-group mesor
    y = work["_v"].to_numpy(float)

    X_red = np.column_stack([D, cos, sin])                       # common rhythm
    X_full = np.column_stack([D, D * cos[:, None], D * sin[:, None]])  # per-group rhythm

    def _rss(X):
        beta, _, rank, singular_values = np.linalg.lstsq(X, y, rcond=None)
        r = y - X @ beta
        # Use the identifiable subspace for rank-deficient designs. The bound
        # distinguishes an exact fit from least-squares floating-point noise.
        condition = singular_values[0] / singular_values[rank - 1] if rank else 0.
        resolution = np.finfo(float).eps * max(X.shape) * np.linalg.norm(y) * condition
        rss = 0. if np.linalg.norm(r) <= resolution else float(r @ r)
        return rss, int(rank)

    rss_r, p_r = _rss(X_red)
    rss_f, p_f = _rss(X_full)
    df1 = p_f - p_r
    df2 = n - p_f
    if df1 <= 0 or df2 <= 0 or rss_f == 0:
        different_exact = df1 > 0 and df2 > 0 and rss_f == 0 and rss_r > 0
        return {"F": float("inf") if different_exact else float("nan"),
                "p": 0. if different_exact else float("nan"), "df1": int(max(df1, 0)),
                "df2": int(max(df2, 0)), "n": int(n), "groups": groups}
    # Clamp the numerator: the full model is nested and cannot fit worse, so a
    # negative (rss_r - rss_f) is float noise on a near-perfect/constant fit.
    F = (max(rss_r - rss_f, 0.0) / df1) / (rss_f / df2)
    p = float(_sps.f.sf(F, df1, df2))
    return {"F": float(F), "p": p, "df1": int(df1), "df2": int(df2),
            "n": int(n), "groups": groups}


# ── Circular statistics ──────────────────────────────────────────────
# Acrophase, activity onset, and L5/M10 start times are clock times: they live on
# a circle, so an ordinary mean or t-test is wrong (23:30 and 00:30 are 1 h apart,
# not 23). These treat a set of times (in the units of ``period``, e.g. hours on a
# 24 h clock, or months on a 12-month year) as angles.
def _validate_circular_period(period):
    from numbers import Real
    if isinstance(period, (bool, np.bool_)) or not isinstance(period, Real) or not np.isfinite(period) or period <= 0:
        raise ValueError('period must be a finite positive number.')


def _circ_angles(values, period):
    _validate_circular_period(period)
    v = np.asarray([np.nan if x is None or x is pd.NA else float(x) for x in values], float)
    v = v[np.isfinite(v)]
    return np.remainder(v, float(period)) * (2.0 * np.pi / float(period)), v


def circular_stats(values, period=24.0):
    """Descriptive circular statistics for a set of times on a ``period`` cycle.

    Returns ``{n, mean, r, rayleigh_z, rayleigh_p}`` — the mean time (in the units
    of ``period``), the mean resultant length ``r`` in [0, 1] (1 = perfectly
    concentrated, 0 = uniform), and the Rayleigh test that the times are NOT
    uniformly distributed (i.e. that a preferred phase exists).
    """
    ang, _v = _circ_angles(values, period)
    n = len(ang)
    if n == 0:
        return {"n": 0, "mean": float("nan"), "r": float("nan"),
                "rayleigh_z": float("nan"), "rayleigh_p": float("nan")}
    C, S = float(np.cos(ang).mean()), float(np.sin(ang).mean())
    R = float(np.hypot(C, S))
    mean_ang = float(np.arctan2(S, C))
    mean = float((mean_ang % (2.0 * np.pi)) / (2.0 * np.pi) * period)
    Z = n * R * R
    factor = (1 + (2 * Z - Z * Z) / (4 * n)
              - (24 * Z - 132 * Z ** 2 + 76 * Z ** 3 - 9 * Z ** 4) / (288 * n * n)) if n < 50 else 1.0
    p = float(np.exp(-Z) * factor)
    if R <= np.finfo(float).eps:
        mean = float('nan')
    return {"n": int(n), "mean": mean, "r": R, "rayleigh_z": float(Z),
            "rayleigh_p": float(min(max(p, 0.0), 1.0))}


def rayleigh_test(values, period=24.0):
    """Rayleigh test for a non-uniform (clustered) distribution of circular times.

    Returns ``{n, r, z, p, mean}``. Small ``p`` means the times cluster around a
    preferred phase rather than being spread around the whole cycle.
    """
    s = circular_stats(values, period)
    return {"n": s["n"], "r": s["r"], "z": s["rayleigh_z"],
            "p": s["rayleigh_p"], "mean": s["mean"]}


def _a1inv(r):
    """Inverse of the ratio of Bessel functions I1/I0 — the von Mises MLE for kappa."""
    if r >= 1.0:
        return float("inf")     # fully concentrated -> infinite concentration
    if r < 0.53:
        return 2 * r + r ** 3 + 5 * r ** 5 / 6.0
    if r < 0.85:
        return -0.4 + 1.39 * r + 0.43 / (1 - r)
    return 1.0 / (r ** 3 - 4 * r ** 2 + 3 * r)


def watson_williams(groups, period=24.0):
    """Watson-Williams k-sample test for equal circular means (a circular ANOVA).

    ``groups`` is a list of arrays of times (in the units of ``period``). Tests
    whether the mean phase is the same across groups — the circular analogue of a
    one-way ANOVA on acrophase. Assumes reasonably concentrated, similar-spread
    von Mises data; a concentration correction (Mardia) is applied. Returns
    ``{F, p, df1, df2, k, n, means, R}``.
    """
    _validate_circular_period(period)
    angs = []
    for g in groups:
        a, _v = _circ_angles(g, period)
        if len(a):
            angs.append(a)
    k = len(angs)
    N = int(sum(len(a) for a in angs))
    if k < 2 or N <= k:
        return {"F": float("nan"), "p": float("nan"), "df1": 0, "df2": 0,
                "k": k, "n": N, "means": [], "R": float("nan")}

    vectors = [(np.cos(a), np.sin(a)) for a in angs]
    totals = [(c.sum(), s.sum()) for c, s in vectors]
    Rj = [float(np.hypot(c, s)) for c, s in totals]
    Rj = [0.0 if r / len(a) <= np.finfo(float).eps else r
          for r, a in zip(Rj, angs)]
    R = float(np.hypot(sum(c for c, s in totals), sum(s for c, s in totals)))
    if R / N <= np.finfo(float).eps:
        R = 0.0
    rw = sum(Rj) / N
    kappa = _a1inv(rw) if 0 < rw < 1 else np.inf
    corr = 1.0 + 3.0 / (8.0 * kappa) if np.isfinite(kappa) and kappa > 0 else 1.0
    directions = [(c/r, s/r) if r else None
                  for (c, s), r in zip(totals, Rj)]
    # Evaluate the same resultant differences through squared distances.
    # Subtraction otherwise turns identical means into a spurious F value and
    # loses precision when within-group scatter is very small.
    between = sum(Rj[i]*Rj[j]*sum((x-y)**2 for x, y in zip(directions[i], directions[j]))
                  for i in range(k) for j in range(i+1, k)
                  if directions[i] is not None and directions[j] is not None)
    between = between/(sum(Rj)+R) if sum(Rj)+R else 0.0
    denom = sum(0.0 if np.all(a == a[0]) else len(a) if direction is None else
                float(((c-direction[0])**2+(s-direction[1])**2).sum()/2)
                for a, (c, s), direction in zip(angs, vectors, directions))
    if denom == 0:
        F = float('nan') if all(np.all(a == angs[0][0]) for a in angs) else float('inf')
    else:
        F = corr * (N - k) / (k - 1) * between / denom
    p = float(_sps.f.sf(F, k - 1, N - k))
    means = [float((np.arctan2(s, c) % (2 * np.pi))/(2 * np.pi)*period)
             if r else float('nan') for (c, s), r in zip(totals, Rj)]
    return {"F": float(F), "p": p, "df1": int(k - 1), "df2": int(N - k),
            "k": int(k), "n": int(N), "means": means, "R": float(R)}


def circular_linear_corr(theta_values, x, period=24.0):
    """Circular-linear correlation between a circular time and a linear variable.

    Quantifies association between a clock time (``theta_values`` on a ``period``
    cycle) and a continuous variable ``x`` (e.g. acrophase vs age, or activity
    amplitude vs recording month). Returns ``{r, r_squared, p, n}`` where ``r`` is
    the circular-linear correlation coefficient and ``p`` its F-test.
    """
    _validate_circular_period(period)
    theta = np.asarray([np.nan if v is None or v is pd.NA else float(v) for v in theta_values], float)
    x = np.asarray([np.nan if v is None or v is pd.NA else float(v) for v in x], float)
    if len(theta) != len(x):
        raise ValueError('theta_values and x must have the same number of observations.')
    ok = np.isfinite(theta) & np.isfinite(x)
    theta, x = theta[ok], x[ok]
    n = len(x)
    if n < 4:
        return {"r": float("nan"), "r_squared": float("nan"), "p": float("nan"), "n": int(n)}
    ang = np.remainder(theta, float(period)) * (2.0 * np.pi / float(period))
    c, s = np.cos(ang), np.sin(ang)
    if x.std() == 0 or c.std() == 0 or s.std() == 0:
        return {"r": float("nan"), "r_squared": float("nan"), "p": float("nan"), "n": int(n)}
    rxc = float(np.corrcoef(x, c)[0, 1])
    rxs = float(np.corrcoef(x, s)[0, 1])
    rcs = float(np.corrcoef(c, s)[0, 1])
    denom = 1.0 - rcs * rcs
    if abs(denom) < 1e-12:
        return {"r": float("nan"), "r_squared": float("nan"), "p": float("nan"), "n": int(n)}
    R2 = (rxc * rxc + rxs * rxs - 2 * rxc * rxs * rcs) / denom
    R2 = float(min(max(R2, 0.0), 1.0))
    if n > 3 and R2 < 1.0:
        F = (n - 3) / 2.0 * R2 / (1.0 - R2)
        p = float(_sps.f.sf(F, 2, n - 3))
    else:
        p = 0.0
    return {"r": float(np.sqrt(R2)), "r_squared": R2, "p": p, "n": int(n)}


def circular_dispersion_test(groups, period=24.0):
    """Wallraff test for equal circular dispersion (phase *spread*) across groups.

    The circular analogue of Levene's test — it asks whether the angular scatter
    around each group's own mean differs between groups, independent of where those
    means sit (Watson-Williams tests the means; this tests the spread). Each
    observation is reduced to its absolute angular deviation from its group mean,
    then a Kruskal-Wallis is run on those deviations (the own-mean, multi-group
    Wallraff convention used by R's circular package). Undefined mean directions
    yield undefined inference and dispersion; groups with fewer than two finite
    observations are omitted. Higher-precision geometry determines ranks so
    trigonometric roundoff cannot split equal angular distances. Returns
    ``{statistic, p, k, n, dispersions}`` where ``dispersions`` is each group's mean
    angular deviation in the units of ``period`` (larger = more scattered phases).
    """
    _validate_circular_period(period)
    finite_groups = []
    for g in groups:
        a, _v = _circ_angles(g, period)
        if len(a) < 2:
            continue
        finite_groups.append(np.remainder(_v, float(period)))
    k, n = len(finite_groups), int(sum(map(len, finite_groups)))
    dev_lists, disp = _circular_deviation_ranks(finite_groups, float(period))
    if k < 2 or dev_lists is None:
        return {"statistic": float("nan"), "p": float("nan"), "k": k, "n": n,
                "dispersions": disp}
    try:
        h = _sps.kruskal(*dev_lists)
        stat, p = float(h.statistic), float(h.pvalue)
    except ValueError:
        stat, p = float("nan"), float("nan")
    return {"statistic": stat, "p": p, "k": int(k), "n": n, "dispersions": disp}


def _circular_deviation_ranks(groups, period):
    """Rank before conversion to binary64, preserving resolved input differences.

    The precision floor only absorbs final-digit uncertainty in the chosen
    high-precision arithmetic. It is unrelated to the statistical tolerance.
    Tiny phases increase working precision instead of being rounded to zero.
    A private context keeps concurrent callers' precision settings isolated.
    """
    import math
    import mpmath
    arithmetic = mpmath.mp.clone()
    nonzero = [float(v) for g in groups for v in g if v != 0]
    digits = max((max(0, -math.floor(math.log10(v)-math.log10(period)))
                  for v in nonzero), default=0)
    arithmetic.dps = 80+digits
    cycle = 2*arithmetic.pi
    deviations, dispersions, invalid = [], [], False
    for group in groups:
        phases = [arithmetic.mpf(float(v))*cycle/arithmetic.mpf(period) for v in group]
        cosine = arithmetic.fsum(arithmetic.cos(v) for v in phases)
        sine = arithmetic.fsum(arithmetic.sin(v) for v in phases)
        if arithmetic.hypot(cosine, sine)/len(phases) <= arithmetic.mpf(np.finfo(float).eps):
            invalid = True
            dispersions.append(float('nan'))
            continue
        if np.all(group == group[0]):
            distances = [arithmetic.mpf(0)]*len(group)
        else:
            center = arithmetic.atan2(sine, cosine)
            distances = [abs((v-center+arithmetic.pi)%cycle-arithmetic.pi) for v in phases]
        deviations.append(distances)
        dispersions.append(float(arithmetic.fsum(distances)/len(phases)*period/cycle))
    if invalid:
        return None, dispersions
    pooled = sorted((v, j, i) for j, group in enumerate(deviations) for i, v in enumerate(group))
    rank_groups = [np.empty(len(g)) for g in deviations]
    precision_error = arithmetic.eps*128*(len(pooled)+1)
    start = 0
    while start < len(pooled):
        end = start+1
        while end < len(pooled) and abs(pooled[end][0]-pooled[start][0]) <= precision_error:
            end += 1
        rank = (start+1+end)/2
        for _, group_index, within_index in pooled[start:end]:
            rank_groups[group_index][within_index] = rank
        start = end
    return rank_groups, dispersions
