import json
import gzip
from pathlib import Path
import pytest
from reproducibility import compact_evidence as c
from reproducibility import source_retention as retention


@pytest.fixture(autouse=True)
def ram(monkeypatch):
    monkeypatch.setattr(c,'available_ram',lambda:8*1024**3)


def snapshot(tmp_path):
    output=tmp_path/'closed-run'
    sources=output/'sources'
    sources.mkdir(parents=True)
    code=sources/'code.py'
    code.write_bytes(b'original producing code')
    rows=[{'path':'code.py','sha256':c.digest(code)}]
    c.atomic_json(output/'run-started.json',{'sources':rows,'passed':False})
    return output,sources,rows,tmp_path/'canonical'


def test_exact_code_restores_after_original_names_are_deleted(tmp_path):
    output,sources,rows,store=snapshot(tmp_path)
    result=retention.preserve_and_retire(output,sources,rows,store)
    assert result['directory_absent'] and not sources.exists()
    assert result['source_files_retired']==1
    restored=tmp_path/'recovered'
    c.restore(output/result['manifest'],store,restored)
    assert (restored/'code.py').read_bytes()==b'original producing code'


def test_retirement_accepts_authenticated_previously_retired_paths_and_separate_journal(tmp_path):
    output,sources,rows,store=snapshot(tmp_path)
    code=sources/'code.py'
    record={'path':'code.py','sha256':c.digest(code),'size':code.stat().st_size}
    blob=c.object_path(store,record['sha256'])
    blob.parent.mkdir(parents=True)
    c.os.link(code,blob)
    manifest=output/'version.jsonl.gz'
    with gzip.open(manifest,'wt') as f:
        f.write(json.dumps(record)+'\n')
    # First prove independent recovery, then simulate recorded compaction
    # retirement of the original because Windows could not add another link.
    c.restore_file(blob,tmp_path/'independent.py',record)
    retention.unlink_alias(code,blob)
    journal=output/'version-specific-retirement.jsonl.gz'
    assert retention.retire_snapshot(sources,manifest,store,
                                    already_retired={'code.py'},journal_path=journal)==1
    assert not sources.exists() and journal.exists()
    c.restore(manifest,store,tmp_path/'restored')
    assert (tmp_path/'restored/code.py').read_bytes()==b'original producing code'


def test_retirement_rejects_previously_retired_path_outside_manifest(tmp_path):
    output,sources,rows,store=snapshot(tmp_path)
    code=sources/'code.py'
    manifest=output/'version.jsonl.gz'
    with gzip.open(manifest,'wt') as f:
        f.write(json.dumps({'path':'code.py','sha256':c.digest(code),'size':code.stat().st_size})+'\n')
    with pytest.raises(ValueError,match='outside this manifest'):
        retention.retire_snapshot(sources,manifest,store,already_retired={'unknown.py'})
    assert code.exists()


def test_unknown_files_prevent_all_original_name_deletion(tmp_path):
    output,sources,rows,store=snapshot(tmp_path)
    (sources/'unresolved.log').write_text('needed diagnosis')
    with pytest.raises(ValueError,match='unlisted|file list changed'):
        retention.preserve_and_retire(output,sources,rows,store)
    assert (sources/'code.py').read_bytes()==b'original producing code'
    assert (sources/'unresolved.log').read_text()=='needed diagnosis'


def test_unknown_empty_directory_is_preserved_as_possible_input_state(tmp_path):
    output,sources,rows,store=snapshot(tmp_path)
    (sources/'unresolved-empty-input').mkdir()
    with pytest.raises(ValueError,match='unlisted directory'):
        retention.preserve_and_retire(output,sources,rows,store)
    assert (sources/'code.py').exists() and (sources/'unresolved-empty-input').is_dir()


