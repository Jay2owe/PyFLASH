"""Extras-only callbacks must propagate their original error exactly once."""
from types import SimpleNamespace
import pytest
from PyFLASH.batch import Batch


@pytest.mark.parametrize('method', ['export_unregistered_summary_excel', 'export_extra_summary_excel', 'export_excel', 'export_all_excel'])
@pytest.mark.parametrize('legacy', [False, True])
def test_missing_extra_summary_callback_error_is_not_hidden(tmp_path, method, legacy):
    calls = []
    def modern(*, progress):
        calls.append(progress)
        raise TypeError('declared rebuilding failure')
    def old():
        calls.append('legacy')
        raise TypeError('declared rebuilding failure')
    batch = object.__new__(Batch)
    batch.name = 'extras-only callback'
    batch.summaries = {}
    batch.experiment_list = [SimpleNamespace(summaries={}, summary=None, createSummary=old if legacy else modern)]
    options = dict(behaviour=False, if_extended=False, if_summary=False, unregistered_summary=True) if method in ('export_excel', 'export_all_excel') else {}
    with pytest.raises(TypeError, match='declared rebuilding failure'):
        getattr(batch, method)(save_path=tmp_path, **options)
    assert calls == ['legacy' if legacy else False]
    assert not list(tmp_path.iterdir())


@pytest.fixture(scope='module')
def literal_extra_client():
    import ijson
    from reproducibility import excel_coupled_contract as client
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(client.ARCHIVE, 'source-manifest.json', client.MANIFEST_SHA256)
    with (client.ARCHIVE / 'client-reference.json').open('rb') as stream:
        for row in ijson.items(stream, 'rows.item', use_float=True):
            if row['method'] == 'export_extra_summary_excel':
                return row
    raise AssertionError('Required canonical literal client missing')


@pytest.mark.parametrize('method', ['export_unregistered_summary_excel', 'export_extra_summary_excel', 'export_excel', 'export_all_excel'])
def test_extras_only_rebuilds_missing_batch_summary_with_complete_native_output(
        tmp_path, monkeypatch, literal_extra_client, method):
    from copy import deepcopy
    import hashlib
    import json
    from reproducibility import excel_coupled_contract as client
    factory = client.literal_batch
    def missing_summary(folder, row):
        batch = factory(folder, row)
        batch.summaries = {}
        batch.experiment_list[0].summaries = {'SCN': client.frame(row['design']['summaries']['SCN'])}
        return batch
    monkeypatch.setattr(client, 'literal_batch', missing_summary)
    row = deepcopy(literal_extra_client)
    row.update(method=method, key='excel-missing-summary.' + method)
    if method in ('export_excel', 'export_all_excel'):
        row['options'] = dict(behaviour=False, if_extended=False, if_summary=False,
            unregistered_summary=True, unregistered_summary_include=[], unregistered_summary_exclude=[])
    row['_case_digest'] = hashlib.sha256(json.dumps(row, sort_keys=True, allow_nan=False).encode()).hexdigest()
    observed = client.observe(row, tmp_path)
    assert observed['error'] is None
    assert observed['disagreements'] == []
