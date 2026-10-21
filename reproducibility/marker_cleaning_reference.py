"""Full raw-marker cleaning tables, predicted before package calls by native R.

This is a functional composition contract. Native R supplies every numeric
transformation; existing native ImageJ calibration controls remain required.
No extra independent statistical-method vote is claimed.
"""
from itertools import product
from types import SimpleNamespace
import copy,contextlib,io,json,warnings
import numpy as np
import pandas as pd
from reproducibility.scientific_utility_contract import table

def categorical_table(frame):
    result=table(frame)
    result['rows']=[['NaN' if v is None or v is pd.NA else v for v in row] for row in result['rows']]
    return result

def cases():
    for owner in ('Antibody','cellMarker','objectMarker'):
        calibrations=('legacy',) if owner=='Antibody' else ('legacy','um','nm','axis')
        areas=('absent',) if owner=='Antibody' else ('absent','exact','split')
        families=('none',) if owner!='objectMarker' else ('none','legacy','cpc','both')
        for name,label,header,profile,calibration,area,family in product(('A','CD68'),(False,True),('raw','prefixed'),('positive','absent','nullable','empty'),calibrations,areas,families):
            yield dict(key='.'.join(map(str,(owner,name,label,header,profile,calibration,area,family))),owner=owner,name=name,label=label,header=header,profile=profile,calibration=calibration,area=area,family=family)

def inputs(case):
    n=case['name'];frame=pd.DataFrame({'Region':['SCN2','SCN1','SCN2','SCN3'],'Hemisphere':['L','R','L','R'],'ROI':[2,1,2,3],'Animal Name':['A1','B2','A1','C3']},index=pd.Index([9,2,9,5],name='AcquiredRow'))
    if case['owner']=='Antibody':numeric={'Mean':[1.25,2.5,3.75,5.] if case['profile']=='positive' else [1.25,np.nan,3.75,np.nan],'Median':[1.,2.,3.,4.],'Area (micron^2)':[3.,4.,5.,6.]}
    else:
        volume=[2.,3.,4.,5.] if case['profile']=='positive' else [2.,0.,np.nan,-1.]
        numeric={'Volume (micron^3)':volume,'Surface':[8.,9.,10.,11.],'Mean':[1.25,2.5,3.75,5.],'StdDev':[.5,1.,1.5,2.],'Median':[1.,2.,3.,4.],'Min':[0.,1.,2.,3.],'Max':[3.,4.,5.,6.],'IntDen':[5.,10.,15.,20.],'XM':[2.,4.,6.,8.],'YM':[3.,6.,9.,12.],'ZM':[0.,1.,2.,3.]}
        if case['calibration']!='legacy':
            numeric.update(SourcePixelWidth=[.5]*4,SourcePixelHeight=[.75]*4,SourcePixelDepth=[2.]*4)
            if case['calibration']=='nm':
                for key in ('SourcePixelWidth','SourcePixelHeight','SourcePixelDepth'):numeric[key]=[v*1000 for v in numeric[key]]
        if case['family'] in ('legacy','both'):numeric['Colocalisation with Target']=[0.,30.,50.,1.]
        if case['family'] in ('cpc','both'):numeric['CPCColoc_Target']=[1.,0.,1.,0.]
    dtype='Float64' if case['profile']=='nullable' else 'float64'
    for key,values in numeric.items():
        header=n+'_'+key if case['header']=='prefixed' and key not in ('Volume (micron^3)',) else key
        frame[header]=pd.array(values,dtype=dtype)
    if case['owner']!='Antibody' and case['calibration']!='legacy':
        if case['calibration']=='axis':
            for axis,unit in zip('XYZ',('um','nm','mm')):frame['SourcePixel'+axis+'Unit']=unit
            # Identical physical pitches represented in three different units.
            for key,factor in [('SourcePixelHeight',1000),('SourcePixelDepth',.001)]:
                key=n+'_'+key if case['header']=='prefixed' else key;frame[key]*=factor
        else:frame['SourcePixelUnit']='nm' if case['calibration']=='nm' else 'um'
    frame.attrs={'acquisition':['original',1]}
    if case['profile']=='empty':frame=frame.iloc[:0].copy()
    labels=pd.DataFrame({'Original':['A1','B2'],'Label':['Control1','Treated2']}) if case['label'] else None
    areas={}
    if case['area']!='absent':
        area=pd.DataFrame({'AnimalName':['Control1' if case['label'] else 'A1','B2','Other'],'Region':['SCN2','SCN1','SCN9']})
        if case['area']=='exact':areas={'ROI Properties':SimpleNamespace(df=area)}
        else:areas={f'ROI Properties {i}':SimpleNamespace(df=part.copy()) for i,part in enumerate((area.iloc[:1],area.iloc[1:]))}
    return frame,labels,areas

