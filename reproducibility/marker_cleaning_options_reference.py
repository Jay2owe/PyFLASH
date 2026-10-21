"""Supplementary native-R full-table inputs and literal refusal policy.

The refusal expressions and reconstruction below are retained verbatim from
the executed producer. Configuration expressions change only declared pixel
density and threshold constants in the already-qualified native reference.
No additional independent statistical-method vote is inferred.
"""
import copy
from reproducibility import marker_cleaning_reference as ref
original_inputs=ref.inputs
def inputs(case):
    frame,labels,areas=original_inputs(case);name=case['name'];bad=case['refusal']
    col=lambda key:name+'_'+key if case['header']=='prefixed' else key
    if bad=='partial':frame=frame.drop(columns=col('SourcePixelDepth'))
    elif bad=='missing-units':frame=frame.drop(columns='SourcePixelUnit')
    elif bad=='zero':frame[col('SourcePixelWidth')]=0.
    elif bad=='negative':frame[col('SourcePixelDepth')]=-1.
    elif bad=='unit':frame['SourcePixelUnit']='pixels'
    elif bad=='axis-unit':frame['SourcePixelZUnit']='unknown'
    elif bad=='pitch-overflow':frame[col('SourcePixelWidth')]=1e308;frame['SourcePixelUnit']='mm'
    elif bad=='pitch-underflow':frame[col('SourcePixelWidth')]=5e-324;frame['SourcePixelUnit']='nm'
    elif bad=='coordinate-overflow':frame[col('XM')]=1e308;frame[col('SourcePixelWidth')]=2.
    else:raise AssertionError(bad)
    return frame,labels,areas

def reference_query(case):
    ref.inputs=inputs
    try:row=ref.query(case)
    finally:ref.inputs=original_inputs
    code=row['code'];needle='d[["'+case['name']+'_RawYM"]]'
    assert code.count(needle)==1
    prefix=code[:code.index(needle)]
    suffix=code[code.index('pack<-function'):]
    row['code']=prefix+suffix
    return row

def expected(case,values):
    ref.inputs=inputs
    try:answer=ref.expected(case,values)
    finally:ref.inputs=original_inputs
    # Failure precedes coordinate insertion, ROI merge and set_index. Restore
    # the literal acquired row index and Region column to the native table.
    frame,_,_=inputs(case);table=answer['table'];regions=table['index']
    table['columns'].insert(0,'Region');table['dtypes'].insert(0,'object')
    table['rows']=[[region,*row] for region,row in zip(regions,table['rows'],strict=True)]
    table['index']=list(frame.index);table['index_name']=frame.index.name;table['attrs']=copy.deepcopy(frame.attrs)
    return answer

def configured_query(item):
    case=item['case'];row=ref.query(case);old=repr(1/3.51998900003)
    if case['owner']!='Antibody':
        assert row['code'].count(old)==2
        row['code']=row['code'].replace(old,repr(1/item['density']))
    if case['owner']=='objectMarker':
        assert row['code'].count('x>30')==2
        row['code']=row['code'].replace('x>30','x>'+repr(item['threshold']))
    return row
