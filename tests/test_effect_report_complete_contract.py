"""Complete effect reports and preflight requests before mutable RNG use."""
import copy
import numpy as np
import pytest
from PyFLASH.stats_extra import effect_sizes_for_test
from reproducibility import effect_report_contract as reference

@pytest.mark.parametrize('case', reference.cases(), ids=lambda row: row['key'])
def test_complete_effect_report_against_original_independent_answers(case):
    assert reference.equal(reference.production(case), reference.expected(case))

def test_effect_report_frozen_inputs_sources_and_original_failures():
    fixture = reference.check_identity()
    assert len(fixture['rows']) == 600
    assert len(fixture['original_failures']) == 206
    assert len(fixture['arrangements']) == 60

def test_original_effect_report_answers_are_preserved():
    import hashlib,json
    previous = reference.FIXTURE.with_name('effect_report_reference.json')
    original = json.loads(previous.read_text(encoding='utf-8'))
    current = reference.check_identity()
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == current['previous_fixture_sha256']
    assert current['rows'][:len(original['rows'])] == original['rows']

@pytest.mark.parametrize('options', [
    {'test': 'unknown'}, {'test': None}, {'test': []}, {'ci': 'yes'}, {'ci': 1},
    {'groups': '12'}, {'groups': 42}, {'groups': {'a': [1,2]}},
    {'groups': [[1,2], [[3,4]]]}, {'comparisons': ['1-2','bad']},
    {'comparisons': ['0-2']}, {'comparisons': ['1-3']},
    {'comparisons': ['1-1']}, {'comparisons': ['1.0-2']},
    {'comparisons': [12]}, {'comparisons': 12},
    {'n_resamples': 0}, {'n_resamples': True}, {'random_state': True},
])
def test_invalid_report_request_fails_before_any_interval(options, monkeypatch):
    from PyFLASH import stats_extra
    def forbidden(*args, **kwargs):
        raise AssertionError('Invalid request reached interval sampling')
    monkeypatch.setattr(stats_extra, 'effect_ci', forbidden)
    parameters = dict(groups=[[1,2,3],[2,4,6]], test='Independent T-Test',
                      comparisons=['1-2'], n_resamples=31)
    parameters.update(options)
    with pytest.raises(ValueError):
        effect_sizes_for_test(**parameters)

def test_invalid_last_comparison_cannot_consume_shared_random_generator():
    rng = np.random.default_rng(17)
    before = copy.deepcopy(rng.bit_generator.state)
    with pytest.raises(ValueError):
        effect_sizes_for_test([[1,2,3],[2,4,6]], 'Independent T-Test',
                              ['1-2','bad'], random_state=rng)
    assert rng.bit_generator.state == before

def test_raw_groups_cannot_infer_adjusted_linear_model_effects():
    assert effect_sizes_for_test([[1,2,3],[2,4,6]], 'Linear Model', ['1-2']) == {
        'overall': {}, 'pairwise': [], 'family': None}

def test_single_pair_and_no_pairs_preserve_return_schema():
    one = effect_sizes_for_test([[1,2,3],[2,4,6]], 'Independent T-Test', '1-2', ci=False)
    assert [row['comparison'] for row in one['pairwise']] == ['1-2']
    assert effect_sizes_for_test([[1,2,3],[2,4,6]], 'Independent T-Test', None, ci=False) == {
        'overall': {}, 'pairwise': [], 'family': None}

def test_effect_report_does_not_change_inputs_or_comparison_order():
    groups = [[1,2,3], [2,4,6]]
    pairs = ['2-1','1-2','2-1']
    before = copy.deepcopy(groups)
    answer = effect_sizes_for_test(groups, 'Independent T-Test', pairs, ci=False)
    assert groups == before
    assert [row['comparison'] for row in answer['pairwise']] == pairs

def test_resample_order_does_not_change_identical_effect_estimates():
    from PyFLASH.stats_extra import hedges_g
    a, b = [1,1,2,3], [1,2,2,3,4]
    assert hedges_g(a,b) == hedges_g(a[::-1],b[::-1])
