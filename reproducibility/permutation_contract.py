"""Full rank-permutation outputs against published R and exact arithmetic.

Monte Carlo uses a recorded common NumPy random stream; only enumeration and
inference are independent. No independent random-generator claim is made.
"""
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from itertools import product
import hashlib, json, math
from pathlib import Path
import mpmath as mp

FIXTURE = Path(__file__).with_name('fixtures')/'permutation_reference.json'
SOURCE_ROOT = Path(__file__).with_name('reference-sources')/'PMCMRplus'
CAPABILITY = 'PyFLASH.stats_extra.permutation_null'


def cases():
    designs = [([1,1],None),([2,2],None),([3,2],None),([3,3],None),
        ([1,2,2],None),([2,2,2],None),([1,1,2,2],None),
        ([2,2],[1.5,1.5,3.,4.]),([2,2],[1.5,1.5,3.5,3.5]),
        ([2,3],[1.,2.5,2.5,4.5,4.5]),([2,2,2],[1.,2.5,2.5,4.,5.5,5.5]),
        ([2,2],[2.5]*4),([1,2,2],[3.]*5)]
    result = []
    for statistic in ('dunn','conover'):
        for sizes,ranks in designs:
            if statistic=='conover' and sum(sizes)==len(sizes):
                continue
            result.append({'parameters':{'group_sizes':sizes,'ranks':ranks,'statistic':statistic},'kind':'exact'})
        for seed,resamples,sizes,ranks in ((0,1,[2,2],None),(7,17,[2,2,2],None),
                (9,31,[2,3],[1.,2.5,2.5,4.5,4.5])):
            result.append({'parameters':{'group_sizes':sizes,'ranks':ranks,'statistic':statistic,
                'seed':seed,'n_resamples':resamples,'exact_max':0},'kind':'sampled'})
        result.append({'parameters':{'group_sizes':[2,2],'statistic':statistic,'exact_max':6,
            'n_resamples':3,'seed':12},'kind':'threshold'})
    result.append({'parameters':{'group_sizes':[2,2]},'kind':'default'})
    return [{**r,'key':f'permutation.{i}','capability':CAPABILITY} for i,r in enumerate(result)]


def invalid_cases():
    rows = []
    for sizes in ([],[2],[0,2],[-1,3],[2.1,2],[True,2],['2',2],[float('inf'),2]):
        rows.append({'group_sizes':sizes})
    for name,values in (('n_resamples',(0,-1,2.5,True,'3')),('exact_max',(-1,.5,True,'3')),
                         ('seed',(-1,.5,True,'3'))):
        rows.extend({'group_sizes':[2,2],name:v} for v in values)
    for ranks in ([1,2,3],[1,2,3,float('nan')],[1,2,3,float('inf')],
                  [[1,2],[3,4]],[1,2,3,4.0000001],[0,1,2,3]):
        rows.append({'group_sizes':[2,2],'ranks':ranks})
    rows += [{'group_sizes':[1,1],'statistic':'conover'},
             {'group_sizes':[2,2],'statistic':'not-a-rank-statistic'}]
    return rows


def arrangements(parameters):
    sizes = parameters['group_sizes']
    n,k = sum(sizes),len(sizes)
    total = math.factorial(n)//math.prod(math.factorial(v) for v in sizes)
    if total<=parameters.get('exact_max',10000):
        # Enumerate label words, independently of the production combinations.
        words = [word for word in product(range(k),repeat=n)
                 if all(word.count(i)==size for i,size in enumerate(sizes))]
        rows = [tuple(tuple(j for j,v in enumerate(word) if v==i) for i in range(k)) for word in words]
        return sorted(rows),total,'exact'
    import numpy as np
    random = np.random.default_rng(parameters.get('seed',0)).random((parameters.get('n_resamples',20000),n))
    rows = []
    for draw in random:
        ordered = sorted(range(n),key=lambda i:draw[i])
        cuts = [sum(sizes[:i]) for i in range(k+1)]
        rows.append(tuple(tuple(ordered[cuts[i]:cuts[i+1]]) for i in range(k)))
    return rows,total,'sampled'


def ranks(parameters):
    n = sum(parameters['group_sizes'])
    return sorted(parameters.get('ranks') or list(range(1,n+1)))


def metadata(parameters,count,total,mode):
    k = len(parameters['group_sizes'])
    pairs = [(i,j) for i in range(k) for j in range(i+1,k)]
    return [total,count,int(mode=='sampled'),int(parameters.get('statistic','dunn')=='conover'),len(pairs),
            *[v for pair in pairs for v in pair]]


@lru_cache(maxsize=2048)
def tail(statistic,numerator,denominator,df):
    with mp.workdps(70):
        q = mp.mpf(numerator.numerator)/numerator.denominator
        v = mp.mpf(denominator.numerator)/denominator.denominator
        squared = q*q/v
        return float(mp.erfc(mp.sqrt(squared/2))) if statistic=='dunn' else float(mp.betainc(mp.mpf(df)/2,mp.mpf('.5'),0,mp.mpf(df)/(df+squared),regularized=True))


