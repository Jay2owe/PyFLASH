"""Whole control-comparison outputs, preflight, input and RNG ownership."""
import copy
import numpy as np
import pytest
from PyFLASH.stats_extra import dunnett_vs_control
from reproducibility import dunnett_contract as reference

@pytest.mark.parametrize('case', reference.cases(), ids=lambda row: row['key'])
def test_complete_control_report_against_independent_frozen_answers(case):
    assert reference.equal(reference.production(case), reference.expected(case))

def test_frozen_dunnett_inputs_original_failures_and_native_sources():
    fixture = reference.check_identity()
    assert len(fixture['rows']) == 1164
    assert len(fixture['native_queries']) == 48
    assert len(fixture['original_failures']) == 1164

@pytest.mark.parametrize('options', [
    {'groups': []}, {'groups': [[1,2]]}, {'groups': [[1],[2]]},
    {'groups': [[], [1,2]]}, {'groups': [[None,np.inf],[1,2]]},
    {'groups': [[[1,2]], [1,2]]}, {'groups': '12'}, {'groups': {'a':[1,2]}},
    {'control': True}, {'control': np.bool_(True)}, {'control': .5},
    {'control': -1}, {'control': 2}, {'control': 'absent'},
    {'labels': ['same','same']}, {'labels': [1,'1']}, {'labels': ['one']},
    {'labels': 'ab'}, {'labels': {'a':1,'b':2}}, {'labels': [['a'],['b']]},
    {'alternative': 'bad'}, {'alternative': None}, {'alternative': []},
    {'random_state': True}, {'random_state': -1}, {'random_state': 1.5},
])
def test_invalid_control_report_fails_before_quadrature(options, monkeypatch):
    import PyFLASH._dunnett as kernel
    def forbidden(*args, **kwargs):
        raise AssertionError('Invalid request reached integration')
    monkeypatch.setattr(kernel, '_probability', forbidden)
    parameters = {'groups': [[1,2,3], [2,4,6]]}
    parameters.update(options)
    with pytest.raises(ValueError): dunnett_vs_control(**parameters)

@pytest.mark.parametrize('kind', ['generator','random-state'])
def test_deterministic_control_report_preserves_random_draw_ownership(kind):
    rng = np.random.default_rng(17) if kind == 'generator' else np.random.RandomState(17)
    before = copy.deepcopy(rng.bit_generator.state if kind == 'generator' else rng.get_state())
    dunnett_vs_control([[1,2,3],[2,4,6]], random_state=rng)
    after = rng.bit_generator.state if kind == 'generator' else rng.get_state()
    if kind == 'generator': assert before == after
    else:
        assert before[0] == after[0] and np.array_equal(before[1],after[1]) and before[2:] == after[2:]

def test_control_report_preserves_inputs_labels_and_treatment_order():
    groups = [[1,2,3], [2,4,6], [3,5,8]]
    labels = ['early', 'control', 'late']
    original = copy.deepcopy((groups, labels))
    result = dunnett_vs_control(groups, labels, control='control')
    assert (groups, labels) == original
    assert result.comparison.tolist() == ['early vs control', 'late vs control']

def test_control_probability_cache_has_an_entry_and_memory_bound():
    from PyFLASH._dunnett import _probability
    _probability.cache_clear()
    try:
        for index in range(300):
            _probability(float(index), (3,), 3, 4, 'two-sided')
        assert _probability.cache_info().currsize <= 256
        assert _probability.cache_bytes() <= 64*1024**2
    finally:
        _probability.cache_clear()
