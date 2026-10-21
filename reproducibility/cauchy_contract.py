"""Independent high-precision ACAT formula on exact binary input p-values.

The package clips each finite input at 1e-15 and 1-1e-15; these two binary
floating numbers are not exact complements. The reference retains that existing
convention and does not substitute decimal-text inputs or change the estimator.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path

FIXTURE = Path(__file__).with_name('fixtures')/'cauchy_contract_reference.json'
SOURCE = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7531765/'


def cases():
    values = [[], [None, 'nan', 'inf'], [0.], [1.], [0., 1.], [.5],
              [.01, .03, .2], [.01, .99, .2], [1e-15], [1e-12], [1e-8],
              [1e-10, .5], [1e-15, .99],
              *[[small, 1-small, .2] for small in (1e-8, 1e-10, 1e-12, 1e-14, 1e-15)],
              [-1., 2., .3], [.001, None, 'nan', 'inf', .2], [.05]*20]
    rows = []
    for index, ps in enumerate(values):
        for reverse in (False, True):
            rows.append({'key':f'cauchy.complete.{index}.{int(reverse)}',
                         'capability':'PyFLASH.stats.cauchy_combination_test',
                         'parameters':{'pvalues':list(reversed(ps)) if reverse else ps}})
    return rows


def numbers(row):
    return [float(v) for v in row['parameters']['pvalues']
            if v is not None and math.isfinite(float(v))]


def reference(row):
    import mpmath as mp
    values = numbers(row)
    if not values:
        return [math.nan]
    with mp.workdps(90):
        # mp.mpf(float) preserves the exact binary number, unlike str(float).
        clipped = [mp.mpf(max(1e-15, min(1-1e-15, p))) for p in values]
        statistic = mp.fsum(mp.cot(mp.pi*p) for p in clipped)/len(values)
        return [float(mp.mpf('.5')-mp.atan(statistic)/mp.pi)]


def production(row):
    from PyFLASH.stats import cauchy_combination_test
    return [cauchy_combination_test([float(v) if v is not None else None
                                    for v in row['parameters']['pvalues']])]


def freeze(reason):
    if FIXTURE.exists():
        raise ValueError('Preserve the existing reference fixture.')
    if not reason.strip():
        raise ValueError('A scientific reason is required.')
    from importlib.metadata import version
    rows = [{**row, 'expected':[v if math.isfinite(v) else None for v in reference(row)]}
            for row in cases()]
    FIXTURE.write_text(json.dumps({'schema_version':1, 'reason':reason,
        'sources':[SOURCE, 'https://github.com/yaowuliu/ACAT/blob/master/R/ACAT.R'],
        'reference':'90-digit direct cotangent and Cauchy survival formula',
        'versions':{'mpmath':version('mpmath')}, 'rows':rows,
        'reference_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'equal-weight finite-input helper with existing binary clipping'},
        indent=2, allow_nan=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--reason', default='')
    args = parser.parse_args()
    if args.freeze:
        freeze(args.reason)
