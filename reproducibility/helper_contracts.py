"""Complete returned fields/options of correlation and descriptive helpers.

Pure rational/50-digit formulas and literal order statistics supply answers.
These contracts cover no parent pipeline, bootstrap, plot or circular inference.
"""
from collections import defaultdict
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

FIXTURE = Path(__file__).with_name('fixtures') / 'helper_contracts_reference.json'
TAILS = {'two': 'two', 'two-sided': 'two', '2': 'two', 'two_sided': 'two', 'twosided': 'two',
         'both': 'two', 'ne': 'two', '!=': 'two', 'one': 'one', '1': 'one', 'one-sided': 'one',
         'one_sided': 'one', 'onesided': 'one', 'less': 'less', 'lt': 'less', '<': 'less',
         'smaller': 'less', 'greater': 'greater', 'gt': 'greater', '>': 'greater', 'larger': 'greater'}


def cases():
    rows = []
    def add(name, parameters):
        rows.append({'key': f'{name}.{len(rows)}', 'capability': 'PyFLASH.' + name, 'parameters': parameters})
    correlations = [(.6, 15, -.2, 23), (-.7, 7, .1, 19), (1., 4, -1., 8), (.4, 3, .3, 10),
                    (.3, 20, .3, 20), (None, 10, .1, 20)]
    methods = ('pearson', 'pearsonr', 'spearman', 'spearmanr', 's', 'kendall')
    for r1, n1, r2, n2 in correlations:
        for method in methods:
            add('stats.fisher_z_se', {'r': r1, 'n': n1, 'method': method})
            for tail in ('two', 'one', 'less', 'greater'):
                add('stats.fisher_z_correlation_difference', dict(r1=r1, n1=n1, r2=r2, n2=n2, method=method, tail=tail))
            for alpha in (.0001, .05, .2):
                add('stats.zou_correlation_difference_ci', dict(r1=r1, n1=n1, r2=r2, n2=n2, method=method, alpha=alpha))
    for tail in TAILS:
        add('stats.fisher_z_correlation_difference', dict(r1=.4, n1=17, r2=-.3, n2=12, tail=tail))
    outliers = [[1, 2, 3, 4, 5, 30], [1, None, 3, 4, 'bad', 5, 9], [2, 2, 2, 2],
                [1, 2, 3], [], [None, 'inf', '-inf'], [-8, -3, -.5, 0, 2, 3],
                [1, 2, 3, 4, 'inf', '-inf']]
    for values in outliers:
        for k in (0, 1.5, 2.75, 3):
            add('stats_extra.iqr_bounds', {'values': values, 'k': k})
        add('stats_extra.mad_modified_z', {'values': values})
    groups = [[[1, 2, 4], [2, 3, 8]], [[1, 1], [2, 2, 2], [3, 4, 7, 9]],
              [[3, 3], [3, 3]], [[3, 4], [3, 4]], [[1], [2]], [[1, 2]], [],
              [[1, None, 'bad', 4], [2, 4, 9]], [[1, 'inf'], [2, 3]], [[-3, 0, 4], [8, 3]]]
    for groupset in groups:
        for value_col, group_col in (('Value', 'AnimalName'), ('Signal', 'Subject')):
            add('stats_extra.icc1', {'groups': groupset, 'value_col': value_col, 'group_col': group_col})
    return rows


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def quantile(values, probability):
    order = sorted(values)
    position = Fraction(len(order)-1) * probability
    low, high = math.floor(position), math.ceil(position)
    return order[low] + (position-low) * (order[high]-order[low])


