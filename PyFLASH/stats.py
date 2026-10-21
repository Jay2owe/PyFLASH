"""
Statistical testing and plot annotation utilities.
"""

from __future__ import annotations
import re

import csv
import math
import os
import unicodedata
import warnings
from copy import deepcopy
from collections.abc import Mapping
from typing import Iterable

from PyFLASH._logging import logger as _log

# Numeric helpers do not need to import every plotting and model engine.
# Cache actual objects so external access and monkeypatches retain ownership.
_DEFERRED_IMPORTS = {'sp': ('scikit_posthocs', None), 'sns': ('seaborn', None), 'sm': ('statsmodels.api', None), 'ols': ('statsmodels.formula.api', 'ols'), 'plt': ('matplotlib.pyplot', None), 'Rectangle': ('matplotlib.patches', 'Rectangle')}

def _dependency(name):
    if name in {'plt', 'Rectangle', 'sns'}:
        apply_matplotlib_fast_path()
    if name in globals():
        return globals()[name]
    from importlib import import_module
    module_name, attribute = _DEFERRED_IMPORTS[name]
    value = import_module(module_name)
    if attribute is not None:
        value = getattr(value, attribute)
    globals()[name] = value
    return value

def __getattr__(name):
    if name in _DEFERRED_IMPORTS:
        return _dependency(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import anderson, f_oneway, kstest, normaltest, ttest_ind_from_stats
import itertools

from PyFLASH.config import apply_matplotlib_fast_path
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
# Keyed on caller identity, with measured inputs and settings verified on reuse.
# Populated by multipleComparisons when Config.STATS_CACHE is True.
# Call clear_stats_cache() between independent analysis runs.
from PyFLASH._cache import BoundedCache
_stats_cache = BoundedCache()


def _cache_key_value(value):
    """Detach nested settings into immutable, type-aware cache identities."""
    if isinstance(value, np.random.Generator):
        engine = value.bit_generator
        return ('numpy.random.Generator', type(engine).__module__,
                type(engine).__qualname__, _cache_key_value(engine.state))
    if isinstance(value, np.random.RandomState):
        return ('numpy.random.RandomState', _cache_key_value(value.get_state()))
    if isinstance(value, dict):
        return ('mapping', tuple(sorted(
            ((_cache_key_value(key), _cache_key_value(item)) for key, item in value.items()),
            key=repr)))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(_cache_key_value(item) for item in value))
    if isinstance(value, (set, frozenset)):
        return (type(value).__name__, frozenset(_cache_key_value(item) for item in value))
    if isinstance(value, np.ndarray):
        return ('array', value.dtype.str, value.shape,
                tuple(_cache_key_value(item) for item in value.flat))
    if isinstance(value, np.generic):
        return _cache_key_value(value.item())
    if isinstance(value, float):
        return ('float', value.hex())
    hash(value)
    return (type(value).__module__, type(value).__qualname__, value)


def stats_cache_key(column_name, condition_names, specificity, stats_options=None):
    """Build a hashable cache key for a stats computation.

    Folds in the two session-wide settings that change the answer but are not
    visible in *stats_options*: ``Config.POSTHOC_CORRECTION``, which
    ``multipleComparisons`` resolves ``"auto"`` against after this key is
    built, and ``Config.CORRECTION_AUDIT``, which decides which
    ``Correction-*`` rows the results dict carries. Without them, switching
    either mid-session would serve a stale verdict.
    """
    from PyFLASH.config import Config

    conds = tuple(condition_names) if condition_names is not None else ()
    if specificity is None or (isinstance(specificity, (list, tuple, Mapping)) and not specificity):
        specificity = ()
    spec = _cache_key_value(specificity)
    opts = _cache_key_value(stats_options if stats_options is not None else {})
    session = (str(getattr(Config, "POSTHOC_CORRECTION", "auto")),
               str(getattr(Config, "CORRECTION_AUDIT", "cheap")),
               bool(Config.EFFECT_SIZES), bool(Config.EFFECT_CI),
               int(Config.EFFECT_CI_RESAMPLES), _cache_key_value(Config.EFFECT_CI_RANDOM_STATE))
    annotation_style = _cache_key_value({key: get_pyflash_style(key) for key in
                                        ('significance_thresholds', 'significance_ns')})
    return (str(column_name), conds, spec, opts, session, annotation_style)


def clear_stats_cache():
    """Reset the stats cache (call between independent analysis runs)."""
    _stats_cache.clear()


def get_annotation(p, ns="ns"):
    """Return significance annotation text for a p-value."""
    return pyflash_significance_annotation(p, ns=ns)


def _is_nonsignificant_annotation(annot):
    from numbers import Real
    try:ns=get_pyflash_style('significance_ns')
    except Exception:ns='ns'
    return annot==ns or annot=='ns' or isinstance(annot,Real)


def extract_p_and_stats_from_results(result_object, comparisons):
    """Extract ordered pair cells from matching square result matrices.

    Comparison tokens use one-based group numbers such as ``'1-2'``. Zero,
    negative or out-of-range numbers are errors, never NumPy wraparound.
    """
    probability = np.asarray(result_object.pvalue)
    statistic = np.asarray(result_object.statistic)
    if (probability.ndim != 2 or probability.shape[0] != probability.shape[1]
            or statistic.shape != probability.shape):
        raise ValueError('Pair results must be matching square statistic and p-value matrices.')
    pvalues = []
    statistics = []
    from PyFLASH._comparison_tokens import parse_pairs
    for _,first,second in parse_pairs(comparisons,probability.shape[0]):
        pvalues.append(float(probability[first,second]))
        statistics.append(float(statistic[first,second]))
    return statistics, pvalues


def _report_cells(label, value, *, statistic=False):
    from collections.abc import Sequence
    if statistic:
        if not isinstance(value, (list, tuple, np.ndarray)) or (isinstance(value, np.ndarray) and value.ndim != 1) or len(value) != 2:
            raise ValueError('Each exported statistic needs its statistic and probability fields')
        first, second = value
        prefix = [label, first]
    else:
        prefix = [label]
        second = value
    if isinstance(second, (list, tuple, np.ndarray)):
        if np.ndim(second) != 1:
            raise ValueError('Exported probabilities and summary lists must have one dimension')
        return prefix + list(second)
    return prefix + [second]

def results_to_excel(results_dict, other, experiment_save_path, save_name, verbose=True, output_dir=None):
    """Write complete ordered statistics and summary cells atomically to CSV. Private result keys are omitted; each public statistic has two fields."""
    from pathlib import Path
    from PyFLASH._persistence import atomic_text
    rows = [['Statistics Results'], ['Test', 'Statistic', 'P-Values']]
    for label, value in results_dict.items():
        if not str(label).startswith('_'):
            rows.append(_report_cells(label, value, statistic=True))
    rows += [[''], ['Analysis Summary']]
    for label, value in other.items():
        rows.append(_report_cells(label, value))
    target = Path(output_dir or experiment_save_path) / (str(save_name) + '.csv')
    with atomic_text(target, newline='') as stream:
        csv.writer(stream).writerows(rows)
    if verbose:
        _log.confirm(f'Stats results saved to {target}')


def _scalar_probability_count(p_value,n_tests):
    """A finite scalar probability and a nonnegative whole comparison count."""
    try:
        probability=np.asarray(p_value,dtype=object)
        count=np.asarray(n_tests,dtype=object)
        if probability.ndim or count.ndim:raise ValueError('Probability and comparison count must be scalars.')
        probability=probability.item();raw_count=count.item()
        if isinstance(probability,(bool,np.bool_)) or isinstance(raw_count,(bool,np.bool_)):
            raise ValueError('Probability and comparison count cannot be booleans.')
        probability=float(probability);count=int(raw_count)
        if not math.isfinite(probability) or not 0<=probability<=1:
            raise ValueError('Probability must be finite and between zero and one.')
        if count<0 or (not isinstance(raw_count,str) and raw_count!=count):
            raise ValueError('Comparison count must be a nonnegative whole number.')
        return probability,count
    except (ValueError,TypeError,OverflowError) as error:
        raise ValueError('Provide a finite scalar probability and a nonnegative whole comparison count.') from error

def bonferroni_correction(p_value,n_tests):
    from fractions import Fraction

    probability,count=_scalar_probability_count(p_value,n_tests)
    return float(min(Fraction(probability)*count,Fraction(1)))


