"""Actual subclass boundary calls and their independently reproduced carriers."""
from pathlib import Path
from functools import lru_cache
import copy,json
ARCHIVE=Path(__file__).with_name('reference-sources')/'inherited-roi'
MANIFEST_SHA256='19eb703b950ae4606edda63062f481cb9f0e5f66a98f9b8b86254974a9690bc4'
CAPABILITIES=frozenset('PyFLASH.markers.'+name+'.analyse_roi' for name in ('objectMarker','cellMarker'))
COMPLETE_CAPABILITIES=CAPABILITIES
CAPABILITY_PREFIXES={name:('inherited-roi.',) for name in CAPABILITIES}

@lru_cache(maxsize=8)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))
def read(name):return _read((ARCHIVE/name).resolve())
@lru_cache(maxsize=4)
def _index(path):return {item['key']:item for item in _read(path)}

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import roi_analysis_contract as original
    from reprofig import verify_proof
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256);original.check_identity()
    proof=read('run.json');items=read('predictions.json');final=read('final-proof/run.json')
    assert proof['passed'] and proof['actual_calls']==932 and proof['failed']==0 and not proof['source_changes']
    assert final['passed'] and not final['source_changes'] and len(final['rows'])==2
    expected={item['key']:item for item in original.cases()}
    assert len(items)==len(proof['rows'])==len({item['key'] for item in items})==932
    for item,row in zip(items,proof['rows'],strict=True):
        assert item['case']==expected[item['case']['key']]
        assert item['key']==row['key'] and item['capability']==row['capability']
        assert row['passed'] and row['error'] is None and item['capability'] in CAPABILITIES
    bundle=ARCHIVE/'Ventricle Analysis'
    for name in ('objectMarker','cellMarker'):
        master=bundle/('Ventricle Analysis boundary '+name+'.svg')
        report=bundle/'verification'/(master.stem+'-reproduction-report.json')
        actual=verify_proof(master,required=['figure_reproduced'],reproduction_report=report)
        assert actual.valid,actual.to_dict()

def cases():
    items=copy.deepcopy(read('predictions.json'))
    return items+[dict(key='inherited-roi.'+name+'.saved-preview-reproduction',owner=name,kind='saved',capability='PyFLASH.markers.'+name+'.analyse_roi') for name in ('objectMarker','cellMarker')]
def required_keys(capability):return {item['key'] for item in cases() if item['capability']==capability} if capability in CAPABILITIES else set()

def production(item,output=None,observation=None):
    if item.get('kind')=='saved':
        from reprofig import reproduce_figure,verify_proof
        assert item in cases()
        bundle=ARCHIVE/'Ventricle Analysis';master=bundle/('Ventricle Analysis boundary '+item['owner']+'.svg')
        output=Path(output);report_path=output/'reproduction-report.json'
        report=reproduce_figure(master,bundle_root=bundle,output_dir=output/'reproduced',report_path=report_path,execute_trusted_producer=True)
        assert report.valid,report.to_dict()
        assert verify_proof(master,required=['figure_reproduced'],reproduction_report=report_path).valid
        actual=dict(execution=report.execution_status,**report.comparisons)
        expected=dict(execution='pass',data_tables='pass',statistics='pass',display='pass')
        if observation is not None:observation.update(actual=actual,expected=expected)
        assert actual==expected;return actual
    from PyFLASH import markers
    from reproducibility import roi_analysis_contract as original
    assert item==_index((ARCHIVE/'predictions.json').resolve())[item['key']]
    return original.production(item['case'],observation,marker_class=getattr(markers,item['owner']))

def validate(output):
    from reproducibility import roi_analysis_contract as original,roi_analysis_reference as reference
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity();output=Path(output)
    native=execute_queries([reference.query(shape,points) for shape in reference.SHAPES for points in reference.POINTS],output/'native',name='inherited-roi-original-native')
    assert native['rows']==original.read('native/reference-runtime/whole-roi-analysis-results.json')['rows']
    return replay(cases(),lambda item,observed,path:production(item,path,observed),output,
        reference='Actual subclass with unchanged native R tracing, GEOS projections, high-precision storage controls and separate saved-carrier reproduction; no additional scientific implementation vote',
        family='whole-inherited-boundary-analysis-and-saved-preview',shape='all-distances-projections-traced-coordinates-admission-ownership-drawing-and-saved-carrier',rtol=1e-12,atol=1e-12)
