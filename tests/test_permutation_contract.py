"""Independent full rank-null tables, domains, and caller ownership."""
import json, math
import numpy as np
import pytest
from reproducibility import permutation_contract as reference
from reproducibility.reference_runtime import values
from PyFLASH import stats_extra


@pytest.mark.parametrize('row',reference.cases(),ids=lambda r:r['key'])
def test_full_permutation_contract(row):
    fixture = json.loads(reference.FIXTURE.read_text())
    expected = next(r for r in fixture['rows'] if r['key']==row['key'])
    assert expected['parameters']==row['parameters']
    truth = values({'values':expected['mathematical_values'],'nonfinite':expected['mathematical_nonfinite']})
    result = stats_extra.permutation_null(**row['parameters'])
    assert set(result)=={'p','pairs','mode','statistic','n_perm','n_arrangements'}
    assert result['p'].shape==(int(truth[1]),int(truth[4]))
    assert type(result['n_perm']) is int and type(result['n_arrangements']) is int
    np.testing.assert_allclose(reference.production(row),truth,rtol=1e-9,atol=1e-12,equal_nan=True)


@pytest.mark.parametrize('parameters',reference.invalid_cases())
def test_invalid_design_is_rejected_before_enumeration(parameters,monkeypatch):
    def forbidden(*args):
        pytest.fail('An invalid design reached expensive cached enumeration')
    monkeypatch.setattr(stats_extra,'_permutation_null_cached',forbidden)
    with pytest.raises(ValueError):
        stats_extra.permutation_null(**parameters)


def test_returned_metadata_cannot_corrupt_another_result():
    first = stats_extra.permutation_null([2,2])
    first['mode']='caller edit'
    first['pairs'].append((9,9))
    first['p'].flags.writeable=True
    first['p'][:]=123
    second = stats_extra.permutation_null([2,2])
    assert second['mode']=='exact' and second['pairs']==[(0,1)]
    assert not second['p'].flags.writeable
    assert (second['p']<=1).all()


@pytest.mark.parametrize('row',reference.cases(),ids=lambda r:r['key'])
def test_rank_order_and_attainable_floor_against_frozen_full_tables(row):
    fixture = json.loads(reference.FIXTURE.read_text())
    expected = next(r for r in fixture['rows'] if r['key']==row['key'])
    truth = np.array(values({'values':expected['mathematical_values'],'nonfinite':expected['mathematical_nonfinite']}))
    parameters = dict(row['parameters'],ranks=list(reversed(reference.ranks(row['parameters']))))
    np.testing.assert_allclose(reference.production({'parameters':parameters}),truth,rtol=1e-9,atol=1e-12,equal_nan=True)
    offset = 5+2*int(truth[4])
    floor = stats_extra.attainable_p_floor(**row['parameters'])
    expected_floor = np.min(truth[offset:])
    assert math.isnan(floor) if math.isnan(expected_floor) else floor==pytest.approx(expected_floor,rel=1e-9,abs=1e-12)


def test_published_native_answers_and_independent_math_are_frozen():
    fixture = json.loads(reference.FIXTURE.read_text())
    assert len(fixture['rows'])==len(reference.cases())
    mismatches = []
    for row in fixture['rows']:
        native = next(r for r in fixture['native']['rows'] if r['key']==row['key'])
        assert native['status']=='executed'
        actual = np.array(values(native))
        truth = np.array(values({'values':row['mathematical_values'],'nonfinite':row['mathematical_nonfinite']}))
        unequal = ~np.isclose(actual,truth,rtol=1e-9,atol=1e-12,equal_nan=True)
        if unequal.any():
            mismatches.append({'key':row['key'],'positions':np.flatnonzero(unequal).tolist(),
                               'native':actual[unequal].tolist(),'truth':truth[unequal].tolist()})
    assert not mismatches,mismatches