def sidak_correction(p_value,n_tests):
    from fractions import Fraction
    from PyFLASH._numeric_scaling import _rational_float

    probability,count=_scalar_probability_count(p_value,n_tests)
    if not count or not probability:return 0.
    if probability==1:return 1.
    exponent=_rational_float(Fraction(count)*Fraction(math.log1p(-probability)))
    return -math.expm1(exponent)


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

    Uses the published Cauchy tail approximation for dependent individual
    tests with equal weights. Returns NaN when no finite p-value is supplied.
    Finite inputs retain the historical clipping at 1e-15 and 1-1e-15.
    Computation respects their exact floating values, including near-cancelling
    opposing tails; clipping endpoints are not exact binary complements.
    """
    ps = [float(p) for p in pvalues if p is not None and np.isfinite(p)]
    if not ps:
        return float("nan")
    ps = np.clip(np.asarray(ps, dtype=float), 1e-15, 1.0 - 1e-15)
    # Cotangent avoids subtracting p from 0.5 near a singularity. fsum keeps
    # ordinary cancellation stable; an exceptional opposing-tail case needs
    # additional digits before summing, rather than a looser answer tolerance.
    terms = [(-1.0 if p > .5 else 1.0) /
             math.tan(math.pi * (1.0-p if p > .5 else p)) for p in ps]
    total = math.fsum(terms)
    scale = math.fsum(abs(value) for value in terms)
    if scale > 1e6 and abs(total) < scale*1e-5:
        from decimal import Decimal, localcontext
        with localcontext() as context:
            context.prec = 70
            pi = Decimal('3.141592653589793238462643383279502884197169399375105820974944592307816')
            precise = []
            for p, ordinary in zip(ps, terms):
                exact = Decimal.from_float(float(p))
                negative = exact > Decimal('.5')
                distance = 1-exact if negative else exact
                if distance < Decimal('0.0001'):
                    x = pi*distance
                    # Cotangent series at the pole, retaining terms through
                    # x**9; the omitted term is below 1e-39 in this branch.
                    cot = 1/x-x/3-x**3/45-2*x**5/945-x**7/4725-2*x**9/93555
                    precise.append(-cot if negative else cot)
                else:
                    precise.append(Decimal.from_float(ordinary))
            t = float(sum(precise)/len(ps))
    else:
        t = total/len(ps)
    # A survival probability formed as 0.5-atan(t)/pi loses small tails.
    if t > 0:
        return math.atan(1.0/t)/math.pi
    if t < 0:
        return 1.0-math.atan(-1.0/t)/math.pi
    return 0.5


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
    """Compare two group slopes with pooled least-squares residual variance.

    Return p, estimate, se, t, df, n, reference, other and both fitted slopes.
    Numeric and categorical additive covariates are supported. Rows with missing
    group labels or nonfinite numeric observations/covariates are omitted together.
    rank and standardize transform the retained paired sample. Singular/saturated
    designs have undefined fitted fields. Identified exact fits retain coefficients
    and zero uncertainty, with signed-infinite/undefined Student-test limits.
    Column normalization keeps finite measurement-unit changes numerically stable.
    """
    from fractions import Fraction
    alternative = _resolve_tail(tail)
    if any(not isinstance(value, (bool,np.bool_)) for value in (standardize,rank)):
        raise ValueError("rank and standardize must be Boolean.")
    for values in (x,y):
        array=np.asarray(values,dtype=object)
        if array.ndim!=1 or any(isinstance(v,(list,tuple,dict,np.ndarray)) for v in array):
            raise ValueError("x and y must be one-dimensional ordered samples.")
    try:
        xs=pd.Series(x).reset_index(drop=True)
        ys=pd.Series(y).reset_index(drop=True)
        labels=pd.Series(group).reset_index(drop=True)
    except (ValueError,TypeError) as error:
        raise ValueError("x, y and group must be ordered one-dimensional samples.") from error
    if len({len(xs),len(ys),len(labels)})!=1:
        raise ValueError("x, y and group must have the same length.")
    xv=pd.to_numeric(xs,errors="coerce").to_numpy(dtype=float)
    yv=pd.to_numeric(ys,errors="coerce").to_numpy(dtype=float)
    retained=np.isfinite(xv)&np.isfinite(yv)&labels.notna().to_numpy()
    cov=pd.DataFrame(covariates).reset_index(drop=True) if covariates is not None else pd.DataFrame(index=range(len(xs)))
    if len(cov)!=len(xs):
        raise ValueError("Covariates length must match x/y/group.")
    if not cov.columns.is_unique:
        raise ValueError("Covariate column identities must be unique.")
    numeric={}
    for column in cov:
        values=cov[column];converted=pd.to_numeric(values,errors="coerce")
        is_numeric=int(converted.notna().sum())==int(values.notna().sum())
        numeric[column]=is_numeric
        retained &= np.isfinite(converted.to_numpy(dtype=float)) if is_numeric else values.notna().to_numpy()
        if is_numeric:cov[column]=converted
    empty={"p":float("nan"),"estimate":float("nan"),"se":float("nan"),"t":float("nan"),
           "df":0,"n":0,"reference":None,"other":None,
           "slope_reference":float("nan"),"slope_other":float("nan")}
    if not retained.any():return empty
    xv,yv=xv[retained],yv[retained]
    labels=labels[retained].reset_index(drop=True)
    cov=cov.loc[retained].reset_index(drop=True)
    try:levels=list(dict.fromkeys(labels.astype(object)))
    except TypeError as error:raise ValueError("Group identities must be hashable.") from error
    if len(levels)!=2:raise ValueError("Exactly two groups must remain after paired finite omission.")
    ref=levels[0] if reference is None else reference
    if ref not in levels:raise ValueError("Reference is absent from retained groups.")
    other=next(level for level in levels if level!=ref)
    n=len(xv);incomplete={**empty,"n":n,"reference":ref,"other":other}
    if rank:xv,yv=stats.rankdata(xv),stats.rankdata(yv)
    raw_x,raw_y=xv.copy(),yv.copy()
    def center_scale(values):
        largest=float(np.max(np.abs(values)))
        exponent=int(np.frexp(largest)[1]) if largest else 0
        normalized=np.ldexp(values,-exponent)
        normalized=normalized-normalized[0]
        return normalized-normalized.mean(),exponent
    xv,xe=center_scale(xv);yv,ye=center_scale(yv)
    xsd,ysd=np.std(xv),np.std(yv)
    if xsd==0 or ysd==0:return incomplete
    # Always solve with balanced column units; the public option controls
    # returned units rather than whether the solver is well conditioned.
    xv/=xsd;yv/=ysd
    indicator=np.asarray([label!=ref for label in labels],dtype=float)
    normalized_parts=[];raw_parts=[]
    for column in cov:
        if numeric[column]:
            values=cov[column].to_numpy(dtype=float)
            raw_parts.append(values)
            normalized=center_scale(values)[0]
            spread=np.std(normalized)
            normalized_parts.append(normalized/spread if spread else normalized)
        else:
            dummies=pd.get_dummies(cov[column].astype(object),drop_first=True,dtype=float)
            for name in dummies:
                values=dummies[name].to_numpy(dtype=float)
                raw_parts.append(values);normalized_parts.append(values)
    design=np.column_stack([np.ones(n),xv,indicator,xv*indicator,*normalized_parts])
    k=design.shape[1]
    if n<=k:return incomplete
    beta,_,identified,_=np.linalg.lstsq(design,yv,rcond=None)
    if identified<k:return incomplete
    residual=yv-design@beta
    exact_difference=None;exact_fit=False
    error_bound=16*np.finfo(float).eps*(np.linalg.norm(design)*np.linalg.norm(beta)+np.linalg.norm(yv))
    if np.linalg.norm(residual)<=error_bound:
        # Check exact representable input equations; the error bound selects
        # this check and never itself declares a fit exact.
        rational=[[Fraction(1),Fraction(float(raw_x[i])),Fraction(int(indicator[i])),
                   Fraction(float(raw_x[i]))*int(indicator[i]),
                   *[Fraction(float(part[i])) for part in raw_parts],Fraction(float(raw_y[i]))]
                  for i in range(n)]
        pivot_row=0
        for column in range(k):
            pivot=next((i for i in range(pivot_row,n) if rational[i][column]),None)
            if pivot is None:break
            rational[pivot_row],rational[pivot]=rational[pivot],rational[pivot_row]
            factor=rational[pivot_row][column]
            rational[pivot_row]=[value/factor for value in rational[pivot_row]]
            for i in range(n):
                if i==pivot_row:continue
                factor=rational[i][column]
                if factor:rational[i]=[v-factor*u for v,u in zip(rational[i],rational[pivot_row])]
            pivot_row+=1
        exact_fit=pivot_row==k and all(not row[-1] for row in rational[k:])
        if exact_fit:exact_difference=rational[3][-1]
    if exact_fit:
        se=0.;statistic=math.copysign(math.inf,float(exact_difference)) if exact_difference else float("nan")
        estimate=float(beta[3]) if exact_difference else 0.
    else:
        _,upper=np.linalg.qr(design,mode="reduced")
        inverse=np.linalg.solve(upper,np.eye(k))
        variance=float(residual@residual)/(n-k)
        se=math.sqrt(variance*float(inverse[3]@inverse[3]))
        estimate=float(beta[3]);statistic=estimate/se if se>0 else math.copysign(math.inf,estimate) if estimate else float("nan")
    if alternative=="two":p=float(2*stats.t.sf(abs(statistic),n-k))
    elif alternative=="one":p=float(stats.t.sf(abs(statistic),n-k))
    elif alternative=="greater":p=float(stats.t.sf(statistic,n-k))
    else:p=float(stats.t.cdf(statistic,n-k))
    def original_units(value):
        if standardize:return float(value)
        try:return math.ldexp(float(value)*(ysd/xsd),ye-xe)
        except OverflowError:return math.copysign(math.inf,value)
    return {"p":p,"estimate":original_units(estimate),"se":original_units(se),"t":float(statistic),
            "df":n-k,"n":n,"reference":ref,"other":other,
            "slope_reference":original_units(beta[1]),"slope_other":original_units(beta[1]+beta[3])}



def modified_anderson(data):
    """Adjusted Anderson-Darling statistic and calibrated normality probability.

    The normal distribution's mean/SD are fitted. Nonfinite/non-numeric
    observations are omitted. The finite-sample adjustment uses the retained
    sample size. Fewer than three varying observations are undefined; below
    eight the statistic is retained but the published probability is undefined.
    Adjusted statistics at least ten use nortest's published 3.7e-24 reporting
    limit, rather than extrapolating its calibrated approximation.
    """
    if np.asarray(data, dtype=object).ndim != 1:
        raise ValueError("Normality data must be one-dimensional.")
    arr = pd.to_numeric(pd.Series(data), errors="coerce").to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n < 3 or np.ptp(arr) == 0:
        return float("nan"), float("nan")
    ad_stat = float(anderson(_normality_balance(arr)).statistic) * (1 + 0.75/n + 2.25/n**2)
    if n < 8:
        return ad_stat, float("nan")
    if ad_stat >= 10:
        p = 3.7e-24
    elif ad_stat >= 0.6:
        p = math.exp(1.2937 - 5.709*ad_stat + 0.0186*ad_stat**2)
    elif ad_stat >= 0.34:
        p = math.exp(0.9177 - 4.279*ad_stat - 1.38*ad_stat**2)
    elif ad_stat >= 0.2:
        p = -math.expm1(-8.318 + 42.796*ad_stat - 59.938*ad_stat**2)
    else:
        p = -math.expm1(-13.436 + 101.14*ad_stat - 223.73*ad_stat**2)
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


def _finite_real_samples(samples):
    """Keep every requested group in place while omitting nonfinite entries."""
    groups=[]
    for sample in samples:
        try:values=np.asarray(sample)
        except (TypeError,ValueError) as error:raise ValueError('Each sample must have one real dimension') from error
        if values.ndim!=1 or values.dtype.kind=='c':
            raise ValueError('Each sample must have one real dimension')
        retained=[]
        for value in values:
            if isinstance(value,(list,tuple,dict,complex)):
                raise ValueError('Each sample must have one real dimension')
            try:number=float(value)
            except (TypeError,ValueError,OverflowError):continue
            if math.isfinite(number):retained.append(number)
        groups.append(np.asarray(retained,dtype=float))
    return groups

def _variance_request(method,alpha):
    from numbers import Real
    if isinstance(alpha,(bool,np.bool_)) or not isinstance(alpha,Real) or not math.isfinite(alpha) or not 0<=alpha<=1:
        raise ValueError('Variance alpha must be a finite real probability in [0, 1]')
    kind,label=_normalize_variance_test(method)
    return kind,label,float(alpha)

def _rational_sample_geometry(groups):
    from fractions import Fraction
    rational=[[Fraction(float(v)) for v in group] for group in groups]
    def average(group):return sum(group)/len(group)
    def median(group):
        ordered=sorted(group);size=len(group)
        return ordered[size//2] if size%2 else (ordered[size//2-1]+ordered[size//2])/2
    return rational,average,median

def _variance_inference(groups,kind):
    from PyFLASH._numeric_scaling import _power_of_two_scale
    rational,average,median=_rational_sample_geometry(groups)
    scaled=_power_of_two_scale(*groups)
    if kind=='fligner':
        residuals=[[v-median(group) for v in group] for group in rational]
        unique=sorted({abs(v) for group in residuals for v in group})
        if len(unique)==1:return math.nan,math.nan
        ordinal={v:i+1 for i,v in enumerate(unique) if v!=0}
        signed=[[0 if v==0 else ordinal[abs(v)]*(1 if v>0 else -1) for v in group] for group in residuals]
        return stats.fligner(*signed)
    if kind=='bartlett':
        variances=[sum((v-average(group))**2 for v in group)/(len(group)-1) for group in rational]
        if all(v==0 for v in variances):return math.nan,math.nan
        if any(v==0 for v in variances):return math.inf,0.
        if len(set(variances))==1:return 0.,1.
        return stats.bartlett(*scaled)
    if kind=='levene_trimmed':
        rational=[sorted(g)[len(g)//20:len(g)-len(g)//20] for g in rational]
    centers=[median(g) if kind=='brown_forsythe' else average(g) for g in rational]
    deviations=[[abs(v-center) for v in group] for group,center in zip(rational,centers)]
    means=list(map(average,deviations));grand=average([v for g in deviations for v in g])
    within=sum(sum((v-center)**2 for v in group) for group,center in zip(deviations,means))
    between=sum(len(group)*(center-grand)**2 for group,center in zip(deviations,means))
    if within==0:return (math.inf,0.) if between else (math.nan,math.nan)
    if between==0:return 0.,1.
    return stats.levene(*scaled,center={'brown_forsythe':'median','levene':'mean','levene_trimmed':'trimmed'}[kind])

def test_equal_variance(df_list,results_dict=None,*,method='brown-forsythe',alpha=.05):
    """Screen preserved finite groups; indeterminate inference stays undefined."""
    kind,label,level=_variance_request(method,alpha)
    groups=_finite_real_samples(df_list)
    raw=results_dict if results_dict is not None else {}
    output={'method':label,'statistic':math.nan,'pvalue':math.nan,'equal_var':None,'alpha':level}
    if kind=='none':
        output['equal_var']=True;raw['Variance check']=[label,math.nan];return output
    if len(groups)<2 or any(len(g)<2 for g in groups):
        raw['Variance '+label]=[math.nan,math.nan];raw['Equal variance']=['insufficient data',math.nan];return output
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        statistic,probability=_variance_inference(groups,kind)
    output['statistic']=float(statistic);output['pvalue']=float(probability)
    output['equal_var']=None if math.isnan(probability) else bool(probability>=level)
    raw['Variance '+label]=[output['statistic'],output['pvalue']]
    raw['Equal variance']=[output['equal_var'],output['pvalue']]
    return output


def _run_tukey(*groups):
    groups=_finite_real_samples(groups)
    if len(groups)<2 or any(len(g)<2 for g in groups):raise ValueError('Tukey inference needs at least two observations in every requested group')
    k=len(groups);tokens=[f'{a+1}-{b+1}' for a in range(k) for b in range(a+1,k)]
    values,probabilities=_one_way_posthoc(groups,tokens,'tukey')
    statistics=np.zeros((k,k));pvalues=np.ones((k,k))
    if _one_way_geometry(groups)[1]==0:np.fill_diagonal(pvalues,math.nan)
    index=0
    for a in range(k):
        for b in range(a+1,k):
            statistics[a,b]=values[index];statistics[b,a]=-values[index]
            pvalues[a,b]=pvalues[b,a]=probabilities[index];index+=1
    return _two_way_namespace(statistic=statistics,pvalue=pvalues)




def runITTest(group1,group2,results_dict,ns='ns',*,equal_var=None,variance_test='brown-forsythe',variance_alpha=.05):
    """Return complete Student/Welch reports, including undefined small samples."""
    from PyFLASH._numeric_scaling import _power_of_two_scale
    if equal_var is not None and not isinstance(equal_var,(bool,np.bool_)):
        raise ValueError('equal_var must be Boolean or None for automatic selection')
    _variance_request(variance_test,variance_alpha)
    groups=_finite_real_samples([group1,group2]);first,second=groups;n1,n2=map(len,groups)
    if equal_var is None:
        selected=test_equal_variance(groups,results_dict,method=variance_test,alpha=variance_alpha)['equal_var']
        equal_var=bool(selected) if selected is not None else False
    pooled=bool(equal_var)
    statistic=probability=degrees=math.nan
    if min(n1,n2)>=2:
        if pooled:
            means,mse,degrees,_,_=_one_way_geometry(groups)
            statistic,probability=_pooled_pair_geometry(means,mse,degrees,groups,0,1)
            degrees=float(degrees)
        else:statistic,probability,degrees=_unequal_pair_geometry(first,second)
    label="Student's t-test" if pooled else "Welch's t-test"
    key="Student's T Test" if pooled else "Welch's T Test"
    results_dict[key]=[statistic,probability]
    results_dict['_group_test']={'symbol':'t','df':[degrees]}
    results_dict['Independent T Test']=[statistic,probability]
    _publish_uncorrected(results_dict,[probability],basis='raw')
    return [probability],[get_annotation(probability,ns)],(statistic,probability),results_dict,label


def mwu_multiple_comparisons(df_list,comparisons,results_dict,ns='ns'):
    from PyFLASH._comparison_tokens import parse_pairs
    groups=_finite_real_samples(df_list)
    requested=parse_pairs(comparisons,len(groups),allow_self=False)
    statistics=[];probabilities=[]
    for _,first,second in requested:
        if not len(groups[first]) or not len(groups[second]):statistic=probability=float('nan')
        else:statistic,probability=stats.mannwhitneyu(groups[first],groups[second])
        statistics.append(float(statistic));probabilities.append(float(probability))
    results_dict['Mann-Whitney U']=[statistics,probabilities]
    results_dict['_group_test']={'symbol':'U'}
    _publish_uncorrected(results_dict,probabilities,basis='raw')
    return probabilities,[get_annotation(p,ns) for p in probabilities],(statistics,probabilities),results_dict,'Mann-Whitney U'


def _extract_posthoc_matrix_pvalues(matrix, comparisons):
    pvalues = []
    for comp in comparisons:
        first, second = [int(part) - 1 for part in comp.split("-")]
        pvalues.append(float(matrix.iloc[first, second]))
    return pvalues


def _run_fisher_lsd(groups,comparisons):
    from PyFLASH._comparison_tokens import parse_pairs
    requested=parse_pairs(comparisons,len(groups),allow_self=False)
    means,mse,degrees,_,_=_one_way_geometry(groups)
    pairs=[_pooled_pair_geometry(means,mse,degrees,groups,a,b) for _,a,b in requested]
    return [row[0] for row in pairs],[row[1] for row in pairs]


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
    """Use the complete deterministic control report with legacy pair ordering."""
    from PyFLASH.stats_extra import dunnett_vs_control
    control_idx = _infer_dunnett_control(comparisons, len(groups))
    result = dunnett_vs_control(groups, control=control_idx)
    indices = [i for i in range(len(groups)) if i != control_idx]
    stats_by_group = dict(zip(indices, result.statistic))
    p_by_group = dict(zip(indices, result.p_value))
    statistics, pvalues = [], []
    from PyFLASH._comparison_tokens import parse_pairs
    for _, first, second in parse_pairs(comparisons, len(groups)):
        other = second if first == control_idx else first
        statistics.append(float(stats_by_group[other]))
        pvalues.append(float(p_by_group[other]))
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
    from PyFLASH.config import Config

    from PyFLASH._comparison_tokens import parse_pairs
    groups = _finite_real_samples(df_list)
    requested = parse_pairs(comparisons,len(groups),allow_self=False)
    _normalize_lsd_correction(posthoc_correction,len(comparisons))
    posthoc_method, posthoc_label, embedded_correction = _normalize_owa_posthoc(posthoc)
    if posthoc_method == 'dunnett':_infer_dunnett_control(comparisons,len(groups))
    if len(groups) < 2 or any(len(g) <= 1 for g in groups):
        return [], [], (float("nan"), float("nan")), results_dict, posthoc_label
    _, _, _, f_stat, pvalue = _one_way_geometry(groups)
    results_dict["OWA"] = [float(f_stat), float(pvalue)]
    results_dict["_group_test"] = {
        "symbol": "F", "df": [len(groups) - 1, sum(len(g) for g in groups) - len(groups)],
    }
    # Tukey, Dunnett, Scheffe and Tamhane all carry their own multiplicity
    # handling inside the statistic, so what they return is already adjusted;
    # only Fisher LSD hands back raw p-values.
    raw_pvalues = None
    try:
        if posthoc_method in {'tukey','scheffe','tamhane'}:
            statistics,pvalues = _one_way_posthoc(groups,comparisons,posthoc_method)
        elif posthoc_method == 'dunnett':
            statistics,pvalues = _run_dunnett(groups,comparisons)
        else:
            statistics, pvalues = _run_fisher_lsd(groups, comparisons)
            raw_pvalues = [float(p) for p in pvalues]
            # Published before the correction is chosen: Westfall-Young is
            # decided from these inputs, not from the p-values alone.
            _publish_uncorrected(
                results_dict, raw_pvalues, basis="raw",
                family="value", statistic="lsd",
                groups=[np.asarray(g, float) for g in groups],
                pairs=tuple(
                    tuple(int(part) - 1 for part in comp.split("-"))
                    for comp in comparisons
                ),
            )
            if embedded_correction is None:
                method, correction = _normalize_lsd_correction(posthoc_correction, len(comparisons))
            else:
                method = embedded_correction
                correction = posthoc_label
            wy = None
            if method == "westfall_young":
                try:
                    identities = [tuple(sorted((first,second))) for _,first,second in requested]
                    if Config.CORRECTION_AUDIT is not False and len(set(identities)) != len(identities):
                        raise CorrectionUnavailable('reported comparisons do not match the null design')
                    wy = _westfall_young_from_inputs(
                        results_dict, raw_pvalues, "lsd", Config)
                except CorrectionUnavailable as exc:
                    results_dict["Correction-Unavailable"] = [str(exc), np.nan]
            pvalues, method, applied = _correct_or_fall_back(
                pvalues, method, correction, len(comparisons), results_dict,
                wy=wy)
            if correction is not None:
                correction = applied
                _record_applied_correction(results_dict, correction)
                if embedded_correction is not None and method == embedded_correction:
                    posthoc_label = correction
                else:
                    posthoc_label = 'Fisher LSD' + (f' {correction}' if correction != 'Uncorrected' else '')
    except ValueError:
        if posthoc_method == "tukey":
            return [], [], (float(f_stat), float(pvalue)), results_dict, posthoc_label
        raise
    results_dict[posthoc_label.replace(" ", "-")] = [statistics, pvalues]
    if raw_pvalues is None:
        # Fisher LSD already published above, before its correction was chosen.
        _publish_uncorrected(
            results_dict, pvalues, basis="self_adjusted",
            family="value_unsupported",
            reason=(
                f"{posthoc_label} already accounts for multiplicity; no permutation "
                "null is implemented for this method."
            ),
        )
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


def _run_games_howell(groups,comparisons):
    from PyFLASH._numeric_scaling import _rational_float,_rational_sqrt,_f_tail_ratio,_t_tail_squared
    from PyFLASH._comparison_tokens import parse_pairs
    from PyFLASH._studentized_range import range_tail,range_tail_squared
    groups=_finite_real_samples(groups);requested=parse_pairs(comparisons,len(groups),allow_self=False)
    statistics=[];probabilities=[]
    for _,first,second in requested:
        if len(groups[first])<2 or len(groups[second])<2:q=probability=math.nan
        else:
            statistic,_,degrees=_unequal_pair_geometry(groups[first],groups[second]);q=abs(statistic)*math.sqrt(2)
            rational,average,_=_rational_sample_geometry([groups[first],groups[second]])
            a,b=rational;ma,mb=average(a),average(b)
            va=sum((v-ma)**2 for v in a)/(len(a)-1);vb=sum((v-mb)**2 for v in b)/(len(b)-1)
            uncertainty=va/len(a)+vb/len(b)
            probability=range_tail_squared(2*(ma-mb)**2/uncertainty,len(groups),degrees) if uncertainty else range_tail(q,len(groups),degrees)
        statistics.append(q);probabilities.append(probability)
    return statistics,probabilities


def runWelchOWA(df_list,comparisons,results_dict,ns='ns',posthoc='Tamhane T2'):
    from PyFLASH._comparison_tokens import parse_pairs
    groups=_finite_real_samples(df_list);kind,label=_normalize_welch_owa_posthoc(posthoc)
    parse_pairs(comparisons,len(groups),allow_self=False)
    if len(groups)<2 or any(len(group)<2 for group in groups):
        return [],[],(math.nan,math.nan),results_dict,label
    statistic,probability,first_df,second_df=_welch_one_way_geometry(groups)
    results_dict['Welch ANOVA']=[statistic,probability]
    results_dict['_group_test']={'symbol':'F','df':[first_df,second_df]}
    if kind=='games_howell':statistics,probabilities=_run_games_howell(groups,comparisons)
    else:statistics,probabilities=_one_way_posthoc(groups,comparisons,'tamhane')
    results_dict[label.replace(' ','-')]=[statistics,probabilities]
    _publish_uncorrected(results_dict,probabilities,basis='self_adjusted',family='unequal_variance',
        reason=('Permuting values across groups imposes equal variance, which is '
            'the assumption Welch ANOVA is chosen to avoid, so a permutation '
            'null here would be wrong rather than approximate. Games-Howell '
            'and Tamhane T2 carry their own correction; a studentised '
            'bootstrap would be needed for a calibrated alternative.'))
    return probabilities,[get_annotation(p,ns) for p in probabilities],(statistic,probability),results_dict,label


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
    # Permutation-calibrated. Opt-in only: "auto" never resolves here.
    "westfall_young": ("westfall_young", "Westfall-Young"),
    "westfall": ("westfall_young", "Westfall-Young"),
    "wy": ("westfall_young", "Westfall-Young"),
    "permutation": ("westfall_young", "Westfall-Young"),
    "perm": ("westfall_young", "Westfall-Young"),
    "maxt": ("westfall_young", "Westfall-Young"),
    "max_t": ("westfall_young", "Westfall-Young"),
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


class CorrectionUnavailable(ValueError):
    """The requested correction cannot be supplied on this test path.

    A distinct type, so the fallback branch can let a genuine bug in the
    permutation engine surface instead of reporting it as "unavailable".
    """


_NO_NULL_MESSAGE = (
    "Westfall-Young needs a permutation null, which is not available for this "
    "test. Rank post-hocs (Dunn, Conover) support it; Welch ANOVA cannot, "
    "because permuting values across groups imposes the equal variance Welch "
    "exists to avoid."
)


def _apply_kw_correction(pvalues, method, wy=None):
    values = [float(p) for p in pvalues]
    if method == "none":
        return values
    if method == "westfall_young":
        if wy is None or len(wy) != len(values):
            raise CorrectionUnavailable(_NO_NULL_MESSAGE)
        return [float(p) for p in wy]
    if method == "bonferroni":
        return [math.nan if math.isnan(p) else bonferroni_correction(p, len(values)) for p in values]
    if method == "sidak":
        return [math.nan if math.isnan(p) else sidak_correction(p, len(values)) for p in values]

    from PyFLASH.stats_extra import adjust_pvalues
    _, adjusted = adjust_pvalues(values, method=method)
    return [float(p) for p in adjusted]


from PyFLASH._cache import bounded_lru_cache as _rank_lru_cache

def _rank_strength(means,sizes,variance,total_ss,kind):
    from fractions import Fraction
    n=sum(sizes);k=len(sizes)
    residual=total_ss-sum(size*(mean-Fraction(n+1,2))**2 for size,mean in zip(sizes,means))
    scale=variance if kind=='dunn' else residual/(n-k)
    values=[]
    for i in range(k):
        for j in range(i+1,k):
            delta=means[i]-means[j];denominator=scale*(Fraction(1,sizes[i])+Fraction(1,sizes[j]))
            values.append(delta**2/denominator if denominator else (math.inf if delta else Fraction()))
    return values


@_rank_lru_cache(maxsize=4)
def _exact_rank_null_strengths(sizes,ranked,count,exact,kind):
    from fractions import Fraction
    from PyFLASH import stats_extra
    means,mode,_=stats_extra._mean_rank_null_cached(sizes,tuple(sorted(ranked)),count,exact,0)
    n=sum(sizes);total_ss=sum((Fraction(value)-Fraction(n+1,2))**2 for value in ranked)
    variance=total_ss/(n-1)
    rows=[]
    for row in means:
        # Midrank sums are half integers. With the parent's n<=200 guard,
        # addition is exact; reconstruct sums before divided means are rounded.
        rational=[Fraction(int(round(2*mean*size)),2*size) for mean,size in zip(row,sizes)]
        rows.append(_rank_strength(rational,sizes,variance,total_ss,kind))
    return rows,mode


def _rank_westfall_young(results_dict,pvalues,kind,Config,design,requested):
    from fractions import Fraction
    inputs=dict(results_dict['_audit_inputs']);plan,reason=_permutation_plan(inputs,len(pvalues),Config,explicit_wy=True)
    if plan is None:
        if Config.CORRECTION_AUDIT is False:reason='Config.CORRECTION_AUDIT is off, so no permutation null was computed'
        elif not pvalues:reason='no comparisons were requested, so there is nothing to correct'
        elif reason is None:reason='a single comparison is not a family, so there is nothing to correct'
        raise CorrectionUnavailable(reason or _NO_NULL_MESSAGE)
    selected=[tuple(sorted((first,second))) for _,first,second in requested]
    if len(set(selected))!=len(selected):raise CorrectionUnavailable('reported comparisons do not match the null design')
    plan['statistic']=kind
    _build_null(plan)  # Shared validated enumeration and configuration.
    sizes=tuple(inputs['group_sizes']);ranked=tuple(inputs['ranks']);n=sum(sizes)
    total_ss=sum((Fraction(value)-Fraction(n+1,2))**2 for value in ranked)
    allpairs=[(a,b) for a in range(len(sizes)) for b in range(a+1,len(sizes))]
    observed=_rank_strength(design[2],sizes,total_ss/(n-1),total_ss,kind)
    indices=[allpairs.index(pair) for pair in selected]
    strengths=[observed[index] for index in indices]
    retained=sorted((i for i,p in enumerate(pvalues) if math.isfinite(p)),key=lambda i:strengths[i],reverse=True)
    output=[math.nan]*len(pvalues)
    if not retained:return output
    rows,mode=_exact_rank_null_strengths(sizes,ranked,plan['n_resamples'],plan['exact_max'],kind)
    previous=Fraction()
    for step,index in enumerate(retained):
        columns=[indices[i] for i in retained[step:]];threshold=strengths[index]
        events=sum(any(row[column]>=threshold for column in columns) for row in rows)
        adjusted=Fraction(events+(mode=='sampled'),len(rows)+(mode=='sampled'))
        previous=max(previous,adjusted);output[index]=float(previous)
    return output


def _rank_design(groups):
    """Exact midrank geometry retains tie limits and one-observation groups."""
    from fractions import Fraction
    pooled=np.concatenate(groups);ranked=stats.rankdata(pooled)
    sizes=tuple(map(len,groups));n=len(pooled);k=len(groups)
    sums=[];start=0
    for size in sizes:
        sums.append(Fraction(float(np.sum(ranked[start:start+size]))));start+=size
    means=[total/size for total,size in zip(sums,sizes)]
    counts=np.unique(pooled,return_counts=True)[1]
    ties=sum(int(count)**3-int(count) for count in counts)
    tie=1-Fraction(ties,n**3-n)
    variance=Fraction(n*(n+1),12)-Fraction(ties,12*(n-1))
    h=(Fraction(12,n*(n+1))*sum(total**2/size for total,size in zip(sums,sizes))-3*(n+1))/tie if tie else None
    statistic=float(h) if h is not None else math.nan
    probability=float(stats.chi2.sf(statistic,k-1))
    return statistic,probability,means,variance,h,tuple(float(v) for v in ranked)


def _rank_pair_arrays(groups,requested,kind,design):
    from fractions import Fraction
    from PyFLASH._numeric_scaling import _rational_sqrt,_t_tail_squared
    from PyFLASH._studentized_range import range_tail_squared
    _,_,means,variance,h,_=design;k=len(groups);n=sum(map(len,groups))
    statistics=[];probabilities=[]
    for _,first,second in requested:
        delta=means[first]-means[second]
        denominator=variance*(Fraction(1,len(groups[first]))+Fraction(1,len(groups[second])))
        if kind=='DSCF':
            a,b=groups[first],groups[second];ni,nj=len(a),len(b);size=ni+nj
            pair=np.concatenate((a,b));ranked=stats.rankdata(pair)
            u=Fraction(float(np.sum(ranked[:ni])))-Fraction(ni*(ni+1),2)
            counts=np.unique(pair,return_counts=True)[1];ties=sum(int(c)**3-int(c) for c in counts)
            denominator=Fraction(ni*nj,size*(size-1))*Fraction(size**3-size-ties,12)
            if denominator:
                squared=2*(u-Fraction(ni*nj,2))**2/denominator
                statistic=_rational_sqrt(squared);probability=range_tail_squared(squared,k,math.inf)
            else:statistic=probability=math.nan
        else:
            if kind=='Conover':
                denominator=denominator*(n-1-h)/(n-k) if h is not None and n>k else None
            if denominator is None or not denominator:
                if denominator==0 and delta and kind=='Conover':statistic=math.copysign(math.inf,float(delta));probability=0.
                else:statistic=probability=math.nan
            else:
                squared=delta**2/denominator
                if kind=='Nemenyi':statistic=float(squared);probability=float(stats.chi2.sf(statistic,k-1))
                elif kind=='Dunn':statistic=_rational_sqrt(squared);probability=math.erfc(statistic/math.sqrt(2))
                else:statistic=math.copysign(_rational_sqrt(squared),float(delta));probability=_t_tail_squared(squared,n-k)
        statistics.append(statistic);probabilities.append(probability)
    return statistics,probabilities


def runKW(df_list,comparisons,results_dict,posthoc='Conover',ns='ns',posthoc_correction='auto'):
    from PyFLASH.config import Config
    from PyFLASH._comparison_tokens import parse_pairs
    groups=_finite_real_samples(df_list)
    if posthoc is not None and not isinstance(posthoc,str):raise ValueError('A named rank method is required')
    posthoc=_normalize_kw_posthoc(posthoc)
    requested=parse_pairs(comparisons,len(groups),allow_self=False)
    correction_method,correction=_normalize_kw_correction(posthoc_correction,len(requested))
    if len(groups)<2 or any(not len(group) for group in groups):
        return [],[],(math.nan,math.nan),results_dict,posthoc
    design=_rank_design(groups);statistic,probability=design[:2]
    results_dict['KW']=[statistic,probability];results_dict['_group_test']={'symbol':'H','df':[len(groups)-1]}
    if posthoc in {'Nemenyi','DSCF'}:
        statistics,pvalues=_rank_pair_arrays(groups,requested,posthoc,design)
        results_dict[posthoc]=[statistics,pvalues]
        _publish_uncorrected(results_dict,pvalues,basis='self_adjusted',family='rank_unsupported',
            reason=('Nemenyi uses a tie-corrected chi-square approximation; no permutation null is implemented for this method.' if posthoc=='Nemenyi' else 'DSCF re-ranks each pair and uses the Gaussian studentised-range distribution; no permutation null is implemented for this method.'))
        return pvalues,[get_annotation(p,ns) for p in pvalues],(statistic,probability),results_dict,posthoc
    arrays={name:_rank_pair_arrays(groups,requested,name,design) for name in ('Dunn','Conover')}
    _publish_uncorrected(results_dict,arrays[posthoc][1],basis='raw',family='rank',statistic=posthoc.lower(),
        group_sizes=tuple(map(len,groups)),ranks=design[-1],pairs=tuple((first,second) for _,first,second in requested))
    corrected={}
    if correction_method=='westfall_young':
        try:
            for name in ('Conover','Dunn'):
                corrected[name]=_rank_westfall_young(results_dict,arrays[name][1],name.lower(),Config,design,requested)
        except CorrectionUnavailable as error:
            results_dict['Correction-Unavailable']=[str(error),math.nan]
            correction_method,correction=_normalize_kw_correction('auto',len(requested));corrected={}
    for name in ('Conover','Dunn'):
        statistics,pvalues=arrays[name]
        results_dict[name+'-Bonferroni']=[statistics,_apply_kw_correction(pvalues,'bonferroni')]
        results_dict[name+'-Uncorrected']=[statistics,pvalues]
        if name not in corrected:corrected[name]=_apply_kw_correction(pvalues,correction_method)
        if correction not in ('Bonferroni','Uncorrected'):results_dict[name+'-'+correction]=[statistics,corrected[name]]
    _record_applied_correction(results_dict,correction)
    pvalues=corrected[posthoc]
    return pvalues,[get_annotation(p,ns) for p in pvalues],(statistic,probability),results_dict,posthoc+' '+correction



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


def _linear_model_prepare(model_df,outcome_col,group_col,comparisons,results_dict,
                          covariates,categorical_covariates,posthoc_correction,
                          cov_type,cov_kwds,group_order):
    from collections.abc import MutableMapping
    from PyFLASH._comparison_tokens import parse_pairs

    if model_df is None:raise ValueError('Linear-model stats need model_df from the plotting wrapper.')
    if not isinstance(results_dict,MutableMapping):raise ValueError('results_dict must be a mutable mapping.')
    original_index=pd.DataFrame(model_df).index.copy()
    df=pd.DataFrame(model_df).copy().reset_index(drop=True)
    for name in (outcome_col,group_col):
        if name not in df.columns:raise ValueError(f'Linear-model column {name!r} was not found.')
    covariates=_as_list(covariates);categorical=_as_list(categorical_covariates)
    if len(set(covariates))!=len(covariates) or not set(categorical)<=set(covariates):
        raise ValueError('Covariates must be unique; categorical covariates must be declared covariates.')
    for name in covariates:
        if name not in df.columns:raise ValueError(f'Linear-model covariate {name!r} was not found.')
    order=(df[group_col].dropna().astype(str).unique().tolist() if group_order is None else [str(g) for g in group_order])
    if len(set(order))!=len(order):raise ValueError('Group order must contain distinct labels.')
    requested=parse_pairs(comparisons,len(order),allow_self=False)
    _normalize_kw_correction(posthoc_correction,len(requested))
    if cov_type is not None and not isinstance(cov_type,str):raise ValueError('A named covariance type is required.')
    kind=(cov_type or 'nonrobust').lower()
    if kind not in ('nonrobust','hc0','hc1','hc2','hc3','fixed scale','fixed_scale','hac','cluster','hac-panel','hac-groupsum'):
        raise ValueError('Unknown covariance type.')
    if cov_kwds is not None and not isinstance(cov_kwds,Mapping):raise ValueError('Covariance options must be a mapping.')
    kw=deepcopy(dict(cov_kwds or {}))
    if kind in ('hc0','hc1','hc2','hc3') and set(kw)-{'use_t'}:
        raise ValueError('Heteroscedasticity robust covariance does not use additional keywords.')
    if kw.get('use_t') is not None and not isinstance(kw['use_t'],(bool,np.bool_)):
        raise ValueError('use_t must be a boolean or None.')
    keep=df[group_col].notna() & df[group_col].astype(str).isin(order)
    for name in (outcome_col,*[c for c in covariates if c not in categorical]):
        values=pd.to_numeric(df[name],errors='coerce');df[name]=values
        keep &= values.notna() & np.isfinite(values)
    for name in categorical:keep &= df[name].notna()
    indices=np.flatnonzero(keep.to_numpy(dtype=bool,na_value=False))
    for key in ('groups','time'):
        if key in kw:
            values=np.asarray(kw[key])
            if values.ndim not in ((1,2) if key=='groups' and kind=='cluster' else (1,)):
                raise ValueError(f'{key} has an invalid shape.')
            if values.ndim==2 and values.shape[1]!=2:raise ValueError('Cluster covariance accepts at most two grouping columns.')
            if len(values)==len(df):kw[key]=values[indices]
            elif len(values)==len(indices):kw[key]=values.copy()
            else:raise ValueError(f'{key} must match original or retained rows.')
    df=df.loc[keep].reset_index(drop=True)
    df.attrs['_pyflash_observation_ids']=list(original_index[indices])
    return df,order,covariates,categorical,kw,requested

def _linear_model_refine_small_error(fitted,cov_type,cov_kwds):
    """Retain real small or zero residuals before constructing model covariance."""
    from fractions import Fraction
    actual=fitted._results
    outcome=np.asarray(actual.model.endog,float);residual=np.asarray(actual.resid,float)
    scale=max(float(np.max(np.abs(outcome))),np.finfo(float).tiny)
    if float(np.max(np.abs(residual))) > 32*np.sqrt(np.finfo(float).eps)*scale:
        return fitted
    design=np.asarray(actual.model.exog,float);n,p=design.shape
    normal=[[Fraction() for _ in range(p)] for _ in range(p)];rhs=[Fraction() for _ in range(p)]
    for row,value in zip(design,outcome):
        q=[Fraction(float(x)) for x in row];y=Fraction(float(value))
        for i in range(p):
            rhs[i]+=q[i]*y
            for j in range(p):normal[i][j]+=q[i]*q[j]
    augmented=[normal[i]+[rhs[i]]+[Fraction(i==j) for j in range(p)] for i in range(p)]
    for column in range(p):
        pivot=max(range(column,p),key=lambda i:abs(augmented[i][column]))
        augmented[column],augmented[pivot]=augmented[pivot],augmented[column]
        divisor=augmented[column][column]
        if not divisor:raise ValueError('The declared model design is not identifiable.')
        augmented[column]=[v/divisor for v in augmented[column]]
        for i in range(p):
            if i!=column:
                factor=augmented[i][column]
                augmented[i]=[a-factor*b for a,b in zip(augmented[i],augmented[column])]
    beta=[row[p] for row in augmented]
    exact_residual=[Fraction(float(y))-sum((Fraction(float(x))*b for x,b in zip(row,beta)),Fraction()) for row,y in zip(design,outcome)]
    actual.params=np.asarray([float(b) for b in beta])
    actual.normalized_cov_params=np.asarray([[float(v) for v in row[p+1:]] for row in augmented])
    actual._cache.clear()
    actual._cache['resid']=np.asarray([float(e) for e in exact_residual])
    actual._cache['wresid']=actual._cache['resid']
    actual.scale=float(sum((e*e for e in exact_residual),Fraction())/(n-p))
    kind=(cov_type or 'nonrobust').lower()
    if kind!='nonrobust':
        kwargs=deepcopy(cov_kwds or {});kwargs.pop('use_t',None)
        actual.get_robustcov_results(cov_type=cov_type,use_t=actual.use_t,use_self=True,**kwargs)
    return fitted

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
    df, order, covariates, categorical_covariates, cov_kwds, requested = _linear_model_prepare(
        model_df, outcome_col, group_col, comparisons, results_dict, covariates,
        categorical_covariates, posthoc_correction, cov_type, cov_kwds, group_order)
    if len(order) < 2 or any(sum(df[group_col].astype(str) == group) < 2 for group in order):
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
        model = _dependency('ols')(formula, data=model_data)
        design = np.asarray(model.exog, dtype=float)
        if np.linalg.matrix_rank(design) < design.shape[1] or len(design) <= design.shape[1]:
            raise ValueError("The declared model needs an identifiable design and residual degrees of freedom.")
        fitted = model.fit(**fit_kwargs)
        fitted = _linear_model_refine_small_error(fitted, cov_type, cov_kwds)

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
            is_f = str(getattr(wald, "distribution", "")).lower() == "f"
            results_dict["_group_test"] = {
                "symbol": "F" if is_f else "chi2",
                "df": ([float(wald.df_num), float(wald.df_denom)] if is_f
                       else [float(wald.df_denom)]),
            }
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
        df_resid = float(getattr(fitted, "df_resid_inference", fitted.df_resid))
        pvalue = (2.0 * stats.t.sf(abs(t_stat), df_resid) if fitted.use_t
                  else 2.0 * stats.norm.sf(abs(t_stat)))
        statistics.append(float(t_stat))
        raw_pvalues.append(float(pvalue))

    correction_method, correction = _normalize_kw_correction(posthoc_correction, len(comparisons))
    pvalues, correction_method, correction = _correct_or_fall_back(
        raw_pvalues, correction_method, correction, len(comparisons),
        results_dict)
    _record_applied_correction(results_dict, correction)
    results_dict["Linear-Model-Contrasts-Uncorrected"] = [statistics, raw_pvalues]
    _publish_uncorrected(results_dict, raw_pvalues, basis="raw")
    results_dict[f"Linear-Model-Contrasts-{correction}"] = [statistics, pvalues]
    annotations = [get_annotation(p, ns) for p in pvalues]
    cov_label = f" {cov_type}" if cov_type else ""
    posthoc_string = f"model contrasts{cov_label} {correction}".strip()
    return pvalues, annotations, (overall_stat, overall_p), results_dict, posthoc_string


from fractions import Fraction as _two_way_fraction
from collections.abc import MutableMapping as _two_way_mutable_mapping
from types import SimpleNamespace as _two_way_namespace

def _two_way_prepare(experiment,column,factors,comparisons):
    from PyFLASH._comparison_tokens import parse_pairs
    try:frame=pd.DataFrame(experiment.summary).copy();conditions=experiment.condition_list
    except (AttributeError,ValueError,TypeError) as error:raise ValueError('Two-way analysis needs a summary and ordered conditions') from error
    names=[getattr(condition,'name',None) for condition in conditions]
    if any(not isinstance(name,str) or not name for name in names) or len(set(names))!=len(names):raise ValueError('Conditions must have unique nonempty names')
    if factors is None:factors=getattr(conditions,'factor',None)
    if not isinstance(factors,(list,tuple)) or len(factors)!=2 or any(not isinstance(name,str) or not name for name in factors) or len(set(factors))!=2:raise ValueError('Two-way analysis requires exactly two distinct named factors')
    if not isinstance(column,str) or not column or any(name not in frame for name in ['Condition',column,*factors]):raise ValueError('The outcome, Condition and both factor columns must exist')
    if comparisons is None:comparisons=_default_comparisons(len(names))
    requested=parse_pairs(comparisons,len(names),allow_self=False)
    retained=[];groups=[[] for _ in names];observation_ids=[[] for _ in names]
    from pandas.api.types import is_scalar
    for source_index,condition,value,a,b in frame[['Condition',column,*factors]].itertuples(index=True,name=None):
        if condition not in names:continue
        if not is_scalar(a) or not is_scalar(b) or not is_scalar(value) or isinstance(value,complex):raise ValueError('Measurements and categories must be scalar and the outcome real')
        try:value=float(value)
        except (ValueError,TypeError,OverflowError):continue
        if not math.isfinite(value) or pd.isna(a) or pd.isna(b):continue
        if any(isinstance(v,(float,np.floating)) and not math.isfinite(v) for v in (a,b)):continue
        retained.append((condition,value,a,b));groups[names.index(condition)].append(value);observation_ids[names.index(condition)].append(source_index)
    return list(factors),requested,retained,[pd.Series(values,index=ids,dtype=float) for values,ids in zip(groups,observation_ids)]



def _categorical_additive_residual(cells,levels_a,levels_b):
    """Solve integer category counts against exact measurement sums."""
    width=len(levels_a)+len(levels_b)-1
    gram=[[_two_way_fraction() for _ in range(width)] for _ in range(width)];rhs=[_two_way_fraction() for _ in range(width)];total=_two_way_fraction()
    for (a,b),values in cells.items():
        indices=[0]+([levels_a.index(a)] if a!=levels_a[0] else [])+([len(levels_a)-1+levels_b.index(b)] if b!=levels_b[0] else [])
        count=len(values);amount=sum(values);total+=sum(v*v for v in values)
        for i in indices:
            rhs[i]+=amount
            for j in indices:gram[i][j]+=count
    augmented=[row+[value] for row,value in zip(gram,rhs)];pivots=[];rank=0
    for column in range(width):
        pivot=next((i for i in range(rank,width) if augmented[i][column]),None)
        if pivot is None:continue
        augmented[rank],augmented[pivot]=augmented[pivot],augmented[rank];scale=augmented[rank][column]
        augmented[rank]=[v/scale for v in augmented[rank]]
        for i in range(width):
            if i==rank:continue
            scale=augmented[i][column]
            if scale:augmented[i]=[v-scale*u for v,u in zip(augmented[i],augmented[rank])]
        pivots.append(column);rank+=1
    beta=[_two_way_fraction() for _ in range(width)]
    for row,column in enumerate(pivots):beta[column]=augmented[row][-1]
    return total-sum(v*b for v,b in zip(rhs,beta)),rank



def _two_way_inference(retained):
    from PyFLASH._numeric_scaling import _rational_float,_f_tail_ratio
    cells={};by_a={};by_b={}
    for _,value,a,b in retained:
        number=_two_way_fraction(value);cells.setdefault((a,b),[]).append(number);by_a.setdefault(a,[]).append(number);by_b.setdefault(b,[]).append(number)
    def residual(collection):return sum((sum(v*v for v in values)-sum(values)**2/len(values) for values in collection.values()),_two_way_fraction())
    full=residual(cells);add,rank=_categorical_additive_residual(cells,list(by_a),list(by_b));degrees=len(retained)-len(cells)
    sums=[residual(by_b)-add,residual(by_a)-add,add-full,full]
    numerator_df=[rank-len(by_b),rank-len(by_a),len(cells)-rank]
    statistics=[];probabilities=[]
    for ss,first in zip(sums[:3],numerator_df):
        if first<=0 or degrees<=0:statistic=probability=math.nan
        elif not full:statistic=math.inf if ss else math.nan;probability=0. if ss else math.nan
        else:
            ratio=ss*degrees/(full*first);statistic=_rational_float(ratio);probability=_f_tail_ratio(ratio,first,degrees)
        statistics.append(statistic);probabilities.append(probability)
    return [_rational_float(v) for v in sums],statistics,probabilities+[math.nan],[*numerator_df,degrees]



def runTWA(experiment,column,factors=None,comparisons=None,results_dict=None,ns='ns'):
    if results_dict is None:results_dict={}
    if not isinstance(results_dict,_two_way_mutable_mapping):raise ValueError('The report must be a mutable mapping')
    factors,requested,retained,groups=_two_way_prepare(experiment,column,factors,comparisons)
    if len(groups)<2 or any(len(g)<2 for g in groups):return [],[],([],[]),results_dict,'Tukey'
    sums,statistics,probabilities,degrees=_two_way_inference(retained)
    results_dict['_group_test']={'symbol':'F','terms':[{'name':label,'statistic':statistic,'p':probability,'df':[float(first),float(degrees[-1])]} for label,statistic,probability,first in zip([*factors,'Interaction'],statistics,probabilities,degrees)]}
    terms=[f'C({factors[0]})',f'C({factors[1]})',f'C({factors[0]}):C({factors[1]})','Residual']
    for term,ss,probability in zip(terms,sums,probabilities):results_dict['2WA '+term.strip('C()')]=[ss,probability]
    tukey=_run_tukey(*groups)
    pair_statistics=[float(tukey.statistic[a,b]) for _,a,b in requested];pvalues=[float(tukey.pvalue[a,b]) for _,a,b in requested]
    results_dict['Tukey']=[pair_statistics,pvalues];_publish_uncorrected(results_dict,pvalues,basis='self_adjusted')
    return pvalues,[get_annotation(p,ns) for p in pvalues],(sums,probabilities),results_dict,'Tukey'



from PyFLASH._cache import bounded_lru_cache

def _normality_balance(values):
    from PyFLASH._numeric_scaling import _power_of_two_scale
    values=_power_of_two_scale(np.asarray(values,float))[0]
    return _power_of_two_scale(values-values[0])[0]

def _normality_dagostino(values):
    n=len(values)
    if n<8 or np.ptp(values)==0:return math.nan,math.nan
    x=_normality_balance(values);x=x-np.mean(x)
    variance=float(np.mean(x*x));skew=float(np.mean(x**3))/variance**1.5;kurt=float(np.mean(x**4))/variance**2
    beta=3*(n*n+27*n-70)*(n+1)*(n+3)/((n-2)*(n+5)*(n+7)*(n+9))
    w2=math.sqrt(2*(beta-1))-1;delta=math.sqrt(2/math.log(w2));a=math.sqrt(2/(w2-1))
    z3=delta*math.asinh(skew*math.sqrt((n+1)*(n+3)/(6*(n-2)))/a)
    sd4=math.sqrt(24*(n-2)*(n-3)*n/((n+1)**2*(n+3)*(n+5)));u4=(kurt-3+6/(n+1))/sd4
    B=6*(n*n-5*n+2)/((n+7)*(n+9))*math.sqrt(6*(n+3)*(n+5)/(n*(n-2)*(n-3)))
    A=6+8/B*(2/B+math.sqrt(1+4/B**2));ratio=(1-2/A)/(1+u4*math.sqrt(2/(A-4)))
    z4=(1-2/(9*A)-math.copysign(abs(ratio)**(1/3),ratio))/math.sqrt(2/(9*A))
    statistic=z3*z3+z4*z4
    return statistic,math.exp(-statistic/2)

@bounded_lru_cache(maxsize=32)
def _normality_shapiro_weights(n):
    quantiles=stats.norm.ppf((np.arange(1,n//2+1)-.375)/(n+.25))
    total=2*math.fsum(float(v)*float(v) for v in quantiles);root=math.sqrt(total);r=1/math.sqrt(n)
    def polynomial(coefficients):
        result=0.
        for coefficient in reversed(coefficients):result=result*r+coefficient
        return result
    first=polynomial([0,.221157,-.147981,-2.07119,4.434685,-2.706056])-quantiles[0]/root
    if n>5:
        second=polynomial([0,.042981,-.293762,-1.752461,5.682633,-3.582633])-quantiles[1]/root
        factor=math.sqrt((total-2*quantiles[0]**2-2*quantiles[1]**2)/(1-2*first**2-2*second**2))
        fixed=[first,second];offset=2
    else:
        factor=math.sqrt((total-2*quantiles[0]**2)/(1-2*first**2));fixed=[first];offset=1
    positive=fixed+[-float(v)/factor for v in quantiles[offset:]]
    return tuple([-v for v in positive]+([0.] if n%2 else [])+list(reversed(positive)))

def _normality_shapiro(values):
    from fractions import Fraction
    from PyFLASH._numeric_scaling import _rational_float
    n=len(values)
    if n<3 or np.ptp(values)==0:return math.nan,math.nan
    if n==3:
        q=sorted(Fraction(float(v)) for v in values);center=sum(q)/3
        W=(q[-1]-q[0])**2/(2*sum((v-center)**2 for v in q))
        numerator=4*W-3;denominator=2*(math.sqrt(float(W))+math.sqrt(float(3*(1-W))))
        ratio=_rational_float(numerator/Fraction(denominator))
        if abs(ratio)<1e-8:
            probability=_rational_float(numerator*Fraction(6/math.pi)/Fraction(denominator))
        else:probability=6/math.pi*math.asin(ratio)
        return float(W),max(0.,min(1.,probability))
    # Published AS R94 weights, with accurately evaluated normal quantiles.
    # Compute the correlation complement as a residual sum of squares so a
    # positive tail does not depend on subtracting a rounded W from one.
    coefficients=_normality_shapiro_weights(n)
    x=np.sort(_normality_balance(values));center=math.fsum(x)/n
    centered=[float(v)-center for v in x]
    coefficient_norm=math.fsum(a*a for a in coefficients)
    numerator=math.fsum(a*v for a,v in zip(coefficients,centered))
    ss=math.fsum(v*v for v in centered)
    projection=numerator/coefficient_norm
    one_minus=math.fsum((v-projection*a)**2 for a,v in zip(coefficients,centered))/ss
    W=1-one_minus
    if n>5000:return W,math.nan
    if one_minus<=0:return W,1.
    y=math.log(one_minus)
    if n<=11:
        gamma=-2.273+.459*n
        if y>=gamma:return W,1e-99
        y=-math.log(gamma-y)
        location=.544-.39978*n+.025054*n*n-.0006714*n**3
        scale=math.exp(1.3822-.77857*n+.062767*n*n-.0020322*n**3)
    else:
        ln=math.log(n);location=-1.5861-.31082*ln-.083751*ln**2+.0038915*ln**3
        scale=math.exp(-.4803-.082676*ln+.0030302*ln**2)
    return W,float(stats.norm.sf((y-location)/scale))

def test_normality(df_list,make_plot=True):
    """Test pooled finite samples and return the verdict, four tests and plot.

    DAgostino and fitted-normal Anderson use their published calibrations.
    Kolmogorov-Smirnov compares raw observations with standard N(0,1).
    Constant fitted samples and unsupported Shapiro probabilities are undefined;
    at least half the defined tests must have p > .05 for the returned verdict.
    """
    try:samples=list(df_list)
    except TypeError as error:raise ValueError('Normality data must be ordered one-dimensional samples.') from error
    groups=_finite_real_samples(samples)
    retained=[pd.Series(values,name=getattr(sample,'name',None)) for sample,values in zip(samples,groups) if len(values)]
    all_data=pd.concat(retained) if retained else pd.Series(dtype=float)
    results={};figure=None;axes=None;n=len(all_data)
    if n>=3:
        results['DA']=list(_normality_dagostino(all_data.to_numpy()))
        results['A']=list(modified_anderson(all_data))
        ks=kstest(all_data,'norm');ks_probability=float(ks.pvalue)
        ordered=np.sort(all_data.to_numpy(dtype=float));positions=np.arange(n,dtype=float)/n
        complement=float(min(np.min(stats.norm.sf(ordered)+positions),
                             np.min(stats.norm.cdf(ordered)+positions[::-1])))
        if complement <= 1./n:
            # Published Ruben-Gambino upper branch: 2*(1-D)**n. Evaluate
            # the complement from Gaussian tails before D rounds to one.
            ks_probability=math.exp(math.log(2.)+n*math.log(complement)) if complement>0 else 0.
        results['KS']=[float(ks.statistic),ks_probability]
        results['SW_all']=list(_normality_shapiro(all_data.to_numpy()))
    if make_plot:
        figure,axes=_dependency('plt').subplots(1,2,layout='constrained',figsize=(10,5))
        if n>=3:
            from fractions import Fraction
            bins=max(8,min(32,int(np.sqrt(n)*2)));lo=Fraction(float(all_data.min()));hi=Fraction(float(all_data.max()))
            if hi<=lo:hi=lo+1
            edges=[lo+(hi-lo)*Fraction(i,bins) for i in range(bins+1)]
            counts=[0]*bins
            for value in all_data:
                position=int((Fraction(float(value))-lo)*bins/(hi-lo))
                counts[min(position,bins-1)]+=1
            axes[0].bar([float(edge) for edge in edges[:-1]],counts,
                        width=[float(right-left) for left,right in zip(edges,edges[1:])],align='edge')
            # Matplotlib's unit conversion obtains widths by subtracting two
            # shifted coordinates. Restore the width before that cancellation.
            for patch,left,right in zip(axes[0].patches,edges,edges[1:]):
                patch.set_x(float(left));patch.set_width(float(right-left))
            axes[0].set_xlabel('' if all_data.name is None else str(all_data.name));axes[0].set_ylabel('Count')
            if np.ptp(all_data.to_numpy())>0:
                _dependency('sm').qqplot(_normality_balance(all_data.to_numpy()),ax=axes[1],fit=True,line='45')
            else:
                axes[1].set_xlabel('Theoretical Quantiles');axes[1].set_ylabel('Sample Quantiles')
            p_k2,p_a,p_ks,p_sw=[results[name][1] for name in ('DA','A','KS','SW_all')]
            k2=round(p_k2,2) if math.isfinite(p_k2) else 'n<8' if n<8 else 'n/a'
            text=f'K2: {k2}\nA: {round(p_a,2)}\nKS: {round(p_ks,2)}\nW: {round(p_sw,2)}'
            axes[0].annotate(text,xy=(.8,.8),size=10,xycoords='axes fraction')
    valid=[row[1] for row in results.values() if math.isfinite(row[1])]
    normal=bool(valid) and sum(p>.05 for p in valid)>=max(1,(len(valid)+1)//2)
    return normal,results,figure


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


def _fmt_test_number(value):
    """Keep small P values and fractional degrees of freedom readable."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return "n/a" if np.isnan(number) else f"{number:.6g}"


