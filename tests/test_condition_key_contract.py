"""The public legend preserves literal encodings, complete text and ownership."""
import pytest
from reproducibility import condition_key_contract as contract


def test_condition_key_parameter_inventory():
    contract.check_parameters()


@pytest.mark.parametrize('case', [row for row in contract.cases() if row['mode'] != 'save'],
                         ids=lambda row: row['key'])
def test_condition_key_in_memory_and_failure_contract(case, tmp_path):
    contract.observe(case, tmp_path)


@pytest.mark.parametrize('fontsize', [12, 19])
def test_condition_key_inherits_shared_font_settings(tmp_path, fontsize):
    import matplotlib
    case = next(row for row in contract.cases() if row['key'] == 'condition-key.base.columns-None')
    with matplotlib.rc_context({'legend.fontsize': fontsize}):
        contract.observe(case, tmp_path)


@pytest.mark.parametrize('case', [row for row in contract.cases() if row['mode'] == 'save'],
                         ids=lambda row: row['key'])
def test_condition_key_actual_saved_carrier(case, tmp_path):
    contract.observe(case, tmp_path)
