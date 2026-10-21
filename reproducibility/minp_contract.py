"""Independent minP supplied-null contracts and selected calibration fields.

Fraction event unions and native base R row predicates; sampled distributions
include the observed arrangement. No assertion of sampling assumptions.
Calibration alone does not certify the complete correction_audit method.
"""
from fractions import Fraction
import hashlib,json,math,random
from pathlib import Path
from reproducibility.reference_runtime import execute_queries,values

FIXTURE=Path(__file__).with_name('fixtures')/'minp_reference.json'
PRIMARY_SOURCES=['https://statistics.berkeley.edu/sites/default/files/tech-reports/633.pdf',
    'https://gksmyth.github.io/pubs/PermPValuesPreprint.pdf']

def base_cases():
    rng=random.Random(20261004)
    rows=[]
    for hypotheses in [1,2,3,5]:
        for permutations in [1,7,23]:
            observed=[rng.randrange(0,21)/20 for _ in range(hypotheses)]
            null=[[rng.randrange(0,21)/20 for _ in observed] for _ in range(permutations)]
            rows.append({'key':f'minP.{hypotheses}.{permutations}','parameters':{'pvalues':observed,'null':{'p':null}}})
            rows.append({'key':f'minP.{hypotheses}.{permutations}.ties','parameters':{'pvalues':[.1]*hypotheses,'null':{'p':null}}})
    rows.extend([
        {'key':'minP.all_missing','parameters':{'pvalues':[None,None],'null':{'p':[[None,None],[None,None]]}}},
        {'key':'minP.missing_column','parameters':{'pvalues':[None,.2,.6],'null':{'p':[[None,.1,.8],[None,.4,.3],[None,.7,.5]]}}},
        {'key':'minP.empty','parameters':{'pvalues':[],'null':{'p':[[],[]]}}},
        {'key':'minP.no_small_tail','parameters':{'pvalues':[.01,.02],'null':{'p':[[.3,.5],[.6,.8]]}}},
    ])
    return rows

def base_queries(rows):
    queries=[]
    for row in rows:
        p=row['parameters']; observed=p['pvalues']; matrix=p['null']['p']
        v='c('+','.join('NA_real_' if x is None else str(x) for x in observed)+')' if observed else 'numeric(0)'
        flat=','.join('NA_real_' if x is None else str(x) for sample in matrix for x in sample)
        null='matrix(c('+flat+'),nrow='+str(len(matrix))+',ncol='+str(len(observed))+',byrow=TRUE)' if observed else 'matrix(numeric(0),nrow=2,ncol=0)'
        code=f'''local({{
          p<-{v}; null<-{null}; answer<-rep(NA_real_,length(p)); ids<-which(!is.na(p));
          if(length(ids)){{
            ordered<-ids[order(p[ids])]; raw<-numeric(length(ids));
            for(i in seq_along(ordered)){{
              selected<-ordered[i:length(ordered)];
              events<-apply(null[,selected,drop=FALSE],1,function(sample)any(sample<=p[ordered[i]]));
              raw[i]<-sum(events)/nrow(null)
            }};
            answer[ordered]<-cummax(raw)
          }};
          answer
        }})'''
        queries.append({'key':row['key'],'code':code})
    return queries

def minp_cases():
    result=[]
    for row in base_cases():
        for mode in ['empirical','exact','sampled']:
            copy=json.loads(json.dumps(row))
            copy['key']+='.'+mode
            if mode!='empirical':copy['parameters']['null']['mode']=mode
            result.append(copy)
    return result

def mathematical(row):
    p=row['parameters']; observed=p['pvalues']; null=p['null']['p']
    if p['null'].get('mode')=='sampled':null=[*null,observed]
    order=sorted([i for i,v in enumerate(observed) if v is not None],key=lambda i:observed[i])
    result=[math.nan]*len(observed); prefix=[]
    for rank,idx in enumerate(order):
        events=set()
        for column in order[rank:]:
            events.update(i for i,sample in enumerate(null) if Fraction(str(sample[column]))<=Fraction(str(observed[idx])))
        prefix.append(Fraction(len(events),len(null)))
        result[idx]=float(max(prefix))
    return result

def native_queries(rows):
    result=[]
    for row in rows:
        bare=json.loads(json.dumps(row)); bare['key']=row['key']
        query=base_queries([bare])[0]
        if row['parameters']['null'].get('mode')=='sampled':
            query['code']=query['code'].replace('answer<-rep(NA_real_,length(p));','null<-rbind(null,p); answer<-rep(NA_real_,length(p));')
        result.append(query)
    return result

def calibration(minima,alpha,mode):
    if mode=='sampled' and Fraction(1,len(minima)+1)>Fraction(str(alpha)):return None
    for boundary in sorted(set(minima)):
        count=sum(Fraction(str(v))<=Fraction(str(boundary)) for v in minima)
        probability=Fraction(count+int(mode=='sampled'),len(minima)+int(mode=='sampled'))
        if probability>Fraction(str(alpha)):
            return math.nextafter(boundary,-math.inf) if boundary>0 else None
    return 1.

