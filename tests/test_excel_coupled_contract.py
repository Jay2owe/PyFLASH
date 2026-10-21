"""Full metadata/provenance and simultaneous measurement/filter export controls."""
from copy import deepcopy
import hashlib
import json
import shutil
import pytest
from reproducibility import excel_coupled_contract as reference


@pytest.mark.parametrize('row',reference.cases(),ids=lambda row:row['key'])
def test_native_coupled_client_preserves_every_workbook_and_input(row,tmp_path):
    observed=reference.observe(row,tmp_path)
    assert observed['inputs_unchanged'] and observed['source_macros_unchanged']
    assert not observed['disagreements'],observed['disagreements']


def test_all_seven_public_export_parameter_and_default_surfaces_are_frozen():
    assert len(reference.check_parameter_inventory())==7


@pytest.mark.parametrize('name',['client-reference.json','reference-producer.py','accepted-label-declarations.py','source-manifest.json'])
def test_changed_coupled_reference_is_refused(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(reference.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError,match='Original coupled Excel client'):reference.check_identity()


def test_changed_declared_measurement_is_refused_before_files_or_calls(tmp_path):
    row=deepcopy(reference.cases()[0])
    row['design']['summaries']['SCN']['rows'][0][-1]=999
    with pytest.raises(AssertionError,match='Declared coupled input/request/answer was changed'):
        reference.observe(row,tmp_path)
    assert not list(tmp_path.iterdir())


def test_new_child_option_requires_extended_reference_cases(monkeypatch):
    from PyFLASH.batch import Batch
    original=Batch.export_IF_summary_excel
    def changed(self,save_path=None,roi_base=None,*,include=None,exclude=None,save_name='IF_Summary',new_scientific_option=False):
        return original(self,save_path,roi_base,include=include,exclude=exclude,save_name=save_name)
    monkeypatch.setattr(Batch,'export_IF_summary_excel',changed)
    with pytest.raises(ValueError,match='parameter/default inventory'):reference.check_parameter_inventory()


def test_changed_child_default_requires_explicit_reference_amendment(monkeypatch):
    from PyFLASH.batch import Batch
    original=Batch.export_extended_data_excel
    def changed(self,save_path=None,verbose=False,use_tqdm=False,roi_base=None,*,include=None,exclude=None,save_name='IF_Extended'):
        return original(self,save_path,verbose,use_tqdm,roi_base,include=include,exclude=exclude,save_name=save_name)
    monkeypatch.setattr(Batch,'export_extended_data_excel',changed)
    with pytest.raises(ValueError,match='parameter/default inventory'):reference.check_parameter_inventory()


@pytest.mark.parametrize('version,manifest_digest',[
    ('v1','5e7d7381a3508f93aa255bb5514a218311735aeb3dbf95a31ca02cef48539688'),
    ('v2','db6ef5f0cca32542c28290deda040267fbcb12db0c56abd19a85469085e02f64'),
])
def test_original_observer_and_actual_export_failures_remain_authenticated(version,manifest_digest):
    archive=reference.ARCHIVE.parent/'original-probes'/version
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest(archive/'source-manifest.json')==manifest_digest
    for name,expected in json.loads((archive/'source-manifest.json').read_text(encoding='utf-8')).items():
        assert digest(archive/name)==expected,name
    ledger=json.loads((archive/'excel-coupled-paired.json').read_text(encoding='utf-8'))
    assert len(ledger['rows'])==672
    if version=='v1':
        classification=json.loads((archive/'observer-failure-classification.json').read_text(encoding='utf-8'))
        assert classification['candidate_export_calls_executed']==0
        assert all(row['observed'] is None and row['error'] for row in ledger['rows'])
    else:
        assert all(row['error'] is None for row in ledger['rows'])
        assert sum(not row['agrees'] for row in ledger['rows'])==368
        assert all(row['observed']['inputs_unchanged'] and row['observed']['source_macros_unchanged'] for row in ledger['rows'])
