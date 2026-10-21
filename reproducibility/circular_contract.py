"""Whole circular statistics and Rayleigh reference contracts; retain raw native and mathematical
answers plus complete input/source/version identities in a new output directory.
No plots or biological inputs. Production is compared only after references run.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
from importlib.metadata import version, distribution
import mpmath as mp
from reproducibility.reference_runtime import execute_queries,values

FIXTURE = Path(__file__).with_name('fixtures')/'circular_contract_reference.json'
PRECISION = 80


def cases():
    inputs = {'ordinary':[1,3,5,6,8,9,10], 'wraparound':[23,23.5,0,.5,1],
              'asymmetric':[2,2.5,3,4,7,13,20], 'constant':[3]*8,
              'singleton':[5], 'empty':[], 'uniform':[0,6,12,18],
              'missing':[1,None,2,'Inf',3,'-Inf',4],
              'missing_only':[None,'Inf','-Inf'],
              'zero_boundary':[0,24,48,72],
              'multiple_cycles':[-47,-23,1,25,49,73],
              'large_cycles':[2400000001,2400000002,2400000003,2400000004]}
    # The sample-size boundary is part of the published method, not a tuned
    # tolerance. Moderate concentration keeps small tail errors observable.
    for n in (2,3,8,20,49,50,51,100,200):
        inputs[f'boundary_{n}'] = [((i*7)%24)+.125*(i%3) for i in range(n)]
        inputs[f'cluster_{n}'] = [2+(i%11)*.43 for i in range(n)]
    result = []
    for name,data in inputs.items():
        for period in (24.,360.,1.):
            scaled = [v/24*period if isinstance(v,(int,float)) else v for v in data]
            for method in ('circular_stats','rayleigh_test'):
                result.append({'key':f'circular.full.{method}.{name}.{period}',
                    'capability':'PyFLASH.stats_extra.'+method,
                    'parameters':{'values':scaled,'period':period}})
    return result


def samples(row):
    return [float(v) for v in row['parameters']['values'] if v is not None and math.isfinite(float(v))]


def mathematical(row):
    with mp.workdps(PRECISION):
        data = samples(row)
        if not data:
            return [0,math.nan,math.nan,math.nan,math.nan]
        period = mp.mpf(row['parameters']['period'])
        # All executed programs receive binary64 values. Converting through a
        # decimal display string invents a different large-cycle input.
        angles = [(mp.mpf(v)%period)*2*mp.pi/period for v in data]
        c = mp.fsum(mp.cos(a) for a in angles)/len(data)
        s = mp.fsum(mp.sin(a) for a in angles)/len(data)
        r = mp.sqrt(c*c+s*s)
        mean = mp.nan if r<mp.mpf('2.220446049250313e-16') else (mp.atan2(s,c)%(2*mp.pi))*period/(2*mp.pi)
        if not mp.isnan(mean) and abs(mean-period)<mp.mpf('1e-60'):
            mean = mp.mpf(0)
        n = len(data)
        z = n*r*r
        factor = (1+(2*z-z*z)/(4*n)-(24*z-132*z*z+76*z**3-9*z**4)/(288*n*n)) if n<50 else 1
        p = min(max(mp.exp(-z)*factor,0),1)
        return [n,float(mean),float(r),float(z),float(p)]


def native_source():
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    kernel = fixture['reference_kernel']
    if hashlib.sha256(kernel.encode()).hexdigest() != fixture['reference_kernel_sha256']:
        raise ValueError('Frozen native circular kernel changed.')
    return kernel


def r_query(row):
    data = samples(row)
    if not data:
        return 'c(0,NaN,NaN,NaN,NaN)'
    source = 'c('+','.join(repr(v) for v in data)+')'
    period = row['parameters']['period']
    return ('local({'+native_source()+f'; raw <- {source}; period <- {period}; '
        'a <- (raw%%period)*(2*pi/period); n <- length(a); answer <- RayleighTestRad(a); '
        'r <- answer$statistic; phase <- atan2(sum(sin(a)),sum(cos(a)))%%(2*pi)*period/(2*pi); '
        'if(r<=.Machine$double.eps) phase <- NaN; '
        'if(is.finite(phase) && abs(phase-period)<=.Machine$double.eps*period) phase <- 0; '
        'c(n,phase,r,n*r*r,answer$p.value) })')


def astropy_reference(row):
    import numpy as np
    from astropy.stats import circmean, circvar, rayleightest
    data = samples(row)
    if not data:
        return [0,math.nan,math.nan,math.nan,math.nan]
    period = row['parameters']['period']
    angle = np.remainder(np.asarray(data),period)*2*np.pi/period
    r = float(1-circvar(angle))
    mean = float((circmean(angle)%(2*np.pi))*period/(2*np.pi)) if r>np.finfo(float).eps else math.nan
    if math.isfinite(mean) and abs(mean-period)<=np.finfo(float).eps*period:
        mean = 0.
    n = len(data)
    return [n,mean,r,n*r*r,min(max(float(rayleightest(angle)),0),1)]


def production(row):
    from PyFLASH import stats_extra
    data = [float(v) if v is not None else None for v in row['parameters']['values']]
    method = row['capability'].rsplit('.',1)[-1]
    answer = getattr(stats_extra,method)(data,period=row['parameters']['period'])
    expected_keys = {'n','mean','r','rayleigh_z','rayleigh_p'} if method=='circular_stats' else {'n','mean','r','z','p'}
    assert set(answer)==expected_keys
    return [answer[k] for k in ('n','mean','r','rayleigh_z','rayleigh_p')] if method=='circular_stats' else [answer[k] for k in ('n','mean','r','z','p')]


def coordinates(answer,period):
    """All five output fields, with the mean represented by its cyclic identity."""
    phase = answer[1]*2*math.pi/period
    return [answer[0],math.cos(phase),math.sin(phase),*answer[2:]]


def _published_source():
    """Verify the exact unmodified CRAN kernel before a fresh native execution."""
    import io
    import shutil
    import tarfile
    import urllib.request
    from reproducibility.reference_runtime import root
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    source = next(r for r in fixture['sources'] if r['package']=='circular')
    cache = root().parent/'circular'/('circular_'+source['version']+'.tar.gz')
    cache.parent.mkdir(parents=True,exist_ok=True)
    if not cache.exists():
        if shutil.disk_usage(cache.parent).free < 8*1024**2:
            raise RuntimeError('Circular verification source needs 8 MB free local space.')
        data = urllib.request.urlopen(source['url'],timeout=30).read()
        if hashlib.sha256(data).hexdigest() != source['archive_sha256']:
            raise ValueError('Published circular archive changed.')
        from PyFLASH._persistence import atomic_replace
        temporary = cache.with_suffix('.tmp')
        temporary.write_bytes(data)
        atomic_replace(temporary,cache)
    data = cache.read_bytes()
    if hashlib.sha256(data).hexdigest() != source['archive_sha256']:
        raise ValueError('Cached circular archive changed.')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        member = next(r for r in source['files'] if r['member'].endswith('/rayleigh.test.R'))
        code = archive.extractfile(member['member']).read()
    if hashlib.sha256(code).hexdigest() != member['sha256'] or native_source() not in code.decode():
        raise ValueError('Executed kernel differs from the pinned published source.')
    return {'archive_sha256':source['archive_sha256'],'source_sha256':member['sha256']}


def execute(output):
    """Execute both accepted packages; mathematical values remain separate."""
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    if version('astropy') != fixture['astropy_version']:
        raise ValueError('Pinned Astropy reference version changed.')
    path = distribution('astropy').locate_file('astropy/stats/circstats.py')
    if hashlib.sha256(path.read_bytes()).hexdigest() != fixture['astropy_source_sha256']:
        raise ValueError('Pinned Astropy reference source changed.')
    source = _published_source()
    result = execute_queries([{**row,'code':r_query(row)} for row in cases()],output,name='circular')
    result.update(published_source=source,astropy_version=version('astropy'),
                  astropy_source_sha256=fixture['astropy_source_sha256'])
    for row in result['rows']:
        row['astropy_values'] = astropy_reference(row)
    return result
