"""Exact subject identifiers through actual constructors; whole options remain open."""
from pathlib import Path
import hashlib
import json
ARCHIVE=Path(__file__).with_name('reference-sources')/'dataframe-identifiers'
MANIFEST_SHA256='e0287f494b9058f3c0163c7fe8e6b83dba1b63796e6d97bc37b7dbad47989825'
CAPABILITY_PREFIXES={'PyFLASH.dataframe.from_dataframe':('dataframe-identifier.from_dataframe.',),'PyFLASH.dataframe.coerce_dataframe_input':('dataframe-identifier.coerce_dataframe_input.',)}
COMPLETE_CAPABILITIES=frozenset()

def check_identity():
    manifest=ARCHIVE/'source-manifest.json'
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=MANIFEST_SHA256:raise ValueError('Identifier evidence manifest changed.')
    for name,digest in json.loads(manifest.read_text(encoding='utf-8')).items():
        if hashlib.sha256((ARCHIVE/name).read_bytes()).hexdigest()!=digest:raise ValueError('Identifier evidence changed: '+name)

def cases():return json.loads((ARCHIVE/'dataframe-identifiers-functional-before-20261007-v3/frozen-before.json').read_text(encoding='utf-8'))['rows']

def production(row,output):
    import numpy as np
    import pandas as pd
    from PyFLASH import dataframe
    kind=row['input']['kind'];value=row['input']['value']
    supplied=value if kind=='text' else int(value) if kind=='integer' else np.int64(value) if kind=='int64' else np.float32(value) if kind=='float32' else float(value) if kind=='float' else None
    frame=pd.DataFrame({'Condition':['A'],'Subject':pd.Series([supplied],dtype=object),'Measured':[2.5]});frame.index=pd.Index([17],name='original');frame.attrs={'identity':'literal input'};snapshot=frame.copy(deep=True)
    output=Path(output)
    result=getattr(dataframe,row['api'])(frame,subject_col='Subject',fig_path=output/'unused-figures',data_path=output/'unused-data')
    actual={'AnimalName':result.summary['AnimalName'].tolist(),'Condition':result.summary['Condition'].tolist(),'Measured':result.summary['Measured'].tolist(),'index':result.summary.index.tolist(),'index_name':result.summary.index.name,'attrs':result.summary.attrs,'region_dict':result.region_dict,'input_name_preserved':result.summary['Subject'].iloc[0] is frame['Subject'].iloc[0] if len(result.summary) else True}
    pd.testing.assert_frame_equal(frame,snapshot,check_exact=True);assert frame.attrs==snapshot.attrs
    return actual

def validate(output):
    from reproducibility.normality_association_validation import comparison
    from PyFLASH._persistence import write_json
    check_identity();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    comparisons=[];paired=[]
    for row in cases():
        actual=None;error=None
        try:actual=production(row,output)
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        agrees=error is None and actual==row['expected']
        scope='Exact identifier and complete retained measurement/index/attribute/region fields at normalization through actual public constructors. Functional identity controls; no scientific vote or complete constructor-option certificate.'
        comparisons.append(comparison(row['key'],'Literal exact identifier and retained-input contract','dataframe-identifiers',actual,row['expected'],agrees,True,scope,0,0))
        paired.append({'key':row['key'],'actual':actual,'expected':row['expected'],'error':error,'agrees':agrees,'scope':scope})
        write_json(output/'dataframe-identifiers-paired.json',{'rows':paired})
    return comparisons
