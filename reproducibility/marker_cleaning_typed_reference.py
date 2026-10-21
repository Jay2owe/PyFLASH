"""Native-R full-table reference retained from the executed original producer.

All query, input and reconstruction functions below are verbatim. The original
48 typed/domain failures remain failures; no numeric allowances change.
"""
from itertools import product
import copy,json,math
import numpy as np
import pandas as pd
from reproducibility import marker_cleaning_reference as ref
ORIGINAL_INPUTS=ref.inputs
UNITS={'micron':1.,'microns':1.,'micrometre':1.,'micrometres':1.,'micrometer':1.,'micrometers':1.,'um':1.,'\u00b5m':1.,'\u03bcm':1.,'nm':.001,'nanometre':.001,'nanometer':.001,'mm':1000.,'millimetre':1000.,'millimeter':1000.}

DENSITIES={'zero':0.,'negative':-1.,'nan':float('nan'),'infinite':float('inf'),'missing':None,'text':'bad','overflow':5e-324,'tiny-output':1e308}

def inputs(item,*,numeric_reference=False):
    case=item['case'];frame,labels,areas=ORIGINAL_INPUTS(case);prefix=case['name']+'_' if case['header']=='prefixed' else ''
    if item['kind']=='complex' and not numeric_reference:
        column=prefix+item['field'];values=np.array(frame[column],dtype=complex)+item['imaginary']*1j
        frame[column]=pd.Series(values.astype(object) if item['storage']=='object' else values,index=frame.index)
    elif item['kind']=='unit':
        factor=UNITS[item['unit']]
        for field in ('SourcePixelWidth','SourcePixelHeight','SourcePixelDepth'):frame[prefix+field]/=factor
        frame['SourcePixelUnit']=item['unit']
        if item['axis_units']:
            for axis in 'XYZ':frame['SourcePixel'+axis+'Unit']=item['unit']
    return frame,labels,areas

def encode(value):
    if isinstance(value,complex):return dict(real=encode(float(value.real)),imag=encode(float(value.imag)))
    if isinstance(value,np.generic):return encode(value.item())
    if isinstance(value,(list,tuple)):return [encode(v) for v in value]
    if isinstance(value,dict):return {key:encode(v) for key,v in value.items()}
    if isinstance(value,float) and not math.isfinite(value):return 'NaN' if math.isnan(value) else 'Inf' if value>0 else '-Inf'
    return value

def is_refused(item):return item['kind']=='complex' and item['imaginary']!=0 or item['kind']=='density' and item['density']!='tiny-output'

def query(item):
    case=item['case'];ref.inputs=lambda ignored:inputs(item,numeric_reference=True)
    try:row=ref.query(case)
    finally:ref.inputs=ORIGINAL_INPUTS
    code=row['code']
    if is_refused(item):
        needle='d[["'+case['name']+'_RawYM"]]';assert code.count(needle)==1
        code=code[:code.index(needle)]+code[code.index('pack<-function'):]
        if case['owner']=='objectMarker':
            needle='pack<-function';old=case['name']+'_Coloc_Target';new=case['name']+'_VolColoc_Target'
            code=code.replace(needle,'names(d)[names(d)=='+json.dumps(old)+']<-'+json.dumps(new)+';'+needle,1)
    if item['kind']=='density' and not is_refused(item):
        old=repr(1/3.51998900003);assert code.count(old)==2;code=code.replace(old,'1e-308')
    if item['kind']=='complex':
        frame,_,_=inputs(item,numeric_reference=True);prefix=case['name']+'_' if case['header']=='prefixed' else ''
        values=[float(v) for v in frame[prefix+item['field']]]
        typed='typed<-complex(real='+ref._r(values)+',imaginary=rep('+str(item['imaginary'])+','+str(len(values))+'));'
        code=code.replace('pack<-function',typed+'pack<-function',1)
        needle='c(pack(d),pack(raw))';assert code.count(needle)==1
        code=code.replace(needle,'c(pack(d),pack(raw),Re(typed),Im(typed),Re(typed)/3.51998900003,Im(typed)/3.51998900003)')
    row.update(key=case['key'],code=code);return row

def expected(item,values):
    case=item['case'];values=list(values);parts=None
    if item['kind']=='complex':parts=[float(v) for v in values[-16:]];values=values[:-16]
    ref.inputs=lambda ignored:inputs(item,numeric_reference=True)
    try:answer=ref.expected(case,values)
    finally:ref.inputs=ORIGINAL_INPUTS
    if is_refused(item):
        frame,_,_=inputs(item,numeric_reference=True);table=answer['table'];regions=table['index']
        table['columns'].insert(0,'Region');table['dtypes'].insert(0,'object');table['rows']=[[region,*row] for region,row in zip(regions,table['rows'],strict=True)]
        table.update(index=list(frame.index),index_name=frame.index.name,attrs=copy.deepcopy(frame.attrs))
    if parts is not None:
        column=case['name']+'_'+item['field'];dtype='object' if item['storage']=='object' else 'complex128'
        for table in (answer['table'],answer['raw_after']):
            position=table['columns'].index(column);table['dtypes'][position]=dtype
            for i,row in enumerate(table['rows']):row[position]=dict(real=parts[i],imag=parts[4+i])
        if not is_refused(item) and case['calibration']=='legacy' and item['field'] in ('XM','YM'):
            table=answer['table'];position=table['columns'].index(case['name']+'_Raw'+item['field']);table['dtypes'][position]=dtype
            for i,row in enumerate(table['rows']):row[position]=dict(real=parts[8+i],imag=parts[12+i])
    return answer

def cases():
    result=[]
    for owner,header in product(('cellMarker','objectMarker'),('raw','prefixed')):
        base=dict(owner=owner,name='A',label=False,header=header,profile='positive',area='absent',family='both' if owner=='objectMarker' else 'none')
        for calibration,field,storage,imaginary in product(('legacy','um'),('XM','YM','ZM','SourcePixelWidth','SourcePixelHeight','SourcePixelDepth'),('complex128','object'),(0,1)):
            if calibration=='legacy' and field.startswith('Source'):continue
            case=dict(base,calibration=calibration,key='.'.join(map(str,(owner,header,'complex',calibration,field,storage,imaginary))))
            result.append(dict(kind='complex',case=case,field=field,storage=storage,imaginary=imaginary))
        for density in DENSITIES:
            case=dict(base,calibration='legacy',key='.'.join((owner,header,'density',density)))
            result.append(dict(kind='density',case=case,density=density))
        for unit,axis_units in product(UNITS,(False,True)):
            case=dict(base,calibration='um',key='.'.join(map(str,(owner,header,'unit',unit,axis_units))))
            result.append(dict(kind='unit',case=case,unit=unit,axis_units=axis_units))
    return result
