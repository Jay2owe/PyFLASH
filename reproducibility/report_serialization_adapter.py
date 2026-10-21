import math
from copy import deepcopy
import numpy as np
import pandas as pd
from PyFLASH import report

def decode(value):
    if isinstance(value,dict):return {key:decode(item) for key,item in value.items()}
    if isinstance(value,list):return [decode(item) for item in value]
    return {'__nan__':math.nan,'__inf__':math.inf,'__neginf__':-math.inf}.get(value,value) if isinstance(value,str) else value

class Unsupported:
    def __str__(self):return 'unsupported-value'

class BadString:
    def __str__(self):raise ValueError('No text representation')

def production(case):
    p=decode(deepcopy(case['input']));kind=p['kind']
    if kind in ('primitive','dictionary'):value=p['value']
    elif kind=='numpy-scalar':value=getattr(np,p['dtype'])(p['value'])
    elif kind=='numpy-array':value=np.asarray(p['value'])
    elif kind=='tuple':value=tuple(p['value'])
    elif kind=='index':value=pd.Index(p['value'])
    elif kind=='series':value=pd.Series(p['value'],index=p['index'])
    elif kind=='dataframe':value=pd.DataFrame(p['value'],columns=p['columns'])
    elif kind=='unsupported':value=Unsupported()
    elif kind=='bad-string':value=BadString()
    else:raise ValueError(kind)
    try:return report.coerce(value) if case['operation']=='coerce' else report.summarize_return(value)
    except Exception as error:return {'error':type(error).__name__}