def _group_test_details(test, group_values=None, raw_stats=None):
    """Recover test metadata without fitting a model or changing its results."""
    details = (raw_stats or {}).get("_group_test")
    if isinstance(details, dict):
        return details
    # Old caches and direct helper calls may predate test metadata. Infer only
    # degrees of freedom fully identified by the tested groups.
    key = str(test).lower()
    if "anova" in key:
        details = {"symbol": "F"}
        if group_values is not None and "welch" not in key and "two-way" not in key:
            sizes = [len(pd.to_numeric(pd.Series(g), errors="coerce").dropna()) for g in group_values]
            sizes = [n for n in sizes if n]
            details["df"] = [len(sizes) - 1, sum(sizes) - len(sizes)]
        return details
    if "kruskal" in key:
        return {"symbol": "H", **({"df": [len(group_values) - 1]} if group_values is not None else {})}
    if "mann-whitney" in key:
        return {"symbol": "U"}
    if "t-test" in key or "t test" in key:
        return {"symbol": "t"}
    return {"symbol": "statistic"}


def _group_test_line(label, statistic, pvalue, details):
    symbol = details.get("symbol", "statistic")
    degrees = details.get("df") or []
    if degrees:
        symbol += "(" + ", ".join(_fmt_test_number(v) for v in degrees) + ")"
    if statistic is None:
        return f"{label} p={_fmt_test_number(pvalue)}"
    return f"{label}: {symbol}={_fmt_test_number(statistic)}, p={_fmt_test_number(pvalue)}"


