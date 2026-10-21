"""The normal suite retains the complete frozen region and progress answers."""
import pytest
from reproducibility import excel_region_selection_contract as contract


@pytest.fixture(scope='module')
def declared_inputs():
    return contract.inputs()


@pytest.mark.parametrize('case', contract.cases(), ids=lambda row: row['key'])
def test_complete_region_workbook_and_report(case, tmp_path, declared_inputs):
    observed = contract.observe(case, tmp_path, declared_inputs)
    assert observed['error'] is None
    assert observed['disagreements'] == []