def calibration_cases():
    result=[]
    vectors=[[.01,.02,.03,.03,.08,.2,.8],[0.,0.,.1,.2,.4],[.04]*5,[.2],
             [5e-324,.01,.5],[.1,.3,.7,1.]]
    for i,mins in enumerate(vectors):
        for alpha in [0.,.05,.25,.5,1.]:
            for mode in ['exact','sampled']:
                result.append({'key':f'calibration.{i}.{alpha}.{mode}','parameters':{'minima':mins,'alpha':alpha,'mode':mode}})
    return result

def native_calibration_query(row):
    p=row['parameters']; vector='c('+','.join(format(v,'.17g') for v in p['minima'])+')'
    plus=int(p['mode']=='sampled')
    return f'''local({{
      x<-{vector};alpha<-{p['alpha']};plus<-{plus};n<-length(x);
      previous_double<-function(value){{
        bytes<-as.integer(writeBin(value,raw(),size=8,endian='little'));
        for(i in 1:8){{if(bytes[i]>0){{bytes[i]<-bytes[i]-1;break}};bytes[i]<-255}};
        readBin(as.raw(bytes),what='double',n=1,size=8,endian='little')
      }};
      cutoff<-1;
      if(plus/(n+plus)>alpha)cutoff<-NA_real_ else {{
        for(boundary in sort(unique(x))){{
          if((sum(x<=boundary)+plus)/(n+plus)>alpha){{
            cutoff<-if(boundary>0) previous_double(boundary) else NA_real_;break
          }}
        }}
      }};
      achieved<-if(is.na(cutoff))0 else sum(x<=cutoff)/n;
      c(cutoff,achieved)
    }})'''

def cases():
    rows=[]
    for row in minp_cases():
        row['capability']='PyFLASH.stats_extra.westfall_young'
        rows.append(row)
        aligned=json.loads(json.dumps(row)); aligned['key']='aligned.'+row['key']
        aligned['capability']='PyFLASH.stats_extra.westfall_young_from_null'
        p=aligned['parameters']; size=len(p['pvalues'])
        declared=[[0,i+1] for i in range(size)]
        p['pairs']=declared
        p['null']['pairs']=declared[::-1]
        p['null']['p']=[sample[::-1] for sample in p['null']['p']]
        aligned['reference_key']=row['key']
        rows.append(aligned)
    for row in calibration_cases():
        row['capability']='PyFLASH.stats_extra.correction_audit'
        row['selected_fields_only']=True
        rows.append(row)
    return rows

def reference(row):
    if row['key'].startswith('calibration.'):
        p=row['parameters']; cutoff=calibration(**p)
        return [math.nan if cutoff is None else cutoff,
                0. if cutoff is None else sum(v<=cutoff for v in p['minima'])/len(p['minima'])]
    if row['key'].startswith('aligned.'):
        row=json.loads(json.dumps(row)); row['parameters']['null']['p']=[sample[::-1] for sample in row['parameters']['null']['p']]
    return mathematical(row)

def production(row):
    from PyFLASH.stats_extra import westfall_young,westfall_young_from_null,correction_audit
    p=row['parameters']
    if row['key'].startswith('calibration.'):
        null={'p':[[v] for v in p['minima']],'pairs':[(0,1)],'mode':p['mode'],'n_perm':len(p['minima'])}
        cutoff=correction_audit([.5],null=null,alpha=p['alpha'])['permutation']['alpha_star']
        return [math.nan if cutoff is None else cutoff,
                0. if cutoff is None else sum(v<=cutoff for v in p['minima'])/len(p['minima'])]
    observed=[math.nan if v is None else v for v in p['pvalues']]
    null={**p['null'],'p':[[math.nan if v is None else v for v in sample] for sample in p['null']['p']]}
    return (westfall_young_from_null(observed,null,p['pairs']) if 'pairs' in p else westfall_young(observed,null))

def queries():
    return native_queries(minp_cases())+[
        {'key':row['key'],'code':native_calibration_query(row)} for row in calibration_cases()]

def execute(output):
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    identity=hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest()
    if identity!=fixture['reference_code_sha256']:
        raise ValueError('Frozen minP reference code changed.')
    if cases()!=[{key:row[key] for key in cases()[i]} for i,row in enumerate(fixture['rows'])]:
        raise ValueError('Frozen minP inputs changed.')
    request=queries()
    if request!=[{key:row[key] for key in query} for query,row in zip(request,fixture['native']['rows'],strict=True)]:
        raise ValueError('Frozen independent minP expressions changed.')
    result=execute_queries(request,output,name='minp-observed-arrangement-and-calibration')
    for key in ['R','webR','wasm_sha256']:
        if result[key]!=fixture['native'][key]:raise ValueError('MinP reference runtime changed: '+key)
    return result

def packed(numbers):
    return {'values':[v if math.isfinite(v) else None for v in numbers],
        'nonfinite':[None if math.isfinite(v) else 'nan' for v in numbers]}