def _annotate_stats_summary(ax, test, post_hoc, overall, comparisons, pairwise_pvalues, condition_list, factor_list=None, effect_strings=None, group_values=None, raw_stats=None):
    """Draw a compact statistics summary to the right of the plot."""
    lines = [f"Test: {test}", f"Post-hoc: {post_hoc}"]

    overall_stat, overall_p = overall if isinstance(overall, tuple) and len(overall) == 2 else (None, None)
    details = _group_test_details(test, group_values, raw_stats)
    if details.get("terms"):
        for term in details["terms"]:
            lines.append(_group_test_line(term["name"], term["statistic"], term["p"], {**term, "symbol": details["symbol"]}))
    elif isinstance(overall_p, (list, tuple)) and details["symbol"] == "U":
        for i, p in enumerate(overall_p):
            comp = comparisons[i] if i < len(comparisons) else f"Comparison {i+1}"
            stat = overall_stat[i] if isinstance(overall_stat, (list, tuple)) and i < len(overall_stat) else None
            lines.append(_group_test_line(comp, stat, p, details))
    elif isinstance(overall_p, (list, tuple)):
        labels = factor_list or ["Factor 1", "Factor 2", "Interaction", "Residual"]
        for i, p in enumerate(overall_p):
            name = labels[i] if i < len(labels) else f"Term {i+1}"
            # Legacy two-way `overall` contains sums of squares, not F values.
            lines.append(f"{name} p={_fmt_test_number(p)}")
    elif overall_p is not None:
        lines.append(_group_test_line("Group", overall_stat, overall_p, details))

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
    """Build ordered significance captions for validated one-based comparison pairs. Every pair must have one corresponding probability. Legacy metadata parameters remain accepted."""
    from PyFLASH._comparison_tokens import parse_pairs
    pairs = parse_pairs(comparisons, len(condition_list), allow_self=False)
    if len(pairs) != len(individual_results):
        raise ValueError('Every comparison needs exactly one result')
    if not isinstance(overall_p, list):
        group = {'Group difference': get_annotation(overall_p, 'ns')}
    else:
        labels = factor_list or ['Factor 1', 'Factor 2', 'Interaction', 'Residual']
        group = {labels[i] if i < len(labels) else f'Term {i + 1}': get_annotation(p, 'ns') for i, p in enumerate(overall_p)}
    summaries = [f"{_name_of(condition_list[a])} vs {_name_of(condition_list[b])} {get_annotation(p, 'ns')}" for (_, a, b), p in zip(pairs, individual_results)]
    return (group, summaries)


