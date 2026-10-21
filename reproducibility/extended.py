"""Additional reference contracts; reference paths never import PyFLASH.

Each row names a narrow, executed contract rather than certifying an entire
parent method. mpmath uses 50 digits for analytic references. Complete returned
arrays are compared, including missing cells. Source documentation and exact
versions are retained in the fixture and run receipt.
"""
from __future__ import annotations

import math
from pathlib import Path
import numpy as np

FIXTURE = Path(__file__).with_name("fixtures") / "extended_reference.json"
LINEAR_FIXTURE = FIXTURE.with_name("linear_analytic_reference.json")


def inputs():
    return {
        "correlations": [[.6, 15, -.2, 23], [.99, 8, .8, 11], [-1, 30, 1, 19]],
        "cauchy": [[.02, .3, .8], [.5, .5], [.001, None, .7, .9]],
        "outliers": [[1, 2, 3, 4, 5, 30], [1, None, 3, 4, 5, 9],
                     [2, 2, 2, 2], [1, 2, 3], [1, 2, 3, 4, "inf", "-inf"]],
        "groups": [[[1, 2, 4, 7], [3, 4, 6, 9], [1, 3, 8]],
                   [[1, 1, 2, 3], [1, 2, 2], [3, 4, 4, 8, 8]],
                   [[2, 2, 2], [2, 2, 2], []]],
        "circular": [[22, 23, 0, 1, 2], [2, 3, 6, 8, 9, None], [1, 1, 1, 1]],
        "growth": {"x": [1, 2, 4, 7, 9, 12, 15, 18],
                   "y": [2.7, 3.5, 5.8, 7.9, 10.4, 12.8, 15.5, 19.1]},
    }


def numeric(values):
    return np.asarray([np.nan if v is None else float(v) for v in values], float)


def finite(values):
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def quantile(values, fraction):
    """Literal order-statistic interpolation, independent of NumPy percentiles."""
    ordered = sorted(values)
    h = (len(ordered)-1)*fraction
    low = math.floor(h)
    high = math.ceil(h)
    return ordered[low] + (h-low)*(ordered[high]-ordered[low])


