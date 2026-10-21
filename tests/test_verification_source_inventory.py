"""Verification must detect new producer files, deletions and changes."""
from pathlib import Path
import shutil
import pytest
from reproducibility import run


def snapshot(root,monkeypatch):
    monkeypatch.setattr(run,'ROOT',root)
    sources = run.verification_sources()
    copied = root/'snapshots'
    for path in sources:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('frozen input')
        target = copied/path.relative_to(root)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
    return sources,copied


def test_new_scientific_producer_and_reference_source_are_detected(tmp_path,monkeypatch):
    sources,copied = snapshot(tmp_path,monkeypatch)
    for name in ('PyFLASH/new_method.py','scripts/new_browser_check.py',
                 'reproducibility/reference-sources/new.R',
                 'reproducibility/fixtures/image-inputs/new.tif'):
        path = tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('new scientific code')
    expected = sorted(str(Path(name)) for name in ('PyFLASH/new_method.py',
        'reproducibility/reference-sources/new.R','scripts/new_browser_check.py',
        'reproducibility/fixtures/image-inputs/new.tif'))
    assert run.verification_source_changes(sources,copied)==expected

@pytest.mark.parametrize('name',['architecture.yaml','architecture.lock.json',
                               'architecture.schema.json','scripts/contracts-requirements.txt'])
@pytest.mark.parametrize('operation',['change','delete'])
def test_changed_or_deleted_verification_configuration_is_detected(tmp_path,monkeypatch,name,operation):
    sources,copied=snapshot(tmp_path,monkeypatch)
    path=tmp_path/name
    assert path in sources
    if operation=='delete':path.unlink()
    else:path.write_text('changed verification rule',encoding='utf-8')
    assert run.verification_source_changes(sources,copied)==[str(Path(name))]


def test_changed_and_deleted_inputs_are_detected_without_graph_artifacts(tmp_path,monkeypatch):
    sources,copied = snapshot(tmp_path,monkeypatch)
    (tmp_path/'README.md').write_text('changed example')
    (tmp_path/'demo/run_demo.py').unlink()
    ignored = tmp_path/'graphify-out/graph.json'
    ignored.parent.mkdir(); ignored.write_text('local graph')
    expected = sorted(str(Path(p)) for p in ('README.md','demo/run_demo.py'))
    assert run.verification_source_changes(sources,copied)==expected


def test_inventory_identity_tracks_runner_code_loaded_before_source_edits(tmp_path,monkeypatch):
    monkeypatch.setattr(run,'ROOT',tmp_path)
    before = run._inventory_base_identity()
    monkeypatch.setattr(run,'RUNNER_SOURCE_AT_IMPORT_SHA256','f'*64)
    after = run._inventory_base_identity()
    assert before['sources']==after['sources']=={}
    assert before['runner_source_at_import'] != after['runner_source_at_import']
