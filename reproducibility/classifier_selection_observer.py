"""Observe actual estimator configurations; no model fitting."""
import builtins
def observe(function,preset,selection,available):
    original_import=builtins.__import__
    def imports(name,*args,**kwargs):
        if name=='mord' and not available:raise ModuleNotFoundError("No module named 'mord'")
        return original_import(name,*args,**kwargs)
    builtins.__import__=imports
    try:
        configs=function(preset=preset,model_families=selection,random_state=17)
        counts={}
        rows=[]
        for row in configs:
            family=row['family'];counts[family]=counts.get(family,0)+1
            estimator=row['estimator']
            rows.append({'family':family,'name':row['name'],'params':row['params'],
                'estimator_type':type(estimator).__module__+'.'+type(estimator).__qualname__,
                'estimator_params':estimator.get_params()})
        return {'families':counts},rows
    except Exception as exc:
        info={'error':type(exc).__name__}
        if isinstance(exc,ImportError) and 'classification' in str(exc):info['fix_extra']='classification'
        return info,{'message':str(exc)}
    finally:builtins.__import__=original_import
