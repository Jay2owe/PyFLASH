"""Complete within-group-concentration Watson-Williams contract.

PyCircStat2 implements the same CircStat/Zar convention. R circular's pooled
concentration convention is retained as a diagnostic, not an extra vote.
"""
from pathlib import Path
import math
import random
import warnings
import mpmath as mp
from reproducibility.reference_runtime import execute_queries

FIXTURE = Path(__file__).with_name('fixtures')/'watson_williams_reference.json'
FIELDS = ['F','p','df1','df2','k','n','R','mean_phase_cos_sin']


def cases():
    rng = random.Random(20261004)
    patterns = {
        'nearby': [[1,2,3,4,5], [2,3,4,5,6]],
        'separated': [[1,2,3,4,5], [9,10,11,12,13]],
        'same': [[1,2,3,4,5], [1,2,3,4,5]],
        'three': [[1,2,3,4], [6,7,8,9,10], [12,13,14,15,16,17]],
        'unequal': [[1,2], [3,4,5,6,7,8,9,10]],
        'singleton_group': [[1], [3,4,5,6]],
        'wrap': [[23,0,1,2,3], [22,23,0,1,2]],
        'loose': [[1,3,6,9,13,16,20], [2,5,8,11,14,18,21]],
        'missing': [[1,None,3,'Inf',5], [2,3,4,None,6]],
        'empty_group': [[], [1,2,3,4], [2,3,4,5]],
        'empty': [], 'one_group': [[1,2,3]], 'singletons': [[1],[3]],
        'constant_same': [[3]*5, [3]*6],
        'constant_separated': [[3]*5, [9]*6],
        'uniform': [[0,6,12,18], [0,6,12,18]],
        'small_resultants': [[0,6,12,18,1], [0,6,12,18,7]],
        'shifted_cycles': [[1,26,-45,76,5], [26,-45,52,5,78]],
        'large_cycles': [[2400000000+v for v in [1,2,3,4,5]],
                         [2400000000+v for v in [2,3,4,5,6]]],
        'noisy': [[rng.uniform(-12,36) for _ in range(n)] for n in [17,23,31]],
    }
    rows = []
    for name, groups in patterns.items():
        for period in (1.,24.,360.):
            converted = [[v/24*period if isinstance(v,(int,float)) else v for v in group]
                         for group in groups]
            rows.append({'key':f'watson.williams.{name}.{period}',
                'capability':'PyFLASH.stats_extra.watson_williams',
                'parameters':{'groups':converted,'period':period}})
    return rows


def samples(row):
    period = row['parameters']['period']
    groups = [[float(v)%period for v in group
               if v is not None and math.isfinite(float(v))]
              for group in row['parameters']['groups']]
    return [g for g in groups if g]


def coordinates(answer, period):
    return [answer[k] for k in ('F','p','df1','df2','k','n','R')] + [
        value for mean in answer['means'] for value in (
            math.cos(mean*2*math.pi/period),math.sin(mean*2*math.pi/period))]


def mathematical(row):
    with mp.workdps(80):
        groups = samples(row)
        k,n = len(groups),sum(map(len,groups))
        if k<2 or n<=k:
            return [math.nan,math.nan,0,0,k,n,math.nan]
        period = mp.mpf(row['parameters']['period'])
        angles = [[mp.mpf(v)*2*mp.pi/period for v in g] for g in groups]
        cs = [(mp.fsum(mp.cos(v) for v in g),mp.fsum(mp.sin(v) for v in g)) for g in angles]
        ri = [mp.sqrt(c*c+s*s) for c,s in cs]
        c,s = mp.fsum(c for c,s in cs),mp.fsum(s for c,s in cs)
        resultant = mp.sqrt(c*c+s*s)
        within = mp.fsum(ri)
        rw = within/n
        if rw < mp.mpf('.53'):
            kap = 2*rw+rw**3+5*rw**5/6
        elif rw < mp.mpf('.85'):
            kap = -mp.mpf('.4')+mp.mpf('1.39')*rw+mp.mpf('.43')/(1-rw)
        elif rw<1:
            kap = 1/(rw**3-4*rw**2+3*rw)
        else:
            kap = mp.inf
        correction = 1+3/(8*kap) if kap>0 else 1
        if all(all(v==g[0] for v in g) for g in groups):
            statistic = mp.inf if any(g[0]!=groups[0][0] for g in groups) else mp.nan
            probability = 0 if statistic==mp.inf else mp.nan
        else:
            statistic = correction*(n-k)*(within-resultant)/((k-1)*(n-within))
            z = (n-k)/(n-k+(k-1)*statistic)
            probability = mp.betainc(mp.mpf(n-k)/2,mp.mpf(k-1)/2,0,z,regularized=True)
        means = []
        for (c,s),r in zip(cs,ri):
            # Uniform groups have no identifiable mean direction.
            means.extend([float(c/r),float(s/r)] if r/n>mp.mpf('1e-15') else [math.nan,math.nan])
        return [float(statistic),float(probability),k-1,n-k,k,n,float(resultant),*means]


