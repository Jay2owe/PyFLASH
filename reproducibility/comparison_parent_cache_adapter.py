from copy import deepcopy
from types import SimpleNamespace
from contextlib import nullcontext
import warnings
import pandas as pd
from PyFLASH import stats
from PyFLASH.config import Config
from PyFLASH.aesthetics import pyflash_style_context
from reproducibility.one_way_contract import clean,equal

class Conditions(list):pass

def one(parent):
    child=deepcopy(parent['child']);p=child['parameters'];factors=p.get('factors') or child.get('default_factors',['FactorA','FactorB'])
    conditions=Conditions(SimpleNamespace(name=name) for name in parent['names']);conditions.factor=factors
    experiment=SimpleNamespace(condition_list=conditions,factor=factors,name='frozen-parent-cache',summary=pd.DataFrame(child['frame'],columns=child.get('columns')))
    with warnings.catch_warnings(),(pyflash_style_context(**child['style']) if 'style' in child else nullcontext()):
        warnings.simplefilter('ignore')
        answer=stats.multipleComparisons(experiment,[pd.Series(group,name=parent['column']) for group in parent['groups']],None,None,None,None,
            draw=False,group_labels=parent['names'],comparisons=p.get('comparisons'),stats_test='two_way',ns=p.get('ns','ns'),cache_key='shared-frozen-key')
    return clean(dict(zip(('test','post_hoc','annotation_objects','results_dict'),answer)))

def production(case):
    previous={name:deepcopy(getattr(Config,name)) for name in ('STATS_CACHE','EFFECT_SIZES','EFFECT_CI','CORRECTION_AUDIT','POSTHOC_CORRECTION')}
    owned=stats._stats_cache;stats._stats_cache={}
    try:
        Config.STATS_CACHE=True;Config.EFFECT_SIZES=False;Config.EFFECT_CI=False;Config.CORRECTION_AUDIT=False;Config.POSTHOC_CORRECTION='auto'
        warm=one(case['warm']);after=one(case['after'])
        return {'warm':warm,'after':after}
    except Exception as error:return {'error':type(error).__name__}
    finally:
        stats._stats_cache=owned
        for name,value in previous.items():setattr(Config,name,value)