def reference_values():
    import mpmath as mp
    import pingouin as pg
    import statsmodels.api as sm
    from scipy import stats
    rows = []
    cases = inputs()

    def add(contract, values, reference="mpmath-50-digit", family="analytic/independent-formula-tail"):
        rows.append((contract, reference, family, list(map(float, values))))

    with mp.workdps(50):
        for case, (r1, n1, r2, n2) in enumerate(cases["correlations"]):
            r1, r2 = [mp.mpf(str(max(-.999999, min(.999999, r)))) for r in (r1, r2)]
            for method in ("pearson", "spearman"):
                s1, s2 = [mp.sqrt((1+r*r/2 if method == "spearman" else 1)/(n-3))
                          for r, n in ((r1, n1), (r2, n2))]
                add(f"fisher.se.{method}.{case}", [s1, s2])
                z = (mp.atanh(r1)-mp.atanh(r2))/mp.sqrt(s1*s1+s2*s2)
                for tail in ("two", "one", "less", "greater"):
                    p = (mp.erfc(abs(z)/mp.sqrt(2)) if tail == "two" else
                         mp.erfc(abs(z)/mp.sqrt(2))/2 if tail == "one" else
                         mp.erfc(-z/mp.sqrt(2))/2 if tail == "less" else
                         mp.erfc(z/mp.sqrt(2))/2)
                    add(f"fisher.difference.{method}.{tail}.{case}", [p])
                for alpha in (.05, .1):
                    critical = mp.sqrt(2)*mp.erfinv(1-mp.mpf(str(alpha)))
                    l1, u1 = [mp.tanh(mp.atanh(r1)+sign*critical*s1) for sign in (-1, 1)]
                    l2, u2 = [mp.tanh(mp.atanh(r2)+sign*critical*s2) for sign in (-1, 1)]
                    delta = r1-r2
                    add(f"zou.{method}.{alpha}.{case}", [delta,
                        delta-mp.sqrt((r1-l1)**2+(u2-r2)**2),
                        delta+mp.sqrt((u1-r1)**2+(r2-l2)**2)])
        for case, values in enumerate(cases["cauchy"]):
            ps = [mp.mpf(str(p)) for p in finite(values)]
            t = mp.fsum(mp.tan((mp.mpf(".5")-p)*mp.pi) for p in ps)/len(ps)
            add(f"cauchy.{case}", [mp.mpf(".5")-mp.atan(t)/mp.pi])

        for case, values in enumerate(cases["outliers"]):
            clean = finite(values)
            for k in (1.5, 3):
                if len(clean) < 4:
                    result = [math.nan, math.nan]
                else:
                    q1, q3 = quantile(clean, .25), quantile(clean, .75)
                    result = [q1-k*(q3-q1), q3+k*(q3-q1)]
                add(f"iqr.{k}.{case}", result, "order-statistic-interpolation", "analytic/independent-ordering")
            median = quantile(clean, .5)
            mad = quantile([abs(x-median) for x in clean], .5)
            result = [math.nan if v is None or not math.isfinite(float(v)) or mad == 0 else
                      .6745*(float(v)-median)/mad for v in values]
            add(f"mad.{case}", result, "nist-modified-z/order-statistics", "analytic/independent-ordering")

        for case, groups in enumerate(cases["groups"]):
            groups = [list(map(mp.mpf, g)) for g in groups if g]
            n, k = sum(map(len, groups)), len(groups)
            grand = mp.fsum(x for g in groups for x in g)/n
            means = [mp.fsum(g)/len(g) for g in groups]
            between = mp.fsum(len(g)*(mu-grand)**2 for g, mu in zip(groups, means))
            within = mp.fsum((x-mu)**2 for g, mu in zip(groups, means) for x in g)
            total = between+within
            msw = within/(n-k)
            eta = between/total if total else math.nan
            omega = (between-(k-1)*msw)/(total+msw) if total+msw else math.nan
            add(f"anova.effect.{case}", [eta, omega])
            k0 = (n-mp.fsum(len(g)**2 for g in groups)/n)/(k-1)
            msb = between/(k-1)
            denom = msb+(k0-1)*msw
            add(f"icc1.{case}", [(msb-msw)/denom if denom > 0 else math.nan])

    for case, values in enumerate(cases["circular"]):
        for period in (24., 12.):
            # Pingouin requires one-cycle radians; wrapping does not alter the
            # circular observations. PyFLASH accepts arbitrary cycle offsets.
            angles = (np.asarray(finite(values))*2*np.pi/period)%(2*np.pi)
            mean = (pg.circ_mean(angles)%(2*np.pi))*period/(2*np.pi)
            resultant = pg.circ_r(angles)
            add(f"circular.descriptive.{period}.{case}", [len(angles), mean, resultant],
                "pingouin-circular", "independent-estimator/shared-numpy-trigonometry")
            # SciPy has its own descriptive implementation; no Rayleigh p-value
            # equivalence is inferred from agreement in means/resultants.
            add(f"circular.descriptive.{period}.{case}", [len(angles), stats.circmean(angles)*period/(2*np.pi),
                math.exp(-stats.circstd(angles)**2/2)], "scipy-circular", "independent-estimator/shared-numpy-trigonometry")
    growth = cases["growth"]
    x, y = np.asarray(growth["x"]), np.asarray(growth["y"])
    fit = sm.OLS(y, np.column_stack([x, np.ones(len(x))])).fit()
    sse = math.fsum((y-fit.fittedvalues)**2)
    add("growth.linear.noisy", [*fit.params, *fit.bse, fit.rsquared,
        len(x)*math.log(sse/len(x))+4, len(x), *fit.predict()],
        "statsmodels-ols", "independent-estimator/shared-lapack")
    return rows


