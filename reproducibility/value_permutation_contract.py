"""Full sampled Fisher-LSD nulls: independent native R and rational/70-digit tails.

Recorded NumPy arrangements are common inputs, not an independent generator vote.
Every probability, pair index and returned metadata field is compared.
"""
from fractions import Fraction as F
import hashlib,json,math
from pathlib import Path
import mpmath as mp
import numpy as np
from reproducibility.reference_runtime import execute_queries,values

FIXTURE=Path(__file__).with_name('fixtures')/'value_permutation_reference.json'
SOURCE='https://www.stat.ethz.ch/R-manual/R-devel/library/stats/html/pairwise.t.test.html'

def cases():
    rows=[]
    designs=[[[.1,.4,1.2],[1.8,2.3]],
             [[-2,-.4,.5],[.8,1.6,2.1],[3.1,3.4,4.2,4.8]],
             [[0,.5],[1,1.7,2.1],[2.6,3.8],[4.1,4.5,5.2]]]
    def add(groups,count,seed,**metadata):
        rows.append({'key':f'value-null.{len(rows)}','capability':'PyFLASH.stats_extra.value_permutation_null',
            'parameters':{'groups':groups,'n_resamples':count,'seed':seed,'statistic':'lsd'},**metadata})
    for groups in designs:
        for count in [1,7,19]:
            for seed in [0,41]:add(groups,count,seed)
    for groups in [[[1,1],[1,1]],[[0,0,0],[0,0],[0,0,0,0]],[[0,0],[1,1]],
                   [[0,0,1],[1,2,2],[3,3]],[[1,1],[1,1],[2,2],[2,3]]]:
        for count in [1,23]:add(groups,count,5)
    add(designs[1],10000,0,omit_defaults=True)
    return rows

def arrangements(p):
    rng=np.random.default_rng(p['seed'])
    count=sum(len(group) for group in p['groups'])
    return np.argsort(rng.random((p['n_resamples'],count)),axis=1).tolist()

def mathematical(row):
    p=row['parameters'];groups=p['groups'];ns=[len(group) for group in groups]
    pooled=[F(str(v)) for group in groups for v in group]
    pairs=[(i,j) for i in range(len(groups)) for j in range(i+1,len(groups))]
    result=[1,p['n_resamples'],math.nan,1,len(pairs),*(v for pair in pairs for v in pair)]
    draws=row.get('arrangements',arrangements(p));df=len(pooled)-len(groups)
    with mp.workdps(70):
        for draw in draws:
            means=[];ss=F(0);start=0
            for size in ns:
                block=[pooled[i] for i in draw[start:start+size]];mean=sum(block)/size
                means.append(mean);ss+=sum((v-mean)**2 for v in block);start+=size
            mse=ss/df
            for i,j in pairs:
                difference=means[i]-means[j]
                if not mse:
                    probability=math.nan if not difference else 0.
                else:
                    squared=difference**2/(mse*(F(1,ns[i])+F(1,ns[j])))
                    t2=mp.mpf(squared.numerator)/squared.denominator
                    probability=float(mp.betainc(mp.mpf(df)/2,mp.mpf('.5'),0,df/(df+t2),regularized=True))
                result.append(probability)
    return result

def native_query(row):
    p=row['parameters'];groups=p['groups'];sizes=[len(group) for group in groups]
    pooled=[v for group in groups for v in group];k=len(groups)
    pairs=[(i,j) for i in range(k) for j in range(i+1,k)]
    vector=lambda v:'c('+','.join(format(x,'.17g') for x in v)+')'
    draw=row.get('arrangements',arrangements(p))
    flat=[i+1 for perm in draw for i in perm]
    return f'''local({{
      pooled<-{vector(pooled)};sizes<-{vector(sizes)};
      permutations<-matrix({vector(flat)},nrow={len(draw)},byrow=TRUE);
      groups<-factor(rep(seq_len({k}),sizes));answer<-numeric(0);
      for(draw in seq_len(nrow(permutations))){{
        fit<-pairwise.t.test(pooled[permutations[draw,]],groups,p.adjust.method='none',pool.sd=TRUE);
        answer<-c(answer,{','.join('fit$p.value["'+str(j+1)+'","'+str(i+1)+'"]' for i,j in pairs)})
      }};
      c(1,nrow(permutations),NA_real_,1,{len(pairs)},{','.join(str(v) for pair in pairs for v in pair)},answer)
    }})'''

