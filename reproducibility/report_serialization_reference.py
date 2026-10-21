"""Literal JSON summaries for typed input declarations; independent of PyFLASH."""
import math


def primitive(value):
    if isinstance(value,dict):return {str(key):primitive(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):return [primitive(item) for item in value]
    if isinstance(value,float) and not math.isfinite(value):return None
    return value


def report(case):
    p=case['input'];kind=p['kind']
    if case['operation']=='summarize' and kind!='dictionary':return None
    if kind in ('primitive','numpy-scalar','numpy-array','index','dictionary'):return primitive(p['value'])
    if kind=='series':return {str(key):primitive(value) for key,value in zip(p['index'],p['value'])}
    if kind=='dataframe':
        out={'_dataframe':True,'shape':[len(p['value']),len(p['columns'])],'columns':[str(key) for key in p['columns']],
            'records':[{str(key):primitive(value) for key,value in zip(p['columns'],row)} for row in p['value'][:200]]}
        if len(p['value'])>200:out.update({'truncated':True,'omitted_rows':len(p['value'])-200})
        return out
    if kind=='tuple':return primitive(p['value'])
    if kind=='unsupported':return p['display']
    if kind=='bad-string':return None
    if kind=='figure':return p['display']
    raise ValueError(kind)
