"""An adapter revision cannot replace original answers or unapproved evidence."""
from copy import deepcopy
import hashlib,json
import pytest
from reproducibility.evidence_identity import verify_sources


@pytest.fixture
def revision(tmp_path):
    sha=lambda data:hashlib.sha256(data).hexdigest()
    files={'original.py':b'original','candidate.py':b'candidate','adapter.py':b'candidate',
           'proof.json':json.dumps({'complete_outputs_unchanged':True,'source_unchanged':True,
                                    'exception_preserved':True}).encode()}
    for name,data in files.items():(tmp_path/name).write_bytes(data)
    previous={'rows':[{'expected':[1.25]}],'source_manifest':{'adapter.py':sha(files['original.py'])}}
    raw=json.dumps(previous).encode();(tmp_path/'previous.json').write_bytes(raw)
    fixture={**previous,'previous_fixture_path':'previous.json','previous_fixture_sha256':sha(raw),
             'source_revisions':{'adapter.py':{'original_path':'original.py','candidate_path':'candidate.py',
                 'current_sha256':sha(files['candidate.py']),'proof_path':'proof.json',
                 'evidence':[{'path':name,'sha256':sha(data)} for name,data in files.items() if name!='adapter.py']}}}
    return tmp_path,fixture


def test_evidenced_adapter_preserves_original_answer_and_manifest(revision):
    root,fixture=revision;before=deepcopy(fixture)
    verify_sources(root,fixture)
    assert fixture==before


@pytest.mark.parametrize('change',('original.py','candidate.py','adapter.py','proof.json','previous.json',
                                  'answers','original-declarations','undeclared-revision'))
def test_any_unapproved_revision_or_answer_is_rejected(revision,change):
    root,fixture=revision
    if change.endswith(('.py','.json')):(root/change).write_bytes(b'changed')
    elif change=='answers':fixture['rows'][0]['expected'][0]=99.
    elif change=='original-declarations':fixture['source_manifest'].clear()
    else:fixture['source_revisions']['undeclared.py']=fixture['source_revisions']['adapter.py']
    with pytest.raises(ValueError):verify_sources(root,fixture)
