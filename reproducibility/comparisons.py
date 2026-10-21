"""Run PyFLASH and independent reference estimators on identical literal inputs.

References never call PyFLASH. Shared SciPy distribution tails are disclosed;
mpmath uses high-precision incomplete-beta evaluation instead. Full plot and
pipeline contracts are not inferred from successful subroutine comparisons.
"""
from __future__ import annotations

import math
import numpy as np
from reproducibility.cases import inputs


def _clean(values):
    return np.asarray([v for v in values if v is not None and math.isfinite(v)], float)


def _high_precision_t(a, b, pooled):
    import mpmath as mp
    with mp.workdps(50):
        a, b = [[mp.mpf(str(v)) for v in x] for x in (a, b)]
        n, m = len(a), len(b)
        ma, mb = mp.fsum(a) / n, mp.fsum(b) / m
        va = mp.fsum((v - ma)**2 for v in a) / (n - 1)
        vb = mp.fsum((v - mb)**2 for v in b) / (m - 1)
        if pooled:
            degrees = mp.mpf(n + m - 2)
            se2 = ((n - 1)*va + (m - 1)*vb) / degrees * (mp.mpf(1)/n + mp.mpf(1)/m)
        else:
            se2 = va/n + vb/m
            degrees = se2**2 / ((va/n)**2/(n - 1) + (vb/m)**2/(m - 1))
        statistic = (ma - mb) / mp.sqrt(se2)
        p = mp.betainc(degrees/2, mp.mpf("0.5"), 0, degrees/(degrees + statistic**2), regularized=True)
        return [float(statistic), float(p), float(degrees)]


def reference_values():
    """Reference-only path used to establish independently generated fixtures."""
    from statsmodels.stats.weightstats import ttest_ind
    import pingouin as pg
    from scipy import stats
    rows = []
    cases = inputs()
    for case in ("balanced", "unequal", "ties", "missing_ttest"):
        a, b = map(_clean, cases[case])
        for method, pooled in (("student", True), ("welch", False)):
            contract = f"ttest.{method}.{case}"
            rows.append((contract, "statsmodels-weightstats", "independent-estimator/shared-scipy-tail",
                         list(map(float, ttest_ind(a, b, usevar="pooled" if pooled else "unequal")))))
            rows.append((contract, "mpmath-formula", "analytic/high-precision-independent-tail",
                         _high_precision_t(a, b, pooled)))
            upstream = stats.ttest_ind(a, b, equal_var=pooled)
            rows.append((contract, "scipy", "shared-upstream-integration",
                         [float(upstream.statistic), float(upstream.pvalue), float(upstream.df)]))
    for case in ("balanced", "unequal", "ties"):
        a, b = map(_clean, cases[case])
        for kind in ("cohen", "hedges"):
            contract = f"effect.{kind}.{case}"
            rows.append((contract, "pingouin", "independent-effect-estimator/shared-numpy",
                         [float(pg.compute_effsize(a, b, eftype=kind))]))
            # Independent pair-difference construction of pooled dispersion.
            variance = lambda x: sum((u-v)**2 for i,u in enumerate(x) for v in x[i+1:])/(len(x)*(len(x)-1))
            pooled = math.sqrt(((len(a)-1)*variance(a)+(len(b)-1)*variance(b))/(len(a)+len(b)-2))
            estimate = (math.fsum(a)/len(a)-math.fsum(b)/len(b))/pooled
            if kind == "hedges":
                estimate *= 1 - 3/(4*(len(a)+len(b))-9)
            rows.append((contract, "pair-difference-formula", "analytic/independent-dispersion", [float(estimate)]))
        pairwise = sum(float(u>v)-float(u<v) for u in a for v in b)/(len(a)*len(b))
        rows.append((f"effect.rank_biserial.{case}", "pair-enumeration", "analytic/exact-pair-count", [pairwise]))
    # Constant variance has no defined standardized effect; preserve missingness.
    for kind in ("cohen", "hedges"):
        rows.append((f"effect.{kind}.constant_effect", "analytic-degenerate", "analytic/undefined-dispersion", [float("nan")]))
    pvalues = np.asarray([np.nan if p is None else p for p in cases["corrections"]])
    finite = np.isfinite(pvalues)
    p = pvalues[finite]
    for method in ("fdr_bh", "fdr_by", "bonferroni", "holm", "sidak"):
        m = len(p)
        order = np.argsort(p, kind="stable")
        sorted_p = p[order]
        if method.startswith("fdr_"):
            scale = sum(1/i for i in range(1,m+1)) if method == "fdr_by" else 1
            adjusted = np.minimum.accumulate((sorted_p*m*scale/np.arange(1,m+1))[::-1])[::-1]
        elif method == "holm":
            adjusted = np.maximum.accumulate(sorted_p*np.arange(m,0,-1))
        elif method == "bonferroni":
            adjusted = sorted_p*m
        else:
            adjusted = -np.expm1(m*np.log1p(-sorted_p))
        original = np.empty_like(p)
        original[order] = np.minimum(adjusted,1)
        all_adjusted = np.full_like(pvalues,np.nan)
        all_adjusted[finite] = original
        rows.append((f"correction.{method}", "order-statistic-formula", "analytic/independent-correction", all_adjusted.tolist()))
        if method.startswith("fdr_"):
            alternative = np.full_like(pvalues,np.nan)
            alternative[finite] = stats.false_discovery_control(p, method=method[-2:])
            rows.append((f"correction.{method}", "scipy-fdr", "independent-estimator/shared-numpy", alternative.tolist()))
    # All coefficients, uncertainty estimates, significance, and full prediction
    # arrays for the fixed-period noisy, sparse-time cosinor contract.
    import statsmodels.api as sm
    c = cases["cosinor"]
    t = np.array(c["t"],float)
    w = 2*np.pi/c["period"]
    y = c["mesor"]+c["amplitude"]*np.cos(w*(t-c["acrophase"]))+c["noise"]
    X = np.column_stack([np.ones(len(t)),np.cos(w*t),np.sin(w*t)])
    fit = sm.OLS(y,X).fit()
    M,b,g = fit.params
    amp = np.hypot(b,g)
    acro = (np.arctan2(g,b)/w)%c["period"]
    covariance = fit.cov_params()
    amp_grad = np.array([0,b/amp,g/amp])
    acro_grad = np.array([0,-g/(amp**2*w),b/(amp**2*w)])
    values = [M,amp,acro,b,g,fit.rsquared,fit.fvalue,fit.f_pvalue,fit.bse[0],
              np.sqrt(amp_grad@covariance@amp_grad),np.sqrt(acro_grad@covariance@acro_grad),len(t)]
    rows.append(("cosinor.fixed_sparse", "statsmodels-ols", "independent-estimator/shared-lapack-scipy-tail", list(map(float,values))+fit.predict(X).tolist()))
    return rows


