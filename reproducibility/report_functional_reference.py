"""Independent literal captions and ordered cells; no inference vote."""
from decimal import Decimal
import math
def annotation(p, style):
    try:
        value = float(p)
    except (TypeError, ValueError, OverflowError):
        return style['significance_ns']
    if isinstance(p, bool) or not math.isfinite(value) or (not 0 <= value <= 1):
        return style['significance_ns']
    for threshold, label in sorted(style['significance_thresholds'].items(), key=lambda item: float(item[0])):
        if Decimal.from_float(value) < Decimal.from_float(float(threshold)):
            return label
    return style['significance_ns']

def print_reference(case):
    p = case['parameters']
    names = case['names']
    tokens = p['comparisons']
    probabilities = p['individual_results']
    if not isinstance(tokens, (list, tuple)) or len(tokens) != len(probabilities):
        return {'error': 'ValueError'}
    import re
    pairs = []
    for token in tokens:
        if not isinstance(token, str) or re.fullmatch('\\s*[0-9]+\\s*-\\s*[0-9]+\\s*', token) is None:
            return {'error': 'ValueError'}
        a, b = map(int, token.split('-'))
        if not 1 <= a <= len(names) or not 1 <= b <= len(names) or a == b:
            return {'error': 'ValueError'}
        pairs.append((a - 1, b - 1))
    overall = p['overall_p']
    style = case['style']
    factors = p.get('factor_list')
    if isinstance(overall, list):
        labels = factors or ['Factor 1', 'Factor 2', 'Interaction', 'Residual']
        group = {labels[i] if i < len(labels) else f'Term {i + 1}': annotation(v, style) for i, v in enumerate(overall)}
    else:
        group = {'Group difference': annotation(overall, style)}
    summaries = [f'{names[a]} vs {names[b]} {annotation(value, style)}' for (a, b), value in zip(pairs, probabilities)]
    return {'result': [group, summaries]}

def unpack(value):
    if isinstance(value, dict) and 'wire' in value:
        if value['wire'] == 'tuple':
            return tuple(value['value'])
        if value['wire'] == 'array':
            import numpy as np
            return np.asarray(value['value'])
    if isinstance(value, list):
        return [unpack(v) for v in value]
    if isinstance(value, dict):
        return {k: unpack(v) for k, v in value.items()}
    return value

def cell(value):
    if value is None:
        return ''
    return str(value)

def export_reference(case):
    p = case['parameters']
    rows = [['Statistics Results'], ['Test', 'Statistic', 'P-Values']]
    for label, value in p['results_dict'].items():
        if str(label).startswith('_'):
            continue
        value = unpack(value)
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return {'error': 'ValueError', 'previous_file_preserved': True, 'input_unchanged': True}
        statistic, probability = value
        if isinstance(probability, (list, tuple)) or getattr(probability, 'ndim', 0) == 1:
            if any((isinstance(v, (list, tuple)) or getattr(v, 'ndim', 0) > 0 for v in probability)):
                return {'error': 'ValueError', 'previous_file_preserved': True, 'input_unchanged': True}
            row = [label, statistic, *probability]
        else:
            row = [label, statistic, probability]
        rows.append(list(map(cell, row)))
    rows += [[''], ['Analysis Summary']]
    for label, value in p['other'].items():
        value = unpack(value)
        row = [label, *value] if isinstance(value, (list, tuple)) or getattr(value, 'ndim', 0) == 1 else [label, value]
        rows.append(list(map(cell, row)))
    return {'result': None, 'rows': rows, 'output_override_used': case['override'], 'input_unchanged': True}
