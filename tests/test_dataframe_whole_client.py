"""Complete returned state is checked against predeclared client requests."""
import inspect
import shutil
import pytest
from reproducibility import dataframe_whole_contract as reference


@pytest.mark.parametrize('row',reference.cases(),ids=lambda row:row['key'])
def test_predeclared_complete_constructor_state(row,tmp_path):
    actual,_=reference.production(row,tmp_path)
    assert actual==row['expected']


@pytest.mark.parametrize('name',['client-reference.json','reference-producer.py','source-manifest.json','table-transport.py','native-table-input-factory.py'])
def test_changed_client_answers_or_producer_are_refused(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(reference.ARCHIVE,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError,match='Constructor client'):
        reference.check_identity()


@pytest.mark.parametrize('name',['first/run.json','corrected-observer/run.json','observer-amendment.json','source-manifest.json'])
def test_original_failed_probe_evidence_cannot_change(name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(reference.ORIGINAL_PROBES,archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ORIGINAL_PROBES',archive)
    with pytest.raises(ValueError,match='Original constructor probe'):
        reference.check_original_failures()


@pytest.mark.parametrize('owner',['DataFrameExperiment','coerce_dataframe_input'])
def test_an_added_public_parameter_requires_new_contract_coverage(owner,monkeypatch):
    from PyFLASH import dataframe
    target=getattr(dataframe,owner)
    signature=inspect.signature(target)
    extra=inspect.Parameter('new_public_setting',inspect.Parameter.KEYWORD_ONLY,default=None)
    monkeypatch.setattr(target,'__signature__',signature.replace(parameters=[*signature.parameters.values(),extra]),raising=False)
    with pytest.raises(ValueError,match='Unclassified'):
        reference.assert_parameter_inventory()


def test_an_added_public_class_field_requires_new_contract_coverage(monkeypatch):
    from PyFLASH.dataframe import DataFrameExperiment
    monkeypatch.setattr(DataFrameExperiment,'new_public_metadata','unclassified',raising=False)
    with pytest.raises(ValueError,match='Unclassified constructor class fields'):
        reference.assert_parameter_inventory()


@pytest.mark.parametrize('owner',['TYPED_ORIGINAL_PROBES','OPTIONS_ORIGINAL_PROBES','GROUP_ORIGINAL_PROBES','FINAL_ORIGINAL_PROBES'])
@pytest.mark.parametrize('name',['run.json','dataframe.py','dataframe-whole-client-paired.json','source-manifest.json'])
def test_typed_and_coupled_original_failures_cannot_change(owner,name,tmp_path,monkeypatch):
    archive=tmp_path/'archive';shutil.copytree(getattr(reference,owner),archive)
    path=archive/name;path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,owner,archive)
    with pytest.raises(ValueError,match='Original (typed constructor|constructor option|constructor group|final constructor) probe'):
        reference.check_original_failures()


@pytest.mark.parametrize('changed',['measurement','metadata','unexpected-field','index-type','class-field','category-order'])
def test_changed_returned_values_or_fields_are_detected(changed,tmp_path):
    label='typed-ordered-category' if changed=='category-order' else 'defaults'
    row=next(row for row in reference.cases() if row['key']=='dataframe-whole.from_dataframe.'+label)
    actual,_=reference.production(row,tmp_path)
    if changed=='measurement':actual['state']['summary']['values'][0][2]=123.0
    elif changed=='metadata':actual['state']['condition_list']['groups'][0]['label']='Changed label'
    elif changed=='index-type':actual['state']['summary']['index']['dtype']['name']='uint64'
    elif changed=='class-field':actual['state']['data_layout']='changed'
    elif changed=='category-order':actual['state']['summary']['dtypes'][2]['ordered']=False
    else:actual['state']['unexpected_field']=True
    assert actual!=row['expected']


def test_all_original_client_answers_remain_unchanged_in_the_typed_declarations():
    import json
    import math
    from reproducibility import dataframe_table_protocol as transport
    original=json.loads((reference.ARCHIVE.parent/'v2/client-reference.json').read_text(encoding='utf-8'))
    current={row['key']:row for row in reference.cases()}
    def legacy(value):
        if isinstance(value,dict) and value.get('protocol')==1:
            frame=transport.restore(value)
            return dict(split=legacy(frame.to_dict(orient='split')),dtypes=[str(dtype) for dtype in frame.dtypes],
                        index_name=frame.index.name,attrs=legacy(frame.attrs))
        if isinstance(value,dict):return {key:legacy(item) for key,item in value.items() if key!='data_layout'}
        if isinstance(value,(list,tuple)):return [legacy(item) for item in value]
        if isinstance(value,float) and math.isnan(value):return {'nonfinite':'nan'}
        return value
    assert len(original['rows'])==251
    for row in original['rows']:
        assert legacy(current[row['key']]['expected'])==row['expected'],row['key']


@pytest.mark.parametrize('borrowed',[False,True])
def test_attached_metadata_is_copied_and_preserved_after_a_join(borrowed,tmp_path):
    import pandas as pd
    from PyFLASH.dataframe import from_dataframe
    summary=pd.DataFrame({'AnimalName':['one','two'],'Condition':['A','B'],'Measurement':[1.,2.]})
    marker=pd.DataFrame({'AnimalName':['two','one'],'CellMeasure':[5.,7.]})
    if not borrowed:marker['Condition']=['B','A']
    marker.attrs={'source':{'annotations':['original'],'units':'cells'}}
    before=marker.copy(deep=True)
    result=from_dataframe(summary,file_path=tmp_path,data={'Cells':marker})
    assert result.data['Cells'].df.attrs==marker.attrs
    result.data['Cells'].df.attrs['source']['annotations'].append('output-only')
    pd.testing.assert_frame_equal(marker,before,check_exact=True)
    assert marker.attrs==before.attrs
