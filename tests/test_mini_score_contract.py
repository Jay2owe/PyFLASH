"""Whole summary score tables must retain native numbers and raw observations."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import mini_score_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def original_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=[row['key'] for row in CASES])
def test_complete_public_score_tables(item):
    contract.production(item)


@pytest.mark.parametrize('name', ['scores-reference-v2/before.json', 'score_reference_v2.py',
                                   'scores-reference-v2/native/marker-summary-scores-results.json'])
def test_changed_original_evidence_refuses(name, tmp_path, monkeypatch):
    copied = tmp_path / 'original'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['burden', 'fragmentation', 'dtype', 'raw-value'])
def test_damaged_full_score_prediction_refuses(damage):
    item = deepcopy(CASES[0])
    if damage == 'dtype':
        item['expected']['dtypes'][-1] = 'int64'
    else:
        position = -2 if damage == 'burden' else -1 if damage == 'fragmentation' else 1
        item['expected']['rows'][0][position] = 99.
    with pytest.raises(AssertionError):
        contract.production(item)


def test_scope_retains_all_original_options_and_disagreements():
    assert len(CASES) == len({row['key'] for row in CASES}) == 96
    assert {row['case']['surface'] for row in CASES} == {'SATotal', 'SurfaceTotal'}
    assert {row['case']['area'] for row in CASES} == {'%AreaMean', 'ROI_%AreaMean'}
    assert not contract.COMPLETE_CAPABILITIES
    assert contract.read('scores-original/independent-disagreement.json')['native_R_burden'] != (
        contract.read('scores-original/independent-disagreement.json')['mpmath_burden'])
