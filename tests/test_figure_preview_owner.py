"""Auxiliary previews use the established writer without scientific side effects."""
from io import BytesIO
import pytest
from PIL import Image
from reprofig import extract_record
from PyFLASH import report,utils
from PyFLASH.config import Config,config_snapshot
from test_reprofig_integration import _experiment,plot_module


@pytest.fixture
def preview_settings(monkeypatch):
    for name,value in {'SAVE_MODE':True,'SKIP_EXISTING':False,
            'FIGURE_FORMATS':('svg',),'FIGURE_COMPANION_CSV':False,
            'FIGURE_PROOF':False,'FIGURE_PROOF_POLICY':{},
            'FIGURE_WIDTH':None,'FIGURE_HEIGHT':None}.items():
        monkeypatch.setattr(Config,name,value)
    report.collect();report.start()
    yield
    report.collect()


@pytest.mark.parametrize('mode',('saved','no-write','skip-existing','public','minimal_public','proof','minimal-public-proof'))
def test_preview_keeps_evidence_pixels_and_observer_ownership(tmp_path,monkeypatch,plot_module,preview_settings,mode):
    experiment,_,_=_experiment(tmp_path)
    delegate=utils.save_fig;figures=[];calls=[];events=[];written=[]
    def observe(*args,**kwargs):
        calls.append(kwargs.get('preview_of'))
        result=delegate(*args,**kwargs)
        if kwargs.get('preview_of') is None:figures.append(args[0])
        return result
    monkeypatch.setattr(utils,'save_fig',observe)
    def before(*args):events.append(args[1])
    def after(*args):written.append(args[0])
    utils.register_fig_save_observer(before);utils.register_fig_saved_observer(after)
    try:
        if mode=='skip-existing':plot_module.plot_group(experiment,str(tmp_path),'master')
        Config.SAVE_MODE=mode!='no-write';Config.SKIP_EXISTING=mode=='skip-existing'
        Config.FIGURE_PROOF=mode in ('proof','minimal-public-proof');events.clear();written.clear();calls.clear()
        profile='minimal_public' if mode=='minimal-public-proof' else mode if mode in ('public','minimal_public') else 'master'
        plot_module.plot_group(experiment,str(tmp_path),'master',figure_profile=profile,
                              safe_columns=['group','metric','value'] if profile!='master' else None)
        figure=figures[-1];master=tmp_path/'master.svg'
        master_bytes=master.read_bytes() if master.exists() else None
        saved=extract_record(master) if master_bytes else None
        expected_image=BytesIO()
        figure.savefig(expected_image,format='png',dpi=150,bbox_inches='tight',facecolor='white')
        with Image.open(expected_image) as image:expected_pixels=image.convert('RGBA').tobytes()
        size=list(figure.get_size_inches())
        # Delivery dimensions from a primary carrier must not resize its preview.
        monkeypatch.setattr(Config,'FIGURE_WIDTH',.75);monkeypatch.setattr(Config,'FIGURE_HEIGHT',.75)
        settings=config_snapshot()
        result=utils.save_fig(figure,tmp_path/'previews','preview',preview_of=str(master),
                             figure_formats=('png',),dpi=150,save_bbox='tight',
                             transparent=False,write_companion_csv=False,skip_existing=False,
                             verbose=False,proof_policy={})
        preview=extract_record(result)
        assert preview.data_tables and preview.distribution_profile==profile
        if saved:
            if mode=='skip-existing':assert preview.figure_id!=saved.figure_id
            else:assert preview.figure_id==saved.figure_id
            assert [t.to_dict() for t in preview.data_tables]==[t.to_dict() for t in saved.data_tables]
            assert preview.statistics==saved.statistics
            assert master.read_bytes()==master_bytes
        if mode in ('proof','minimal-public-proof'):
            root=saved.extensions['proof']['root_sha256']
            assert root and preview.extensions['proof']['root_sha256']==root
        with Image.open(result) as image:
            assert image.convert('RGBA').tobytes()==expected_pixels
            assert abs(image.info['dpi'][0]-150)<1
        assert calls==[None,str(master)] and len(events)==1
        assert len(written)==(0 if mode in ('no-write','skip-existing') else 1)
        assert list(figure.get_size_inches())==size and config_snapshot()==settings
    finally:
        utils.unregister_fig_save_observer(before);utils.unregister_fig_saved_observer(after)


def test_corrupt_primary_evidence_refuses_without_replacing_the_preview(tmp_path,plot_module,preview_settings,monkeypatch):
    experiment,_,_=_experiment(tmp_path);delegate=utils.save_fig;figures=[]
    def capture(*args,**kwargs):figures.append(args[0]);return delegate(*args,**kwargs)
    monkeypatch.setattr(utils,'save_fig',capture)
    plot_module.plot_group(experiment,str(tmp_path),'master')
    master=tmp_path/'master.svg';master.write_bytes(b'corrupt scientific evidence')
    preview=tmp_path/'preview.png';preview.write_bytes(b'preserved previous preview')
    with pytest.raises(Exception):
        delegate(figures[-1],tmp_path,'preview',preview_of=master,figure_formats=('png',),verbose=False)
    assert preview.read_bytes()==b'preserved previous preview'


