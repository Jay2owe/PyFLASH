"""Verified overflow backings remain recoverable after source aliases retire."""
import gzip
import json
import os
import shutil
import pytest
from reproducibility import compact_evidence as c
from reproducibility import source_retention as retention


def fixture(tmp_path):
    snapshot = tmp_path / 'snapshot'
    snapshot.mkdir()
    source = snapshot / 'code.py'
    source.write_bytes(b'original scientific source')
    row = dict(path='code.py', size=source.stat().st_size, sha256=c.digest(source))
    store = tmp_path / 'store'
    canonical = c.object_path(store, row['sha256'])
    canonical.parent.mkdir(parents=True)
    shutil.copyfile(source, canonical)
    relative = 'consumer-links/' + row['sha256'] + '/backing-1.bin'
    backing = c.owned(store, relative)
    backing.parent.mkdir(parents=True)
    source.rename(backing)
    os.link(backing, source)
    manifest = tmp_path / 'manifest.jsonl.gz'
    with gzip.open(manifest, 'wt') as stream:
        stream.write(json.dumps(row) + '\n')
    return snapshot, source, row, store, manifest, relative, canonical, backing


def test_declared_backing_is_verified_retired_and_restored(tmp_path):
    snapshot, source, row, store, manifest, relative, canonical, backing = fixture(tmp_path)
    assert retention.retire_snapshot(snapshot, manifest, store,
        consumer_backings={row['sha256']: [relative]}) == 1
    assert not snapshot.exists()
    c.validate(canonical, row)
    c.validate(backing, row)
    c.restore(manifest, store, tmp_path / 'restored')
    assert (tmp_path / 'restored/code.py').read_bytes() == b'original scientific source'


@pytest.mark.parametrize('fault', ['undeclared', 'corrupt', 'wrong-namespace'])
def test_unverified_backing_cannot_delete_original(tmp_path, fault):
    snapshot, source, row, store, manifest, relative, canonical, backing = fixture(tmp_path)
    declared = {row['sha256']: [relative]}
    if fault == 'undeclared':
        declared = None
    elif fault == 'corrupt':
        backing.write_bytes(b'corrupt')
    else:
        declared = {row['sha256']: ['objects/' + row['sha256'][:2] + '/' + row['sha256'] + '.bin']}
    with pytest.raises((ValueError, OSError)):
        retention.retire_snapshot(snapshot, manifest, store, consumer_backings=declared)
    assert source.exists()


def test_missing_unjournaled_alias_resumes_via_verified_backing_at_link_limit(tmp_path, monkeypatch):
    snapshot, source, row, store, manifest, relative, canonical, backing = fixture(tmp_path)
    source.unlink()
    real_link = os.link
    def full_canonical(src, dst):
        if str(src) == str(canonical):
            error = OSError('canonical hard-link ceiling')
            error.winerror = 1142
            raise error
        return real_link(src, dst)
    monkeypatch.setattr(os, 'link', full_canonical)
    assert retention.retire_snapshot(snapshot, manifest, store,
        consumer_backings={row['sha256']: [relative]}) == 1
    assert not snapshot.exists()
    c.validate(canonical, row)


def test_normal_finalization_handles_full_canonical_link_capacity(tmp_path, monkeypatch):
    snapshot, source, row, store, manifest, relative, canonical, backing = fixture(tmp_path)
    output = snapshot.parent
    owned = output / 'sources'
    snapshot.rename(owned)
    c.atomic_json(output / 'run-started.json', {'sources': [row]})
    real_link = os.link
    def full_canonical(src, dst):
        if str(src) == str(canonical):
            error = OSError('canonical hard-link ceiling')
            error.winerror = 1142
            raise error
        return real_link(src, dst)
    monkeypatch.setattr(os, 'link', full_canonical)
    result = retention.preserve_and_retire(output, owned, [row], store)
    assert result['directory_absent']
    c.restore(output / result['manifest'], store, tmp_path / 'complete-recovery')
    assert (tmp_path / 'complete-recovery/code.py').read_bytes() == b'original scientific source'
