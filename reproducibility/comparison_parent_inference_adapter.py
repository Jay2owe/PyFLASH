from types import SimpleNamespace
from copy import deepcopy
from contextlib import nullcontext
import warnings
import pandas as pd
from PyFLASH import stats
from PyFLASH.config import Config
from PyFLASH.aesthetics import pyflash_style_context
from reproducibility.one_way_contract import clean

class Conditions(list):pass

def production(case):
    child=case['child'];p=deepcopy(child['parameters']);names=case['names'];family=case['family']
    conditions=Conditions(SimpleNamespace(name=name) for name in names)
    experiment=SimpleNamespace(condition_list=conditions,name='frozen-parent-input')
    parameters={'comparisons':p.get('comparisons'),'ns':p.get('ns','ns'),'draw':False,'group_labels':names,
                'multiple_comparison':'One-Way','stats_test':{'one-way':'anova','welch':'welch_anova','rank':'kruskal','two-way':'two_way','model':'linear_model'}[family]}
    if family in ('one-way','welch','rank'):
        parameters.update(posthoc=p['posthoc'],posthoc_correction=p.get('posthoc_correction','auto'))
    if family=='two-way':
        factors=p.get('factors') or child.get('default_factors',['FactorA','FactorB'])
        conditions.factor=factors;experiment.factor=factors;experiment.summary=pd.DataFrame(deepcopy(child['frame']),columns=child.get('columns'))
    if family=='model':
        parameters.update(model_df=pd.DataFrame(deepcopy(child['data'])),model_group_col=p['group_col'],model_value_col=p['outcome_col'],
            covariates=p.get('covariates'),categorical_covariates=p.get('categorical_covariates'),cov_type=p.get('cov_type','HC3'),
            cov_kwds=p.get('cov_kwds'),posthoc_correction=p.get('posthoc_correction','auto'))
    previous={name:deepcopy(getattr(Config,name)) for name in ('EFFECT_SIZES','EFFECT_CI','CORRECTION_AUDIT','STATS_CACHE','POSTHOC_CORRECTION')}
    try:
        Config.EFFECT_SIZES=False;Config.EFFECT_CI=False;Config.CORRECTION_AUDIT=False;Config.STATS_CACHE=False;Config.POSTHOC_CORRECTION='auto'
        with warnings.catch_warnings(),(pyflash_style_context(**child['style']) if 'style' in child else nullcontext()):
            warnings.simplefilter('ignore')
            test,post_hoc,objects,raw=stats.multipleComparisons(experiment,
                [pd.Series(group,name=case['column']) for group in case['groups']],None,None,None,None,**parameters)
        return clean({'test':test,'post_hoc':post_hoc,'annotation_objects':objects,'results_dict':raw})
    except Exception as error:return {'error':type(error).__name__}
    finally:
        for name,value in previous.items():setattr(Config,name,value)
