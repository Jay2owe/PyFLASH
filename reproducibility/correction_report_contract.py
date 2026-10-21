"""Independent complete correction reports composed from frozen reference nulls.

The numerical workflow executes these complete reports. Base R builds them
independently; Fraction references do not call production inference.
"""
from pathlib import Path
from fractions import Fraction
import hashlib,json,math
import numpy as np
from reproducibility import multiplicity_contract as multiplicity
from reproducibility import minp_contract as minp
from reproducibility import permutation_contract as ranks
from reproducibility import value_permutation_contract as values_reference
from reproducibility.reference_runtime import execute_queries,values

FIXTURE=Path(__file__).with_name('fixtures')/'correction_report_reference_v4.json'
METHODS={'holm':'holm','bh_q':'fdr_bh','bonferroni':'bonferroni','sidak':'sidak'}
CONVENTIONS=['uncorrected',*METHODS,'westfall_young']

def packed(value):
    if isinstance(value,(float,np.floating)) and not math.isfinite(value):
        return '__nan__' if math.isnan(value) else '__positive_infinity__' if value>0 else '__negative_infinity__'
    if isinstance(value,dict):return {str(k):packed(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [packed(v) for v in value]
    return value

def decoded(value):
    if isinstance(value,str) and value.startswith('__'):
        return {'__nan__':math.nan,'__positive_infinity__':math.inf,'__negative_infinity__':-math.inf}[value]
    if isinstance(value,list):return [decoded(v) for v in value]
    if isinstance(value,dict):return {k:decoded(v) for k,v in value.items()}
    return value

def complete_equal(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        assert set(a)==set(b),(path,set(a),set(b))
        for key in a:complete_equal(a[key],b[key],path+'.'+key)
    elif isinstance(a,list) and isinstance(b,list):
        assert len(a)==len(b),(path,len(a),len(b))
        for i,(left,right) in enumerate(zip(a,b)):complete_equal(left,right,path+f'[{i}]')
    elif isinstance(a,(int,float)) and isinstance(b,(int,float)):
        assert np.isclose(a,b,rtol=1e-9,atol=1e-12,equal_nan=True),(path,a,b)
    else:assert a==b,(path,a,b)

def ladder(observed):
    raw=[math.nan if v is None else v for v in observed]
    result={'uncorrected':raw}
    for name,method in METHODS.items():
        reference=multiplicity.reference({'parameters':{'pvalues':observed},'canonical':method})
        result[name]=reference[1+len(observed):]
    return result

def cases():
    rows=[]
    def add(capability,p,**options):
        rows.append({'key':f'correction-report.{len(rows)}','capability':'PyFLASH.stats_extra.'+capability,'parameters':p,**options})
    vectors=[[.001,.019,.04,.2,.9],[.1,.1,.1],[None,.01,.5],[],[None,None],[0,1],[1e-200,1e-15,.3]]
    for vector in vectors:
        add('correction_ladder',{'pvalues':vector})
        add('correction_ladder',{'pvalues':vector},generator=True)
        for alpha in [0.,.05,.5,1.]:
            add('correction_audit',{'pvalues':vector,'alpha':alpha,'want_permutation':False})
    for base in minp.minp_cases():
        p=json.loads(json.dumps(base['parameters']));null=p['null'];size=len(p['pvalues'])
        null.update(pairs=[[0,i+1] for i in range(size)],n_perm=len(null['p']),n_arrangements=None)
        p.update(alpha=.05)
        add('correction_audit',p)
        if size and all(v is not None for v in p['pvalues']):
            reverse=json.loads(json.dumps(p));reverse['pairs']=null['pairs'][::-1]
            reverse['pvalues']=reverse['pvalues'][::-1]
            add('correction_audit',reverse)
    for i,p in enumerate([
        {'pvalues':[.1],'null':{'p':[[.2,.3]],'pairs':[[0,1],[0,2]],'mode':'exact','n_perm':1}},
        {'pvalues':[.1,.2],'pairs':[[0,1],[1,2]],'null':{'p':[[.3,.4]],'pairs':[[0,1],[0,2]],'mode':'sampled','n_perm':1}},
        {'pvalues':[.01,.2],'null':{'p':[[.03,.04],[.3,.6]],'pairs':[[0,1],[0,2]],'mode':'sampled','n_perm':2},'alpha':.5},
    ]):add('correction_audit',p)
    rank_fixture=json.loads(ranks.FIXTURE.read_text(encoding='utf-8'))
    for row in rank_fixture['rows']:
        vector=values({'values':row['mathematical_values'],'nonfinite':row['mathematical_nonfinite']})
        n,m=int(vector[1]),int(vector[4]);offset=5+2*m
        pairs=[vector[5+2*i:7+2*i] for i in range(m)]
        probabilities=np.array(vector[offset:]).reshape(n,m).tolist()
        null={'p':packed(probabilities),'pairs':pairs,'mode':'sampled' if vector[2] else 'exact','n_perm':n,'n_arrangements':int(vector[0])}
        observed=[None]*m if not any(math.isfinite(v) for v in vector[offset:]) else [.01+.08*i for i in range(m)]
        p={'pvalues':observed,**row['parameters']}
        add('westfall_young_adjusted',p,reference_null=null)
        for alpha in [.05,.5]:add('correction_audit',{**p,'alpha':alpha},reference_null=null)
    value_fixture=json.loads(values_reference.FIXTURE.read_text(encoding='utf-8'))
    for row in value_fixture['rows']:
        vector=values(row['expected']);n,m=int(vector[1]),int(vector[4]);offset=5+2*m
        null={'p':packed(np.array(vector[offset:]).reshape(n,m).tolist()),
              'pairs':[vector[5+2*i:7+2*i] for i in range(m)],'mode':'sampled','n_perm':n,'n_arrangements':None}
        observed=[None]*m if not any(math.isfinite(v) for v in vector[offset:]) else [.01+.08*i for i in range(m)]
        p={'pvalues':observed,**row['parameters']}
        add('value_westfall_young_adjusted',p,reference_null=null)
    audits=[row for row in rows if row['capability'].endswith('.correction_audit')]
    for row in audits[::7]:
        for alpha in [.01,.05,1.]:
            add('verdict_changes',{'audit_case':row['key'],'alpha':alpha,
                'comparisons':['contrast '+str(i) for i in range(len(row['parameters']['pvalues']))]})
        add('verdict_changes',{'audit_case':row['key'],'alpha':.05,'comparisons':None})
    for row in list(rows):
        if not row['capability'].endswith('_adjusted'):continue
        p=json.loads(json.dumps(row['parameters']));null=row['reference_null']
        reverse=json.loads(json.dumps(p));reverse['pairs']=null['pairs'][::-1]
        reverse['pvalues']=reverse['pvalues'][::-1]
        add(row['capability'].rsplit('.',1)[-1],reverse,reference_null=null)
        if len(p['pvalues'])>1:
            subset=json.loads(json.dumps(p));indices=list(range(0,len(p['pvalues']),2))
            subset['pvalues']=[p['pvalues'][i] for i in indices]
            subset['pairs']=[null['pairs'][i] for i in indices]
            add(row['capability'].rsplit('.',1)[-1],subset,reference_null=null)
    return rows

def aligned_null(row):
    p=row['parameters'];null=decoded(row.get('reference_null',p.get('null')))
    if null is None:return None,None
    null={**null,'p':[[math.nan if v is None else v for v in sample] for sample in null['p']]}
    observed=p['pvalues'];k=len(null['pairs'])
    if k!=len(observed) and not (row.get('capability','').endswith('_adjusted') and p.get('pairs')):
        return None,f'null covers {k} comparisons but {len(observed)} were reported'
    wanted=p.get('pairs',null['pairs'])
    def identity(pair):return tuple(sorted(pair))
    lookup={identity(pair):i for i,pair in enumerate(null['pairs'])}
    if len(set(map(identity,wanted)))!=len(wanted) or any(identity(pair) not in lookup for pair in wanted):
        return None,'reported comparisons do not match the null design'
    positions=[lookup[identity(pair)] for pair in wanted]
    return {**null,'p':[[sample[i] for i in positions] for sample in null['p']]},None

def reference(row,*,all_rows=None):
    p=row['parameters'];capability=row['capability'].rsplit('.',1)[-1]
    if capability=='verdict_changes':
        audit_row=next(r for r in (all_rows or cases()) if r['key']==p['audit_case'])
        audit=reference(audit_row);alpha=p['alpha'];labels=p['comparisons']
        out={}
        for i,raw in enumerate(audit['uncorrected']):
            label=str(labels[i]) if labels is not None and i<len(labels) else str(i+1)
            names=[key for key in CONVENTIONS if key in audit and math.isfinite(audit[key][i]) and audit[key][i]<=alpha]
            cutoff=(audit.get('permutation') or {}).get('alpha_star')
            if cutoff is not None and math.isfinite(raw) and raw<=cutoff:names.append('calibrated')
            out[label]=names
        return out
    if capability=='correction_ladder':return ladder(p['pvalues'])
    null,skipped=aligned_null(row)
    observed=p['pvalues']
    if capability.endswith('_adjusted'):
        return minp.mathematical({'parameters':{'pvalues':observed,'null':{'p':[[None if math.isnan(v) else v for v in sample] for sample in null['p']],'mode':null['mode']}}})
    alpha=p.get('alpha',.05);out={'alpha':alpha,**ladder(observed)}
    if null is None:
        out['permutation']=None
        if skipped:out['skipped']=skipped
        return out
    out['westfall_young']=minp.mathematical({'parameters':{'pvalues':observed,'null':{
        'p':[[None if math.isnan(v) else v for v in sample] for sample in null['p']],'mode':null.get('mode','empirical')}}})
    valid=[i for i,v in enumerate(observed) if v is not None]
    if not valid:
        out.update(permutation=None,skipped='no finite observed comparisons to calibrate');return out
    minima=[min(sample[i] for i in valid) for sample in null['p']];n=len(minima);mode=null.get('mode','empirical')
    k=len(valid)
    out['permutation']={'mode':mode,'n_perm':n,'n_arrangements':null.get('n_arrangements'),
        'p_resolution':1/(n+int(mode=='sampled')),'p_floor':min(minima),
        'fwer_if_uncorrected':float(sum(Fraction(str(v))<=Fraction(str(alpha)) for v in minima)/n),
        'fwer_of_bonferroni':float(sum(Fraction(str(v))<=Fraction(str(alpha))/k for v in minima)/n),
        'alpha_star':minp.calibration(minima,alpha,mode),
        'alpha_bonferroni':alpha/k}
    return out

def production(row,*,all_rows=None):
    from PyFLASH import stats_extra as se
    p=decoded(json.loads(json.dumps(row['parameters'])));capability=row['capability'].rsplit('.',1)[-1]
    if capability=='verdict_changes':
        audit_case=p.pop('audit_case')
        audit=production(next(r for r in (all_rows or cases()) if r['key']==audit_case))
        return se.verdict_changes(audit,**p)
    p['pvalues']=[math.nan if v is None else v for v in p['pvalues']]
    if 'null' in p:p['null']['p']=[[math.nan if v is None else v for v in sample] for sample in p['null']['p']]
    if row.get('generator'):p['pvalues']=(v for v in p['pvalues'])
    return getattr(se,capability)(**p)

R_JSON=r'''
 json_number<-function(x){if(is.na(x))'"__nan__"' else if(!is.finite(x))if(x>0)'"__positive_infinity__"' else '"__negative_infinity__"' else sprintf('%.17g',x)};
 json_write<-function(x){
   if(is.null(x))return('null');
   if(inherits(x,'json_array'))return(paste0('[',paste(vapply(unclass(x),json_write,''),collapse=','),']'));
   if(is.list(x)){
     return(paste0('{',paste(vapply(seq_along(x),function(i)paste0(encodeString(names(x)[i],quote='"'),':',json_write(x[[i]])),''),collapse=','),'}'))
   };
   if(is.character(x))return(encodeString(x,quote='"'));
   json_number(x)
 };
 array<-function(x)structure(as.list(x),class='json_array');
'''

def rvector(items):
    return 'c('+','.join('NA_real_' if v is None or isinstance(v,float) and math.isnan(v) else format(v,'.17g') for v in items)+')' if items else 'numeric(0)'

def audit_expression(row):
    p=row['parameters'];observed=p['pvalues'];alpha=p.get('alpha',.05)
    null,skipped=aligned_null(row)
    expressions=[]
    for key,method in METHODS.items():
        query=multiplicity.r_query({'canonical':method,'parameters':{'pvalues':observed}})
        expressions.append(f"z<-{query};out${key}<-array(tail(z,{len(observed)}))" if observed else f"out${key}<-array(numeric(0))")
    ladder_code=';'.join(expressions)
    prefix=f"p<-{rvector(observed)};out<-list(alpha={alpha},uncorrected=array(p));{ladder_code};"
    if null is None:
        return 'local({'+prefix+'out$permutation<-list(NULL);out$permutation<-NULL;out<-c(out,list(permutation=NULL));'+(
            f"out$skipped<-{json.dumps(skipped)};" if skipped else '')+'out})'
    raw_null=[[None if math.isnan(v) else v for v in sample] for sample in null['p']]
    minp_row={'key':'inner','parameters':{'pvalues':observed,'null':{'p':raw_null,'mode':null.get('mode','empirical')}}}
    query=minp.native_queries([minp_row])[0]['code']
    code=prefix+f'out$westfall_young<-array({query});ids<-which(is.finite(p));'
    code+='if(!length(ids)){out<-c(out,list(permutation=NULL));out$skipped<-"no finite observed comparisons to calibrate";return(out)};'
    n=len(raw_null);k=len(observed)
    code+=f"null<-matrix({rvector([v for sample in raw_null for v in sample])},nrow={n},ncol={k},byrow=TRUE);"
    code+='minima<-apply(null[,ids,drop=FALSE],1,min);'
    mode=null.get('mode','empirical');plus=int(mode=='sampled')
    # An independent native discrete CDF threshold, including exact predecessor.
    code+=f'alpha<-{alpha};plus<-{plus};n<-length(minima);cutoff<-1;'
    code+=r'''
       previous_double<-function(value){bytes<-as.integer(writeBin(value,raw(),size=8,endian='little'));
         for(i in 1:8){if(bytes[i]>0){bytes[i]<-bytes[i]-1;break};bytes[i]<-255};
         readBin(as.raw(bytes),what='double',n=1,size=8,endian='little')};
       if(plus/(n+plus)>alpha)cutoff<-NULL else {
         for(boundary in sort(unique(minima))){
           if((sum(minima<=boundary)+plus)/(n+plus)>alpha){cutoff<-if(boundary>0)previous_double(boundary) else NULL;break}
         }
       };
    '''
    total=null.get('n_arrangements');total_r='NULL' if total is None else str(total)
    code+=f'''out$permutation<-list(mode={json.dumps(mode)},n_perm=n,n_arrangements={total_r},
        p_resolution=1/(n+plus),p_floor=min(minima),fwer_if_uncorrected=mean(minima<=alpha),
        fwer_of_bonferroni=mean(minima<=alpha/length(ids)),alpha_star=cutoff,alpha_bonferroni=alpha/length(ids));out'''
    return 'local({'+code+'})'

def native_query(row,all_rows):
    capability=row['capability'].rsplit('.',1)[-1];p=row['parameters']
    if capability=='correction_ladder':
        expression=audit_expression({'parameters':{**p,'want_permutation':False}})
        expression='local({out<-'+expression+';out$alpha<-NULL;out$permutation<-NULL;out})'
    elif capability=='correction_audit':expression=audit_expression(row)
    elif capability.endswith('_adjusted'):
        null,_=aligned_null(row)
        query=minp.native_queries([{'key':'inner','parameters':{'pvalues':p['pvalues'],'null':{
            'p':[[None if math.isnan(v) else v for v in sample] for sample in null['p']],'mode':null['mode']}}}])[0]['code']
        expression='array('+query+')'
    elif capability=='verdict_changes':
        audit_row=next(r for r in all_rows if r['key']==p['audit_case'])
        expression=audit_expression(audit_row)
        labels=p['comparisons'];labels_r='NULL' if labels is None else 'c('+','.join(json.dumps(label) for label in labels)+')'
        expression=f'''local({{
            audit<-{expression};labels<-{labels_r};answer<-list();alpha<-{p['alpha']};
            keys<-c('uncorrected','holm','bh_q','bonferroni','sidak','westfall_young');
            if(length(audit$uncorrected)) for(i in seq_along(audit$uncorrected)){{
                names<-character(0);
                for(key in keys){{v<-audit[[key]];if(!is.null(v)&&length(v)&&is.finite(v[[i]])&&v[[i]]<=alpha)names<-c(names,key)}};
                cutoff<-audit$permutation$alpha_star;raw<-audit$uncorrected[[i]];
                if(!is.null(cutoff)&&is.finite(raw)&&raw<=cutoff)names<-c(names,'calibrated');
                label<-if(!is.null(labels)&&i<=length(labels))labels[i] else as.character(i);
                answer[[label]]<-array(names)
            }};answer
        }})'''
    return 'local({'+R_JSON+'json_write('+expression+')})'


def dependency_identities():
    return {module.FIXTURE.name:hashlib.sha256(module.FIXTURE.read_bytes()).hexdigest()
            for module in [multiplicity,minp,ranks,values_reference]}

def execute(output):
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    if hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest()!=fixture['reference_code_sha256']:
        raise ValueError('Frozen complete correction-report reference code changed.')
    if dependency_identities()!=fixture['dependencies']:
        raise ValueError('A composed independently frozen correction reference changed.')
    check_dependency_lineage(fixture)
    current=cases()
    if current!=[{key:row[key] for key in case} for case,row in zip(current,fixture['rows'],strict=True)]:
        raise ValueError('Frozen complete correction-report inputs changed.')
    queries=[{'key':row['key'],'code':native_query(row,current)} for row in current]
    if queries!=[{key:row[key] for key in query} for query,row in zip(queries,fixture['native']['rows'],strict=True)]:
        raise ValueError('Frozen native complete correction-report expression changed.')
    result=execute_queries(queries,output,name='complete-correction-reports')
    for key in ['R','webR','wasm_sha256']:
        if result[key]!=fixture['native'][key]:raise ValueError('Native correction reference runtime changed: '+key)
    return result

def native_result(row):
    return decoded(json.loads(row['values'][0]))


def check_dependency_lineage(fixture=None):
    """A deadline revision cannot replace numerical inputs or answers."""
    fixture=fixture or json.loads(FIXTURE.read_text(encoding='utf-8'))
    lineage=fixture['dependency_lineage'];root=Path(__file__).parent
    for path,expected in lineage['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original correction dependency evidence changed: '+path)
    previous=json.loads((root/lineage['previous_fixture']).read_text(encoding='utf-8'))
    if fixture['rows']!=previous['rows'] or fixture['native']!=previous['native']:
        raise ValueError('Correction inputs, answers or native results changed during deadline revision')
    old_path=root/lineage['original_value_fixture'];old=json.loads(old_path.read_text(encoding='utf-8'))
    current=json.loads(values_reference.FIXTURE.read_text(encoding='utf-8'))
    if hashlib.sha256(old_path.read_bytes()).hexdigest()!=previous['dependencies']['value_permutation_reference.json']:
        raise ValueError('Original composed value reference does not match prior correction proof')
    if ({k:v for k,v in current.items() if k not in ('reference_code_sha256','verification_adapter_history')}
            != {k:v for k,v in old.items() if k!='reference_code_sha256'}):
        raise ValueError('Composed value-reference numerical evidence changed')
    adapter=(root/'reference-sources/value-permutation-deadline/original-adapter.py').read_text(encoding='utf-8')
    if hashlib.sha256(adapter.encode()).hexdigest()!=old['reference_code_sha256']:
        raise ValueError('Original composed value-reference adapter changed')
    comments="    # The default case executes 10,000 unchanged native R fits.\n    # Retain the exact query and comparisons while bounding shared-host work.\n"
    revised=adapter.replace("    result=execute_queries(queries,output,name='value-permutation-full-contract')",comments+"    result=execute_queries(queries,output,name='value-permutation-full-contract',timeout=900)")
    if revised!=Path(values_reference.__file__).read_text(encoding='utf-8'):
        raise ValueError('Composed value-reference adapter changed beyond declared deadline')
    return fixture