def reference(row):
    import mpmath as mp
    name, params = row['capability'].rsplit('.', 1)[-1], row['parameters']
    with mp.workdps(50):
        if name.startswith('fisher_') or name == 'zou_correlation_difference_ci':
            def clipped(value):
                value = number(value)
                return mp.mpf(str(min(.999999, max(-.999999, value)))) if not math.isnan(value) else mp.nan
            def se(r, n):
                if int(n) <= 3: return mp.nan
                r = clipped(r)
                factor = 1 + r*r/2 if params.get('method', 'pearson') in ('spearman', 'spearmanr', 's') else mp.mpf(1)
                return mp.sqrt(factor/(int(n)-3))
            if name == 'fisher_z_se':
                return [float(se(params['r'], params['n']))]
            r1, r2 = clipped(params['r1']), clipped(params['r2'])
            s1, s2 = se(params['r1'], params['n1']), se(params['r2'], params['n2'])
            if not all(mp.isfinite(x) for x in (s1, s2)):
                return [math.nan] * (3 if name.startswith('zou') else 1)
            if name.startswith('zou'):
                critical = mp.sqrt(2) * mp.erfinv(1-mp.mpf(str(params['alpha'])))
                intervals = [[mp.tanh(mp.atanh(r) + sign*critical*s) for sign in (-1, 1)] for r, s in ((r1, s1), (r2, s2))]
                (l1, u1), (l2, u2) = intervals
                delta = r1-r2
                return [float(x) for x in (delta, delta-mp.hypot(r1-l1, u2-r2), delta+mp.hypot(u1-r1, r2-l2))]
            z = (mp.atanh(r1)-mp.atanh(r2))/mp.hypot(s1, s2)
            tail = TAILS[params.get('tail', 'two')]
            p = (mp.erfc(abs(z)/mp.sqrt(2)) if tail == 'two' else mp.erfc(abs(z)/mp.sqrt(2))/2 if tail == 'one'
                 else mp.erfc(-z/mp.sqrt(2))/2 if tail == 'less' else mp.erfc(z/mp.sqrt(2))/2)
            return [float(p)]
        if name in ('iqr_bounds', 'mad_modified_z'):
            original = [number(v) for v in params['values']]
            values = [Fraction(str(v)) for v in original if math.isfinite(v)]
            if name == 'iqr_bounds':
                if len(values) < 4: return [math.nan, math.nan]
                first, third = quantile(values, Fraction(1,4)), quantile(values, Fraction(3,4))
                gap = Fraction(str(params['k'])) * (third-first)
                return [float(first-gap), float(third+gap)]
            if not values: return [math.nan] * len(original)
            median = quantile(values, Fraction(1,2))
            mad = quantile([abs(v-median) for v in values], Fraction(1,2))
            return [float(Fraction('0.6745')*(Fraction(str(v))-median)/mad) if mad and math.isfinite(v) else math.nan for v in original]
        if name == 'icc1':
            groups = [[number(v) for v in g if not math.isnan(number(v))] for g in params['groups']]
            groups = [g for g in groups if g]
            n, k = sum(map(len, groups)), len(groups)
            if k < 2 or n <= k or any(not math.isfinite(v) for g in groups for v in g): return [math.nan]
            groups = [[Fraction(str(v)) for v in g] for g in groups]
            grand = sum(sum(g) for g in groups) / n
            means = [sum(g)/len(g) for g in groups]
            between = sum(len(g)*(mean-grand)**2 for g, mean in zip(groups, means))/(k-1)
            within = sum(sum((v-mean)**2 for v in g) for g, mean in zip(groups, means))/(n-k)
            corrected_size = (n-Fraction(sum(len(g)**2 for g in groups), n))/(k-1)
            denominator = between+(corrected_size-1)*within
            return [float((between-within)/denominator) if denominator > 0 else math.nan]
        raise ValueError(name)


def production(row):
    from importlib import import_module
    import pandas as pd
    module, name = row['capability'].rsplit('.', 1)
    params = dict(row['parameters'])
    if name == 'icc1':
        groups = params.pop('groups')
        params['roi_df'] = pd.DataFrame([(str(i), v) for i, g in enumerate(groups) for v in g],
                                      columns=[params['group_col'], params['value_col']])
    elif 'r' in params and params['r'] is None:
        params['r'] = math.nan
    for key in ('r1', 'r2'):
        if key in params and params[key] is None: params[key] = math.nan
    result = getattr(import_module(module), name)(**params)
    return list(map(float, result)) if hasattr(result, '__iter__') else [float(result)]


def freeze(reason):
    if FIXTURE.exists(): raise ValueError('Preserve the existing reference fixture.')
    if not reason.strip(): raise ValueError('A scientific reason is required.')
    from importlib.metadata import version
    rows = [{**row, 'expected': [v if math.isfinite(v) else None for v in reference(row)]} for row in cases()]
    FIXTURE.write_text(json.dumps({'schema_version': 1, 'reason': reason, 'rows': rows,
        'reference': '50-digit Fisher/Zou mathematics; exact rational ICC(1) and order statistics',
        'versions': {'mpmath': version('mpmath')},
        'reference_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'sources': ['https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm',
                    'https://github.com/cran/psych/blob/master/R/ICC.R'],
        'scope': 'six helper contracts; no parent analysis or plot certification'}, indent=2, allow_nan=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--reason', default='')
    args = parser.parse_args()
    if args.freeze: freeze(args.reason)
