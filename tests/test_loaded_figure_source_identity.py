"""Consumed loader bytes survive later replacement in actual figure records."""
from pathlib import Path
import hashlib
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
from reprofig import extract_record
from PyFLASH import serialization,report,from_dataframe
from PyFLASH._cache_identity import read_csv_verified
from PyFLASH.config import Config
from PyFLASH.ui import workspace
from test_reprofig_integration import _experiment,plot_module

DATA=Path(__file__).resolve().parents[1]/'reproducibility/reference-sources/loaded-figure-source-identity/loaded-figure-source-frozen-before/public'

@pytest.fixture(autouse=True)
def settings(monkeypatch):
    for key,value in {'SAVE_MODE':True,'SKIP_EXISTING':False,'FIGURE_FORMATS':('svg',),
        'FIGURE_COMPANION_CSV':False,'FIGURE_PROOF':False,'FIGURE_PROOF_POLICY':{}}.items():
        monkeypatch.setattr(Config,key,value)
    report.collect();report.start()
    yield
    report.collect()
    import matplotlib.pyplot as plt
    plt.close('all')

def load(path,endpoint):
    return serialization.load_state(path,verbose=False,resave_if_migrated=False) if endpoint=='public' else serialization._load_cached_state(path,verbose=False)

@pytest.mark.parametrize('endpoint',('public','cached'))
def test_loaded_state_record_keeps_consumed_source_hash(tmp_path,plot_module,endpoint):
    path=tmp_path/'input.pkl';original=(DATA/'original-input.pkl').read_bytes();path.write_bytes(original)
    batch=load(path,endpoint);before=batch.summary.copy(deep=True);digest=hashlib.sha256(original).hexdigest()
    assert batch._pyflash_resident_input_sha256==digest
    path.write_bytes((DATA/'source.pkl').read_bytes())
    assert hashlib.sha256(path.read_bytes()).hexdigest()!=digest
    plot_module.plot_group(batch,str(tmp_path),'master')
    records=[s for s in extract_record(tmp_path/'master.svg').sources if s.role=='batch_pickle' and s.relative_path=='input.pkl']
    assert records and all(s.sha256==digest for s in records)
    assert_frame_equal(batch.summary,before,check_exact=True)

@pytest.mark.parametrize('endpoint',('public','cached'))
def test_substituted_consumption_refuses_before_returning_state(tmp_path,monkeypatch,endpoint):
    path=tmp_path/'input.pkl';original=(DATA/'original-input.pkl').read_bytes();path.write_bytes(original)
    delegate=serialization._read_pickle
    def replace(*args,**kwargs):
        path.write_bytes((DATA/'source.pkl').read_bytes())
        try:return delegate(*args,**kwargs)
        finally:path.write_bytes(original)
    monkeypatch.setattr(serialization,'_read_pickle',replace)
    with pytest.raises(RuntimeError,match='changed'):load(path,endpoint)
    assert path.read_bytes()==original

@pytest.mark.parametrize('endpoint',('workspace','verified-frame','implicit-source'))
def test_csv_record_keeps_consumed_source_hash(tmp_path,plot_module,endpoint):
    _,frame,path=_experiment(tmp_path);original=path.read_bytes();digest=hashlib.sha256(original).hexdigest()
    if endpoint=='workspace':batch=workspace.load_table(path)
    else:
        consumed,_=read_csv_verified(path)
        options={'source_paths':[path]} if endpoint=='verified-frame' else {}
        batch=from_dataframe(consumed,group_col='Condition',subject_col='AnimalName',**options)
    before=batch.summary.copy(deep=True);frame.loc[:,'value']+=100;frame.to_csv(path,index=False)
    plot_module.plot_group(batch,str(tmp_path),'master')
    records=[s for s in extract_record(tmp_path/'master.svg').sources if s.relative_path==path.name and s.role=='source_csv']
    assert records and all(s.sha256==digest for s in records)
    assert_frame_equal(batch.summary,before,check_exact=True)
