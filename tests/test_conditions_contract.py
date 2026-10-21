"""Every returned design field and requested comparison must stay consistent."""
import hashlib
import json
from pathlib import Path
import pytest
from reproducibility import conditions_contract as contract
from reproducibility.iteration_contract import assert_contract_equal

REFERENCE = json.loads(contract.FIXTURE.read_text())


@pytest.mark.parametrize('row',REFERENCE['rows'],ids=lambda row:row['key'])
def test_full_independent_group_design(row):
    assert_contract_equal(contract.production(row),row['expected'])


def test_frozen_inputs_and_reference_identity():
    assert hashlib.sha256(Path(contract.__file__).read_bytes()).hexdigest()==REFERENCE['reference_code_sha256']
    assert [{k:row[k] for k in ['key','capability','capabilities','parameters']} for row in REFERENCE['rows']]==contract.cases()
    assert REFERENCE['inputs']=={'entries':contract.ENTRIES,'treatments':contract.TREATMENTS}
