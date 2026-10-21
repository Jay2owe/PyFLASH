import copy,shutil
import pytest
from reproducibility import marker_cleaning_options_contract as contract

CASES=contract.cases()

@pytest.fixture(scope='module',autouse=True)
def authentic_native_options():contract.check_identity()

@pytest.mark.parametrize('row',CASES,ids=lambda row:row['key'])
def test_actual_cleaner_configuration_constructor_and_refusal(row):
    before=copy.deepcopy(row);contract.production(row);assert row==before

@pytest.mark.parametrize('name',['source-files.json',contract.CONFIGURED+'/predictions.json',contract.REFUSED+'/run.json'])
def test_modified_option_evidence_refuses(name,tmp_path,monkeypatch):
    target=tmp_path/'evidence';shutil.copytree(contract.ARCHIVE,target)
    path=target/name;path.write_bytes(path.read_bytes()+b' ');monkeypatch.setattr(contract,'ARCHIVE',target)
    with pytest.raises(ValueError,match='evidence'):contract.check_identity()

@pytest.mark.parametrize('kind',['configured','refused'])
def test_modified_option_prediction_never_reaches_product(kind,monkeypatch):
    from PyFLASH import markers
    row=copy.deepcopy(next(row for row in CASES if row['kind']==kind))
    row['expected']['table']['columns'].append('invented')
    def forbidden(self):pytest.fail('Changed prediction reached production')
    monkeypatch.setattr(getattr(markers,row['input']['case']['owner']),'clean_df',forbidden)
    with pytest.raises(AssertionError):contract.production(row)

DAMAGE=[(owner,damage) for owner in ('Antibody','cellMarker','objectMarker')
        for damage in ('value','dtype','index','attrs','return','roi','labels','unrelated')
        if owner!='Antibody' or damage!='roi']

@pytest.mark.parametrize('owner,damage',DAMAGE)
def test_nondefault_cleaner_damage_is_detected(owner,damage,monkeypatch):
    from PyFLASH import markers
    cls=getattr(markers,owner);method=cls.clean_df
    def damaged(self):
        result=method(self)
        if damage=='value':result.iloc[0,result.columns.get_loc('AnimalName')]='changed'
        elif damage=='dtype':result['Condition']=result.Condition.astype('string')
        elif damage=='index':result.index=result.index.rename('changed')
        elif damage=='attrs':result.attrs['changed']=True
        elif damage=='return':return result.copy(deep=True)
        elif damage=='roi':self.experiment.data['ROI Properties'].df.iloc[0,0]='changed'
        elif damage=='labels':self.experiment.condition_labels.iloc[0,1]='changed'
        else:self._unrelated=object()
        return result
    monkeypatch.setattr(cls,'clean_df',damaged)
    row=next(row for row in CASES if row['kind']=='configured' and row['input']['mode']=='direct'
             and row['input']['density']==2.5 and row['input']['case']['owner']==owner
             and row['input']['case']['label'] and row['input']['case']['area']==('absent' if owner=='Antibody' else 'exact'))
    with pytest.raises(AssertionError):contract.production(row)

@pytest.mark.parametrize('owner',['cellMarker','objectMarker'])
@pytest.mark.parametrize('damage',['swallow','partial-value','raw-attrs','labels'])
def test_refusal_cannot_hide_partial_or_caller_mutation(owner,damage,monkeypatch):
    from PyFLASH import markers
    cls=getattr(markers,owner);method=cls.clean_df
    def damaged(self):
        raw=self.df
        try:return method(self)
        except ValueError:
            if damage=='swallow':return self.df
            if damage=='partial-value':self.df.iloc[0,self.df.columns.get_loc('AnimalName')]='changed'
            elif damage=='raw-attrs':raw.attrs['changed']=True
            else:self.experiment.condition_labels.iloc[0,1]='changed'
            raise
    monkeypatch.setattr(cls,'clean_df',damaged)
    row=next(row for row in CASES if row['kind']=='refused' and row['input']['case']['owner']==owner and row['input']['case']['label'])
    with pytest.raises(AssertionError):contract.production(row)

@pytest.mark.parametrize('owner',['Antibody','cellMarker','objectMarker'])
def test_failed_comparison_restores_global_configuration(owner,monkeypatch):
    from PyFLASH import markers
    from PyFLASH.config import Config
    original=(Config.PIXEL_SIZE,Config.THRESHOLD)
    def failure(self):raise RuntimeError('controlled failure')
    monkeypatch.setattr(getattr(markers,owner),'clean_df',failure)
    row=next(row for row in CASES if row['kind']=='configured' and row['input']['case']['owner']==owner)
    with pytest.raises(RuntimeError,match='controlled failure'):contract.production(row)
    assert (Config.PIXEL_SIZE,Config.THRESHOLD)==original

def test_option_obligations_belong_only_to_actual_cleaning_owners():
    assert len(CASES)==len({row['key'] for row in CASES})==396
    assert {owner:len(contract.required_keys('PyFLASH.markers.'+owner+'.clean_df')) for owner in ('Antibody','cellMarker','objectMarker')}=={'Antibody':12,'cellMarker':96,'objectMarker':288}
    assert not contract.required_keys('PyFLASH.experiment.Experiment.processData')

def test_option_inputs_and_predictions_are_fresh_caller_owned_values():
    original=contract.cases();changed=contract.cases();changed[0]['input'].clear();changed[0]['expected'].clear()
    assert contract.cases()==original
