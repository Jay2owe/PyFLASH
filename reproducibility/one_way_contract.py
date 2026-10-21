"""Complete group reports with retained numerical answers and declared metadata."""
from pathlib import Path
from copy import deepcopy
import json,hashlib,math,warnings
from contextlib import nullcontext
from PyFLASH import stats
from PyFLASH.config import Config
from PyFLASH.aesthetics import pyflash_style_context
FIXTURE=Path(__file__).with_name('fixtures')/'one_way_complete_reference_v2.json'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def declared_report(row):
    retained=deepcopy(row);inputs=retained['expected'].get('results_dict',{}).get('_audit_inputs',{})
    if inputs.get('basis')=='self_adjusted':
        inputs['reason']=f"{retained['expected']['method']} already accounts for multiplicity; no permutation null is implemented for this method."
    return retained

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original one-way evidence changed: '+path)
    original=[declared_report(row) for path in fixture['before_rounds'] for row in json.loads((root/path).read_text(encoding='utf-8'))['rows'] if row.get('family')==fixture['family']]
    if fixture['rows']!=original:raise ValueError('One-way inputs or answers differ from frozen before-correction evidence')
    return fixture

def clean(value):
    if hasattr(value,'tolist'):value=value.tolist()
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    return str(value) if isinstance(value,float) and not math.isfinite(value) else value

def equal(actual,expected,path=()):
    if isinstance(expected,dict):return isinstance(actual,dict) and actual.keys()==expected.keys() and all(equal(actual[k],expected[k],path+(k,)) for k in expected)
    if isinstance(expected,list):return isinstance(actual,list) and len(actual)==len(expected) and all(equal(a,b,path+(i,)) for i,(a,b) in enumerate(zip(actual,expected)))
    if isinstance(actual,(float,int)) and isinstance(expected,(float,int)):
        probability='pvalues' in path or 'Posthoc-Uncorrected' in path or ('overall' in path and path[path.index('overall')+1]==1)
        if path and path[0]=='results_dict' and len(path)>2 and path[1] not in ('_audit_inputs','_group_test') and path[2]==1:probability=True
        return math.isclose(actual,expected,rel_tol=1e-9,abs_tol=0. if probability else 1e-12)
    return type(actual)==type(expected) and actual==expected

def production(case):
    previous=(Config.CORRECTION_AUDIT,Config.CORRECTION_RESAMPLES_VALUE)
    try:
        Config.CORRECTION_AUDIT=case.get('audit','cheap');Config.CORRECTION_RESAMPLES_VALUE=case.get('count',7)
        raw={'caller-note':'retained'}
        try:
            style=pyflash_style_context(**case['style']) if 'style' in case else nullcontext()
            with warnings.catch_warnings(),style:
                warnings.simplefilter('ignore')
                p,labels,overall,result,method=stats.runOWA(results_dict=raw,**deepcopy(case['parameters']))
            return clean({'pvalues':p,'annotations':labels,'overall':overall,'results_dict':result,'method':method})
        except Exception as error:return {'error':type(error).__name__}
    finally:Config.CORRECTION_AUDIT,Config.CORRECTION_RESAMPLES_VALUE=previous
