"""Queue labels and region ranges preserve authenticated complete points."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import scatter_queue_display_contract as M


@pytest.fixture(scope='module',autouse=True)
def authenticate_originals():M.check_identity()


@pytest.mark.parametrize('original',M.originals(),ids=lambda row:row['case']['key'])
def test_original_3d_queue_labels_ranges_and_complete_points(original,tmp_path):
    M.production(original,tmp_path)


@pytest.mark.parametrize('name',['source-manifest.json',M.ORIGINAL+'/run.json'])
def test_changed_original_evidence_refuses(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(M.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ');monkeypatch.setattr(M,'ARCHIVE',archive)
    with pytest.raises(ValueError):M.check_identity()


@pytest.mark.parametrize('damage',['bounds','point','label'])
def test_wrong_range_points_or_labels_cannot_pass(damage,tmp_path):
    original=next(r for r in M.originals() if r['case']['queued'] and r['case']['share_axes'] and r['case']['labels'])
    actual=deepcopy(M.production(original,tmp_path))
    if damage=='bounds':actual[0]['ylim'][1]+=1
    elif damage=='point':actual[0]['points'][0][0][1]+=1
    else:actual[0]['zlabel']='Wrong label'
    with pytest.raises(AssertionError):M.check_result(original,actual)
