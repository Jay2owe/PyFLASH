import copy,shutil
import pytest
from reproducibility import mini_condition_whole_contract as contract

CASES=contract.cases()
@pytest.fixture(scope='module',autouse=True)
def authentic_originals():contract.check_identity()

@pytest.mark.parametrize('item',CASES,ids=lambda item:item['key'])
def test_actual_subclass_complete_condition_tables_and_ownership(item):
    original=copy.deepcopy(item);contract.production(item);assert item==original

@pytest.mark.parametrize('name',['observer-oracle-amendment.json','empty-original/predictions.json','private-qualified/run.json'])
def test_changed_condition_evidence_refuses(name,tmp_path,monkeypatch):
    target=tmp_path/'evidence';shutil.copytree(contract.ARCHIVE,target);path=target/name;path.write_bytes(path.read_bytes()+b' ');monkeypatch.setattr(contract,'ARCHIVE',target)
    with pytest.raises(ValueError,match='evidence'):contract.check_identity()

@pytest.mark.parametrize('kind',['explicit','fallback'])
def test_changed_condition_prediction_refuses(kind):
    item=copy.deepcopy(next(row for row in CASES if row['kind']==kind));item['expected']={'invented':'answer'}
    with pytest.raises(AssertionError):contract.production(item)

@pytest.mark.parametrize('damage',['summary-value','raw-index','raw-type','image-value','nested-images','conditions-alias','carrier-owner','empty-factor-type'])
def test_installed_condition_damage_is_detected(damage,monkeypatch):
    import pandas as pd
    from PyFLASH.experiment import MiniExperiment
    method=MiniExperiment.set_condition_list
    def damaged(self,groups):
        result=method(self,groups)
        if damage=='summary-value':self.summary.iloc[0,1]+=1
        elif damage=='raw-index':self.data['Data'].df.index.name='changed'
        elif damage=='raw-type':self.data['Data'].df['Measurement']=self.data['Data'].df.Measurement.astype('float32')
        elif damage=='image-value':self.images.iloc[0,0]='changed'
        elif damage=='nested-images':self.imagesDict['retained']['paths'].append('changed')
        elif damage=='conditions-alias':self.conditions=list(self.conditions)
        elif damage=='carrier-owner':self.data['Data'].experiment=object()
        else:self.summary['Treatment']=pd.Series(index=self.summary.index,dtype=float)
        return result
    monkeypatch.setattr(MiniExperiment,'set_condition_list',damaged)
    item=next(row for row in CASES if row['kind']=='explicit' and row['case']['layout']=='both' and row['case']['images']=='stale' and bool(row['case'].get('empty'))==(damage=='empty-factor-type'))
    with pytest.raises(AssertionError):contract.production(item)

def test_all_actual_routes_are_required_without_promoting_parents():
    keys=contract.required_keys(contract.CAPABILITY)
    assert len(CASES)==1440 and sum(row['kind']=='explicit' for row in CASES)==576
    assert {row['key'] for row in CASES}<=keys and len(keys)>1440
    for capability in ('PyFLASH.experiment.MiniExperiment.processData','PyFLASH.experiment.Experiment.set_condition_list','PyFLASH.batch.Batch.processData'):
        assert not contract.required_keys(capability)


def test_inventory_requires_every_actual_subclass_obligation():
    from reproducibility.run import inventory, _inventory_metadata, _inventory_execution_status
    keys=contract.required_keys(contract.CAPABILITY)
    assert contract.COMPLETE_CAPABILITIES=={contract.CAPABILITY}
    # Authenticate the immutable fixture catalogue once. Changing which cases
    # executed does not change its source files or scientific obligations.
    metadata=_inventory_metadata()
    original=copy.deepcopy(metadata)
    complete=_inventory_execution_status(metadata,keys)
    assert inventory(keys)==complete
    rows={row['capability']:row for row in complete}
    assert rows[contract.CAPABILITY]['status']=='validated-complete-contract'
    for prefix in ('whole-mini-condition.explicit.','whole-mini-condition.fallback.',
                   'mini-lifecycle.','mini-image-conditions.','empty-parent.','literal-factors.'):
        selected=next((key for key in sorted(keys) if key.startswith(prefix)),None)
        assert selected is not None, (prefix,sorted(keys))
        rows={row['capability']:row for row in _inventory_execution_status(metadata,keys-{selected})}
        assert rows[contract.CAPABILITY]['status']!='validated-complete-contract'
    assert rows['PyFLASH.experiment.MiniExperiment.processData']['status']!='validated-complete-contract'
    assert metadata==original
