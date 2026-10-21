"""Complete native workbook comparisons for frozen filter and refusal controls."""
import pytest
from reproducibility import excel_filter_controls_contract as contract


@pytest.fixture(scope='module')
def declared_inputs():
    return contract.inputs()


@pytest.mark.parametrize('case', [row for row in contract.cases() if row['preflight']],
                         ids=lambda row: row['key'])
def test_excel_filter_preflight(case, tmp_path, declared_inputs):
    contract.observe(case, tmp_path, declared_inputs)


@pytest.mark.parametrize('case', [row for row in contract.cases() if not row['preflight']],
                         ids=lambda row: row['key'])
def test_excel_filter_remaining_controls(case, tmp_path, declared_inputs):
    contract.observe(case, tmp_path, declared_inputs)
