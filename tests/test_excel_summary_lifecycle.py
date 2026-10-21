"""Real public exports rebuild or preserve frozen summary states as declared."""
import pytest
from reproducibility import excel_summary_lifecycle_contract as contract


@pytest.fixture(scope='module')
def declared_inputs(): return contract.inputs()


@pytest.mark.parametrize('case', [row for row in contract.cases() if row['preflight']], ids=lambda row: row['key'])
def test_excel_lifecycle_preflight(case, tmp_path, declared_inputs):
    contract.observe(case, tmp_path, declared_inputs)


@pytest.mark.parametrize('case', [row for row in contract.cases() if not row['preflight']], ids=lambda row: row['key'])
def test_excel_lifecycle_remaining(case, tmp_path, declared_inputs):
    contract.observe(case, tmp_path, declared_inputs)
