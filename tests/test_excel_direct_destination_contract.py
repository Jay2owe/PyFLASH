"""The permanent suite executes the same predeclared direct-export contract."""
import pytest
from reproducibility import excel_destination_contract as contract


@pytest.fixture(scope='module')
def declared_rows():
    return contract.declared_rows()


@pytest.mark.parametrize('case', contract.cases(), ids=lambda row: row['key'])
def test_direct_destination_complete_workbook_and_report(tmp_path, declared_rows, case):
    contract.observe_case(tmp_path, declared_rows, case)


def test_direct_inputs_stream_first_authenticated_row_per_method(monkeypatch, tmp_path):
    import hashlib
    import json
    from reproducibility import evidence_identity
    rows = [{'method': method, 'key': method, 'value': 1.25}
            for method in contract.METHODS]
    (tmp_path / 'client-reference.json').write_text(json.dumps({'rows': rows}))
    calls = []
    monkeypatch.setattr(contract.client, 'ARCHIVE', tmp_path)
    monkeypatch.setattr(evidence_identity, 'verify_manifest', lambda *args: calls.append(args))
    def forbidden():
        raise AssertionError('Whole frozen JSON was loaded')
    monkeypatch.setattr(contract.client, 'cases', forbidden)
    selected = contract.declared_rows()
    assert calls == [(tmp_path, 'source-manifest.json', contract.client.MANIFEST_SHA256)]
    for row in rows:
        digest = hashlib.sha256(json.dumps(row, sort_keys=True, allow_nan=False).encode()).hexdigest()
        assert selected[row['method']] == dict(row, _case_digest=digest)
