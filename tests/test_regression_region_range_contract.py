"""Region-specific display bounds retain original scientific artists."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import regression_region_range_contract as M
@pytest.fixture(scope='module',autouse=True)
def authenticate_originals():M.check_identity()
@pytest.mark.parametrize('original',M.originals(),ids=lambda row:row['case']['key'])
def test_original_selected_region_ranges_and_artists(original,tmp_path):M.production(original,tmp_path)
@pytest.mark.parametrize('name',['source-manifest.json',M.ORIGINAL+'/run.json'])
def test_changed_original_evidence_refuses(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(M.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ');monkeypatch.setattr(M,'ARCHIVE',archive)
    with pytest.raises(ValueError):M.check_identity()
@pytest.mark.parametrize('damage',['bounds','point','statistic'])
def test_wrong_bounds_coordinates_or_annotation_cannot_pass(damage,tmp_path):
    original=next(row for row in M.originals() if row['case']['queued'] and row['case']['share_axes'])
    actual=deepcopy(M.production(original,tmp_path))
    if damage=='bounds':actual['records'][0]['ylim'][1]+=1
    elif damage=='point':actual['records'][0]['collections'][0][0][1]+=1
    else:actual['records'][0]['texts'][0]='Wrong statistic'
    with pytest.raises(AssertionError):M.check_result(original,actual)