def pyflash_values():
    from PyFLASH.stats import runITTest
    from PyFLASH import stats_extra as extra
    cases = inputs()
    results = {}
    for case in ("balanced", "unequal", "ties", "missing_ttest"):
        a,b = [[np.nan if v is None else v for v in g] for g in cases[case]]
        for method, pooled in (("student", True),("welch",False)):
            raw = {}
            output = runITTest(a,b,raw,equal_var=pooled)
            results[f"ttest.{method}.{case}"] = list(output[2])+raw["_group_test"]["df"]
    for case in ("balanced", "unequal", "ties", "constant_effect"):
        a,b = cases[case]
        results[f"effect.cohen.{case}"] = [extra.cohens_d(a,b)]
        results[f"effect.hedges.{case}"] = [extra.hedges_g(a,b)]
        if case != "constant_effect":
            results[f"effect.rank_biserial.{case}"] = [extra.rank_biserial(a,b)]
    for method in ("fdr_bh", "fdr_by", "bonferroni", "holm", "sidak"):
        p = [np.nan if p is None else p for p in cases["corrections"]]
        reject,adjusted = extra.adjust_pvalues(p,method=method)
        # Rejection decisions are checked separately, including missing values.
        expected_reject = [bool(np.isfinite(v) and v <= .05) for v in adjusted]
        if reject != expected_reject:
            raise AssertionError(f"{method}: rejection decisions differ from adjusted p values")
        results[f"correction.{method}"] = adjusted
    c = cases["cosinor"]
    t = np.array(c["t"],float)
    y = c["mesor"]+c["amplitude"]*np.cos(2*np.pi/c["period"]*(t-c["acrophase"]))+c["noise"]
    fit = extra.fit_cosinor(t,y,period=c["period"])
    results["cosinor.fixed_sparse"] = [fit[k] for k in ("mesor","amplitude","acrophase","coef_cos","coef_sin","r_squared","f_stat","p")]+[fit["params"][k]["stderr"] for k in ("mesor","amplitude","acrophase")]+[fit["n"]]+fit["predict"](t).tolist()
    return results
