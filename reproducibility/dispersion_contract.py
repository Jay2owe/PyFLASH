"""Independent own-mean circular deviations and complete Kruskal inference.

This is the R circular Wallraff own-mean multi-group definition. PyCircStat2's
two-sample specified-angle/Mann-Whitney definition is different.
"""
import math
import random
import mpmath as mp
from pathlib import Path
from reproducibility.reference_runtime import execute_queries
from reproducibility import dispersion_decimal

FIXTURE = Path(__file__).parent/'fixtures/dispersion_contract_reference.json'


def cases():
    rng = random.Random(20261004)
    patterns = {
        'ordinary':[[1,2,4,7,8],[3,5,9,11,15]],
        'symmetric':[[1,2,3,4,5],[2,4,6,8,10]],
        'same':[[1,2,4,7,8],[1,2,4,7,8]],
        'three':[[1,2,4,7,8],[3,5,9,11,15],[2,5,8,12,18]],
        'unequal':[[1,2],[3,5,9,11,15,17,22]],
        'wrap':[[22,23,1,2,3],[21,23,2,3,4]],
        'missing':[[1,None,4,'Inf',8],[3,5,None,11,15]],
        'omit_small':[[1],[3,5,9,11,15],[],[2,5,8,12,18]],
        'none':[],'one':[[1,2,4]],'small':[[1],[3]],
        'constant_same':[[3]*5,[3]*6],'constant_shifted':[[3]*5,[8]*6],
        'uniform':[[0,6,12,18],[0,6,12,18]],
        'small_resultants':[[0,6,12,18,1],[0,6,12,18,7]],
        'shifted_cycles':[[1,26,-44,79,8],[27,-43,57,11,87]],
        'noisy':[[rng.uniform(-12,36) for _ in range(n)] for n in [17,23,31]],
    }
    return [{'key':f'circular.dispersion.{name}.{period}',
        'capability':'PyFLASH.stats_extra.circular_dispersion_test',
        'parameters':{'period':period,'groups':[[v/24*period if isinstance(v,(int,float)) else v
                      for v in group] for group in groups]}}
        for name,groups in patterns.items() for period in (1.,24.,360.)]


def samples(row):
    period=row['parameters']['period']
    groups=[[float(v)%period for v in g if v is not None and math.isfinite(float(v))]
            for g in row['parameters']['groups']]
    return [g for g in groups if len(g)>=2]


def mathematical(row):
    with mp.workdps(80):
        period=mp.mpf(row['parameters']['period'])
        groups=samples(row)
        k,n=len(groups),sum(map(len,groups))
        deviations,spreads=[],[]
        undefined_mean=False
        for group in groups:
            a=[mp.mpf(v)*2*mp.pi/period for v in group]
            c,s=mp.fsum(mp.cos(v) for v in a),mp.fsum(mp.sin(v) for v in a)
            if mp.sqrt(c*c+s*s)/len(a)<=mp.mpf(float.fromhex('0x1.0000000000000p-52')):
                undefined_mean=True
                spreads.append(math.nan)
                continue
            mean=mp.atan2(s,c)
            d=[abs((v-mean+mp.pi)%(2*mp.pi)-mp.pi) for v in a]
            deviations.append(d)
            spreads.append(float(mp.fsum(d)/len(d)*period/(2*mp.pi)))
        if k<2 or undefined_mean:
            return [math.nan,math.nan,k,n,*spreads]
        pooled=[x for d in deviations for x in d]
        # An 80-digit evaluation of an analytic tie can differ at its final
        # digit. This precision guard is far below any binary64 input spacing.
        clusters=[]
        for value in sorted(pooled):
            if clusters and abs(value-clusters[-1][-1])<mp.mpf('1e-65'):
                clusters[-1].append(value)
            else: clusters.append([value])
        def rank(value):
            less=sum(value>x+mp.mpf('1e-65') for x in pooled)
            tied=sum(abs(value-x)<mp.mpf('1e-65') for x in pooled)
            return mp.mpf(less)+(mp.mpf(tied)+1)/2
        correction=1-mp.mpf(sum(len(g)**3-len(g) for g in clusters))/(n**3-n)
        if correction==0:
            return [math.nan,math.nan,k,n,*spreads]
        statistic=(12*mp.fsum(mp.fsum(rank(x) for x in d)**2/len(d) for d in deviations)
                   /(n*(n+1))-3*(n+1))/correction
        probability=mp.gammainc(mp.mpf(k-1)/2,statistic/2,mp.inf,regularized=True)
        return [float(statistic),float(probability),k,n,*spreads]


