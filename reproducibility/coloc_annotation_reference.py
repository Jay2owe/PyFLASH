"""Explicit functional table-annotation obligations, authored before repair.

These are literal data-policy controls, not an independent scientific method.
Column names and zero/one answers are declared here without the package parser.
"""
from copy import deepcopy
PROFILES=(
 ('nullable-boolean','boolean',[False,True,None],90,[0,1,0],None),
 ('nullable-integer','Int64',[0,2,None],1,[0,1,0],None),
 ('nullable-float','Float64',[0.,2.,None],1,[0,1,0],None),
 ('float-boundary','float64',[-1.,0.,1.,1.5,None],1,[0,0,0,1,0],None),
 ('numeric-string-threshold','float64',[0.,2.,None],'1',[0,1,0],None),
 ('missing-threshold','float64',[0.,2.,None],None,None,'TypeError'),
 ('invalid-threshold','float64',[0.,2.,None],'unknown',None,'ValueError'),
 ('nan-threshold','float64',[0.,2.,None],'nan',[0,0,0],None),
 ('positive-infinite-threshold','float64',[0.,2.,None],'inf',[0,0,0],None),
 ('negative-infinite-threshold','float64',[0.,2.,None],'-inf',[1,1,0],None),
 ('binary-with-missing','float64',[0.,1.,None],90,[0,1,0],None),
 ('binary-ignores-invalid-threshold','Int64',[0,1,None],None,[0,1,0],None),
 ('zero-only','Int64',[0,0,None],'unknown',[0,0,0],None),
 ('one-only','Int64',[1,1,None],'unknown',[1,1,0],None),
 ('all-missing','Float64',[None,None,None],None,[0,0,0],None),
 ('missing-boolean','boolean',[None,None,None],None,[0,0,0],None),
 ('text-policy','object',[' yes ','NO','True','false','Y','n','T','f','junk','',None],None,[1,0,1,0,1,0,1,0,0,0,0],None),
 ('mixed-numeric-text','object',['0','2',None,'True','yes'],1,[0,1,0,0,0],None),
 ('numeric-binary-mixed-text','object',['1','0','yes',None],999,[1,0,0,0],None),
 ('negative-value','float64',[-2.,-1.,0.,None],-2,[0,1,1,0],None),
 ('empty','object',[],None,[],None),
)
OWNERS=('Antibody','objectMarker','cellMarker')
NAMES=('M','M.+[x]','微胶质_A','7')
STYLES=('volume','cpc','legacy-separated','legacy-joined','both-families','last-alias-wins','no-raw')

def cases():
    rows=[]
    for owner in OWNERS:
      for name_index,name in enumerate(NAMES):
       for style in STYLES:
        for index,profile in enumerate(PROFILES):
         key,dtype,values,threshold,expected,error=profile
         rows.append(dict(key=f'whole-coloc.{owner}.name-{name_index}.{style}.{key}',owner=owner,name=name,style=style,dtype=dtype,values=deepcopy(values),threshold=threshold,expected=deepcopy(expected),error=error,index_kind=('duplicate','string','multi')[index%3],repeat=error is None))
    fresh=[]
    for item in rows:
        if item['name']==NAMES[0]:
            item=deepcopy(item);item['key']+='.fresh-columns';item['fresh_columns']=True;fresh.append(item)
    return rows+fresh

def frame_for(item):
    import pandas as pd
    name=item['name'];style=item['style'];count=len(item['values'])
    if item['index_kind']=='duplicate':index=pd.Index([i//2 for i in range(count)],name='original')
    elif item['index_kind']=='string':index=pd.Index(['row-'+str(i) for i in range(count)],name='original')
    else:index=pd.MultiIndex.from_tuples([(i//2,str(i)) for i in range(count)],names=['subject','row'])
    raw=pd.array(item['values'],dtype=item['dtype']);columns={name+'_Volume':pd.array([13.]*count,dtype='Float64'),'unrelated':pd.array(['keep']*count,dtype='string')}
    generated={};expected=item['expected'];error=item['error']
    def volume(column,answer):
        columns[column]=raw.copy()
        generated[name+'_VolColocCountTarget_β']=answer
        generated[name+'_ColocCountTarget_β']=answer
        generated[name+'_NonColocCountTarget_β']=None if answer is None else [1-v for v in answer]
    if style in ('volume','both-families'):volume(name+'_VolColoc_Target_β',expected)
    elif style=='legacy-separated':volume(name+'_Coloc_Target_β',expected)
    elif style=='legacy-joined':volume(name+'_ColocTarget_β',expected)
    elif style=='last-alias-wins':
        volume(name+'_VolColoc_Target_β',expected)
        columns[name+'_Coloc_Target_β']=pd.array([1]*count,dtype='int64')
        answer=[1]*count;generated={name+'_VolColocCountTarget_β':answer,name+'_ColocCountTarget_β':answer,name+'_NonColocCountTarget_β':[0]*count}
    if style in ('cpc','both-families'):
        columns[name+'_CPCColoc_Target_β']=raw.copy();generated[name+'_CPCColocCountTarget_β']=expected
    if style=='no-raw':generated={};error=None
    # Existing outputs must be replaced in place, with no raw-column changes.
    if not item.get('fresh_columns'):
        for column in generated:columns[column]=pd.array([77]*count,dtype='int16')
    columns[name+'_ColocCountIgnored']=pd.array([42]*count,dtype='int16')
    columns['different_VolColoc_Target_β']=pd.array([1]*count,dtype='int8')
    frame=pd.DataFrame(columns,index=index);frame.attrs={'preserved':['metadata',1]}
    return frame,generated,error

def production(item,observation=None):
    import contextlib,io
    import pandas as pd
    from PyFLASH import markers
    marker=object.__new__(getattr(markers,item['owner']));marker.name=item['name'];marker.df,generated,error=frame_for(item)
    frame=marker.df;before=frame.copy(deep=True);sentinel=object();marker.unrelated=sentinel;marker.threshold='preserve-owner-setting'
    observed_error=None;result=None
    try:
        with contextlib.redirect_stdout(io.StringIO()):result=marker.addColocData(item['threshold'])
    except Exception as exc:observed_error=type(exc).__name__
    if observation is not None:observation.update(actual={'error':observed_error,'counts':{name:frame[name].tolist() if name in frame else None for name in generated}},expected={'error':error,'counts':generated})
    assert observed_error==error,(item['key'],observed_error,error)
    assert marker.df is frame and marker.unrelated is sentinel and marker.threshold=='preserve-owner-setting'
    assert frame.attrs==before.attrs
    if error:
        pd.testing.assert_frame_equal(frame,before,check_exact=True);return
    assert result is frame
    expected_columns=list(before.columns)+[name for name in generated if name not in before]
    assert list(frame.columns)==expected_columns
    pd.testing.assert_frame_equal(frame.drop(columns=list(generated)),before.drop(columns=list(generated),errors='ignore'),check_exact=True)
    for name,answer in generated.items():
        assert frame[name].tolist()==answer,(item['key'],name,frame[name].tolist(),answer)
        assert str(frame[name].dtype)=='int8'
    if item['repeat']:
        prior=frame.copy(deep=True)
        with contextlib.redirect_stdout(io.StringIO()):again=marker.addColocData(item['threshold'])
        assert again is frame;pd.testing.assert_frame_equal(frame,prior,check_exact=True)
