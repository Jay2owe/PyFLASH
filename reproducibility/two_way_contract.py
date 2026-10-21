"""Complete two-factor reports and original full Tukey matrix answers."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
from contextlib import nullcontext
import json,hashlib,math,warnings
import pandas as pd
from PyFLASH import stats
from PyFLASH.aesthetics import pyflash_style_context
from reproducibility.one_way_contract import clean
FIXTURE=Path(__file__).with_name('fixtures')/'two_way_complete_reference.json'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']
def matrix_cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['matrix_rows']

def equal(actual,expected):
    if isinstance(expected,dict):return isinstance(actual,dict) and actual.keys()==expected.keys() and all(equal(actual[k],expected[k]) for k in expected)
    if isinstance(expected,list):return isinstance(actual,list) and len(actual)==len(expected) and all(equal(a,b) for a,b in zip(actual,expected))
    if isinstance(actual,(float,int)) and isinstance(expected,(float,int)):return math.isclose(actual,expected,rel_tol=1e-9,abs_tol=0.)
    return type(actual)==type(expected) and actual==expected

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original two-factor evidence changed: '+path)
    for field,rounds in [('rows','before_rounds'),('matrix_rows','matrix_before_rounds')]:
        original=[row for path in fixture[rounds] for row in json.loads((root/path).read_text(encoding='utf-8'))['rows']]
        if fixture[field]!=original:raise ValueError('Two-factor requests or answers differ from frozen before-correction evidence')
    return fixture

class _Conditions(list):pass

def production(case):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            if case['key'].startswith('two-way-tukey-matrix.'):
                result=stats._run_tukey(*deepcopy(case['parameters']['groups']))
                return clean({'statistics':result.statistic,'probabilities':result.pvalue})
            initial={} if case.get('empty_initial') else {'caller-note':'retained'}
            conditions=_Conditions(SimpleNamespace(name=name) for name in case['conditions']);conditions.factor=case.get('default_factors',['FactorA','FactorB'])
            frame=pd.DataFrame(deepcopy(case['frame']),columns=case.get('columns'))
            if frame.empty and not len(frame.columns):frame=pd.DataFrame(columns=['Condition','FactorA','FactorB','Marker'])
            experiment=SimpleNamespace(summary=frame,condition_list=conditions)
            with (pyflash_style_context(**case['style']) if 'style' in case else nullcontext()):
                p,labels,overall,result,method=stats.runTWA(experiment,results_dict=initial,**deepcopy(case['parameters']))
        return clean({'pvalues':p,'annotations':labels,'overall':overall,'results_dict':result,'method':method,'same_report_object':result is initial})
    except Exception as error:return {'error':type(error).__name__}