def pycircstat_reference(row):
    import numpy as np
    from pycircstat2.hypothesis import watson_williams_test
    from pycircstat2.descriptive import circ_mean, circ_r
    groups = samples(row)
    k,n = len(groups),sum(map(len,groups))
    if k<2 or n<=k:
        return [math.nan,math.nan,0,0,k,n,math.nan]
    period = row['parameters']['period']
    angles = [np.asarray(g)*2*np.pi/period for g in groups]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        answer = watson_williams_test(angles)
    means = [value for a in angles for value in (
        math.cos(circ_mean(a)),math.sin(circ_mean(a)))]
    return [answer.F,answer.pval,answer.df_between,answer.df_within,k,n,
            n*circ_r(np.concatenate(angles)),*means]


def r_query(row, *, pooled=False):
    groups = samples(row)
    k,n = len(groups),sum(map(len,groups))
    if k<2 or n<=k:
        return f'c(NaN,NaN,0,0,{k},{n},NaN)'
    vector = lambda g: 'c('+','.join(repr(v) for v in g)+')'
    period = row['parameters']['period']
    concentration = 'R/N' if pooled else 'sum(Ri)/N'
    return (f'local({{ groups <- list({",".join(vector(g) for g in groups)}); '
        f'a <- lapply(groups,function(g) g*2*pi/{period}); '
        'ns <- lengths(a); N <- sum(ns); k <- length(a); '
        'C <- vapply(a,function(x) sum(cos(x)),0.0); S <- vapply(a,function(x) sum(sin(x)),0.0); '
        'Ri <- sqrt(C*C+S*S); Ri[Ri/ns<.Machine$double.eps] <- 0; '
        'R <- sqrt(sum(C)^2+sum(S)^2); if(R/N<.Machine$double.eps) R <- 0; '
        f'rw <- {concentration}; '
        'kap <- if(rw<.53) 2*rw+rw^3+5*rw^5/6 else if(rw<.85) -.4+1.39*rw+.43/(1-rw) '
        'else if(rw<1) 1/(rw^3-4*rw^2+3*rw) else Inf; '
        'K <- if(is.finite(kap)&&kap>0) 1+3/(8*kap) else 1; '
        'constant <- all(vapply(groups,function(g) all(g==g[1]),TRUE)); '
        'F <- if(constant) { if(length(unique(unlist(groups)))>1) Inf else NaN } '
        'else { B <- 0; for(i in seq_len(k-1)) for(j in (i+1):k) '
        'if(Ri[i]>0&&Ri[j]>0) B <- B+Ri[i]*Ri[j]*'
        '((C[i]/Ri[i]-C[j]/Ri[j])^2+(S[i]/Ri[i]-S[j]/Ri[j])^2); '
        'B <- if(sum(Ri)+R>0) B/(sum(Ri)+R) else 0; '
        'K*(N-k)*B/((k-1)*(N-sum(Ri))) }; '
        'means <- unlist(lapply(seq_len(k),function(i) '
        'if(Ri[i]/ns[i]<1e-15) c(NaN,NaN) else c(C[i]/Ri[i],S[i]/Ri[i]))); '
        'c(F,pf(F,k-1,N-k,lower.tail=FALSE),k-1,N-k,k,N,R,means) })')


def execute(output):
    return execute_queries([{**row,'code':r_query(row)} for row in cases()],output,name='watson-williams')


def production(row):
    from PyFLASH.stats_extra import watson_williams
    p = row['parameters']
    groups = [[float(v) if v is not None else None for v in g] for g in p['groups']]
    answer = watson_williams(groups,period=p['period'])
    assert set(answer)=={'F','p','df1','df2','k','n','means','R'}
    return coordinates(answer,p['period'])
