"""Enable intervals through the existing public parent report adapters."""
import inspect
from copy import deepcopy
from PyFLASH import report
from PyFLASH.config import Config
from reproducibility import comparison_parent_inference_adapter as inference,comparison_parent_routing_adapter as routing


def production(case):
    point=case['point_case'];module=inference if point['owner']=='inference' else routing
    source=inspect.getsource(module.production)
    assert source.count('Config.EFFECT_SIZES=False')==1 and source.count('Config.EFFECT_CI=False')==1
    source=source.replace('Config.EFFECT_SIZES=False','Config.EFFECT_SIZES=True').replace('Config.EFFECT_CI=False','Config.EFFECT_CI=True')
    namespace=dict(module.__dict__);exec(compile(source,'<public-parent-intervals-enabled>','exec'),namespace)
    previous={name:deepcopy(getattr(Config,name)) for name in ('EFFECT_CI_RESAMPLES','EFFECT_CI_RANDOM_STATE')}
    try:
        Config.EFFECT_CI_RESAMPLES=case['resamples'];Config.EFFECT_CI_RANDOM_STATE=case['seed']
        report.collect()
        return namespace['production'](point['parent'])
    finally:
        report.collect()
        for name,value in previous.items():setattr(Config,name,value)
