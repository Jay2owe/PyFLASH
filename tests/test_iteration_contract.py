"""Full rows, labels, source preservation and separately computed averages."""
import hashlib
import json
from pathlib import Path
import pytest
from reproducibility import iteration_contract as contract

REFERENCE = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row', REFERENCE['rows'], ids=lambda row: row['key'])
def test_complete_frozen_selection_metadata_and_iteration_order(row):
    actual = contract.production(row)
    contract.assert_contract_equal(actual, row['expected'])
    if 'exact_arithmetic' in row:
        contract.assert_contract_equal(actual, row['exact_arithmetic'])


def test_reference_inputs_and_adapter_remain_immutable():
    assert hashlib.sha256(Path(contract.__file__).read_bytes()).hexdigest() == REFERENCE['reference_code_sha256']
    assert [{k: row[k] for k in ('key', 'capability', 'method', 'state')}
            for row in REFERENCE['rows']] == contract.cases()
    assert REFERENCE['inputs'] == {
        'columns': contract.COLUMNS, 'primary': contract.INPUT, 'noisy': contract.NOISY_INPUT,
        'markers': contract.MARKERS, 'regions': contract.REGIONS,
        'secondary_regions': contract.SECONDARY_REGIONS, 'conditions': contract.CONDITIONS}