def draw_comparison_brackets(ax, centers, comparisons, annotations, *,
                             base_height, pad_height, handles, visible_y_span,
                             lw=2, offset=.1, floor=None, color='black',
                             star_y_offset_frac=None):
    """Draw validated house brackets at declared centers without changing group order."""
    from matplotlib.axes import Axes
    if not isinstance(ax,Axes):raise ValueError('Comparison drawing requires Matplotlib axes.')
    plan=_comparison_bracket_plan(centers,comparisons,annotations,base_height=base_height,
        pad_height=pad_height,handles=handles,visible_y_span=visible_y_span,lw=lw,
        offset=offset,floor=floor,color=color,star_y_offset_frac=star_y_offset_frac)
    ax.set_ylim(*ax.get_ylim())
    return _comparison_draw_plan(ax,plan)


def plot_comparison_lines_from_figdata(scatter,bar,ax,annotations=None,comparisons=None,
    errobar_width=.12,lw=2,pad=10,handles_fraction=.3,max_override=None,
    group_values=None,group_positions=None,group_colors=None,draw_error_bars=True):
    """Draw finite group SEM and selected brackets, preserving original group positions."""
    from matplotlib.axes import Axes
    from matplotlib.colors import to_rgba
    from PyFLASH._comparison_tokens import parse_pairs
    if not isinstance(ax,Axes):raise ValueError('Comparison drawing requires Matplotlib axes.')
    cap=_comparison_number(errobar_width,0.);width=_comparison_number(lw,0.,True)
    padding=_comparison_number(pad,0.,True);handle_fraction=_comparison_number(handles_fraction,0.)
    override=None if max_override is None else _comparison_number(max_override)
    if not isinstance(draw_error_bars,(bool,np.bool_)):raise ValueError('draw_error_bars must be Boolean.')
    if group_positions is not None:centers=_comparison_centers(group_positions)
    elif bar is not None:
        try:centers=list(dict.fromkeys(patch.get_x()+patch.get_width()/2 for patch in bar.patches
                                     if patch.get_gid()!='pyflash-comparison-height-anchor'))
        except (AttributeError,TypeError) as error:raise ValueError('Bars must expose their group centers.') from error
        centers=_comparison_centers(centers)
    else:return None
    count=len(centers);colors=['black']*count
    if group_values is not None:
        groups=_finite_real_samples(group_values)
        if len(groups)!=count:raise ValueError('Every declared group needs one bar center.')
    else:
        groups=[[] for _ in centers]
        if scatter is None or not hasattr(scatter,'collections'):return None
        for collection in scatter.collections:
            offsets=collection.get_offsets()
            if offsets is None or not len(offsets):continue
            edge=collection.get_edgecolor();edge_color=edge[0] if edge is not None and len(edge) else 'black'
            points=np.ma.asarray(offsets,dtype=float)
            if points.ndim!=2 or points.shape[1]!=2:raise ValueError('Scatter observations need x/y coordinates.')
            for x,y in points.filled(np.nan):
                if not math.isfinite(x) or not math.isfinite(y) or not count:continue
                index=min(range(count),key=lambda i:abs(centers[i]-x));groups[index].append(float(y));colors[index]=edge_color
    if group_colors is not None:
        if isinstance(group_colors,(str,bytes,Mapping)):raise ValueError('Group colors must be an ordered color sequence.')
        try:provided=list(group_colors)
        except TypeError as error:raise ValueError('Group colors must be an ordered color sequence.') from error
        for i,color in enumerate(provided):
            try:to_rgba(color)
            except (ValueError,TypeError) as error:raise ValueError('Invalid group color.') from error
            if i<count:colors[i]=color
    try:colors=[to_rgba(color) for color in colors]
    except (ValueError,TypeError) as error:raise ValueError('Invalid scatter color.') from error
    if isinstance(annotations,(str,bytes,Mapping)):raise ValueError('Annotations must be an ordered label sequence.')
    try:labels=[] if annotations is None else list(annotations)
    except TypeError as error:raise ValueError('Annotations must be an ordered label sequence.') from error
    if comparisons is None:comparisons=_default_comparisons(count) if labels else []
    parse_pairs(comparisons,count,allow_self=False)
    if labels and len(labels)!=len(comparisons):raise ValueError('Every requested bracket needs one annotation.')
    active={i:values for i,values in enumerate(groups) if len(values)}
    if not active:return None
    means={};sems={}
    for index,values in active.items():means[index],sems[index]=_comparison_sample_moments(values)
    upper={i:means[i]+sems[i] for i in active}
    outward={i:means[i]+sems[i] if means[i]>=0 else means[i]-sems[i] for i in active}
    maximum=max(max(float(v) for group in active.values() for v in group),max(upper.values()))
    if override is not None:maximum=max(maximum,override)
    bottom,top=map(float,ax.get_ylim());required=max(upper.values())*1.03
    if top<required:top=required
    if min(outward.values())<bottom:bottom=min(outward.values())*1.03
    if not all(math.isfinite(v) for v in [*means.values(),*sems.values(),*upper.values(),*outward.values(),maximum,bottom,top]):
        raise ValueError('Measurement uncertainty exceeds finite drawing coordinates.')
    span=top-bottom
    if not math.isfinite(span) or span<=0:span=max(abs(top),abs(bottom),1.)
    plan=_comparison_bracket_plan(centers,comparisons,labels,base_height=top+span/padding,
        pad_height=span/padding,handles=span/padding*handle_fraction,visible_y_span=span,
        lw=width,floor=maximum,available=set(active))
    result=plan[0];anchor=None
    if result[1] is not None:
        xmin,xmax=ax.get_xlim();xepsilon=max(abs(float(xmax-xmin)),1.)*1e-9
        anchor=(centers[0],result[1]+span*.07,xepsilon,span*1e-9)
        if not all(math.isfinite(v) for v in anchor):raise ValueError('Comparison envelope exceeds finite coordinates.')
    ax.set_ylim(bottom,top)
    if draw_error_bars:
        for i in active:
            x=centers[i];ax.plot([x,x],[means[i],outward[i]],color=colors[i],zorder=2.5,lw=2.5)
            ax.plot([x-cap,x+cap],[outward[i],outward[i]],color=colors[i],zorder=2.6,lw=2.5)
    _comparison_draw_plan(ax,plan)
    if anchor is not None:
        patch=_dependency('Rectangle')((anchor[0],anchor[1]),anchor[2],anchor[3],
            facecolor='none',edgecolor='none',linewidth=0,clip_on=False)
        patch.set_gid('pyflash-comparison-height-anchor');ax.add_patch(patch)
    return maximum