def pyflash_values():
    from PyFLASH import stats as core, stats_extra as extra
    import pandas as pd
    cases, results = inputs(), {}
    for case, (r1, n1, r2, n2) in enumerate(cases["correlations"]):
        for method in ("pearson", "spearman"):
            results[f"fisher.se.{method}.{case}"] = [core.fisher_z_se(r1, n1, method), core.fisher_z_se(r2, n2, method)]
            for tail in ("two", "one", "less", "greater"):
                results[f"fisher.difference.{method}.{tail}.{case}"] = [core.fisher_z_correlation_difference(r1, n1, r2, n2, method, tail)]
            for alpha in (.05, .1):
                results[f"zou.{method}.{alpha}.{case}"] = core.zou_correlation_difference_ci(r1, n1, r2, n2, method, alpha)
    for case, values in enumerate(cases["cauchy"]):
        results[f"cauchy.{case}"] = [core.cauchy_combination_test(values)]
    for case, values in enumerate(cases["outliers"]):
        for k in (1.5, 3):
            results[f"iqr.{k}.{case}"] = extra.iqr_bounds(numeric(values), k)
        results[f"mad.{case}"] = extra.mad_modified_z(numeric(values)).tolist()
    for case, groups in enumerate(cases["groups"]):
        result = extra.anova_effect_sizes(groups)
        results[f"anova.effect.{case}"] = [result["eta_squared"], result["omega_squared"]]
        rows = [(str(i), value) for i, g in enumerate(groups) for value in g]
        frame = pd.DataFrame(rows, columns=["AnimalName", "value"])
        results[f"icc1.{case}"] = [extra.icc1(frame, "value")]
    for case, values in enumerate(cases["circular"]):
        for period in (24., 12.):
            result = extra.circular_stats(numeric(values), period)
            results[f"circular.descriptive.{period}.{case}"] = [result[k] for k in ("n", "mean", "r")]
    growth = cases["growth"]
    fit = extra.fit_growth_curve(growth["x"], growth["y"], model="linear")
    results["growth.linear.noisy"] = [*[fit["params"][k]["value"] for k in ("slope", "intercept")],
        *[fit["params"][k]["stderr"] for k in ("slope", "intercept")], fit["r_squared"], fit["aic"],
        fit["n"], *fit["predict"](growth["x"])]
    return results


def linear_reference_values():
    """Second linear-fit reference: scalar high-precision normal equations.

    This shares neither the Statsmodels solver nor SciPy's numerical Jacobian.
    Residual covariance, AIC and every prediction are included.
    """
    import mpmath as mp
    with mp.workdps(50):
        growth = inputs()["growth"]
        x, y = [[mp.mpf(str(v)) for v in growth[key]] for key in ("x", "y")]
        n = len(x)
        mx, my = mp.fsum(x)/n, mp.fsum(y)/n
        xx = mp.fsum((v-mx)**2 for v in x)
        slope = mp.fsum((u-mx)*(v-my) for u, v in zip(x, y))/xx
        intercept = my-slope*mx
        prediction = [slope*v+intercept for v in x]
        sse = mp.fsum((v-p)**2 for v, p in zip(y, prediction))
        variance = sse/(n-2)
        total = mp.fsum((v-my)**2 for v in y)
        values = [slope, intercept, mp.sqrt(variance/xx),
                  mp.sqrt(variance*(mp.mpf(1)/n+mx*mx/xx)),
                  1-sse/total, n*mp.log(sse/n)+4, n, *prediction]
    return [("growth.linear.noisy", "mpmath-normal-equations", "analytic/independent-solver-covariance", list(map(float, values)))]


def freeze(reason, *, linear=False):
    import json
    from datetime import datetime, timezone
    from reproducibility.run import versions, sha256, write_json
    target = LINEAR_FIXTURE if linear else FIXTURE
    if target.exists():
        raise ValueError("Preserve the existing fixture; review an explicitly versioned revision.")
    if not reason.strip():
        raise ValueError("A reason is required.")
    # Obtain values before touching any production code path.
    rows = linear_reference_values() if linear else reference_values()
    import pingouin.circular, statsmodels.regression.linear_model
    sources = [Path(__file__), Path(pingouin.circular.__file__), Path(statsmodels.regression.linear_model.__file__)]
    write_json(target, {"schema_version": 1, "reason": reason, "inputs": inputs(),
        "created_at": datetime.now(timezone.utc).isoformat(), "versions": versions(),
        "sources": [{"name": p.name, "sha256": sha256(p)} for p in sources],
        "documentation": ["https://www.statsmodels.org/stable/regression.html",
                          "https://pingouin-stats.org/generated/pingouin.circ_mean.html",
                          "https://itl.nist.gov/div898/handbook/eda/section3/eda35h.htm"],
        "rtol": 1e-9, "atol": 1e-12, "rows": rows})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--reason", default="")
    parser.add_argument("--linear", action="store_true")
    args = parser.parse_args()
    if not args.freeze:
        parser.error("Use reproducibility.run for comparisons; --freeze only creates new reference fixtures.")
    freeze(args.reason, linear=args.linear)
