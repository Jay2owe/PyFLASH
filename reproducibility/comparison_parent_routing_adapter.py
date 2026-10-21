from types import SimpleNamespace
from copy import deepcopy
import warnings
from PyFLASH import stats
from PyFLASH.config import Config
from reproducibility.one_way_contract import clean

class Conditions(list):pass

def production(case):
    conditions=Conditions(SimpleNamespace(name=name) for name in case['names'])
    if 'condition_comparisons' in case:conditions.comparisons=case['condition_comparisons']
    experiment=SimpleNamespace(condition_list=conditions,name='frozen-parent-routing')
    previous={name:deepcopy(getattr(Config,name)) for name in ('EFFECT_SIZES','EFFECT_CI','CORRECTION_AUDIT','STATS_CACHE','POSTHOC_CORRECTION')}
    try:
        Config.EFFECT_SIZES=False;Config.EFFECT_CI=False;Config.CORRECTION_AUDIT=False;Config.STATS_CACHE=False;Config.POSTHOC_CORRECTION='auto'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            parameters=deepcopy(case['parameters'])
            test,post_hoc,objects,raw=stats.multipleComparisons(experiment,deepcopy(case['groups']),None,None,None,None,
                draw=False,group_labels=case['names'],**parameters)
        return clean({'test':test,'post_hoc':post_hoc,'annotation_objects':objects,'results_dict':raw})
    except Exception as error:return {'error':type(error).__name__}
    finally:
        for name,value in previous.items():setattr(Config,name,value)
