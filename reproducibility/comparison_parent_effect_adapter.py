import inspect
from reproducibility import comparison_parent_inference_adapter as inference,comparison_parent_routing_adapter as routing

def production(case):
    module=inference if case['owner']=='inference' else routing
    source=inspect.getsource(module.production);needle='Config.EFFECT_SIZES=False';assert source.count(needle)==1
    namespace=dict(module.__dict__);exec(compile(source.replace(needle,'Config.EFFECT_SIZES=True'),'<public-parent-effects-enabled>','exec'),namespace)
    return namespace['production'](case['parent'])