def plot_comparison_lines_from_fig_data(*args,**kwargs):
    """Backward-compatible alias for alternative function naming."""
    return plot_comparison_lines_from_figdata(*args,**kwargs)


def _record_applied_correction(results_dict, label):
    """Remember which correction actually produced the reported p-values.

    Recovered from data rather than by splitting a display string like
    "Dunn Bonferroni", which breaks the moment someone adds a hyphen.
    """
    inputs = results_dict.get("_audit_inputs")
    if not isinstance(inputs, dict):
        inputs = {}
    inputs["correction"] = label
    results_dict["_audit_inputs"] = inputs
    return results_dict


def _public_results(results_dict):
    """The result rows only - no underscore-prefixed plumbing.

    ``_audit_inputs`` holds raw value and rank arrays; letting those reach a
    stored record would inflate every manifest with a second copy of the data.
    """
    return {k: v for k, v in results_dict.items() if not str(k).startswith("_")}


def _strip_audit_inputs(results_dict):
    """A copy of *results_dict* without the raw arrays the audit needed.

    ``_audit_inputs`` carries the observed values and the rank vector. The
    stats cache lives for a whole session, so pinning a figure's data there
    long after the figure is drawn is pure waste.
    """
    inputs = results_dict.get("_audit_inputs")
    if not inputs:
        return results_dict
    trimmed = dict(results_dict)
    trimmed["_audit_inputs"] = {
        key: value for key, value in inputs.items()
        if key not in ("groups", "ranks")
    }
    return trimmed


def _publish_uncorrected(results_dict, pvalues, *, basis="raw", **extra):
    """Publish a post-hoc's own p-values on the one channel the audit reads.

    Every post-hoc path writes here, aligned one-to-one with *comparisons*, so
    the correction audit never has to know which test produced the numbers.
    *basis* records whether those p-values are raw or already adjusted by the
    post-hoc itself; *extra* carries whatever a path can offer towards a
    permutation null.
    """
    values = []
    for p in pvalues:
        try:
            values.append(float(p))
        except (TypeError, ValueError):
            values.append(float("nan"))
    results_dict["Posthoc-Uncorrected"] = [1, values]
    inputs = results_dict.get("_audit_inputs")
    if not isinstance(inputs, dict):
        inputs = {}
    inputs["basis"] = basis
    inputs.update(extra)
    results_dict["_audit_inputs"] = inputs
    return results_dict