def _r(values):
    if len(values)==0:return 'numeric(0)'
    return 'c('+','.join('NA_real_' if pd.isna(v) else json.dumps(float(v)) if isinstance(v,(int,float,np.number)) else json.dumps(str(v),ensure_ascii=False) for v in values)+')'

def output_name(case,column):
    if column in ('Region','Hemisphere','ROI','Animal Name'):return column.replace(' ','')
    # This is an explicit export spelling contract, not a package helper call.
    text=column.replace('Colocalisation with ','Coloc_').replace(' ','').replace('(micron^3)','').replace('(micron^2)','')
    return text if text.startswith(case['name']+'_') else case['name']+'_'+text

def query(case):
    frame,labels,areas=inputs(case);n=case['name'];count=len(frame)
    statements=['d<-data.frame('+','.join('v'+str(i)+'='+('character(0)' if count==0 and frame[col].dtype==object else _r(frame[col].tolist())) for i,col in enumerate(frame))+',stringsAsFactors=FALSE,check.names=FALSE)', 'names(d)<-'+_r([output_name(case,col) for col in frame])]
    if case['owner']!='Antibody':
        statements+=['valid<-!is.na(d[['+json.dumps(n+'_Volume')+']]) & d[['+json.dumps(n+'_Volume')+']]>0', 'd[['+json.dumps(n+'_Count')+']]<-as.integer(valid)']
        numeric_cols=[output_name(case,col) for col in frame if col not in ('Region','Hemisphere','ROI','Animal Name')]
        statements+=['for(k in '+_r(numeric_cols)+') d[[k]][!valid]<-NA', 'raw<-d', 'names(d)<-vapply(names(d),function(k) if(grepl("Mean|StdDev|Median|Min|Max",k)) paste0(k,"IntDen") else k,character(1))']
    if labels is not None:statements+=['j<-match(d$AnimalName,c("A1","B2"));d$AnimalName[!is.na(j)]<-c("Control1","Treated2")[j[!is.na(j)]]']
    statements+=['d$Condition<-gsub("[^[:alpha:]]","",d$AnimalName)']
    if case['owner']!='Antibody':
        statements+=['d[['+json.dumps(n+'_SAtoVolumeRatio')+']]<-d[['+json.dumps(n+'_Surface')+']]/d[['+json.dumps(n+'_Volume')+']]']
        sx,sy,sz=(1/3.51998900003,1/3.51998900003,1.) if case['calibration']=='legacy' else (.5,.75,2.)
        # The legacy default is authenticated separately against Config below.
        for axis,scale in [('Y',sy),('X',sx)]+([] if case['calibration']=='legacy' else [('Z',sz)]):statements+=['d[['+json.dumps(n+'_Raw'+axis+'M')+']]<-d[['+json.dumps(n+'_'+axis+'M')+']]*'+repr(scale)]
        if case['area']!='absent':
            for axis,scale in [('X',500/1024),('Y',-800/1024)]:statements+=['d[['+json.dumps(n+'_'+axis+'M')+']]<-d[['+json.dumps(n+'_'+axis+'M')+']]*'+repr(scale)]
        if case['owner']=='objectMarker' and case['family']!='none':
            if case['family'] in ('legacy','both'):
                old=n+'_Coloc_Target';new=n+'_VolColoc_Target';statements+=['names(d)[names(d)=='+json.dumps(old)+']<-'+json.dumps(new)]
            for family in (['Vol'] if case['family']=='legacy' else ['CPC'] if case['family']=='cpc' else ['Vol','CPC']):
                raw=n+'_'+family+'Coloc_Target';dest=n+'_'+family+'ColocCountTarget';statements+=['x<-d[['+json.dumps(raw)+']]; v<-x[!is.na(x)]; b<-if(all(v %in% c(0,1))) !is.na(x)&x!=0 else !is.na(x)&x>30;d[['+json.dumps(dest)+']]<-as.integer(b)']
                if family=='Vol':statements+=['d[['+json.dumps(n+'_ColocCountTarget')+']]<-as.integer(b)','d[['+json.dumps(n+'_NonColocCountTarget')+']]<-as.integer(!b)']
    if case['owner']=='Antibody':statements+=['raw<-d']
    statements+=['pack<-function(t)c(as.character(ncol(t)),names(t),unlist(lapply(t,function(x) ifelse(is.na(x),"<missing>",as.character(x))),use.names=FALSE));c(pack(d),pack(raw))']
    return dict(key=case['key'],code='local({'+ ';'.join(statements)+'})')

