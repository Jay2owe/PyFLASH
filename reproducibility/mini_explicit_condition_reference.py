"""Native R categorical tables for explicit flat-experiment factor ownership.

These are functional categorical comparisons, not a statistical-method vote.
Inputs and native predictions are frozen before any actual package calls.
"""
from itertools import product
from types import SimpleNamespace
import copy,contextlib,io,json
import numpy as np
import pandas as pd
from reproducibility.scientific_utility_contract import table

def categorical_table(frame):
    """A missing label has one meaning across None, NaN and nullable text."""
    result=table(frame)
    result['rows']=[['NaN' if value is None or value is pd.NA else value for value in row] for row in result['rows']]
    return result

FACTORS=('Treatment','Sex','Protocol')
LEVELS=(('Control','Treated'),('Female','Male'),('Light','Dark'))
LAYOUTS=('summary','raw','both','partial','split','summary-attribute','other-region','indexed-summary')

def cases():
    for count,layout,profile,images,condition in product((1,2,3),LAYOUTS,('canonical','aliases','unknown-missing'),('absent','empty','stale'),(False,True)):
        yield dict(key='.'.join(map(str,(count,layout,profile,images,condition))),factors=count,layout=layout,profile=profile,images=images,condition=condition)
    for count,layout,images,condition in product((1,2,3),LAYOUTS,('absent','empty','stale'),(False,True)):
        yield dict(key='.'.join(map(str,(count,layout,'canonical',images,condition,'empty'))),factors=count,layout=layout,profile='canonical',images=images,condition=condition,empty=True)

def mappings(case):
    return {factor:{'001':LEVELS[j][0],'002':LEVELS[j][1]} for j,factor in enumerate(FACTORS[:case['factors']])} if case['profile']=='aliases' else {}

def inputs(case):
    factors=FACTORS[:case['factors']]
    def frame(selected,offset):
        out=pd.DataFrame({'AnimalName':['A1','B2','C3','D4','A1'],'Measurement':[1.25+offset,2.5+offset,3.75+offset,5+offset,6.25+offset]},index=pd.Index(['r4','r2','r1','r3','r4'],name='RetainedRow'))
        if case['condition']:out['Condition']='stale'
        for factor in selected:
            j=FACTORS.index(factor);a,b=LEVELS[j]
            vals=[a,b,a,b,a] if case['profile']=='canonical' else [' 001 ','002',a.lower(),b.upper(),'001'] if case['profile']=='aliases' else [a,b,'Unknown'+str(j),None,a]
            out[factor]=pd.Series(vals,index=out.index,dtype=object)
        out.attrs={'units':'authored','nested':{'retain':[1,2]}}
        return out
    layout=case['layout'];summary_factors=factors if layout not in ('raw','partial','split') else factors[:1] if layout in ('partial','split') else ()
    raw_factors=factors if layout in ('raw','both','partial','indexed-summary') else factors[1:] if layout=='split' else ()
    summary=frame(summary_factors,0)
    if layout=='indexed-summary':summary=summary.set_index('AnimalName')
    region='OC' if layout=='other-region' else 'SCN'
    summaries={region:summary};raw={'Data':frame(raw_factors,10),'Other':frame((),20)}
    images=None if case['images']=='absent' else pd.DataFrame({'AnimalName':['B2','A1','Missing5','A1'],'Marker':['M']*4,'Condition':['stale']*4,**{f:['stale']*4 for f in factors}})
    if case['images']=='empty':images=images.iloc[:0].copy()
    if images is not None:images.attrs={'pixels':'unchanged','nested':{'retain':[3]}}
    if case.get('empty'):
        summaries={k:v.iloc[:0].copy() for k,v in summaries.items()}
        raw={k:v.iloc[:0].copy() for k,v in raw.items()}
    return summaries,raw,images

def _vector(values):
    if len(values)==0:return 'character(0)'
    return 'c('+','.join('NA_character_' if pd.isna(v) else json.dumps(str(v),ensure_ascii=False) for v in values)+')'

