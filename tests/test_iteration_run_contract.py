"""Full action traces and selected data must match an independent event model."""
import hashlib
import json
from pathlib import Path
import pytest
from reproducibility import iteration_run_contract as contract, iteration_contract

REFERENCE = json.loads(contract.FIXTURE.read_text())


@pytest.mark.parametrize('row',REFERENCE['rows'],ids=lambda row:row['key'])
def test_all_orchestration_events_results_and_source_preservation(row):
    iteration_contract.assert_contract_equal(contract.production(row),row['expected'])


def test_frozen_sources_and_input_parameters():
    assert hashlib.sha256(Path(contract.__file__).read_bytes()).hexdigest()==REFERENCE['reference_code_sha256']
    assert hashlib.sha256(Path(iteration_contract.__file__).read_bytes()).hexdigest()==REFERENCE['input_adapter_sha256']
    assert [{k:row[k] for k in ['key','capability','parameters']} for row in REFERENCE['rows']]==contract.cases()