def mathematical(row):
    p = row['parameters']
    ns,n = p['group_sizes'],sum(p['group_sizes'])
    rk = [Fraction(str(v)) for v in ranks(p)]
    tied = sum(c**3-c for c in Counter(rk).values())
    variance = Fraction(n*(n+1),12)-Fraction(tied,12*(n-1))
    tie = 1-Fraction(tied,n**3-n)
    sample_variance = (sum(r*r for r in rk)-Fraction(n*(n+1)**2,4))/(n-1)
    parts,total,mode = arrangements(p)
    output = metadata(p,len(parts),total,mode)
    statistic = p.get('statistic','dunn')
    for groups in parts:
        means = [sum((rk[i] for i in g),Fraction())/len(g) for g in groups]
        h = Fraction(12,n*(n+1))*sum(ns[i]*means[i]**2 for i in range(len(ns)))-3*(n+1)
        for i in range(len(ns)):
            for j in range(i+1,len(ns)):
                difference = abs(means[i]-means[j])
                if not tie:
                    value = math.nan
                else:
                    denominator = variance*(Fraction(1,ns[i])+Fraction(1,ns[j])) if statistic=='dunn' else sample_variance*(Fraction(1,ns[i])+Fraction(1,ns[j]))*max(Fraction(),(n-1-h/tie)/(n-len(ns)))
                    if denominator==0:
                        value = 1. if difference==0 else 0.
                    else:
                        value = tail(statistic,difference,denominator,n-len(ns))
                output.append(value)
    return output


def production(row):
    from PyFLASH.stats_extra import permutation_null
    result = permutation_null(**row['parameters'])
    return [result['n_arrangements'],result['n_perm'],{'exact':0,'sampled':1}.get(result['mode'],-1),
            {'dunn':0,'conover':1}.get(result['statistic'],-1),len(result['pairs']),
            *[v for pair in result['pairs'] for v in pair],*result['p'].ravel().tolist()]


def source_setup():
    payload = json.loads((SOURCE_ROOT/'sources.json').read_text())
    text = ''
    for name in ('gettiesDunn.R','gettiesKruskal.R','HStat.R','kwAllPairsDunnTest.R','kwAllPairsConoverTest.R'):
        content = (SOURCE_ROOT/name).read_bytes()
        assert hashlib.sha256(content).hexdigest()==payload['sources'][name]['sha256']
        text += content.decode()+'\n'
    chunks = [json.dumps(text[i:i+3500]) for i in range(0,len(text),3500)]
    return 'local({eval(parse(text=paste0(c('+','.join(chunks)+'),collapse="")),envir=.GlobalEnv);0})'


def native_query(row):
    p = row['parameters']
    parts,total,mode = arrangements(p)
    rk,ns = ranks(p),p['group_sizes']
    # Flatten assignment-specific groups into one observed-value vector;
    # published R kernels independently rank and evaluate every arrangement.
    inputs = [[rk[i] for group in groups for i in group] for groups in parts]
    flat = ','.join(format(v,'.17g') for values in inputs for v in values)
    sizes = ','.join(map(str,ns))
    prefix = ','.join(map(str,metadata(p,len(parts),total,mode)))
    function = 'kwAllPairsDunnTest.default' if p.get('statistic','dunn')=='dunn' else 'kwAllPairsConoverTest.default'
    return ('local({ns<-c('+sizes+');g<-rep(seq_along(ns),ns); '
        'inputs<-matrix(c('+flat+'),ncol=sum(ns),byrow=TRUE); out<-c('+prefix+'); '
        'for(r in seq_len(nrow(inputs))) {ans<-suppressWarnings('+function+'(inputs[r,],g,p.adjust.method="none")); '
        'for(i in seq_len(length(ns)-1)) for(j in (i+1):length(ns)) out<-c(out,ans$p.value[j-1,i]);};out})')


def execute(output):
    from reproducibility.reference_runtime import execute_queries
    queries = [{'key':'setup','code':source_setup()},
        *[{**row,'code':native_query(row)} for row in cases()]]
    if FIXTURE.exists():
        fixture = json.loads(FIXTURE.read_text())
        for actual,expected in zip(queries,fixture['native']['rows'],strict=True):
            if actual!={key:expected[key] for key in actual}:
                raise ValueError('Published permutation queries or fixed random inputs changed.')
        if json.loads((SOURCE_ROOT/'sources.json').read_text())!=fixture['sources']:
            raise ValueError('Published permutation source identity changed.')
    result = execute_queries(queries,output,name='published-r-permutations')
    if FIXTURE.exists():
        for name in ('R','webR','wasm_sha256'):
            if result[name]!=fixture['native'][name]:
                raise ValueError('Published permutation runtime changed: '+name)
    return result


def freeze(output):
    if FIXTURE.exists():
        raise FileExistsError('Preserve the independent permutation fixture.')
    native = execute(output)
    rows = []
    for row in cases():
        values = mathematical(row)
        rows.append({**row,'mathematical_values':[None if math.isnan(v) else v for v in values],
                     'mathematical_nonfinite':['nan' if math.isnan(v) else None for v in values]})
    payload = {'schema_version':1,'rows':rows,'native':native,
        'sources':json.loads((SOURCE_ROOT/'sources.json').read_text()),
        'reason':'Complete rank-null distributions and metadata, including tied and degenerate designs, exact/sample crossover, seed and sample count.',
        'scope':'Published unchanged native R inference and exact-fraction/70-digit tails; common recorded NumPy random draws for sampled assignments. Undefined all-tied inference is NaN; zero residual variance with zero contrast uses the declared no-evidence extension p=1.'}
    FIXTURE.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n',encoding='utf-8')


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--freeze',action='store_true')
    args = parser.parse_args()
    freeze(args.output) if args.freeze else execute(args.output)
