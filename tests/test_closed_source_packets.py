import gzip
import json

import pytest

from reproducibility import compact_evidence as c
from reproducibility import retire_closed_sources as closed


@pytest.fixture(autouse=True)
def ram(monkeypatch):
    monkeypatch.setattr(c, 'available_ram', lambda: 8 * 1024**3)


def packet(tmp_path):
    root, packet, store = tmp_path/'snapshot', tmp_path/'packet', tmp_path/'store'
    root.mkdir(); packet.mkdir()
    code = root/'code.py'
    code.write_bytes(b'exact historical source')
    row = {'path':'code.py','size':code.stat().st_size,'sha256':c.digest(code)}
    terminal = tmp_path/'terminal.json'
    c.atomic_json(terminal, {'status':'finished'})
    manifest = packet/'version.jsonl.gz'
    with gzip.open(manifest, 'wt') as f:
        f.write(json.dumps(row)+'\n')
    version = {'id':'version-1','snapshot':str(root),'files':1,'manifest':manifest.name,
               'manifest_sha256':c.digest(manifest),'terminal_receipt':str(terminal),
               'terminal_receipt_sha256':c.digest(terminal)}
    plan = packet/'plan.json'
    c.atomic_json(plan, {'versions':[version],'peak_temporary_bytes':row['size']})
    result = c.compact(plan,store,packet)
    c.atomic_json(packet/'verification.json', {
        'passed':True,'plan_sha256':c.digest(plan),'run_receipt_sha256':c.digest(packet/'run.json'),
        'cleanup_chain_file_sha256':c.digest(packet/'cleanup-chain.jsonl.gz'),
        'files':1,'last_record_sha256':result['last_chain_sha256']})
    c.atomic_json(packet/'link-limit-consumer-check.json', {
        'plan_sha256':c.digest(plan),'running_command_reference_matches':0})
    return root,packet,store


def test_terminal_alias_retirement_retains_full_recovery_and_skips_completed_version(tmp_path):
    root,p,store=packet(tmp_path)
    result=closed.retire(p,store)
    assert result['passed'] and not root.exists()
    assert result['versions'][0]['source_paths_retired']==1
    c.restore(p/'version.jsonl.gz',store,tmp_path/'recovered')
    assert (tmp_path/'recovered/code.py').read_bytes()==b'exact historical source'
    c.restore(p/result['producer_manifest'],store,tmp_path/'recovered-producers')
    for row in result['producers']:
        assert c.digest(tmp_path/'recovered-producers'/row['path'])==row['sha256']
    assert closed.retire(p,store)['passed']
    assert len(json.loads((p/'retirement.json').read_text())['versions'])==1


def test_changed_receipt_blocks_retirement_and_preserves_source(tmp_path):
    root,p,store=packet(tmp_path)
    receipt=json.loads((p/'run.json').read_text())
    receipt['source_files_verified']=99
    c.atomic_json(p/'run.json',receipt)
    with pytest.raises(ValueError,match='unchanged verified packet'):
        closed.retire(p,store)
    assert (root/'code.py').exists()


def test_directory_state_fix_resumes_in_new_receipt_and_preserves_failed_attempt(tmp_path):
    root,p,store=packet(tmp_path)
    (root/'Exports').mkdir()
    first=closed.retire(p,store)
    assert not first['passed'] and root.exists()
    old_sha=c.digest(p/'retirement.json')
    dirs=p/'version.directories.jsonl.gz'
    with gzip.open(dirs,'wt') as f:
        f.write(json.dumps({'kind':'directory','path':'Exports'})+'\n')
    c.atomic_json(p/'directory-state-version-1.json', {
        'directory_manifest':dirs.name,'directory_manifest_sha256':c.digest(dirs)})
    result=closed.retire(p,store,receipt_name='retirement-with-directories.json',resume_from='retirement.json')
    assert result['passed'] and not root.exists()
    assert c.digest(p/'retirement.json')==old_sha
    assert result['resumed_receipt_sha256']==old_sha
    c.restore(p/'version.jsonl.gz',store,tmp_path/'recovered',directories=dirs)
    assert (tmp_path/'recovered/Exports').is_dir()
    assert (tmp_path/'recovered/code.py').read_bytes()==b'exact historical source'
