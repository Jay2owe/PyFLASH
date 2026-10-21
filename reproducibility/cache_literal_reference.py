"""Independently declared equivalence/ownership rules for opaque statistics keys."""
from copy import deepcopy
import hashlib, json, pickle
from pathlib import Path
import numpy as np
from PyFLASH import stats
from PyFLASH.config import Config
from PyFLASH.aesthetics import pyflash_style_context
from PyFLASH._cache import BoundedCache
BASE = {'column_name': 'Signal', 'condition_names': ['A', 'B'], 'specificity': ['female'], 'stats_options': {'covariates': ['Age', 'Sex'], 'cov_kwds': {'groups': [1, 1, 2, 2]}}}

def params(**updates):
    return deepcopy(BASE) | updates

def cases():
    rows = []

    def add(label, left, right, equal, **extra):
        rows.append({'key': 'stats-cache.literal.' + label, 'left': left, 'right': right, 'expected_equal': equal, **extra})
    add('unchanged', params(), params(), True)
    add('column', params(), params(column_name='Other'), False)
    add('condition-order', params(), params(condition_names=['B', 'A']), False)
    add('condition-empty', params(condition_names=None), params(condition_names=[]), True)
    add('specificity-empty', params(specificity=None), params(specificity=[]), True)
    add('specificity-values', params(), params(specificity=['male']), False)
    add('specificity-order', params(specificity=['female', 'SCN']), params(specificity=['SCN', 'female']), False)
    add('options-empty', params(stats_options=None), params(stats_options={}), True)
    add('mapping-order', params(), params(stats_options={'cov_kwds': {'groups': [1, 1, 2, 2]}, 'covariates': ['Age', 'Sex']}), True)
    values = [('bool-int', True, 1, False), ('int-float', 1, 1.0, False), ('text-bytes', 'x', {'wire': 'bytes', 'value': 'x'}, False), ('positive-negative-zero', 0.0, -0.0, False), ('float-next', 1.0, float(np.nextafter(1.0, 2.0)), False), ('list-tuple', [1, 2], {'wire': 'tuple', 'value': [1, 2]}, False), ('set-order', {'wire': 'set', 'value': [1, 2]}, {'wire': 'set', 'value': [2, 1]}, True), ('numpy-integer', 1, {'wire': 'np-int', 'value': 1}, True), ('numpy-float', 1.0, {'wire': 'np-float', 'value': 1.0}, True), ('array-shape', {'wire': 'array', 'value': [1, 2], 'dtype': 'float64'}, {'wire': 'array', 'value': [[1, 2]], 'dtype': 'float64'}, False), ('array-dtype', {'wire': 'array', 'value': [1, 2], 'dtype': 'int64'}, {'wire': 'array', 'value': [1, 2], 'dtype': 'float64'}, False), ('array-order', {'wire': 'array', 'value': [1, 2], 'dtype': 'int64'}, {'wire': 'array', 'value': [2, 1], 'dtype': 'int64'}, False), ('nan', {'wire': 'float', 'value': 'nan'}, {'wire': 'float', 'value': 'nan'}, True), ('infinity', {'wire': 'float', 'value': 'inf'}, {'wire': 'float', 'value': '-inf'}, False)]
    for label, left, right, equal in values:
        for nested in (False, True):
            l = {'value': left}
            r = {'value': right}
            if nested:
                l = {'nested': l}
                r = {'nested': r}
            add(label + '.' + str(nested), params(stats_options=l), params(stats_options=r), equal)
    for field, first, second in [('POSTHOC_CORRECTION', 'auto', 'holm'), ('CORRECTION_AUDIT', 'cheap', 'full'), ('EFFECT_SIZES', True, False), ('EFFECT_CI', True, False), ('EFFECT_CI_RESAMPLES', 400, 401), ('EFFECT_CI_RANDOM_STATE', 17, 18)]:
        add('setting.' + field, params(), params(), False, config_left={field: first}, config_right={field: second})
    for label, left, right, equal in [('symbols', {'significance_thresholds': {0.05: '*'}}, {'significance_thresholds': {0.05: '+'}}, False), ('cutoff', {'significance_thresholds': {0.05: '*'}}, {'significance_thresholds': {0.1: '*'}}, False), ('missing-label', {'significance_ns': 'ns'}, {'significance_ns': 'undefined'}, False), ('appearance', {'line_width': 1}, {'line_width': 3}, True)]:
        add('style.' + label, params(), params(), equal, style_left=left, style_right=right)
    return rows

def unpack(value):
    if isinstance(value, list):
        return [unpack(item) for item in value]
    if isinstance(value, dict):
        if 'wire' not in value:
            return {key: unpack(item) for key, item in value.items()}
        kind, item = (value['wire'], value['value'])
        if kind == 'bytes':
            return item.encode()
        if kind == 'tuple':
            return tuple(item)
        if kind == 'set':
            return set(item)
        if kind == 'np-int':
            return np.int64(item)
        if kind == 'np-float':
            return np.float64(item)
        if kind == 'float':
            return float(item)
        if kind == 'array':
            return np.asarray(item, dtype=value['dtype'])
        raise ValueError(kind)
    return value

def production(case):
    fields = set(case.get('config_left', {})) | set(case.get('config_right', {}))
    before = {key: getattr(Config, key) for key in fields}
    try:
        keys = []
        for side in ('left', 'right'):
            for key, value in case.get('config_' + side, {}).items():
                setattr(Config, key, value)
            with pyflash_style_context(**case.get('style_' + side, {})):
                keys.append(stats.stats_cache_key(**unpack(case[side])))
        equal = keys[0] == keys[1]
        return {'equal': equal, 'hashable': bool(hash(keys[0]) or True) and bool(hash(keys[1]) or True), 'equal_keys_have_equal_hashes': not equal or hash(keys[0]) == hash(keys[1])}
    finally:
        for key, value in before.items():
            setattr(Config, key, value)

def clear_production(case):
    previous = stats._stats_cache
    cache = BoundedCache(max_entries=case['capacity'], max_bytes=case['budget'])
    owned = []
    stats._stats_cache = cache
    try:
        for index in range(case['entries']):
            value = {'independent-result': [index, index + 1]}
            owned.append(value)
            cache[index] = value
        expected = deepcopy(owned)
        first = stats.clear_stats_cache()
        second = stats.clear_stats_cache()
        return {'return_is_none': first is None and second is None, 'empty': len(cache) == 0, 'retained_bytes_zero': cache.retained_bytes == 0, 'capacity_unchanged': cache.max_entries == case['capacity'], 'budget_unchanged': cache.max_bytes == case['budget'], 'caller_values_unchanged': owned == expected}
    finally:
        stats._stats_cache = previous
