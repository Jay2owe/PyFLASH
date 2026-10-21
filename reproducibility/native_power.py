"""Complete power contracts against directly executed R noncentral-t tails."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import subprocess

FIXTURE = Path(__file__).with_name('fixtures')/'native_power_reference.json'
ROOT = Path(__file__).resolve().parents[1]


def cases():
    rows = []
    def add(name, params):
        rows.append({'key':f'native.power.{name}.{len(rows)}',
                     'capability':'PyFLASH.stats_extra.'+name, 'parameters':params})
    for effect in (-.8, 0, .1, .5, 2., 10., None):
        for n1, n2 in ((1,None), (3,None), (10,20), (24,8), (20,0)):
            for alpha in (.01, .05, .1):
                add('achieved_power',dict(effect_size=effect,n1=n1,n2=n2,alpha=alpha))
    for effect in (-.8, 0, .1, .5, 2., 10., None):
        for alpha in (.01, .05, .1):
            for power in (.5, .8, .95):
                add('required_n',dict(effect_size=effect,alpha=alpha,power=power))
    return rows


def r_query(row):
    p = row['parameters']
    effect = p['effect_size']
    if effect is None or (row['capability'].endswith('achieved_power') and p['n1'] < 2) or (row['capability'].endswith('required_n') and effect == 0):
        return 'NaN'
    if row['capability'].endswith('achieved_power'):
        n1, n2 = p['n1'], p['n2'] or p['n1']
        return (f'local({{df <- {n1+n2-2}; critical <- qt(1-{p["alpha"]}/2, df); '
                f'ncp <- {abs(effect)}/sqrt(1/{n1}+1/{n2}); '
                'pt(-critical, df, ncp=ncp)+pt(critical, df, ncp=ncp, lower.tail=FALSE)})')
    return (f'local({{target <- {p["power"]}; effect <- {abs(effect)}; alpha <- {p["alpha"]}; '
            'fun <- function(n) {df <- 2*n-2; critical <- qt(1-alpha/2, df); '
            'ncp <- effect*sqrt(n/2); '
            'pt(-critical, df, ncp=ncp)+pt(critical, df, ncp=ncp, lower.tail=FALSE)-target}; '
            'uniroot(fun, c(1+1e-7, 1e7), tol=1e-12)$root})')


def execute(output):
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    from reproducibility.reference_runtime import ensure
    runtime = ensure()
    queries = [{**row, 'code':r_query(row)} for row in cases()]
    source = output/'native-power-queries.json'
    source.write_text(json.dumps(queries,indent=2)+'\n',encoding='utf-8')
    answer = output/'native-power-results.json'
    completed = subprocess.run(['node', '--import', (ROOT/'reproducibility/windows_r_loader.mjs').as_uri(),
        str(ROOT/'reproducibility/run_native_r.mjs'),str(source),str(answer),str(runtime)],
        cwd=ROOT,capture_output=True,text=True,timeout=180)
    (output/'native-power.log').write_text(completed.stdout+completed.stderr,encoding='utf-8')
    if completed.returncode:
        raise RuntimeError('Native R reference failed; see native-power.log.')
    result = json.loads(answer.read_text(encoding='utf-8'))
    if any(row['status'] != 'executed' for row in result['rows']):
        raise RuntimeError('A native R query failed; retain native-power-results.json.')
    return result


def production(row):
    from PyFLASH import stats_extra
    parameters = {key:(math.nan if key == 'effect_size' and value is None else value)
                  for key,value in row['parameters'].items()}
    return [getattr(stats_extra,row['capability'].rsplit('.',1)[-1])(**parameters)]


def freeze(output, reason):
    if FIXTURE.exists():
        raise ValueError('Preserve the existing native fixture.')
    if not reason.strip():
        raise ValueError('A scientific reason is required.')
    result = execute(output)
    result.update(schema_version=1, reason=reason,
        sources=['https://stat.ethz.ch/R-manual/R-devel/library/stats/html/power.t.test.html'],
        convention='two-sided, both rejection tails (strict TRUE); equal or unequal independent groups; fractional required sample-size root')
    FIXTURE.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--freeze',action='store_true')
    parser.add_argument('--reason',default='')
    args = parser.parse_args()
    if args.freeze:
        freeze(args.output,args.reason)
    else:
        execute(args.output)
