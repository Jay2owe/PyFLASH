"""The public marker setter must retain exact caller ownership."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import marker_assignment_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def unchanged_literal_assignment_evidence():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_complete_direct_setter_ownership(item):
    original = deepcopy(item)
    contract.production(item)
    assert item == original


@pytest.mark.parametrize('name', ['before.json', 'original-reference.py', 'original-markers.py'])
def test_changed_literal_assignment_evidence_refuses(name, tmp_path, monkeypatch):
    copied = tmp_path / 'evidence'
    shutil.copytree(contract.ARCHIVE, copied)
    path = copied / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', copied)
    with pytest.raises(ValueError):
        contract.check_identity()


@pytest.mark.parametrize('damage', ['return', 'store'])
@pytest.mark.parametrize('owner', ['Antibody', 'objectMarker', 'cellMarker'])
def test_wrong_setter_identity_cannot_pass(damage, owner, monkeypatch):
    from PyFLASH import markers
    def broken(self, value):
        self.df = object() if damage == 'store' else value
        return object() if damage == 'return' else value
    monkeypatch.setattr(getattr(markers, owner), 'set_df', broken)
    item = next(item for item in CASES if item['case']['owner'] == owner)
    with pytest.raises(AssertionError):
        contract.production(item)


def test_changed_literal_prediction_refuses():
    item = deepcopy(CASES[0])
    item['expected']['returned_input'] = False
    with pytest.raises(AssertionError):
        contract.production(item)


def test_only_direct_assignment_is_complete():
    capability = 'PyFLASH.markers.Antibody.set_df'
    assert len(CASES) == len({item['key'] for item in CASES}) == 72
    assert contract.COMPLETE_CAPABILITIES == {
        f'PyFLASH.markers.{owner}.set_df'
        for owner in ('Antibody', 'objectMarker', 'cellMarker')
    }
    assert contract.required_keys(capability) == {item['key'] for item in CASES}
    for owner in ('objectMarker', 'cellMarker'):
        keys = contract.required_keys(f'PyFLASH.markers.{owner}.set_df')
        assert len(keys) == 24
        assert keys == {item['key'] for item in CASES if item['case']['owner'] == owner}
    assert not contract.required_keys('PyFLASH.markers.Antibody.clean_df')


def test_actual_inherited_setters_require_their_own_executed_cases():
    from reproducibility.run import _build_inventory
    metadata = _build_inventory()
    rows = {row['capability']: row for row in metadata['rows']}
    for capability in contract.COMPLETE_CAPABILITIES:
        assert rows[capability]['kind'] == 'functional-marker-table-ownership'
        assert set(metadata['required'][capability]) == contract.required_keys(capability)
