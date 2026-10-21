from types import SimpleNamespace
from copy import deepcopy
import warnings
import pandas as pd
from PyFLASH import stats
from PyFLASH.config import Config
from reproducibility.one_way_contract import clean,equal

class Conditions(list):pass

def cases():
    parents=json.loads(Path('reproducibility/fixtures/comparison_parent_inference_reference.json').read_text(encoding='utf-8'))['rows'];result=[]
    for parent in parents:
        if parent['family']!='two-way':continue
        for variant in ('matching-summary','stale-plot-arrays','empty-plot-arrays'):
            raw=parent['groups'] if variant=='matching-summary' else [[1000.+i for i in range(len(g))] for g in parent['groups']] if variant=='stale-plot-arrays' else [[] for _ in parent['groups']]
            result.append({'key':'comparison-parent-auto-scope.'+str(len(result)),'parent':deepcopy(parent),'raw_groups':deepcopy(raw),'variant':variant,
                'parameters':{'stats_test':'auto','multiple_comparison':'Two-Way','comparisons':parent['child']['parameters'].get('comparisons'),'ns':parent['child']['parameters'].get('ns','ns'),'posthoc':'Conover','posthoc_correction':'auto'}})
    return result

def production(case):
    parent=case['parent'];child=parent['child'];p=deepcopy(case['parameters']);factors=child['parameters'].get('factors') or child.get('default_factors',['FactorA','FactorB'])
    conditions=Conditions(SimpleNamespace(name=name) for name in parent['names']);conditions.factor=factors
    experiment=SimpleNamespace(condition_list=conditions,factor=factors,name='frozen-auto-scope',summary=pd.DataFrame(child['frame'],columns=child.get('columns')))
    previous={name:deepcopy(getattr(Config,name)) for name in ('STATS_CACHE','EFFECT_SIZES','EFFECT_CI','CORRECTION_AUDIT','POSTHOC_CORRECTION')}
    try:
        Config.STATS_CACHE=False;Config.EFFECT_SIZES=False;Config.EFFECT_CI=False;Config.CORRECTION_AUDIT=False;Config.POSTHOC_CORRECTION='auto'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            value=stats.multipleComparisons(experiment,[pd.Series(g,name=parent['column']) for g in case['raw_groups']],None,None,None,None,draw=False,group_labels=parent['names'],**p)
        return clean(dict(zip(('test','post_hoc','annotation_objects','results_dict'),value)))
    except Exception as error:return {'error':type(error).__name__}
    finally:
        for name,value in previous.items():setattr(Config,name,value)
