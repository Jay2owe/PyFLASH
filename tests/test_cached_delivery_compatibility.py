"""Carrier delivery and source timestamps preserve canonical scientific identity."""
import hashlib,os
import pytest
from reprofig import extract_record,source_reference
from PyFLASH import report
from PyFLASH.config import Config
from test_reprofig_integration import _experiment,plot_module
from test_partial_figure_formats import format_settings

@pytest.mark.parametrize('profile',('master','public','minimal_public'))
@pytest.mark.parametrize('proof',(False,True))
def test_touching_identical_input_completes_same_figure(tmp_path,plot_module,format_settings,profile,proof):
    experiment,_,csv=_experiment(tmp_path);Config.FIGURE_PROOF=proof
    kwargs={'figure_profile':profile,'safe_columns':['group','metric','value'] if profile!='master' else None}
    plot_module.plot_group(experiment,str(tmp_path),'master',**kwargs)
    svg=tmp_path/'master.svg';original=svg.read_bytes();old=extract_record(svg)
    digest=hashlib.sha256(csv.read_bytes()).hexdigest();stat=csv.stat();os.utime(csv,ns=(stat.st_atime_ns,stat.st_mtime_ns+10_000_000_000))
    Config.SKIP_EXISTING=True;Config.FIGURE_FORMATS=('svg','png');report.collect();report.start()
    plot_module.plot_group(experiment,str(tmp_path),'master',**kwargs);new=extract_record(tmp_path/'master.png')
    assert new.figure_id==old.figure_id and svg.read_bytes()==original
    assert [t.to_dict() for t in new.data_tables]==[t.to_dict() for t in old.data_tables] and new.statistics==old.statistics
    assert hashlib.sha256(csv.read_bytes()).hexdigest()==digest
    if proof:assert new.extensions['proof']['root_sha256']==old.extensions['proof']['root_sha256']

@pytest.mark.parametrize('profile',('master','public','minimal_public'))
def test_adding_companions_preserves_existing_scientific_identity(tmp_path,plot_module,format_settings,profile):
    experiment,_,_=_experiment(tmp_path)
    kwargs={'figure_profile':profile,'safe_columns':['group','metric','value'] if profile!='master' else None}
    plot_module.plot_group(experiment,str(tmp_path),'master',**kwargs);old=extract_record(tmp_path/'master.svg')
    Config.SKIP_EXISTING=True;Config.FIGURE_FORMATS=('svg','png');report.collect();report.start()
    plot_module.plot_group(experiment,str(tmp_path),'master',write_companion_csv=True,**kwargs)
    assert extract_record(tmp_path/'master.png').figure_id==old.figure_id
    assert (tmp_path/'master-plotted-data.csv').is_file() and (tmp_path/'master-statistics.csv').is_file()

def test_timestamp_compatibility_never_mutates_caller_source_reference(tmp_path,plot_module,format_settings):
    experiment,_,csv=_experiment(tmp_path);Config.FIGURE_PROOF=True
    experiment._provenance_sources=[source_reference(csv,role='source_csv',project_root=tmp_path)]
    plot_module.plot_group(experiment,str(tmp_path),'master')
    stat=csv.stat();os.utime(csv,ns=(stat.st_atime_ns,stat.st_mtime_ns+10_000_000_000))
    current=source_reference(csv,role='source_csv',project_root=tmp_path);experiment._provenance_sources=[current]
    before=current.to_dict()
    Config.SKIP_EXISTING=True;Config.FIGURE_FORMATS=('svg','png');report.collect();report.start()
    plot_module.plot_group(experiment,str(tmp_path),'master')
    assert current.to_dict()==before


@pytest.mark.parametrize('proof',(False,True))
def test_matching_content_with_missing_optional_source_metadata_completes_old_cache(tmp_path,plot_module,format_settings,proof):
    from reprofig import SourceReference
    experiment,_,csv=_experiment(tmp_path);Config.FIGURE_PROOF=proof
    plot_module.plot_group(experiment,str(tmp_path),'master')
    old=extract_record(tmp_path/'master.svg');original=(tmp_path/'master.svg').read_bytes()
    experiment._provenance_sources=[SourceReference(role='source_csv',relative_path=csv.name,
        sha256=hashlib.sha256(csv.read_bytes()).hexdigest(),uri='https://example.org/measurements.csv')]
    Config.SKIP_EXISTING=True;Config.FIGURE_FORMATS=('svg','png');report.collect();report.start()
    plot_module.plot_group(experiment,str(tmp_path),'master');new=extract_record(tmp_path/'master.png')
    assert new.figure_id==old.figure_id and (tmp_path/'master.svg').read_bytes()==original
    assert [t.to_dict() for t in new.data_tables]==[t.to_dict() for t in old.data_tables] and new.statistics==old.statistics
    if proof:assert new.extensions['proof']['root_sha256']==old.extensions['proof']['root_sha256']