def production(row):
    from PyFLASH.stats_extra import value_permutation_null
    kwargs=dict(row['parameters'])
    if row.get('omit_defaults'):
        for key in ['n_resamples','seed','statistic']:kwargs.pop(key)
    answer=value_permutation_null(**kwargs)
    if set(answer)!= {'p','pairs','mode','statistic','n_perm','n_arrangements'}:
        raise ValueError('Returned null fields differ from the declared contract.')
    if answer['mode']!='sampled' or answer['statistic']!='lsd' or answer['n_arrangements'] is not None:
        raise ValueError('Returned null metadata differs from the declared contract.')
    if answer['p'].shape!=(row['parameters']['n_resamples'],len(answer['pairs'])):
        raise ValueError('Returned null dimensions differ from the declared contract.')
    return [1,answer['n_perm'],math.nan,1,len(answer['pairs']),
            *(v for pair in answer['pairs'] for v in pair),*answer['p'].ravel().tolist()]

def execute(output):
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    if hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest()!=fixture['reference_code_sha256']:
        raise ValueError('Frozen value-permutation reference code changed.')
    if cases()!=[{key:row[key] for key in case} for case,row in zip(cases(),fixture['rows'],strict=True)]:
        raise ValueError('Frozen value-permutation inputs changed.')
    queries=[{'key':row['key'],'code':native_query(row)} for row in fixture['rows']]
    if queries!=[{key:row[key] for key in query} for query,row in zip(queries,fixture['native']['rows'],strict=True)]:
        raise ValueError('Frozen native R value-permutation expression changed.')
    # The default case executes 10,000 unchanged native R fits.
    # Retain the exact query and comparisons while bounding shared-host work.
    result=execute_queries(queries,output,name='value-permutation-full-contract',timeout=900)
    for key in ['R','webR','wasm_sha256']:
        if result[key]!=fixture['native'][key]:raise ValueError('Native reference runtime changed: '+key)
    return result

def packed(numbers):
    return {'values':[v if math.isfinite(v) else None for v in numbers],
            'nonfinite':[None if math.isfinite(v) else 'nan' for v in numbers]}

def freeze(output):
    if FIXTURE.exists():raise FileExistsError(FIXTURE)
    rows=[{**row,'arrangements':arrangements(row['parameters'])} for row in cases()]
    native=execute_queries([{'key':row['key'],'code':native_query(row)} for row in rows],output,name='value-permutation-full-contract')
    by_key={row['key']:values(row) for row in native['rows']}
    failures=[]
    for row in rows:
        expected=mathematical(row)
        np.testing.assert_allclose(by_key[row['key']],expected,rtol=1e-9,atol=1e-12,equal_nan=True,err_msg=row['key'])
        before=production(row)
        if not np.all(np.isclose(before,expected,rtol=1e-9,atol=1e-12,equal_nan=True)):failures.append(row['key'])
        row.update(expected=packed(expected),before=packed(before))
    FIXTURE.write_text(json.dumps({'schema_version':1,'reason':'Freeze complete native R and rational/high-precision nulls before correcting zero-variance inference.',
        'reference_code_sha256':hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
        'rows':rows,'native':native,'source':SOURCE,'common_arrangements':'NumPy PCG64 random-matrix/argsort arrangements; common input only, no independent random-generator vote'},
        indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'complete_cases':len(rows),'native_math_agree':len(rows),'before_failures':failures}))
