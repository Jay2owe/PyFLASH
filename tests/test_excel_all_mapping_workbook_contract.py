"""No declared map or normalization field can disappear from actual workbooks."""
from copy import deepcopy
import shutil
import pytest
from reproducibility import excel_all_mapping_workbook_contract as reference
from reproducibility import excel_coupled_contract as coupled

@pytest.mark.parametrize('row',reference.cases(),ids=lambda row:row['key'])
def test_every_declared_map_survives_the_complete_workbook_and_report(row,tmp_path):
    actual=reference.observe(row,tmp_path)
    assert actual['disagreements']==[]
    assert actual['error'] is None
    for book in actual['workbooks']:
        for worksheet in book['worksheets']:
            if 'Ventricle' in worksheet['name']:
                assert '(µm)' in worksheet['name'], 'A duplicate distance alias clipped its physical unit'

@pytest.mark.parametrize('name',['client-reference.json','source-manifest.json',
    'original-measurement-maps.json','original-client-table-helpers.py','reference-producer.py'])
def test_changed_original_all_mapping_evidence_is_refused(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(reference.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError,match='Original all-mapping workbook'):
        reference.check_identity()

def test_changed_expected_workbook_is_refused_before_creating_files(tmp_path):
    row=deepcopy(reference.cases()[0])
    row['expected_workbooks'][0]['worksheets'][0]['cells'][0][0]='candidate-approved'
    with pytest.raises(AssertionError,match='Declared coupled input/request/answer was changed'):
        reference.observe(row,tmp_path)
    assert list(tmp_path.iterdir())==[]

def test_all_declared_maps_have_isolated_executed_client_cases():
    assert len(reference.check_mapping_inventory())==96
    assert not reference.COMPLETE_CAPABILITIES

def test_future_mapping_needs_a_new_workbook_contract(monkeypatch):
    from PyFLASH import export
    monkeypatch.setitem(export.IF_NAME_MAP,'<ab>_NewScientificValue',dict(label='New',desc='New'))
    with pytest.raises(ValueError,match='mapping inventory needs extended frozen cases'):
        reference.check_mapping_inventory()

def test_changed_public_export_parameter_surface_is_refused(monkeypatch):
    from PyFLASH.batch import Batch
    monkeypatch.setattr(Batch,'export_IF_summary_excel',lambda self,unknown=None:None)
    with pytest.raises(ValueError,match='Public Excel parameter/default inventory'):
        coupled.check_parameter_inventory(reference.check_identity())

def test_original_eight_losses_remain_authenticated():
    original=reference.check_original_failures()
    assert not original['passed']
    assert original['disagreements']==8
