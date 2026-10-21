"""Independent complete scalar estimators on ordinary and degenerate inputs.

Expected values come from rational arithmetic, pair enumeration and 50-digit
mathematics, never from PyFLASH. Parameterless estimators are checked over all
documented return fields; test-size correction helpers cover clipping and size.
"""
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

FIXTURE = Path(__file__).with_name('fixtures') / 'scalar_contracts_reference.json'


def cases():
    groups = [
        [[1.2, 2.4, 2.9, 3.8, 5.1, 6.3], [2., 4.2, 5.7, 6.8, 7., 8.1]],
        [[1., 1., 2., 3.], [1., 2., 2.], [3., 4., 4., 8., 8.]],
        [[3., 3., 3.], [3., 3., 3.]],
        [[1., 1., 1.], [2., 2., 2.]],
        [[1.], [2.]], [[], [1., 2., 3.]], [[1., 2., 3.]], [],
        [[-5., -1., 0., 2.], [4., 3., 0.]],
    ]
    rows = []
    for name in ('cohens_d', 'hedges_g', 'rank_biserial'):
        for index, values in enumerate(groups):
            if len(values) == 2:
                for reverse in (False, True):
                    values = list(reversed(values)) if reverse else values
                    rows.append({'key': f'{name}.{index}.{reverse}',
                                 'capability': 'PyFLASH.stats_extra.'+name,
                                 'parameters': {'a': values[0], 'b': values[1]}})
    for name in ('anova_effect_sizes', 'kw_epsilon_squared'):
        for index, values in enumerate(groups):
            rows.append({'key': f'{name}.{index}', 'capability': 'PyFLASH.stats_extra.'+name,
                         'parameters': {'groups': values}})
    for name in ('bonferroni_correction', 'sidak_correction'):
        for p in (0., .00001, .02, .2, 1.):
            for count in (1, 2, 5, 40):
                rows.append({'key': f'{name}.{p}.{count}', 'capability': 'PyFLASH.stats.'+name,
                             'parameters': {'p_value': p, 'n_tests': count}})
    return rows


def reference(row):
    import mpmath as mp
    name = row['capability'].rsplit('.', 1)[-1]
    params = row['parameters']
    with mp.workdps(50):
        if name.endswith('_correction'):
            p = mp.mpf(str(params['p_value']))
            count = params['n_tests']
            return [float(min(p * count, 1) if name.startswith('bonferroni') else 1-(1-p)**count)]
        if name in ('cohens_d', 'hedges_g', 'rank_biserial'):
            a, b = params['a'], params['b']
            if not a or not b:
                return [math.nan]
            if name == 'rank_biserial':
                # Kerby (2014): favorable minus unfavorable evidence over pairs.
                return [float(Fraction(sum((x > y)-(x < y) for x in a for y in b), len(a)*len(b)))]
            if min(len(a), len(b)) < 2:
                return [math.nan]
            a, b = [[mp.mpf(str(x)) for x in group] for group in (a, b)]
            ma, mb = [mp.fsum(group)/len(group) for group in (a, b)]
            ss = mp.fsum((x-ma)**2 for x in a) + mp.fsum((x-mb)**2 for x in b)
            if ss == 0:
                return [math.nan]
            d = (ma-mb)/mp.sqrt(ss/(len(a)+len(b)-2))
            if name == 'hedges_g':
                d *= 1-mp.mpf(3)/(4*(len(a)+len(b))-9)
            return [float(d)]
        groups = [[Fraction(str(x)) for x in group] for group in params['groups'] if group]
        n, k = sum(map(len, groups)), len(groups)
        if name == 'kw_epsilon_squared':
            if k < 2 or n <= k:
                return [math.nan]
            values = [x for group in groups for x in group]
            counts = Counter(values)
            ranks, offset = {}, 0
            for value in sorted(counts):
                count = counts[value]
                ranks[value] = Fraction(2*offset+count+1, 2)
                offset += count
            tie_factor = 1-Fraction(sum(count**3-count for count in counts.values()), n**3-n)
            if tie_factor == 0:
                return [math.nan]
            h = (Fraction(12, n*(n+1))*sum(sum(ranks[x] for x in group)**2/len(group)
                                         for group in groups)-3*(n+1))/tie_factor
            return [float((h-k+1)/(n-k))]
        if k < 2:
            return []
        means = [sum(group)/len(group) for group in groups]
        grand = sum(sum(group) for group in groups)/n
        between = sum(len(group)*(mean-grand)**2 for group, mean in zip(groups, means))
        within = sum(sum((x-mean)**2 for x in group) for group, mean in zip(groups, means))
        total = between+within
        eta = float(between/total) if total else math.nan
        if n == k:
            return [eta, math.nan]
        msw = within/(n-k)
        omega = float((between-(k-1)*msw)/(total+msw)) if total+msw else math.nan
        return [eta, omega]


def production(row):
    from importlib import import_module
    module, name = row['capability'].rsplit('.', 1)
    result = getattr(import_module(module), name)(**row['parameters'])
    if isinstance(result, dict):
        return [result[name] for name in ('eta_squared', 'omega_squared') if name in result]
    return [float(result)]


def freeze(reason):
    if FIXTURE.exists():
        raise ValueError('Preserve existing independent expected values; create a reviewed revision.')
    if not reason.strip():
        raise ValueError('A scientific reason is required.')
    from importlib.metadata import version
    rows = [{**row, 'expected': [value if math.isfinite(value) else None for value in reference(row)]}
            for row in cases()]
    payload = {'schema_version': 1, 'reason': reason, 'rows': rows,
        'reference': '50-digit scalar mathematics / exact rational rank and variance arithmetic',
        'versions': {'mpmath': version('mpmath')},
        'reference_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'sources': ['https://journals.sagepub.com/doi/10.2466/11.IT.3.1',
                    'https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.kruskal.html'],
        'scope': 'complete fields of seven scalar helpers; no parent pipeline/plot inference claim'}
    FIXTURE.write_text(json.dumps(payload, indent=2, allow_nan=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--reason', default='')
    arguments = parser.parse_args()
    if arguments.freeze:
        freeze(arguments.reason)