def r_query(row):
    groups=samples(row)
    period=row['parameters']['period']
    if not groups: return 'c(NaN,NaN,0,0)'
    vector=lambda g:'c('+','.join(repr(v) for v in g)+')'
    return (f'local({{ groups<-list({",".join(vector(g) for g in groups)}); '
        f'a<-lapply(groups,function(g) g*2*pi/{period}); '
        'dev<-lapply(a,function(g) { m<-atan2(sum(sin(g)),sum(cos(g))); '
        'abs((g-m+pi)%%(2*pi)-pi) }); '
        f'spread<-vapply(dev,mean,0.0)*{period}/(2*pi); '
        'k<-length(a); N<-sum(lengths(a)); '
        'invalid<-vapply(a,function(g) sqrt(sum(cos(g))^2+sum(sin(g))^2)/length(g)<=.Machine$double.eps,TRUE); '
        'spread[invalid]<-NaN; '
        'h<-if(k<2||any(invalid)) c(NaN,NaN) else tryCatch({ v<-kruskal.test(dev); '
        'c(unname(v$statistic),v$p.value) },error=function(e) c(NaN,NaN)); '
        'c(h,k,N,spread) })')


def execute(output):
    return execute_queries([{**row,'code':dispersion_decimal.native_query(row)} for row in cases()],
                           output,name='decimal-geometry-native-r-ranks')


def published_sources():
    import tarfile
    import hashlib
    from reproducibility.reference_runtime import root
    archive = root().parent/'circular'/'circular_0.5-2.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != '3925622cd99d902d2c0e11b85127873f3d301f2b9db05edf722a9c10731f7ddc':
        raise ValueError('Pinned published circular source archive changed')
    with tarfile.open(archive) as package:
        names = ['circular/R/wallraff.test.R','circular/R/range.circular.R','circular/src/mean.circular.c']
        return {n: package.extractfile(n).read().decode() for n in names}


def published_query(row):
    groups, period = samples(row), row['parameters']['period']
    if not groups: return 'c(NaN,NaN,0,0)'
    sources = published_sources()
    vector = lambda g: 'c('+','.join(repr(v) for v in g)+')'
    # The R Wallraff and range kernels execute unchanged. Its compiled C mean
    # cannot run inside WebR; this native R wrapper follows the retained C
    # formula and epsilon test. It is a port, not an unchanged compiled package.
    return ('local({ '+sources['circular/R/wallraff.test.R']+'\n'+sources['circular/R/range.circular.R']+'\n'
            f' a<-list({",".join(vector(g) for g in groups)}); a<-lapply(a,function(g) g*2*pi/{period}); '
            'mu<-vapply(a,function(g) { s<-sum(sin(g)); c<-sum(cos(g)); '
            'if(sqrt(s*s+c*c)/length(g)>.Machine$double.eps) atan2(s,c) else NaN },0.0); '
            'N<-sum(lengths(a)); k<-length(a); '
            f'disp<-vapply(seq_along(a),function(j) mean(vapply(a[[j]],function(v) RangeCircularRad(c(v,mu[j]),FALSE),0.0)),0.0)*{period}/(2*pi); '
            'h<-if(k<2||anyNA(mu)) c(NaN,NaN) else tryCatch({ '
            'z<-WallraffTestRad(unlist(a),factor(rep(seq_along(a),lengths(a))),mu); '
            'c(unname(z$statistic),z$p.value) },error=function(e) c(NaN,NaN)); c(h,k,N,disp) })')


def production(row):
    from PyFLASH.stats_extra import circular_dispersion_test
    groups=[[float(v) if v is not None else None for v in g] for g in row['parameters']['groups']]
    answer=circular_dispersion_test(groups,period=row['parameters']['period'])
    assert set(answer)=={'statistic','p','k','n','dispersions'}
    return [answer[k] for k in ['statistic','p','k','n']]+answer['dispersions']
