import copy,os,shutil
import pytest
from reproducibility import marker_cleaning_whole_contract as contract

CASES=contract.cases()

@pytest.fixture(scope='module',autouse=True)
def authentic_native_and_original_outputs():contract.check_identity()

@pytest.mark.parametrize('item',CASES,ids=lambda item:item['key'])
def test_actual_whole_cleaning_and_input_ownership(item):
    before=copy.deepcopy(item);contract.production(item);assert item==before

@pytest.mark.parametrize('name',['source-files.json',contract.QUALIFIED+'/predictions.json',contract.ORIGINAL+'/run.json'])
def test_changed_cleaning_evidence_refuses(name,tmp_path,monkeypatch):
    target=tmp_path/'evidence'
    # Hardlinks preserve the large original records; detach the selected file
    # before modifying it, so the retained source never changes.
    shutil.copytree(contract.ARCHIVE,target,copy_function=os.link)
    path=target/name;original=path.read_bytes();path.unlink();path.write_bytes(original+b' ')
    monkeypatch.setattr(contract,'ARCHIVE',target)
    with pytest.raises(ValueError,match='evidence'):contract.check_identity()

@pytest.mark.parametrize('owner',['Antibody','cellMarker','objectMarker'])
def test_modified_cleaning_prediction_refuses_before_product(owner,monkeypatch):
    from PyFLASH import markers
    item=copy.deepcopy(next(row for row in CASES if row['case']['owner']==owner))
    item['expected']['table']['columns'].append('invented')
    def forbidden(*args,**kwargs):pytest.fail('A changed prediction reached production')
    monkeypatch.setattr(getattr(markers,owner),'clean_df',forbidden)
    with pytest.raises(AssertionError):contract.production(item)

@pytest.mark.parametrize('owner',['Antibody','cellMarker','objectMarker'])
@pytest.mark.parametrize('damage',['value','dtype','index','attrs','return','raw-input','condition-labels'])
def test_damaged_complete_cleaning_output_is_detected(owner,damage,monkeypatch):
    from PyFLASH import markers
    cls=getattr(markers,owner);method=cls.clean_df
    def damaged(self):
        raw=self.df;result=method(self)
        if damage=='value':result.iloc[0,result.columns.get_loc('AnimalName')]='changed'
        elif damage=='dtype':result['Condition']=result.Condition.astype('string')
        elif damage=='index':result.index=result.index.rename('invented')
        elif damage=='attrs':result.attrs['invented']='changed'
        elif damage=='return':return result.copy(deep=True)
        elif damage=='raw-input':raw.attrs['invented']='changed'
        else:self.experiment.condition_labels.iloc[0,1]='changed'
        return result
    monkeypatch.setattr(cls,'clean_df',damaged)
    item=next(row for row in CASES if row['case']['owner']==owner and row['case']['profile']=='positive' and row['case']['label'] and row['case']['calibration']=='legacy' and row['case']['area']=='absent')
    with pytest.raises(AssertionError):contract.production(item)

@pytest.mark.parametrize('owner',['cellMarker','objectMarker'])
def test_cleaning_cannot_mutate_roi_properties(owner,monkeypatch):
    from PyFLASH import markers
    cls=getattr(markers,owner);method=cls.clean_df
    def damaged(self):
        result=method(self);self.experiment.data['ROI Properties'].df.iloc[0,0]='changed';return result
    monkeypatch.setattr(cls,'clean_df',damaged)
    item=next(row for row in CASES if row['case']['owner']==owner and row['case']['profile']=='positive' and row['case']['area']=='exact')
    with pytest.raises(AssertionError):contract.production(item)

def test_each_actual_marker_owner_has_its_own_full_table_obligations():
    assert len(CASES)==len({item['key'] for item in CASES})==1952
    assert {owner:sum(item['case']['owner']==owner for item in CASES) for owner in ('Antibody','cellMarker','objectMarker')}=={'Antibody':32,'cellMarker':384,'objectMarker':1536}
    assert {owner:len(contract.required_keys('PyFLASH.markers.'+owner+'.clean_df')) for owner in ('Antibody','cellMarker','objectMarker')}=={'Antibody':44,'cellMarker':664,'objectMarker':2008}
    assert not contract.required_keys('PyFLASH.experiment.Experiment.processData')

def test_cleaning_cases_and_expected_tables_are_fresh_caller_owned_values():
    original=contract.cases();changed=contract.cases();changed[0]['case'].clear();changed[0]['expected'].clear()
    assert contract.cases()==original
