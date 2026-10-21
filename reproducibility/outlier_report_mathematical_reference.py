"""Independent complete report grouping and quantile/MAD composition."""
import math,json
from reproducibility.rout_mathematical_reference import reference as rout
OUT=['group','column','row','value','iqr_outlier','mad_outlier','modified_z','iqr_lower','iqr_upper',
     'rout_outlier','rout_p','rout_threshold','rout_t','rout_center','rout_rsdr']
rout_cache={}

def finite(value):
    try:value=float(value)
    except (TypeError,ValueError):return None
    return value if math.isfinite(value) else None

def quantile(values,probability):
    values=sorted(values);pos=(len(values)-1)*probability;i=int(math.floor(pos));f=pos-i
    return values[i]*(1-f)+values[min(i+1,len(values)-1)]*f

def reference(case):
    index=case['input']['index'];data=case['input']['data'];options=case['parameters']
    columns=options['columns'];columns=[columns] if isinstance(columns,str) else columns
    methods=options['methods'];methods=[methods.lower()] if isinstance(methods,str) else [m.lower() for m in (methods or [])]
    if any(col not in data for col in columns):return {'error_type':'ValueError'}
    labels=case['input']['groups'];labels=['all']*len(index) if labels is None else labels
    unique=[]
    for label in labels:
        if label is not None and label not in unique:unique.append(label)
    rows=[]
    for group in unique:
        for column in columns:
            pairs=[(idx,value) for idx,label,raw in zip(index,labels,data[column]) if label==group and (value:=finite(raw)) is not None]
            arr=[value for idx,value in pairs];n=len(arr)
            use_iqr='iqr' in methods and n>=options.get('min_rows',4)
            use_mad='mad' in methods and n>=options.get('min_rows',4)
            use_rout='rout' in methods and n>=3
            if not(use_iqr or use_mad or use_rout):continue
            median=quantile(arr,.5);mad=quantile([abs(v-median) for v in arr],.5)
            if use_iqr:
                first,third=quantile(arr,.25),quantile(arr,.75);span=third-first
                lower=first-options.get('iqr_k',1.5)*span;upper=third+options.get('iqr_k',1.5)*span
            else:lower=upper=None
            if use_rout:
                p={'values':arr,'q':options.get('rout_q',1.)};identity=json.dumps(p)
                if identity not in rout_cache:rout_cache[identity]=rout({'parameters':p})
                flags,probabilities,thresholds,tt,center,rsdr=rout_cache[identity]
            else:flags=[False]*n;probabilities=thresholds=tt=[None]*n;center=rsdr=None
            for i,(idx,value) in enumerate(pairs):
                iqr=bool(use_iqr and (value<lower or value>upper))
                z=.6745*(value-median)/mad if use_mad and mad>0 else None
                mz=bool(z is not None and abs(z)>options.get('mad_threshold',3.5))
                if not(iqr or mz or flags[i]):continue
                rows.append([str(group),column,idx,value,iqr,mz,z,lower,upper,flags[i],probabilities[i],thresholds[i],tt[i],center,rsdr])
    return {'columns':OUT,'rows':rows}
