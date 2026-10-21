"""Complete circular-linear correlation against R/Statsmodels linear fits.

The declared significance method is the two-predictor F test, not Pingouin's
asymptotic chi-square probability. Mathematical least squares is separate.
"""
from pathlib import Path
import math
import random
import mpmath as mp
from reproducibility.reference_runtime import execute_queries

FIXTURE = Path(__file__).with_name('fixtures')/'circular_linear_reference.json'
PRECISION = 80


def cases():
    angles = [1., 2., 4., 6., 8., 13., 16., 21.]
    noise = [2., 1., 3., 5., 4., 7., 8., 6.]
    rng = random.Random(20261004)
    patterns = {
        'ordinary': (angles, noise), 'reverse': (angles, list(reversed(noise))),
        'perfect_cosine': (angles, [math.cos(v*math.pi/12) for v in angles]),
        'perfect_mixed': (angles, [4+2*math.cos(v*math.pi/12)-3*math.sin(v*math.pi/12) for v in angles]),
        'missing': ([1., None, 4., 6., 'Inf', 13., 16., 21.], noise),
        'pairwise_missing': (angles, [2., 1., None, 5., 4., '-Inf', 8., 6.]),
        'constant_x': (angles, [3.]*len(angles)),
        'constant_angle': ([3.]*len(angles), noise),
        'two_angles': ([0., 12.]*4, noise), 'empty': ([], []),
        'singleton': ([3.], [4.]), 'three': (angles[:3], noise[:3]),
        'four': (angles[:4], noise[:4]),
        'shifted_cycles': ([v+24*(i-4) for i,v in enumerate(angles)], noise),
        'large_cycles': ([v+2400000000 for v in angles], noise),
        'noisy_40': ([rng.uniform(-48, 72) for _ in range(40)], [rng.uniform(-4, 9) for _ in range(40)]),
    }
    rows = []
    for name, (theta, x) in patterns.items():
        for period in (1., 24., 360.):
            phase = [v/24*period if isinstance(v, (int, float)) else v for v in theta]
            rows.append({'key': f'circular.linear.{name}.{period}',
                'capability': 'PyFLASH.stats_extra.circular_linear_corr',
                'parameters': {'theta_values': phase, 'x': x, 'period': period}})
    return rows


def samples(row):
    p = row['parameters']
    pairs = [(float(a), float(x)) for a,x in zip(p['theta_values'],p['x'],strict=True)
             if a is not None and x is not None and math.isfinite(float(a)) and math.isfinite(float(x))]
    return pairs


def mathematical(row):
    with mp.workdps(PRECISION):
        pairs = samples(row)
        n = len(pairs)
        undefined = [math.nan, math.nan, math.nan, n]
        if n < 4:
            return undefined
        period = mp.mpf(row['parameters']['period'])
        a = [(mp.mpf(t)%period)*2*mp.pi/period for t,x in pairs]
        y = mp.matrix([mp.mpf(x) for t,x in pairs])
        c, s = [[f(v) for v in a] for f in (mp.cos, mp.sin)]
        def centered(v):
            mean = mp.fsum(v)/n
            return [x-mean for x in v]
        cc, ss, yy = map(centered, (c, s, list(y)))
        cv, sv, yv = [mp.fsum(x*x for x in v) for v in (cc,ss,yy)]
        if min(cv, sv, yv) < mp.mpf('1e-65'):
            return undefined
        cross = mp.fsum(x*z for x,z in zip(cc,ss))
        if abs(1-cross*cross/(cv*sv)) < mp.mpf('1e-12'):
            return undefined
        design = mp.matrix([[1, x, z] for x,z in zip(c,s)])
        beta = mp.lu_solve(design.T*design, design.T*y)
        residual = y-design*beta
        error = mp.fsum(v*v for v in residual)
        r2 = min(max(1-error/yv, 0), 1)
        # F(2,n-3) survival function is (1-R²)^((n-3)/2).
        p = (1-r2)**(mp.mpf(n-3)/2)
        return [float(mp.sqrt(r2)), float(r2), float(p), n]


def statsmodels_reference(row):
    import numpy as np
    import statsmodels.api as sm
    pairs = samples(row)
    n = len(pairs)
    if n < 4:
        return [math.nan, math.nan, math.nan, n]
    t, y = np.asarray(pairs).T
    a = np.remainder(t,row['parameters']['period'])*2*np.pi/row['parameters']['period']
    c,s = np.cos(a),np.sin(a)
    if y.std()==0 or c.std()==0 or s.std()==0 or abs(1-np.corrcoef(c,s)[0,1]**2)<1e-12:
        return [math.nan,math.nan,math.nan,n]
    fit = sm.OLS(y,sm.add_constant(np.column_stack((c,s)))).fit()
    r2 = min(max(float(fit.rsquared),0),1)
    return [math.sqrt(r2),r2,float(fit.f_pvalue),n]


def r_query(row):
    pairs = samples(row)
    n = len(pairs)
    if n < 4:
        return f'c(NaN,NaN,NaN,{n})'
    t,y = zip(*pairs)
    vector = lambda v: 'c('+','.join(repr(x) for x in v)+')'
    period = row['parameters']['period']
    return (f'local({{ t <- {vector(t)}; y <- {vector(y)}; '
        f'a <- (t%%{period})*(2*pi/{period}); c <- cos(a); s <- sin(a); n <- length(y); '
        'if(sd(y)==0 || sd(c)==0 || sd(s)==0 || abs(1-cor(c,s)^2)<1e-12) '
        'c(NaN,NaN,NaN,n) else { model <- lm(y~c+s); fit <- summary(model); '
        'r2 <- min(max(fit$r.squared,0),1); f <- fit$fstatistic; '
        'c(sqrt(r2),r2,pf(f[1],f[2],f[3],lower.tail=FALSE),n) } })')


def execute(output):
    return execute_queries([{**row,'code':r_query(row)} for row in cases()],output,name='circular-linear')


def production(row):
    from PyFLASH.stats_extra import circular_linear_corr
    p = row['parameters']
    convert = lambda items: [float(v) if v is not None else None for v in items]
    answer = circular_linear_corr(convert(p['theta_values']),convert(p['x']),period=p['period'])
    assert set(answer)=={'r','r_squared','p','n'}
    return [answer[k] for k in ('r','r_squared','p','n')]
