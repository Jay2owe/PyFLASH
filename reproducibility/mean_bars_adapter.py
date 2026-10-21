"""Capture actual public mean-bar artists without exporting a figure."""
import math
def actual(groups, normalize, show_points):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import pandas as pd
    from PyFLASH import plotting
    from PyFLASH.config import Config
    n = sum(map(len, groups))
    frame = pd.DataFrame({'AnimalName': [f's{i}' for i in range(n)],
        'Condition': sum(([label]*len(group) for label, group in zip(('A', 'B'), groups)), []),
        'Probe_MeanIntensity': sum(groups, [])})
    captured = []; close = plt.close
    plt.close = lambda fig=None: captured.append(fig) if isinstance(fig, matplotlib.figure.Figure) else None
    prior = {key: getattr(Config, key) for key in ('EFFECT_SIZES', 'EFFECT_CI')}
    Config.EFFECT_SIZES = Config.EFFECT_CI = False
    try:
        result = plotting.plot_mean_bars(frame, data_cols=['Probe_MeanIntensity'], save=False, save_normality=False,
            stats_test='student', comparisons=[], points=show_points, normalize=normalize, bottom_tick_labels=True)
        figures = list({id(fig): fig for fig in captured}.values())
        if not figures: raise RuntimeError('No captured output canvas')
        axis = figures[-1].axes[0]
        bars = [{'group': round(p.get_x()+p.get_width()/2), 'height': float(p.get_height())} for p in axis.patches]
        points = []
        for collection in axis.collections:
            if type(collection).__name__ == 'PathCollection':
                offsets = collection.get_offsets().tolist()
                points.append({'group': round(offsets[0][0]) if offsets else None, 'y': [p[1] for p in offsets], 'full_offsets': offsets})
        uncertainty = []
        for line in axis.lines:
            x, y = list(map(float, line.get_xdata())), list(map(float, line.get_ydata()))
            if len(x)==2 and x[0]==x[1] and all(math.isfinite(v) for v in y):
                uncertainty.append({'group': round(x[0]), 'tip': y[1], 'drawn_spread': y[1]-y[0], 'full_x': x, 'full_y': y})
        return {'bars': bars, 'points': points, 'uncertainty': uncertainty, 'ticks': axis.get_xticks().tolist(),
                'labels': [v.get_text() for v in axis.get_xticklabels()], 'result_type': type(result).__name__}
    finally:
        plt.close = close
        for key, value in prior.items(): setattr(Config, key, value)
        close('all')

def differences(expected, observed, show_points):
    out = []
    for field in ('ticks', 'labels'):
        if expected[field] != observed[field]: out.append({'field': field, 'expected': expected[field], 'actual': observed[field]})
    for field in ('bars', 'points', 'uncertainty'):
        want = expected[field] if field!='points' or show_points else []
        got = observed[field]
        if len(want)!=len(got):
            out.append({'field': field+'.shape', 'expected': len(want), 'actual': len(got)}); continue
        for index, (left, right) in enumerate(zip(want, got)):
            if left['group'] != right['group']: out.append({'field': f'{field}.{index}.group', 'expected': left['group'], 'actual': right['group']})
            for key in ('height', 'tip', 'y'):
                if key not in left: continue
                a, b = left[key], right[key]
                if isinstance(a, list):
                    ok = len(a)==len(b) and all(math.isclose(x,y,rel_tol=1e-12,abs_tol=0) for x,y in zip(a,b))
                else: ok = math.isclose(a,b,rel_tol=1e-12,abs_tol=0)
                if not ok: out.append({'field': f'{field}.{index}.{key}', 'expected': a, 'actual': b})
            # Check positive uncertainty separately; a large baseline must not
            # hide erasure of a resolvable small band.
            if 'sem' in left:
                spread = right['drawn_spread']
                mean = expected['bars'][index]['height']
                if left['sem'] and float(mean+left['sem']) != mean and spread == 0:
                    out.append({'field': f'{field}.{index}.positive_spread', 'expected': left['sem'], 'actual': spread})
    return out

def production(case):
    request=case['request']
    return actual(request['groups'],request['normalize'],request['points'])
