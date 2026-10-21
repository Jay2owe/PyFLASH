"""Receipts and script loaders refuse substituted consumed bytes."""
from pathlib import Path
from contextlib import contextmanager
import ast,hashlib,json
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from PyFLASH import _cache_identity,serialization,control,_replay
from PyFLASH.ui import services,workspace,loading

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'reproducibility/reference-sources/consumed-input-guards'


def inputs(tmp_path,kind):
    folder=EVIDENCE/'input-consumption-endpoints-frozen-before-v2'/('ui-pickle' if kind=='pickle' else 'ui-csv')
    original=(folder/'original-input.bin').read_bytes();changed=(folder/'substituted-input.bin').read_bytes()
    path=tmp_path/('input.pkl' if kind=='pickle' else 'input.csv');path.write_bytes(original)
    return path,original,changed


def substitute(monkeypatch,path,original,changed,kind):
    if kind=='pickle':
        reader=serialization._read_pickle
        def replace(*args,**kwargs):
            path.write_bytes(changed)
            try:return reader(*args,**kwargs)
            finally:path.write_bytes(original)
        monkeypatch.setattr(serialization,'_read_pickle',replace)
    else:
        capture=_cache_identity._capture_source
        @contextmanager
        def replace(*args,**kwargs):
            path.write_bytes(changed)
            try:
                with capture(*args,**kwargs) as captured:
                    path.write_bytes(original);yield captured
            finally:path.write_bytes(original)
        monkeypatch.setattr(_cache_identity,'_capture_source',replace)


@pytest.mark.parametrize('endpoint',('cli','services','loading'))
@pytest.mark.parametrize('kind',('pickle','csv'))
def test_replacement_during_actual_consumption_never_claims_success(tmp_path,monkeypatch,endpoint,kind):
    path,original,changed=inputs(tmp_path,kind);substitute(monkeypatch,path,original,changed,kind)
    if endpoint=='cli':
        output=tmp_path/'result'
        code=control.main(['run','PyFLASH.ui.services.summary_table','--input',str(path),
            '--params','{"display":false}','--output',str(output)])
        assert code!=0
        assert json.loads((output/'run.json').read_text(encoding='utf-8'))['ok'] is False
    else:
        with pytest.raises((ValueError,RuntimeError),match='changed'):
            if endpoint=='loading':
                loading._source.clear();loading.open_source({'path':str(path),'kind':kind})
            elif kind=='pickle':services.open_pickle(str(path))
            else:workspace.load_table(path)
    assert path.read_bytes()==original


@pytest.mark.parametrize('endpoint',('cli','services','loading'))
@pytest.mark.parametrize('kind',('pickle','csv'))
def test_ordinary_complete_tables_keep_the_frozen_compatibility_result(tmp_path,endpoint,kind):
    path,_,_=inputs(tmp_path,kind)
    key=('cli' if endpoint=='cli' else 'ui-load' if endpoint=='loading' else 'ui')+'-'+kind
    frozen=json.loads((EVIDENCE/'input-consumption-normal-tables-before/frozen-before.json').read_text(encoding='utf-8'))
    expected=next(row['result'] for row in frozen['rows'] if row['endpoint']==key)
    if endpoint=='cli':
        output=tmp_path/'result'
        assert control.main(['run','PyFLASH.ui.services.summary_table','--input',str(path),
            '--params','{"display":false}','--output',str(output)])==0
        actual=json.loads((output/'run.json').read_text(encoding='utf-8'))['result']
    else:
        if endpoint=='loading':
            loading._source.clear();batch=loading.open_source({'path':str(path),'kind':kind})
        else:batch=services.open_pickle(str(path)) if kind=='pickle' else workspace.load_table(path)
        actual=control.json_value(batch.summary)
    assert actual==expected


@pytest.mark.parametrize('kind',('pickle','csv'))
@pytest.mark.parametrize('builder',('plot','action'))
def test_actual_export_loaders_guard_consumed_bytes(tmp_path,monkeypatch,kind,builder):
    path,original,changed=inputs(tmp_path,kind)
    source={'kind':kind,'path':str(path),'sha256':hashlib.sha256(original).hexdigest()}
    if builder=='plot':
        script=workspace.equivalent_script(path,'mean_bars',{'data_cols':['Signal']},source_kind=kind);target='batch'
    else:
        script=workspace.equivalent_action_script('PyFLASH.ui.services.summary_table',{'display':False},source);target='data'
    node=next(n for n in ast.parse(script).body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id==target for t in n.targets))
    prefix='\n'.join(script.splitlines()[:node.end_lineno])+'\nresult_produced=True\n'
    unchanged={};exec(prefix,unchanged);assert unchanged['result_produced']
    substitute(monkeypatch,path,original,changed,kind);namespace={}
    with pytest.raises((ValueError,RuntimeError),match='changed'):exec(prefix,namespace)
    assert 'result_produced' not in namespace and path.read_bytes()==original


def test_deferred_verification_requires_an_expected_input_before_opening(tmp_path):
    with pytest.raises(ValueError,match='expected input hash is required'):
        serialization._load_cached_state(tmp_path/'absent.pkl',verify_current=False)


@pytest.mark.parametrize('suffix',('.csv','.csv.gz','.csv.bz2','.csv.xz','.csv.zip'))
def test_compressed_capture_retains_all_parser_values(tmp_path,suffix):
    path=tmp_path/('input'+suffix);frame=pd.DataFrame({'name':['alpha','βeta'],'value':[1.25,None]})
    frame.to_csv(path,index=False);expected=pd.read_csv(path)
    actual,digest=_cache_identity.read_csv_verified(path)
    assert_frame_equal(actual,expected);assert digest==hashlib.sha256(path.read_bytes()).hexdigest()


def test_capture_spills_and_closes_only_its_own_temporary_file(tmp_path):
    path=tmp_path/'large.csv';path.write_bytes(b'value\n'+b'1.23456789\n'*800000)
    with _cache_identity._capture_source(path) as (snapshot,digest):
        assert snapshot._rolled and snapshot.read(6)==b'value\n';owned=snapshot
    assert owned.closed and path.is_file() and digest==hashlib.sha256(path.read_bytes()).hexdigest()


def test_capture_refuses_insufficient_temporary_space(tmp_path,monkeypatch):
    import shutil
    path=tmp_path/'large.csv';path.write_bytes(b'0'*(8*1024**2+1))
    monkeypatch.setattr(shutil,'disk_usage',lambda _:type('Usage',(),{'free':1})())
    with pytest.raises(OSError,match='Insufficient temporary space'):
        with _cache_identity._capture_source(path):raise AssertionError('unexpectedly admitted')


@pytest.mark.parametrize('parameters',({'source_sha256':None},{'source_sha256':'hash','source_kind':'unknown'}))
def test_script_loader_rejects_an_uncaptured_or_unknown_source(parameters):
    with pytest.raises(ValueError):_replay.source_load_lines(target='data',source_expression='SOURCE',**parameters)
