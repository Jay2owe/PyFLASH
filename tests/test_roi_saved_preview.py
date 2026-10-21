import shutil

import pytest

from reproducibility import roi_preview_contract as contract


def test_actual_saved_preview_reproduces_complete_tables_statistics_and_drawing(tmp_path):
    assert contract.production(tmp_path) == {
        'execution': 'pass', 'data_tables': 'pass', 'display': 'pass', 'statistics': 'pass'}


@pytest.mark.parametrize('name', ['source-files.json', 'Ventricle Analysis/src_inputs.json',
    'Ventricle Analysis/verification/reproduction-report.json',
    'Ventricle Analysis/verification/reproduced/ventricle-analysis-boundary-m-reproduced.svg'])
def test_saved_input_report_or_carrier_changes_cannot_be_accepted(name, tmp_path, monkeypatch):
    archive = tmp_path / 'retained-export'
    shutil.copytree(contract.ARCHIVE, archive)
    path = archive / name
    path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', archive)
    with pytest.raises(ValueError, match='evidence'):
        contract.check_identity()
