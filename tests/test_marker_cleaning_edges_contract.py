import copy,shutil
import pytest
from reproducibility import marker_cleaning_edges_contract as contract

CASES=contract.cases()

@pytest.fixture(scope='module',autouse=True)
def authentic_native_edges():contract.check_identity()

@pytest.mark.parametrize('row',CASES,ids=lambda row:row['key'])
def test_actual_cleaner_typed_domain_and_dimensional_routes(row):
    before=copy.deepcopy(row);contract.production(row);assert row==before

@pytest.mark.parametrize('name',['source-files.json',contract.TYPED+'/predictions.json',contract.DIMENSIONAL+'/run.json'])
def test_modified_edge_evidence_refuses(name,tmp_path,monkeypatch):
    target=tmp_path/'evidence';shutil.copytree(contract.ARCHIVE,target)
    path=target/name;path.write_bytes(path.read_bytes()+b' ');monkeypatch.setattr(contract,'ARCHIVE',target)
    with pytest.raises(ValueError,match='evidence'):contract.check_identity()

@pytest.mark.parametrize('kind',['typed','dimensional'])
def test_modified_edge_prediction_never_reaches_product(kind,monkeypatch):
    from PyFLASH import markers
    row=copy.deepcopy(next(row for row in CASES if row['kind']==kind));row['expected']['table']['columns'].append('invented')
    def forbidden(self):pytest.fail('Changed prediction reached production')
    for owner in ('cellMarker','objectMarker'):monkeypatch.setattr(getattr(markers,owner),'clean_df',forbidden)
    with pytest.raises(AssertionError):contract.production(row)

@pytest.mark.parametrize('owner',['cellMarker','objectMarker'])
@pytest.mark.parametrize('damage',['coordinate','dtype','index','attrs','return','roi','unrelated'])
def test_dimensional_cleaner_damage_is_detected(owner,damage,monkeypatch):
    from PyFLASH import markers
    cls=getattr(markers,owner);method=cls.clean_df
    def damaged(self):
        result=method(self)
        if damage=='coordinate':result.iloc[0,result.columns.get_loc('A_RawXM')]+=1
        elif damage=='dtype':result['Condition']=result.Condition.astype('string')
        elif damage=='index':result.index=result.index.rename('changed')
        elif damage=='attrs':result.attrs['changed']=True
        elif damage=='return':return result.copy(deep=True)
        elif damage=='roi':self.experiment.data['ROI Properties'].df.iloc[0,0]='changed'
        else:self._unrelated=object()
        return result
    monkeypatch.setattr(cls,'clean_df',damaged)
    row=next(row for row in CASES if row['kind']=='dimensional' and row['input']['case']['owner']==owner and row['input']['case']['profile']=='positive' and row['input']['case']['route']=='two-dimensional-region-only')
    with pytest.raises(AssertionError):contract.production(row)

@pytest.mark.parametrize('owner',['cellMarker','objectMarker'])
@pytest.mark.parametrize('damage',['swallow','partial-value','raw-attrs','wrong-error','unrelated','insert-coordinate'])
def test_typed_refusal_cannot_hide_partial_mutation_or_error(owner,damage,monkeypatch):
    from PyFLASH import markers
    cls=getattr(markers,owner);method=cls.clean_df
    def damaged(self):
        raw=self.df
        try:return method(self)
        except ValueError:
            if damage=='swallow':return self.df
            if damage=='partial-value':self.df.iloc[0,self.df.columns.get_loc('AnimalName')]='changed'
            elif damage=='raw-attrs':raw.attrs['changed']=True
            elif damage=='wrong-error':raise TypeError('wrong refusal type')
            elif damage=='unrelated':self._unrelated=object()
            else:self.df['A_RawXM']=0.
            raise
    monkeypatch.setattr(cls,'clean_df',damaged)
    row=next(row for row in CASES if row['kind']=='typed' and row['input']['input']['case']['owner']==owner and row['input']['input']['kind']=='density' and row['input']['input']['density']=='zero')
    with pytest.raises(AssertionError):contract.production(row)

@pytest.mark.parametrize('owner',['cellMarker','objectMarker'])
def test_failed_edge_comparison_restores_global_configuration(owner,monkeypatch):
    from PyFLASH import markers
    from PyFLASH.config import Config
    original=(Config.PIXEL_SIZE,Config.THRESHOLD)
    def failure(self):raise RuntimeError('controlled failure')
    monkeypatch.setattr(getattr(markers,owner),'clean_df',failure)
    row=next(row for row in CASES if row['kind']=='typed' and row['input']['input']['case']['owner']==owner and row['input']['input']['kind']=='density')
    with pytest.raises(RuntimeError,match='controlled failure'):contract.production(row)
    assert (Config.PIXEL_SIZE,Config.THRESHOLD)==original

def test_edge_obligations_belong_only_to_actual_cleaning_owners():
    assert len(CASES)==len({row['key'] for row in CASES})==344
    assert {owner:len(contract.required_keys('PyFLASH.markers.'+owner+'.clean_df')) for owner in ('Antibody','cellMarker','objectMarker')}=={'Antibody':0,'cellMarker':172,'objectMarker':172}
    assert not contract.required_keys('PyFLASH.experiment.Experiment.processData') and not contract.COMPLETE_CAPABILITIES

def test_edge_inputs_and_predictions_are_fresh_caller_owned_values():
    original=contract.cases();changed=contract.cases();changed[0]['input'].clear();changed[0]['expected'].clear();assert contract.cases()==original
