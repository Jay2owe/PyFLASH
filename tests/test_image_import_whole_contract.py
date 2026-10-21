import copy,shutil
import pytest
from reproducibility import image_import_whole_contract as contract

CASES=contract.cases()

@pytest.fixture(scope='module',autouse=True)
def authentic_originals():contract.check_identity()

@pytest.mark.parametrize('item',CASES,ids=lambda item:item['key'])
def test_actual_public_import_complete_tables_and_ownership(item,tmp_path):
    original=copy.deepcopy(item);contract.production(item,tmp_path/'actual');assert item==original

@pytest.mark.parametrize('name',['source-files.json','original-v2/run.json','original-v3/predictions.json'])
def test_modified_image_import_evidence_refuses(name,tmp_path,monkeypatch):
    target=tmp_path/'evidence';shutil.copytree(contract.ARCHIVE,target)
    path=target/name;path.write_bytes(path.read_bytes()+b' ');monkeypatch.setattr(contract,'ARCHIVE',target)
    with pytest.raises(ValueError,match='evidence'):contract.check_identity()

@pytest.mark.parametrize('owner',['Experiment','MiniExperiment','Batch'])
def test_changed_image_prediction_refuses_before_import(owner,tmp_path):
    item=copy.deepcopy(next(row for row in CASES if row['case']['owner']==owner))
    item['expected']['table']['columns'].append('invented')
    with pytest.raises(AssertionError):contract.production(item,tmp_path/'actual')

@pytest.mark.parametrize('owner',['Experiment','MiniExperiment','Batch'])
@pytest.mark.parametrize('damage',['value','dtype','lookup','summary','stored-alias','source-data','source-summary'])
def test_damaged_actual_image_import_is_detected(owner,damage,tmp_path,monkeypatch):
    from PyFLASH.experiment import Experiment,MiniExperiment
    from PyFLASH.batch import Batch
    cls={'Experiment':Experiment,'MiniExperiment':MiniExperiment,'Batch':Batch}[owner]
    method=cls.importImages
    def damaged(self,*args,**kwargs):
        result=method(self,*args,**kwargs)
        if damage=='value':result.loc[0,'Marker']='changed'
        elif damage=='dtype':result['Marker']=result.Marker.astype('string')
        elif damage=='lookup':self.imagesDict={}
        elif damage=='summary':self._last_image_import_summary='changed'
        elif damage=='stored-alias':self.images=result.copy()
        elif damage=='source-data':self.data['invented']=object()
        else:self.summaries['SCN'].iloc[0,0]='changed'
        return result
    monkeypatch.setattr(cls,'importImages',damaged)
    item=next(row for row in CASES if row['case']['owner']==owner and row['case']['content']=='plain' and row['case']['option'] is False and row['case']['metadata']=='plain')
    with pytest.raises(AssertionError):contract.production(item,tmp_path/'actual')

def test_import_obligations_are_distinct_for_each_actual_owner():
    assert len(CASES)==len({row['key'] for row in CASES})==330
    assert {owner:len(contract.required_keys('PyFLASH.'+module+'.'+owner+'.importImages')) for module,owner in
        [('experiment','Experiment'),('experiment','MiniExperiment'),('batch','Batch')]}=={'Experiment':90,'MiniExperiment':90,'Batch':150}
    for capability in ('PyFLASH.experiment.Experiment.processData','PyFLASH.experiment.MiniExperiment.processData','PyFLASH.batch.Batch.processData','PyFLASH.image_io.read_image'):
        assert not contract.required_keys(capability)

def test_frozen_import_inputs_and_predictions_are_caller_owned():
    original=contract.cases();changed=contract.cases();changed[0]['case'].clear();changed[0]['expected'].clear()
    assert contract.cases()==original