def test_minimal_preview_uses_published_embedding_api_when_rederivation_is_unavailable(tmp_path,plot_module,preview_settings,monkeypatch):
    experiment,_,_=_experiment(tmp_path);delegate=utils.save_fig;figures=[]
    def capture(*args,**kwargs):figures.append(args[0]);return delegate(*args,**kwargs)
    monkeypatch.setattr(utils,'save_fig',capture)
    plot_module.plot_group(experiment,str(tmp_path),'master',figure_profile='minimal_public',
                           safe_columns=['group','metric','value'])
    master=tmp_path/'master.svg';saved=extract_record(master)
    import reprofig.artifacts
    previous=reprofig.artifacts.derive_profile
    def older_derivation(record,*args,**kwargs):
        if record.distribution_profile=='minimal_public':raise ValueError('no embedded contents')
        return previous(record,*args,**kwargs)
    monkeypatch.setattr(reprofig.artifacts,'derive_profile',older_derivation)
    result=delegate(figures[-1],tmp_path,'preview',preview_of=master,
                    figure_formats=('png',),dpi=150,skip_existing=False,verbose=False)
    preview=extract_record(result)
    assert preview.figure_id==saved.figure_id and preview.distribution_profile=='minimal_public'
    assert [t.to_dict() for t in preview.data_tables]==[t.to_dict() for t in saved.data_tables]
    assert preview.statistics==saved.statistics


@pytest.mark.parametrize('mode',('skip-existing','no-write'))
def test_changed_data_preview_never_inherits_old_file_evidence(tmp_path,monkeypatch,plot_module,preview_settings,mode):
    import pandas as pd
    from io import StringIO
    experiment,_,_=_experiment(tmp_path);delegate=utils.save_fig;figures=[]
    def capture(*args,**kwargs):
        result=delegate(*args,**kwargs)
        if kwargs.get('preview_of') is None:figures.append(args[0])
        return result
    monkeypatch.setattr(utils,'save_fig',capture)
    plot_module.plot_group(experiment,str(tmp_path),'master')
    master=tmp_path/'master.svg';original=master.read_bytes();saved=extract_record(master)
    experiment.summary.loc[:,'value']+=100
    Config.SAVE_MODE=mode!='no-write';Config.SKIP_EXISTING=mode=='skip-existing'
    report.collect();report.start()
    plot_module.plot_group(experiment,str(tmp_path),'master')
    result=delegate(figures[-1],tmp_path,'preview',preview_of=master,
                    figure_formats=('png',),dpi=150,skip_existing=False,verbose=False)
    preview=extract_record(result)
    table=pd.read_csv(StringIO(preview.data_tables[0].contents))
    assert sorted(table['value'])==[101.,101.5,102.,104.,104.5,105.]
    assert preview.figure_id!=saved.figure_id and master.read_bytes()==original


def test_preview_refuses_a_primary_carrier_changed_after_the_current_render(tmp_path,monkeypatch,plot_module,preview_settings):
    experiment,_,_=_experiment(tmp_path);delegate=utils.save_fig;figures=[]
    def capture(*args,**kwargs):figures.append(args[0]);return delegate(*args,**kwargs)
    monkeypatch.setattr(utils,'save_fig',capture)
    plot_module.plot_group(experiment,str(tmp_path),'master');master=tmp_path/'master.svg'
    master.write_bytes(master.read_bytes()+b'\n<!-- changed after the render -->\n')
    preview=tmp_path/'preview.png';preview.write_bytes(b'previous preview')
    with pytest.raises(ValueError,match='changed after this render'):
        delegate(figures[-1],tmp_path,'preview',preview_of=master,figure_formats=('png',),verbose=False)
    assert preview.read_bytes()==b'previous preview'


import os
from PyFLASH import provenance

@pytest.mark.parametrize('mode',('skip-existing','no-write'))
def test_unsaved_evidence_preserves_pending_primary_ownership(tmp_path,monkeypatch,plot_module,preview_settings,mode):
    experiment,_,_=_experiment(tmp_path)
    if mode=='skip-existing':plot_module.plot_group(experiment,str(tmp_path),'master')
    key=os.path.normcase(str(tmp_path/'master.svg'));previous={'owner':'previous pending write'}
    monkeypatch.setitem(provenance._PENDING,key,previous)
    Config.SAVE_MODE=mode!='no-write';Config.SKIP_EXISTING=mode=='skip-existing'
    plot_module.plot_group(experiment,str(tmp_path),'master')
    assert provenance._PENDING[key] is previous


@pytest.mark.parametrize('occupied',(False,True))
def test_pending_scope_restores_owner_after_failed_capture(tmp_path,monkeypatch,occupied):
    path=tmp_path/'primary.svg';key=os.path.normcase(str(path));previous={'owner':'previous'}
    if occupied:monkeypatch.setitem(provenance._PENDING,key,previous)
    else:monkeypatch.delitem(provenance._PENDING,key,raising=False)
    with pytest.raises(RuntimeError,match='failed capture'):
        with provenance._unstaged_save(path):
            provenance._PENDING[key]={'owner':'new capture'}
            raise RuntimeError('failed capture')
    if occupied:assert provenance._PENDING[key] is previous
    else:assert key not in provenance._PENDING