_LADDER_ROWS = (
    ("uncorrected", "Correction-Uncorrected"),
    ("holm", "Correction-Holm"),
    ("bh_q", "Correction-BH-q"),
    ("bonferroni", "Correction-Bonferroni"),
    ("sidak", "Correction-Sidak"),
    ("westfall_young", "Correction-WestfallYoung"),
)

_PERMUTATION_ROWS = (
    ("alpha_star", "Correction-AlphaStar"),
    ("alpha_bonferroni", "Correction-AlphaBonferroni"),
    ("fwer_if_uncorrected", "Correction-FWER-Uncorrected"),
    ("fwer_of_bonferroni", "Correction-FWER-Bonferroni"),
    ("p_floor", "Correction-pFloor"),
    ("p_resolution", "Correction-NullResolution"),
)


def _audit_to_results_dict(audit, comparisons, results_dict, results_strings,
                           basis="raw"):
    """Write the correction ladder into results_dict so the CSV carries it.

    Row shape matches ``results_to_excel``: ``[label, 1, *pvalues]`` for the
    per-comparison ladders, ``[label, value, nan]`` for the design-wide numbers.
    Never changes what is plotted - this only records what each convention
    would have said.
    """
    from PyFLASH.stats_extra import verdict_changes

    alpha = float(audit.get("alpha", 0.05))
    for key, label in _LADDER_ROWS:
        values = audit.get(key)
        if values:
            results_dict[label] = [1, [float(v) for v in values]]

    perm = audit.get("permutation")
    if perm:
        for key, label in _PERMUTATION_ROWS:
            if perm.get(key) is not None:
                results_dict[label] = [float(perm[key]), np.nan]
        results_dict["Correction-NullMode"] = [
            f"{perm.get('mode')} ({perm.get('n_perm')} perms)", np.nan
        ]
    elif audit.get("skipped"):
        results_dict.setdefault("Correction-Unavailable", [str(audit["skipped"]), np.nan])

    # Whether the p-values the ladder was applied to were raw or already
    # multiplicity-adjusted by the post-hoc itself (Tukey, Dunnett, Nemenyi and
    # friends carry their own correction in the studentised range). On a
    # self-adjusted basis the ladder rows are a second correction on top, so
    # they read conservative - the reader has to be told which they are looking
    # at.
    results_dict["Correction-Basis"] = [str(basis), np.nan]

    # Guarded on its own: the ladder rows above are the always-on promise, and
    # a fault in the summary must not take them down with it.
    try:
        changes = verdict_changes(audit, comparisons, alpha=alpha)
    except Exception as exc:
        results_dict["Correction_verdict_error"] = [str(exc), np.nan]
        changes = {}
    if changes:
        results_strings["Correction audit"] = [
            f"{comp}: significant under "
            f"{', '.join(names) if names else 'no convention'}"
            for comp, names in changes.items()
        ]
    if perm:
        calibrated = (f"{perm['alpha_star']:.4f}" if perm['alpha_star'] is not None
                      else 'unattainable')
        results_strings["Correction calibration"] = (
            f"calibrated alpha*={calibrated} vs Bonferroni "
            f"{perm['alpha_bonferroni']:.4f}; uncorrected FWER "
            f"{perm['fwer_if_uncorrected']:.3f}; smallest null raw p "
            f"{perm['p_floor']:.4g}"
        )
    return results_dict


# Guard rails on the permutation audit. Above the pooled-n ceiling the
# sampled branch still costs only ~30 ms, but Bonferroni's conservatism is
# negligible at that n and the audit has nothing to say, so it is not worth a
# (20000, k) allocation on a pathological ROI-level call.
MAX_AUDIT_N = 200
MIN_AUDIT_GROUP = 2


def _westfall_young_from_inputs(results_dict, pvalues, statistic, Config):
    """Westfall-Young values for one statistic, from the published inputs.

    Reuses the same cached null the audit uses, so asking for the correction
    costs nothing beyond what the audit already paid on the rank path.
    """
    from PyFLASH import stats_extra as _se

    inputs = dict(results_dict.get("_audit_inputs") or {})
    # explicit_wy: the request itself authorises the per-column cost the
    # "cheap" tier would otherwise decline.
    plan, reason = _permutation_plan(inputs, len(pvalues), Config,
                                     explicit_wy=True)
    if plan is None:
        if reason is None and getattr(Config, "CORRECTION_AUDIT", "cheap") is False:
            reason = ("Config.CORRECTION_AUDIT is off, so no permutation null "
                      "was computed")
        elif reason is None and len(pvalues) < 2:
            reason = ("a single comparison is not a family, so there is "
                      "nothing to correct")
        raise CorrectionUnavailable(reason or _NO_NULL_MESSAGE)
    if statistic is not None:
        plan["statistic"] = statistic
    try:
        null = _build_null(plan)
        return _se.westfall_young_from_null(
            pvalues, null, inputs.get("pairs"))
    except ValueError as exc:
        raise CorrectionUnavailable(str(exc)) from exc


def _correct_or_fall_back(pvalues, method, label, n_tests, results_dict,
                          wy=None):
    """Apply *method*, or record why it could not be and use ``auto`` instead.

    A user who set a session-wide correction should not lose every figure on a
    path that cannot supply it; the CSV says what happened.
    """
    try:
        return _apply_kw_correction(pvalues, method, wy=wy), method, label
    except CorrectionUnavailable as exc:
        results_dict.setdefault("Correction-Unavailable", [str(exc), np.nan])
        method, label = _normalize_kw_correction("auto", n_tests)
        return _apply_kw_correction(pvalues, method), method, label


def _permutation_plan(inputs, n_comparisons, Config, explicit_wy=False):
    """Decide whether a permutation null is available, valid and affordable.

    Returns ``(kwargs_or_None, reason_or_None)``. A reason without kwargs is
    recorded in the CSV, so a reader can tell "not applicable" from
    "not computed"; no reason means the audit simply had nothing to say.
    """
    tier = getattr(Config, "CORRECTION_AUDIT", "cheap")
    if tier is False:
        return None, None
    if n_comparisons < 2:
        # One comparison is not a family; correcting it is a no-op.
        return None, None
    family = inputs.get("family")
    if family == "rank":
        sizes = tuple(inputs.get("group_sizes") or ())
        blocked = _size_guard(sizes)
        if blocked:
            return None, blocked
        return {
            "family": "rank",
            "group_sizes": sizes,
            "ranks": inputs.get("ranks"),
            "statistic": inputs.get("statistic", "dunn"),
            "n_resamples": int(getattr(Config, "CORRECTION_RESAMPLES", 20000)),
            "exact_max": int(getattr(Config, "CORRECTION_EXACT_MAX", 10000)),
        }, None
    if family == "value":
        # Per column rather than per design, so it does not run on every
        # figure by default. Asking for the correction is asking for its cost.
        if not (tier == "full" or explicit_wy):
            return None, None
        groups = list(inputs.get("groups") or [])
        blocked = _size_guard(tuple(len(g) for g in groups))
        if blocked:
            return None, blocked
        return {
            "family": "value",
            "groups": groups,
            "statistic": inputs.get("statistic", "lsd"),
            "n_resamples": int(
                getattr(Config, "CORRECTION_RESAMPLES_VALUE", 10000)),
        }, None
    return None, inputs.get("reason")


def _size_guard(sizes):
    """Why this design is out of bounds for a permutation audit, or None."""
    if not sizes or min(sizes) < MIN_AUDIT_GROUP:
        return "a group of one carries no information to permute"
    if sum(sizes) > MAX_AUDIT_N:
        return (f"pooled n={sum(sizes)} is above the {MAX_AUDIT_N} ceiling "
                "for the permutation audit")
    return None


def _build_null(plan):
    """Turn a plan into a null. The one place either kind is constructed."""
    from PyFLASH import stats_extra as _se

    plan = dict(plan)
    if plan.pop("family") == "rank":
        return _se.permutation_null(
            plan.pop("group_sizes"), plan.pop("ranks"), **plan)
    return _se.value_permutation_null(plan.pop("groups"), **plan)


def _note_unhonoured_request(results_dict, requested, applied, n_tests, inputs):
    """Record why a requested correction was not the one reported.

    Some paths never look at ``posthoc_correction`` at all - Welch ANOVA picks
    Games-Howell or Tamhane T2 and ignores it - so a request can go unanswered
    without any branch having refused it. Silence there would be the worst
    outcome: the user believes they switched correction and did not.
    """
    if requested is None or "Correction-Unavailable" in results_dict:
        return
    try:
        method, _label = _normalize_kw_correction(requested, n_tests)
    except ValueError:
        return
    if method != "westfall_young":
        return
    if "Westfall-Young" in str(applied or ""):
        return
    results_dict["Correction-Unavailable"] = [
        inputs.get("reason") or _NO_NULL_MESSAGE, np.nan]


def _run_correction_audit(results_dict, results_strings, comparisons, Config,
                          requested=None, applied=None):
    from PyFLASH import stats_extra as _se

    raw = results_dict.get("Posthoc-Uncorrected")
    raw_p = raw[1] if isinstance(raw, (list, tuple)) and len(raw) > 1 else None
    if not raw_p:
        return None
    inputs = results_dict.get("_audit_inputs") or {}
    _note_unhonoured_request(results_dict, requested, applied, len(raw_p), inputs)
    explicit_wy = False
    if requested is not None:
        try:
            explicit_wy = _normalize_kw_correction(requested, len(raw_p))[0] == "westfall_young"
        except ValueError:
            pass
    plan, reason = _permutation_plan(inputs, len(raw_p), Config, explicit_wy=explicit_wy)
    null = None
    if plan is not None:
        try:
            null = _build_null(plan)
            aligned = _se._align_null_columns(np.asarray(null["p"], float), null["pairs"], inputs.get("pairs"))
            if aligned is None:
                null = None
                reason = "reported comparisons do not match the null design"
            else:
                null = {**null, "p": aligned, "pairs": inputs.get("pairs") or null["pairs"]}
        except Exception as exc:
            null = None
            reason = f"the permutation null could not be built: {exc}"
    audit = _se.correction_audit(raw_p, null=null, want_permutation=False, pairs=inputs.get("pairs"))
    if null is not None and inputs.get("family") == "rank":
        ranked = np.asarray(inputs["ranks"], float)
        groups = np.split(ranked, np.cumsum(inputs["group_sizes"])[:-1])
        requested_pairs = [(str(i), a, b) for i, (a, b) in enumerate(inputs["pairs"])]
        audit["westfall_young"] = _rank_westfall_young(
            results_dict, raw_p, inputs["statistic"], Config,
            _rank_design(groups), requested_pairs)
    if reason and not audit.get("permutation"):
        audit.setdefault("skipped", reason)
    _audit_to_results_dict(audit, comparisons, results_dict, results_strings, basis=inputs.get("basis", "raw"))
    results_dict["_correction_audit"] = audit
    return audit


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
            raw_stats=_public_results(results_dict),
            normal=normal,
            factor_terms=term_labels,
            correction_audit=results_dict.get("_correction_audit"),
            correction_reported=(
                (results_dict.get("_audit_inputs") or {}).get("correction")),
        )
        # Carry the same typed statistic/df as the figure, including the actual
        # F tests rather than the legacy two-way return's sums of squares.
        record["test"].update(_group_test_details(test, valid_groups, results_dict))
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

    if posthoc_correction in (None, "auto"):
        # A session-wide switch, so a whole run can move to the calibrated
        # correction without threading a parameter through every call. The
        # signature default stays the literal "auto" so the function is still
        # readable and callable outside a configured session.
        posthoc_correction = getattr(Config, "POSTHOC_CORRECTION", "auto")

    scope_test = _normalize_group_stats_test(stats_test)
    if not dfs and scope_test not in {"linear_model", "two_way"}:
        return "N/A", "N/A", None, {}
    # Validate dimensions before coercion; keep declared group positions.
    _finite_real_samples(dfs)
    clean_dfs = []
    for group in dfs:
        values = pd.to_numeric(pd.Series(group), errors="coerce")
        clean_dfs.append(values[np.isfinite(values)].astype(float))
    if scope_test == "linear_model" and model_df is not None:
        group_column = model_group_col or "Condition"
        value_column = model_value_col or (getattr(dfs[0], "name", None) if dfs else None)
        declared_order = [_name_of(group) for group in (group_labels or [])] or None
        prepared, order, _, _, _, _ = _linear_model_prepare(
            model_df, value_column, group_column, [], {}, covariates,
            categorical_covariates, posthoc_correction, cov_type, cov_kwds,
            declared_order)
        source_ids = pd.Index(prepared.attrs['_pyflash_observation_ids'])
        clean_dfs = [pd.Series(
            prepared.loc[prepared[group_column].astype(str) == name, value_column].to_numpy(),
            index=source_ids[prepared[group_column].astype(str).to_numpy() == name],
            name=value_column, dtype=float) for name in order]
    elif scope_test == "two_way" or (
        scope_test == "auto" and multiple_comparison == "Two-Way"
        and getattr(experiment, "summary", None) is not None
        and isinstance(getattr(getattr(experiment, "condition_list", None), "factor", None), (list, tuple))
        and len(experiment.condition_list.factor) == 2
    ):
        value_column = getattr(dfs[0], "name", None) if dfs else model_value_col
        _, _, _, scoped_groups = _two_way_prepare(experiment, value_column, None, [])
        clean_dfs = [pd.Series(values, name=value_column, dtype=float)
                     for values in scoped_groups]
    valid_groups = clean_dfs
    valid_indices = list(range(len(clean_dfs)))
    if sum(bool(len(group)) for group in valid_groups) < 2:
        return "N/A", "N/A", None, {}

    # â”€â”€ Cache lookup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    cached = None
    input_identity = None
    if cache_key is not None and Config.STATS_CACHE:
        import hashlib
        import pickle
        # A caller's display key cannot establish measurement identity. Keep
        # that key for compatibility, but independently verify the data and
        # inference settings before reusing its stored answer.
        inference = {
            'groups': clean_dfs, 'model_df': model_df,
            'two_way_summary': getattr(experiment, 'summary', None)
                if scope_test == 'two_way' or (scope_test == 'auto' and multiple_comparison != 'One-Way') else None,
            'multiple_comparison': multiple_comparison, 'comparisons': comparisons,
            'force_nonparametric': force_nonparametric, 'posthoc': posthoc,
            'posthoc_correction': posthoc_correction, 'stats_test': stats_test,
            'variance_test': variance_test, 'variance_alpha': variance_alpha,
            'auto_welch': auto_welch, 'model_group_col': model_group_col,
            'model_value_col': model_value_col, 'covariates': covariates,
            'categorical_covariates': categorical_covariates, 'cov_type': cov_type,
            'cov_kwds': cov_kwds, 'ns': ns, 'group_labels': group_labels,
            'conditions': [
                {name: getattr(group, name, None) for name in
                 ('name', 'label', 'factor', 'factor_explanation')}
                if not isinstance(group, str) else group
                for group in (getattr(experiment, 'condition_list', None) or [])
            ],
            'factor': getattr(experiment, 'factor', None),
            'experiment_name': getattr(experiment, 'name', None),
            'session': stats_cache_key('', (), ()),
        }
        input_identity = hashlib.sha256(pickle.dumps(inference, protocol=5)).hexdigest()
        cached = _stats_cache.get(cache_key)
        if cached is not None and cached.get('input_identity') != input_identity:
            cached = None
        elif cached is not None:
            # Drawing, reporting and caller edits must not alter the stored answer.
            cached = deepcopy(cached)
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
                    group_values=valid_groups, raw_stats=results_dict,
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
    from PyFLASH._comparison_tokens import parse_pairs
    comparisons = [token for token, _, _ in parse_pairs(
        comparisons, len(valid_groups), allow_self=False)]
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
        _dependency('plt').close(norm_fig)
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
                    valid_groups, comparisons, results_dict, ns
                )
                test = "Mann-Whitney U"
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
                # The overall t statistic describes the declared two groups;
                # requested pairwise probabilities retain their exact selection.
                probability = results[0]
                results = [probability for _ in comparisons]
                annotations = [get_annotation(probability, ns) for _ in comparisons]
                results_dict["Posthoc-Uncorrected"] = [1, results]
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

    if comparisons and not results and not results_dict.get("_group_test"):
        # A declared empty/singleton group can make the whole test undefined.
        # Keep undefined answers aligned with the requested captions/records.
        results = [math.nan for _ in comparisons]
        annotations = [get_annotation(math.nan, ns) for _ in comparisons]

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

    # â”€â”€ Effect sizes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # â”€â”€ Correction audit â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Always computed, never plotted. The closed-form ladder costs nothing and
    # answers "would a different correction convention have changed this?"
    # without touching the reported verdict.
    if getattr(Config, "CORRECTION_AUDIT", "cheap") is not False:
        try:
            _run_correction_audit(
                results_dict, results_strings, comparisons, Config,
                requested=posthoc_correction, applied=post_hoc)
        except Exception as e:
            results_dict["Correction_audit_error"] = [str(e), np.nan]

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
                group_values=valid_groups, raw_stats=results_dict,
            )

    # â”€â”€ Cache store â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if cache_key is not None and Config.STATS_CACHE:
        _stats_cache[cache_key] = deepcopy({
            'input_identity': input_identity,
            'test': test,
            'post_hoc': post_hoc,
            'annotations': annotations,
            'results': results,
            'overall': overall,
            'results_dict': _strip_audit_inputs(results_dict),
            'comparisons': comparisons,
            'results_strings': results_strings,
            'effect_strings': effect_strings,
            'normal': normal,
        })

    _emit_comparison_record(
        valid_groups, group_labels, cond_list, test, post_hoc,
        overall, comparisons, results, effect_strings, results_dict, normal,
        fallback_metric=save_name, valid_indices=valid_indices,
        factor_list=getattr(experiment, "factor", None), figure=fig,
    )
    return test, post_hoc, annotation_objects, results_dict




