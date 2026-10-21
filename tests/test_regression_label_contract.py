"""Literal regression labels may change; original scientific artists may not."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import regression_label_contract as M
@pytest.fixture(scope='module',autouse=True)
def authenticate_originals():M.check_identity()
@pytest.mark.parametrize('original',M.originals(),ids=lambda row:row['case']['key'])
def test_original_finished_regression_labels_and_artists(original,tmp_path):M.production(original,tmp_path)
@pytest.mark.parametrize('name',['source-manifest.json',M.ORIGINAL+'/run.json'])
def test_changed_original_labels_or_artists_refuse(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(M.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ');monkeypatch.setattr(M,'ARCHIVE',archive)
    with pytest.raises(ValueError):M.check_identity()
@pytest.mark.parametrize('damage',['label','curve','statistic'])
def test_wrong_label_coordinate_or_annotation_fails(damage,tmp_path):
    original=M.originals()[0];actual=deepcopy(M.production(original,tmp_path))
    if damage=='label':actual['records'][0]['xlabel']='Wrong unit'
    elif damage=='curve':actual['records'][0]['lines'][0]['y'][0]+=1
    else:actual['records'][0]['texts'][0]['text']='Wrong statistic'
    with pytest.raises(AssertionError):M.check_result(original,actual)