def test_captured_empty_directory_state_restores_after_alias_retirement(tmp_path):
    output,sources,rows,store=snapshot(tmp_path)
    extra=sources/'Exports'
    extra.mkdir()
    code=sources/'code.py'
    row={'path':'code.py','size':code.stat().st_size,'sha256':c.digest(code)}
    manifest=output/'version.jsonl.gz'
    with gzip.open(manifest,'wt') as f: f.write(json.dumps(row)+'\n')
    blob=c.object_path(store,row['sha256'])
    blob.parent.mkdir(parents=True)
    c.os.link(code,blob)
    c.restore_file(blob,tmp_path/'independent.py',row)
    dirs=output/'directories.jsonl.gz'
    with gzip.open(dirs,'wt') as f:
        f.write(json.dumps({'kind':'directory','path':'Exports'})+'\n')
    assert retention.retire_snapshot(sources,manifest,store,directory_manifest=dirs)==1
    c.restore(manifest,store,tmp_path/'recovered',directories=dirs)
    assert (tmp_path/'recovered/Exports').is_dir()
    assert list((tmp_path/'recovered/Exports').iterdir())==[]
    assert (tmp_path/'recovered/code.py').read_bytes()==b'original producing code'


def test_changed_frozen_source_cannot_be_retired(tmp_path):
    output,sources,rows,store=snapshot(tmp_path)
    (sources/'code.py').write_bytes(b'changed')
    with pytest.raises(ValueError,match='Bytes differ'):
        retention.preserve_and_retire(output,sources,rows,store)
    assert (sources/'code.py').read_bytes()==b'changed'


def test_retirement_pause_resumes_without_losing_producing_bytes(tmp_path,monkeypatch):
    output,sources,rows,store=snapshot(tmp_path)
    extra=sources/'second.py'
    extra.write_bytes(b'second original file')
    rows.append({'path':'second.py','sha256':c.digest(extra)})
    c.atomic_json(output/'run-started.json',{'sources':rows,'passed':False})
    real=retention.unlink_alias
    calls=0
    def pause(path,blob):
        nonlocal calls
        calls+=1
        if calls==2:
            raise c.ResourcePause('RAM pressure during retirement')
        real(path,blob)
    monkeypatch.setattr(retention,'unlink_alias',pause)
    with pytest.raises(c.ResourcePause):
        retention.preserve_and_retire(output,sources,rows,store)
    assert not (sources/'code.py').exists() and extra.exists()
    monkeypatch.setattr(retention,'unlink_alias',real)
    assert retention.preserve_and_retire(output,sources,rows,store)['directory_absent']
    c.restore(output/'source-packet/version.jsonl.gz',store,tmp_path/'restored')
    assert (tmp_path/'restored/code.py').read_bytes()==b'original producing code'
    assert (tmp_path/'restored/second.py').read_bytes()==b'second original file'


def test_transient_windows_directory_lock_retries_after_verified_retirement(tmp_path, monkeypatch):
    output, sources, rows, store = snapshot(tmp_path)
    real = Path.rmdir
    attempts = []
    def locked(directory):
        if directory == sources:
            attempts.append(directory)
            if len(attempts) < 3:
                error = PermissionError('Temporary Windows sharing lock')
                error.winerror = 32
                raise error
        return real(directory)
    monkeypatch.setattr(Path, 'rmdir', locked)
    monkeypatch.setattr(retention.time, 'sleep', lambda seconds: None)
    result = retention.preserve_and_retire(output, sources, rows, store)
    assert result['directory_absent'] and len(attempts) == 3
    c.restore(output / result['manifest'], store, tmp_path / 'restored')
    assert (tmp_path / 'restored/code.py').read_bytes() == b'original producing code'


@pytest.mark.parametrize('winerror, expected_attempts', [(32, 20), (33, 20), (5, 1)])
def test_persistent_directory_failure_preserves_verified_resume_checkpoint(
        tmp_path, monkeypatch, winerror, expected_attempts):
    output, sources, rows, store = snapshot(tmp_path)
    real = Path.rmdir
    attempts = []
    def locked(directory):
        if directory == sources:
            attempts.append(directory)
            error = PermissionError('Directory remains unavailable')
            error.winerror = winerror
            raise error
        return real(directory)
    monkeypatch.setattr(Path, 'rmdir', locked)
    monkeypatch.setattr(retention.time, 'sleep', lambda seconds: None)
    with pytest.raises(PermissionError):
        retention.preserve_and_retire(output, sources, rows, store)
    assert len(attempts) == expected_attempts and sources.is_dir()
    assert not (sources / 'code.py').exists()
    c.restore(output / 'source-packet/version.jsonl.gz', store, tmp_path / 'restored')
    assert (tmp_path / 'restored/code.py').read_bytes() == b'original producing code'
    monkeypatch.setattr(Path, 'rmdir', real)
    assert retention.preserve_and_retire(output, sources, rows, store)['directory_absent']
