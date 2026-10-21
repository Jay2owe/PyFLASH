"""Power benchmark from independent Gaussian/gamma quadrature and beta tails.

No production function or noncentral-t distribution is called. SciPy supplies
only a starting guess for the central-t quantile, refined by independent
high-precision beta-tail mathematics. Native R roots supply starting guesses
for a separate mpmath solver, whose objective uses the full quadrature.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from reproducibility import native_power

FIXTURE = Path(__file__).with_name('fixtures')/'power_integral_reference.json'


def power(effect, first, second, alpha):
    import mpmath as mp
    from scipy.stats import t
    degrees = first+second-2
    alpha = mp.mpf(str(alpha))
    guess = float(t.isf(float(alpha)/2,float(degrees)))
    def central_tail(value):
        return mp.betainc(degrees/2, mp.mpf('.5'), 0,
                         degrees/(degrees+value*value), regularized=True)/2
    critical = mp.findroot(lambda value:central_tail(value)-alpha/2,
                           (mp.mpf(guess)*mp.mpf('.99'),mp.mpf(guess)*mp.mpf('1.01')))
    noncentral = abs(mp.mpf(str(effect)))/mp.sqrt(1/first+1/second)
    log_constant = mp.log(2)+(degrees/2)*mp.log(degrees/2)-mp.loggamma(degrees/2)
    def integrand(s):
        if not s:
            return mp.mpf(0)
        tails = (mp.erfc((critical*s-noncentral)/mp.sqrt(2))+
                 mp.erfc((critical*s+noncentral)/mp.sqrt(2)))/2
        return tails*mp.exp(log_constant+(degrees-1)*mp.log(s)-degrees*s*s/2)
    width = 1/mp.sqrt(degrees)
    mesh = sorted({mp.mpf(0),mp.mpf('.25'),mp.mpf('.5'),mp.mpf(1),mp.mpf(2),mp.mpf(4),
                   *[1+multiple*width for multiple in (-8,-4,-2,-1,1,2,4,8) if 1+multiple*width > 0]})
    return mp.quad(integrand,mesh+[mp.inf])


def reference(row, guess=None):
    import mpmath as mp
    params = row['parameters']
    effect = params['effect_size']
    if effect is None or (row['capability'].endswith('achieved_power') and params['n1'] < 2) or (row['capability'].endswith('required_n') and effect == 0):
        return [math.nan]
    with mp.workdps(45):
        if row['capability'].endswith('achieved_power'):
            first = mp.mpf(params['n1'])
            second = mp.mpf(params['n2'] or params['n1'])
            return [float(power(effect,first,second,params['alpha']))]
        if guess is None:
            native = json.loads(native_power.FIXTURE.read_text(encoding='utf-8'))
            guess = next(r['values'][0] for r in native['rows'] if r['key'] == row['key'])
        center = mp.mpf(guess)
        target = mp.mpf(str(params['power']))
        root = mp.findroot(lambda n:power(effect,n,n,params['alpha'])-target,
            (center*mp.mpf('.99999'),center*mp.mpf('1.00001')),tol=mp.mpf('1e-22'))
        return [float(root)]


def freeze(reason):
    if FIXTURE.exists():
        raise ValueError('Preserve the existing integral fixture.')
    if not reason.strip():
        raise ValueError('A scientific reason is required.')
    from importlib.metadata import version
    native = json.loads(native_power.FIXTURE.read_text(encoding='utf-8'))
    rows = []
    for row in native['rows']:
        answer = reference(row,row['values'][0])
        rows.append({**{key:row[key] for key in ('key','capability','parameters')},
                     'expected':[value if math.isfinite(value) else None for value in answer]})
        print(row['key'],flush=True)
    FIXTURE.write_text(json.dumps({'schema_version':1,'reason':reason,'rows':rows,
        'versions':{name:version(name) for name in ('mpmath','scipy')},
        'reference':'45-digit Gaussian/gamma integral, independent beta-tail quantile and mpmath sample-size root',
        'reference_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'starting_guesses_only':['SciPy central-t quantile','frozen native R sample-size root'],
        'sources':['https://stat.ethz.ch/R-manual/R-devel/library/stats/html/TDist.html']},
        indent=2,allow_nan=False)+'\n',encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',action='store_true')
    parser.add_argument('--reason',default='')
    args = parser.parse_args()
    if args.freeze:
        freeze(args.reason)