def _expected_frame(case,answers,*,raw=False):
    frame,labels,areas=inputs(case);count=len(frame);columns=int(answers[0]);names=answers[1:columns+1];values=answers[columns+1:];assert len(values)==columns*count
    result={};n=case['name']
    original={output_name(case,c):str(frame[c].dtype) for c in frame}
    for i,name in enumerate(names):
        vals=values[i*count:(i+1)*count];is_text=name in ('Region','Hemisphere','AnimalName','Condition') or 'Unit' in name
        if is_text:result[name]=pd.Series([None if v=='<missing>' else v for v in vals],dtype=object)
        else:
            dtype='int8' if 'ColocCount' in name or 'NonColocCount' in name else 'int64' if name in ('ROI',n+'_Count') else original.get(name.removesuffix('IntDen') if name.endswith('IntDen') and name not in original else name,'Float64' if case['profile']=='nullable' and case['calibration']=='legacy' and 'Raw' in name else 'float64')
            if name==n+'_SAtoVolumeRatio' and case['profile']=='nullable':dtype='Float64'
            if name==n+'_VolColoc_Target' and n+'_Coloc_Target' in original:dtype=original[n+'_Coloc_Target']
            result[name]=pd.Series([np.nan if v=='<missing>' else float(v) for v in vals],dtype=dtype)
    result=pd.DataFrame(result)
    # Area merges create a new range index; otherwise the acquired index stays.
    if raw or case['area']=='absent':result.index=frame.index.copy()
    if not raw or case['owner']=='Antibody':result=result.set_index('Region')
    # Unmodified pandas 2.2.2 independently retains the left attributes on
    # these empty merges. The original all-merges-clear assumption and its
    # failed executions remain in the versioned reference evidence.
    result.attrs=copy.deepcopy(frame.attrs) if raw or case['area']=='absent' or count==0 else {}
    return categorical_table(result)

def expected(case,answers):
    count=len(inputs(case)[0]);columns=int(answers[0]);offset=1+columns*(count+1)
    return dict(table=_expected_frame(case,answers[:offset]),raw_after=_expected_frame(case,answers[offset:],raw=True),same_raw_owner=case['owner']=='Antibody')

def production(case,prediction):
    from PyFLASH import markers
    from PyFLASH.config import Config
    assert Config.PIXEL_SIZE==3.51998900003, 'The predeclared legacy density must match the public default.'
    frame,labels,areas=inputs(case);exp=SimpleNamespace(data=areas)
    if labels is not None:exp.condition_labels=labels
    owner=object.__new__(getattr(markers,case['owner']));owner.name=case['name'];owner.df=frame;owner.experiment=exp;owner.color='grey';owner.threshold=30;owner._unrelated=object();state=dict(owner.__dict__);raw_before=frame.copy(deep=True);area_before={k:v.df.copy(deep=True) for k,v in areas.items()};label_before=None if labels is None else labels.copy(deep=True);error=None;returned=None
    try:
        with contextlib.redirect_stdout(io.StringIO()),warnings.catch_warnings():warnings.simplefilter('ignore');returned=owner.clean_df()
        assert returned is owner.df
        assert owner.experiment is exp and owner.color=='grey' and owner.threshold==30 and owner._unrelated is state['_unrelated']
        for k,v in areas.items():pd.testing.assert_frame_equal(v.df,area_before[k],check_exact=True)
        if labels is not None:pd.testing.assert_frame_equal(exp.condition_labels,label_before,check_exact=True)
    except Exception as caught:error=type(caught).__name__+': '+str(caught)
    actual=dict(table=categorical_table(owner.df),raw_after=categorical_table(frame),same_raw_owner=owner.df is frame)
    # Values retain native R precision. Equality of serialization is exact for
    # headers, storage, index and metadata; numeric comparison is declared below.
    return dict(case=case,actual=actual,expected=prediction,raw_before=categorical_table(raw_before),returned_own=returned is owner.df,error=error)
