import importlib.util
import shutil
import pytest
from reproducibility import outlier_request_contract as contract

@pytest.fixture(scope='module', autouse=True)
def authentic_original_requests():
    contract.check_identity()

@pytest.mark.parametrize('row', contract.cases(), ids=lambda row: row['key'])
def test_actual_public_outlier_request_preserves_choices_tables_and_ownership(row, tmp_path):
    assert contract.agrees(row, contract.production(row, tmp_path))

@pytest.mark.parametrize('name', [
    'source-manifest.json',
    'outlier-requests-before-20261007-v1/frozen-before.json',
])
def test_changed_original_outlier_request_evidence_refuses_before_call(tmp_path, monkeypatch, name):
    spec = importlib.util.spec_from_file_location('isolated_outlier_requests', contract.__file__)
    isolated = importlib.util.module_from_spec(spec); spec.loader.exec_module(isolated)
    archive = tmp_path / 'archive'; shutil.copytree(contract.ARCHIVE, archive)
    target = archive / name; target.write_bytes(target.read_bytes() + b'\n')
    isolated.ARCHIVE = archive
    monkeypatch.setattr(isolated, 'production', lambda *_: pytest.fail('Changed evidence reached call'))
    with pytest.raises(ValueError, match='evidence'):
        isolated.validate(tmp_path / 'output')

@pytest.mark.parametrize('method', ['mark_outliers', 'exclude_outliers', 'data_overview'])
def test_changed_returned_measurement_or_flag_fails_healthy_original_control(tmp_path, monkeypatch, method):
    from PyFLASH import exclusions, pipeline
    module = pipeline if method == 'data_overview' else exclusions
    original = getattr(module, method)
    def damaged(*args, **kwargs):
        result = original(*args, **kwargs)
        if method == 'data_overview':
            result['outliers'] = result['outliers'].iloc[:0]
        else:
            result.summary.loc[0, 'Y'] = 999.
        return result
    monkeypatch.setattr(module, method, damaged)
    row = next(row for row in contract.cases() if row['method'] == method
               and row['representation'] == 'tuple' and not row['supplied'])
    assert not contract.agrees(row, contract.production(row, tmp_path))
