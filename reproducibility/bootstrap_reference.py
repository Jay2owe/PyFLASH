"""Analytic BCa benchmark with retained, identical subject-resampling draws.

This implements the two-independent-sample bias-corrected/accelerated equations
using pair differences and stdlib normal quantiles; it does not call PyFLASH or
SciPy bootstrap. NumPy's seeded generator is shared solely to reproduce draws.
The existing reference fixture is preserved; this is a separate added contract.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np
from reproducibility.cases import inputs

FIXTURE = Path(__file__).with_name("fixtures") / "bootstrap_reference.json"


def effect(a, b, kind):
    def variance(x):
        return math.fsum((u-v)**2 for i,u in enumerate(x) for v in x[i+1:])/(len(x)*(len(x)-1))
    na, nb = len(a), len(b)
    pooled = math.sqrt(((na-1)*variance(a)+(nb-1)*variance(b))/(na+nb-2))
    value = (math.fsum(a)/na-math.fsum(b)/nb)/pooled
    return value*(1-3/(4*(na+nb)-9)) if kind == "hedges" else value


def interval(a, b, kind, confidence, draws):
    distribution = sorted(effect([a[i] for i in ix], [b[i] for i in iy], kind)
                          for ix, iy in zip(*draws))
    estimate = effect(a, b, kind)
    percentile = (sum(v < estimate for v in distribution)+sum(v <= estimate for v in distribution))/(2*len(distribution))
    normal = NormalDist()
    z0 = normal.inv_cdf(percentile)
    cubes, squares = [], []
    for group in (0, 1):
        sample = (a,b)[group]
        jackknife = [effect(a[:i]+a[i+1:], b, kind) if group == 0
                     else effect(a, b[:i]+b[i+1:], kind) for i in range(len(sample))]
        mean = math.fsum(jackknife)/len(sample)
        influence = [(len(sample)-1)*(mean-value) for value in jackknife]
        cubes.append(math.fsum(v**3 for v in influence)/len(sample)**3)
        squares.append(math.fsum(v**2 for v in influence)/len(sample)**2)
    acceleration = math.fsum(cubes)/(6*math.fsum(squares)**1.5)
    def quantile(p):
        position = p*(len(distribution)-1)
        index = int(position)
        weight = position-index
        return distribution[index]*(1-weight)+distribution[min(index+1,len(distribution)-1)]*weight
    endpoints = []
    for tail in ((1-confidence)/2, (1+confidence)/2):
        z = normal.inv_cdf(tail)
        probability = normal.cdf(z0+(z0+z)/(1-acceleration*(z0+z)))
        endpoints.append(quantile(probability))
    return endpoints


def reference_rows():
    rows = []
    for case in ("balanced", "unequal", "ties"):
        a,b = inputs()[case]
        rng = np.random.RandomState(17)
        draws = [rng.randint(0,len(sample),size=(400,len(sample))).tolist() for sample in (a,b)]
        for kind in ("hedges", "cohen"):
            for confidence in (.9,.95):
                rows.append({"case":case,"kind":kind,"confidence":confidence,"seed":17,
                             "resamples":400,"draws":draws,
                             "expected":interval(a,b,kind,confidence,draws)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze",action="store_true")
    parser.add_argument("--reason",default="")
    args = parser.parse_args()
    if args.freeze:
        if FIXTURE.exists():
            raise FileExistsError("Preserve existing independent answers; a revision needs a new versioned fixture.")
        if not args.reason.strip():
            raise ValueError("A scientific reason is required.")
        from PyFLASH._persistence import write_json
        write_json(FIXTURE,{"schema_version":1,"reason":args.reason,"inputs":inputs(),
                           "numpy":np.__version__,"code_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           "reference":"analytic BCa; stdlib normal quantiles; shared NumPy draws",
                           "rtol":1e-9,"atol":1e-12,"rows":reference_rows()})
    else:
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for recorded,actual in zip(expected["rows"],reference_rows(),strict=True):
            np.testing.assert_allclose(actual["expected"],recorded["expected"],rtol=1e-9,atol=1e-12)
        print(f"{len(expected['rows'])} retained analytic BCa contracts agree.")


if __name__ == "__main__":
    main()