def _one_way_geometry(groups):
    from PyFLASH._numeric_scaling import _rational_float,_rational_sqrt,_f_tail_ratio,_t_tail_squared
    from fractions import Fraction
    rational,average,_=_rational_sample_geometry(groups)
    means=list(map(average,rational));total=sum(map(len,rational));count=len(rational)
    grand=average([v for group in rational for v in group])
    within=sum(sum((v-center)**2 for v in group) for group,center in zip(rational,means))
    between=sum(len(group)*(center-grand)**2 for group,center in zip(rational,means))
    degrees=total-count;mse=within/degrees
    if not within:statistic,probability=(math.inf,0.) if between else (math.nan,math.nan)
    else:
        ratio=between/within*Fraction(degrees,count-1)
        statistic=_rational_float(ratio)
        probability=_f_tail_ratio(ratio,count-1,degrees)
    return means,mse,degrees,statistic,probability


def _pooled_pair_geometry(means,mse,degrees,groups,first,second):
    from PyFLASH._numeric_scaling import _rational_float,_rational_sqrt,_f_tail_ratio,_t_tail_squared
    from fractions import Fraction
    difference=means[first]-means[second]
    uncertainty=mse*(Fraction(1,len(groups[first]))+Fraction(1,len(groups[second])))
    if not uncertainty:
        statistic=(math.inf if difference>0 else -math.inf) if difference else math.nan
        probability=0. if difference else math.nan
    else:
        squared=difference**2/uncertainty
        statistic=_rational_sqrt(squared)*(1 if difference>=0 else -1)
        probability=_t_tail_squared(squared,degrees)
    return statistic,probability


def _one_way_posthoc(groups,comparisons,kind):
    from PyFLASH._numeric_scaling import _rational_float,_rational_sqrt,_f_tail_ratio,_t_tail_squared
    from fractions import Fraction
    from PyFLASH._comparison_tokens import parse_pairs
    from PyFLASH._studentized_range import range_tail,range_tail_squared
    means,mse,degrees,_,_=_one_way_geometry(groups)
    requested=parse_pairs(comparisons,len(groups),allow_self=False)
    count=len(groups);statistics=[];probabilities=[]
    for _,first,second in requested:
        statistic,probability=_pooled_pair_geometry(means,mse,degrees,groups,first,second)
        difference=means[first]-means[second]
        uncertainty=mse*(Fraction(1,len(groups[first]))+Fraction(1,len(groups[second])))
        if kind=='tukey':
            probability=range_tail_squared(2*difference**2/uncertainty,count,degrees) if uncertainty else range_tail(abs(statistic)*math.sqrt(2),count,degrees)
            statistic=_rational_float(difference)
        elif kind=='scheffe':
            ratio=difference**2/(uncertainty*(count-1)) if uncertainty else math.inf if difference else math.nan
            statistic=_rational_float(ratio);probability=_f_tail_ratio(ratio,count-1,degrees)
        elif kind=='tamhane':
            statistic,probability,_=_unequal_pair_geometry(groups[first],groups[second])
            if probability==1:probability=1.
            elif math.isfinite(probability):probability=sidak_correction(probability,count*(count-1)//2)
        statistics.append(statistic);probabilities.append(probability)
    return statistics,probabilities



def _unequal_pair_geometry(first,second):
    from PyFLASH._numeric_scaling import _rational_float,_rational_sqrt,_f_tail_ratio,_t_tail_squared
    rational,average,_=_rational_sample_geometry([first,second])
    a,b=rational;na,nb=len(a),len(b)
    ma,mb=average(a),average(b)
    va=sum((v-ma)**2 for v in a)/(na-1);vb=sum((v-mb)**2 for v in b)/(nb-1)
    uncertainty=va/na+vb/nb;difference=ma-mb
    if not uncertainty:
        statistic=(math.inf if difference>0 else -math.inf) if difference else math.nan
        return statistic,0. if difference else math.nan,math.nan
    degrees=float(uncertainty**2/((va/na)**2/(na-1)+(vb/nb)**2/(nb-1)))
    squared=difference**2/uncertainty
    statistic=_rational_sqrt(squared)*(1 if difference>=0 else -1)
    return statistic,_t_tail_squared(squared,degrees),degrees


def _welch_one_way_geometry(groups):
    from fractions import Fraction
    rational,average,_=_rational_sample_geometry(groups);count=len(groups)
    means=list(map(average,rational))
    variances=[sum((v-center)**2 for v in group)/(len(group)-1) for group,center in zip(rational,means)]
    if any(not variance for variance in variances):return math.nan,math.nan,float(count-1),math.nan
    weights=[len(group)/variance for group,variance in zip(groups,variances)];total=sum(weights)
    center=sum(w*m for w,m in zip(weights,means))/total
    contribution=sum((1-w/total)**2/(len(group)-1) for w,group in zip(weights,groups))
    numerator=sum(w*(m-center)**2 for w,m in zip(weights,means))/(count-1)
    statistic=float(numerator/(1+Fraction(2*(count-2),count**2-1)*contribution))
    degrees=float(Fraction(count**2-1,3)/contribution)
    return statistic,float(stats.f.sf(statistic,count-1,degrees)),float(count-1),degrees


def _comparison_number(value, minimum=None, strict=False):
    from numbers import Real
    if isinstance(value,(bool,np.bool_)) or not isinstance(value,Real) or not math.isfinite(float(value)):
        raise ValueError('Drawing parameters must be finite real numbers.')
    result=float(value)
    if minimum is not None and (result<=minimum if strict else result<minimum):
        raise ValueError('Drawing parameter is outside its supported range.')
    return result

def _comparison_centers(values):
    if isinstance(values,(str,bytes,Mapping)):
        raise ValueError('Group centers must be an ordered real sequence.')
    try:result=[_comparison_number(value) for value in values]
    except TypeError as error:raise ValueError('Group centers must be an ordered real sequence.') from error
    if len(set(result))!=len(result):raise ValueError('Every group needs a distinct center.')
    return result

def _comparison_sample_moments(values):
    from fractions import Fraction
    from PyFLASH._numeric_scaling import _rational_sqrt
    measured=[Fraction(float(value)) for value in values];size=len(measured)
    center=sum(measured)/size
    uncertainty=sum((value-center)**2 for value in measured)/(size*(size-1)) if size>1 else Fraction(0)
    return float(center),_rational_sqrt(uncertainty)

def _comparison_bracket_plan(centers, comparisons, annotations, *, base_height,
                             pad_height, handles, visible_y_span, lw=2,
                             offset=.1, floor=None, color='black',
                             star_y_offset_frac=None, available=None):
    from PyFLASH._comparison_tokens import parse_pairs
    from matplotlib.colors import to_rgba
    from fractions import Fraction
    centers=_comparison_centers(centers)
    requested=parse_pairs([] if comparisons is None else comparisons,len(centers),allow_self=False)
    if isinstance(annotations,(str,bytes,Mapping)):
        raise ValueError('Annotations must be an ordered label sequence.')
    try:labels=[] if annotations is None else list(annotations)
    except TypeError as error:raise ValueError('Annotations must be an ordered label sequence.') from error
    if labels and len(labels)!=len(requested):raise ValueError('Every requested bracket needs one annotation.')
    if any(not isinstance(label,(str,int,float,np.number,type(None))) for label in labels):
        raise ValueError('Each annotation must be one text or numeric label.')
    base=_comparison_number(base_height);padding=_comparison_number(pad_height,0.)
    handle=_comparison_number(handles,0.);span=_comparison_number(visible_y_span,0.,True)
    width=_comparison_number(lw,0.,True);inset=_comparison_number(offset,0.)
    top=base if floor is None else _comparison_number(floor)
    star=_comparison_number(.0022 if star_y_offset_frac is None else star_y_offset_frac)
    try:rgba=to_rgba(color)
    except (ValueError,TypeError) as error:raise ValueError('Invalid bracket color.') from error
    updated={};lines=[];texts=[];topline=None
    for (_,first,second),annotation in zip(requested,labels):
        if available is not None and (first not in available or second not in available):continue
        left,right=sorted((centers[first],centers[second]))
        covered=[x for x in centers if left<=x<=right];prior=[x for x in covered if x in updated]
        height=max(updated[x] for x in prior) if len(prior)>=2 else base
        xleft,xright=left+inset,right-inset;upper=height+handle
        lines.extend([([xleft,xleft],[height,upper]),([xright,xright],[height,upper]),([xleft,xright],[upper,upper])])
        nonsig=_is_nonsignificant_annotation(annotation)
        y=upper+span*.0385 if nonsig else upper+span*star
        mid=float((Fraction(left)+Fraction(right))/2)
        texts.append((mid,y,annotation,nonsig))
        nextheight=height+padding+handle;updated.update({x:nextheight for x in covered})
        top=max(top,nextheight+handle);topline=upper if topline is None else max(topline,upper)
    coordinates=[top]+([] if topline is None else [topline])+[v for xs,ys in lines for v in xs+ys]+[v for x,y,_,_ in texts for v in (x,y)]
    if not all(math.isfinite(v) for v in coordinates):raise ValueError('Comparison geometry exceeds finite drawing coordinates.')
    return (top,topline),lines,texts,width,rgba

def _comparison_draw_plan(ax,plan):
    result,lines,texts,width,color=plan
    for xs,ys in lines:ax.plot(xs,ys,lw=width,color=color,zorder=1,clip_on=False)
    for x,y,annotation,nonsig in texts:
        ax.text(x,y,annotation,ha='center',va='center',size=18 if nonsig else 35,
                clip_on=False,weight='normal' if nonsig else 'bold',color=color)
    return result
