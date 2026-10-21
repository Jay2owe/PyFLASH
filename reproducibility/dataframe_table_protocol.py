"""Lossless controlled-fixture transport for native pandas table comparisons.

This encodes values and table/index/category metadata only. Both client
declarations and observations use this schema; no candidate normalization or
scientific estimator is imported or executed by the codec.
"""
from copy import deepcopy
from decimal import Decimal
import math
import numpy as np
import pandas as pd


def encode(value):
    if value is pd.NA:return {'@':'pd.NA'}
    if value is pd.NaT:return {'@':'pd.NaT'}
    if isinstance(value,pd.Timestamp):return {'@':'timestamp','iso':value.isoformat()}
    if isinstance(value,pd.Timedelta):return {'@':'timedelta','nanoseconds':value.value}
    if isinstance(value,Decimal):return {'@':'decimal','value':str(value)}
    if isinstance(value,np.ndarray):return {'@':'array','dtype':str(value.dtype),'shape':list(value.shape),'values':encode(value.tolist())}
    if isinstance(value,np.generic):return encode(value.item())
    if isinstance(value,float) and not math.isfinite(value):return {'@':'float','value':'nan' if math.isnan(value) else 'inf' if value>0 else '-inf'}
    if isinstance(value,tuple):return {'@':'tuple','items':[encode(v) for v in value]}
    if isinstance(value,dict):return {'@':'dict','items':[[encode(k),encode(v)] for k,v in value.items()]}
    if isinstance(value,list):return [encode(v) for v in value]
    if value is None or isinstance(value,(str,int,float,bool)):return value
    raise TypeError('Unclassified fixture scalar: '+type(value).__qualname__)


def decode(value):
    if isinstance(value,list):return [decode(v) for v in value]
    if not isinstance(value,dict):return value
    tag=value['@']
    if tag=='pd.NA':return pd.NA
    if tag=='pd.NaT':return pd.NaT
    if tag=='timestamp':return pd.Timestamp(value['iso'])
    if tag=='timedelta':return pd.Timedelta(value['nanoseconds'],unit='ns')
    if tag=='decimal':return Decimal(value['value'])
    if tag=='float':return float(value['value'])
    if tag=='tuple':return tuple(decode(v) for v in value['items'])
    if tag=='dict':return {decode(k):decode(v) for k,v in value['items']}
    if tag=='array':return np.asarray(decode(value['values']),dtype=value['dtype']).reshape(value['shape'])
    raise ValueError('Unknown controlled fixture tag: '+tag)


def dtype_record(dtype):
    result={'name':str(dtype)}
    if isinstance(dtype,pd.CategoricalDtype):result.update(categories=index_record(dtype.categories),ordered=dtype.ordered)
    if isinstance(dtype,pd.StringDtype):result['storage']=dtype.storage
    return result


def restore_dtype(record):
    if 'categories' in record:return pd.CategoricalDtype(restore_index(record['categories']),ordered=record['ordered'])
    if 'storage' in record:return pd.StringDtype(storage=record['storage'])
    return record['name']


def index_record(index):
    record={'class':type(index).__name__,'values':encode(index.tolist()),'names':encode(index.names),
            'dtype':dtype_record(index.dtype)}
    if isinstance(index,pd.RangeIndex):record.update(start=index.start,stop=index.stop,step=index.step)
    if isinstance(index,pd.DatetimeIndex) or isinstance(index,pd.TimedeltaIndex):record['frequency']=index.freqstr
    if isinstance(index,pd.MultiIndex):record.update(levels=[index_record(level) for level in index.levels],codes=[code.tolist() for code in index.codes],sortorder=index.sortorder)
    return record


def restore_index(record):
    names=decode(record['names']);name=names[0]
    if record['class']=='RangeIndex':return pd.RangeIndex(record['start'],record['stop'],record['step'],name=name)
    if record['class']=='MultiIndex':return pd.MultiIndex(levels=[restore_index(level) for level in record['levels']],codes=record['codes'],names=names,sortorder=record['sortorder'])
    values=decode(record['values'])
    if record['class']=='DatetimeIndex':return pd.DatetimeIndex(values,name=name,freq=record['frequency'],dtype=restore_dtype(record['dtype']))
    if record['class']=='TimedeltaIndex':return pd.TimedeltaIndex(values,name=name,freq=record['frequency'],dtype=restore_dtype(record['dtype']))
    return pd.Index(values,dtype=restore_dtype(record['dtype']),name=name)


def table(frame):
    return dict(protocol=1,values=encode(frame.to_numpy(dtype=object).tolist()),
                dtypes=[dtype_record(dtype) for dtype in frame.dtypes],
                index=index_record(frame.index),columns=index_record(frame.columns),attrs=encode(deepcopy(frame.attrs)))


def restore(record):
    columns=restore_index(record['columns']);index=restore_index(record['index'])
    values=decode(record['values'])
    frame=pd.DataFrame(values,index=index,columns=columns)
    for position,dtype in enumerate(record['dtypes']):
        frame.isetitem(position,frame.iloc[:,position].astype(restore_dtype(dtype)))
    frame.attrs=decode(record['attrs'])
    return frame