def query(case):
    summaries,raw,images=inputs(case);frames=list(summaries.values())+list(raw.values());factors=FACTORS[:case['factors']]
    setup=['factors<-'+_vector(factors),'d<-list('+','.join('data.frame(AnimalName='+_vector(frame['AnimalName'] if 'AnimalName' in frame else frame.index)+','+','.join('v'+str(i)+'='+_vector(frame[f]) for i,f in enumerate(factors) if f in frame)+(',' if any(f in frame for f in factors) else '')+'stringsAsFactors=FALSE,check.names=FALSE)' for frame in frames)+')']
    # Column names in R are fixed tokens; factor spelling remains authored data.
    for i,factor in enumerate(factors):
        allowed=LEVELS[i];mapping=mappings(case).get(factor,{})
        setup.append('for(k in seq_along(d)){n<-"v'+str(i)+'";if(n %in% names(d[[k]])){x<-trimws(d[[k]][[n]]); x[x==""]<-NA_character_; j<-match(tolower(x),'+_vector([*mapping,*[a.lower() for a in allowed]])+'); y<-'+_vector([*mapping.values(),*allowed])+'; hit<-!is.na(j);x[hit]<-y[j[hit]];d[[k]][[n]]<-x}}')
    required=['v'+str(i) for i in range(len(factors))];required_r=_vector(required)
    setup.append('for(k in seq_along(d)){if(all('+required_r+' %in% names(d[[k]]))){v<-d[[k]][,'+required_r+',drop=FALSE];d[[k]]$Condition<-if(nrow(v)==0) character(0) else apply(v,1,function(r) if(any(is.na(r))) NA_character_ else paste0(r,collapse=""))}'+('else d[[k]]$Condition<-rep("stale",nrow(d[[k]]))' if case['condition'] else '')+'}')
    setup.append('source<-Filter(function(t) all(c('+','.join(json.dumps(s) for s in ['AnimalName',*required,'Condition'])+') %in% names(t)),d)')
    setup.append('if(length(source)){s<-do.call(rbind,lapply(source,function(t)t[,c("AnimalName",'+','.join(json.dumps(s) for s in [*required,'Condition'])+'),drop=FALSE])); ids<-unique(s$AnimalName); lookup<-lapply(c('+','.join(json.dumps(s) for s in [*required,'Condition'])+'),function(n) vapply(ids,function(id){v<-s[s$AnimalName==id,n];v<-v[!is.na(v)];if(length(v)) v[[1]] else NA_character_},character(1)));names(lookup)<-c('+','.join(json.dumps(s) for s in [*required,'Condition'])+');for(k in seq_along(d)){for(n in names(lookup)){v<-lookup[[n]][match(d[[k]]$AnimalName,ids)];if(n %in% names(d[[k]])){hit<-!is.na(v);d[[k]][[n]][hit]<-v[hit]}else d[[k]][[n]]<-v}}}')
    # Frame values are flattened in column order stated by the native result.
    setup.append('out<-unlist(lapply(d,function(t){cols<-names(t)[names(t)!="AnimalName"];c(as.character(length(cols)),cols,unlist(t[cols],use.names=FALSE))}),use.names=FALSE)')
    setup.append('out')
    return dict(key=case['key'],code='local({'+ ';'.join(setup)+'})')

def expected(case,answers):
    summaries,raw,images=inputs(case);frames=list(summaries.values())+list(raw.values());offset=0;factors=FACTORS[:case['factors']]
    for frame in frames:
        count=int(answers[offset]);offset+=1;names=answers[offset:offset+count];offset+=count
        for name in names:
            column=factors[int(name[1:])] if name.startswith('v') else name
            frame[column]=pd.Series([np.nan if x is None else x for x in answers[offset:offset+len(frame)]],index=frame.index,dtype=object);offset+=len(frame)
    assert offset==len(answers)
    if images is not None and not images.empty and 'SCN' in summaries and not summaries['SCN'].empty:
        summary=summaries['SCN'];ids=list(summary['AnimalName'] if 'AnimalName' in summary else summary.index)
        cols=[n for n in ('Condition',*factors) if n in summary]
        if cols:
            original=images;images=images.drop(columns=cols,errors='ignore').reset_index(drop=True)
            for name in cols:images[name]=pd.Series([summary.iloc[ids.index(a)][name] if a in ids else np.nan for a in images.AnimalName],dtype=object)
            images.attrs=copy.deepcopy(original.attrs)
    return summaries,raw,images

def production(case,prediction):
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.conditions import condition,conditionList,zipConditionLists
    summaries,raw,images=inputs(case);experiment=object.__new__(MiniExperiment);experiment.name='Explicit factor ownership';experiment.factor_mappings=mappings(case)
    if case['layout']=='summary-attribute':experiment.summary=summaries['SCN']
    else:experiment.summaries=summaries
    experiment.data={k:SimpleNamespace(df=v,experiment=experiment) for k,v in raw.items()};experiment.images=images;experiment.imagesDict={'retained':{'paths':['original']}};experiment._unrelated=object()
    state=dict(experiment.__dict__);old_frames=[f for f in summaries.values()]+[c.df for c in experiment.data.values()];old_copies=[f.copy(deep=True) for f in old_frames];image_copy=None if images is None else images.copy(deep=True)
    groups=None
    for f,levels in zip(FACTORS[:case['factors']],LEVELS):
        level=conditionList([condition(v,v,None,f) for v in levels]);groups=level if groups is None else conditionList(zipConditionLists(groups,level))
    error=None
    try:
        with contextlib.redirect_stdout(io.StringIO()):result=experiment.set_condition_list(groups)
        assert result is groups is experiment.condition_list
        assert experiment.conditions is groups.conditions and experiment.factor is groups.factor and experiment.factorDict is groups.factorDict
        assert experiment.summary is next(iter(experiment.summaries.values()))
        assert experiment.imagesDict is state['imagesDict'] and experiment.imagesDict=={'retained':{'paths':['original']}} and experiment._unrelated is state['_unrelated']
        for before,original in zip(old_frames,old_copies):pd.testing.assert_frame_equal(before,original,check_exact=True)
        if images is not None:pd.testing.assert_frame_equal(images,image_copy,check_exact=True)
        for carrier in experiment.data.values():assert carrier.experiment is experiment
    except Exception as caught:error=type(caught).__name__+': '+str(caught)
    actual=dict(summaries={k:categorical_table(v) for k,v in getattr(experiment,'summaries',{}).items()},raw={k:categorical_table(c.df) for k,c in experiment.data.items()},images=None if experiment.images is None else categorical_table(experiment.images))
    return dict(actual=actual,expected=prediction,passed=error is None and actual==prediction,error=error)
