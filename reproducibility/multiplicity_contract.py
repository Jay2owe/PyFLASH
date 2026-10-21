"""All p-value adjustment methods: native R and exact mathematical benchmarks."""
from __future__ import annotations
from fractions import Fraction as F
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name('fixtures')/'multiplicity_contract_reference.json'
ALIASES = {
    'bonferroni':['b','bonf','bonferroni'], 'sidak':['s','sidak'], 'holm':['h','holm'],
    'holm-sidak':['hs','holm-sidak'], 'simes-hochberg':['sh','simes-hochberg'], 'hommel':['ho','hommel'],
    'fdr_bh':['fdr_bh','fdr_i','fdr_p','fdri','fdrp'],
    'fdr_by':['fdr_by','fdr_n','fdr_c','fdrn','fdrcorr'],
    'fdr_tsbh':['fdr_tsbh','fdr_2sbh'], 'fdr_tsbky':['fdr_tsbky','fdr_2sbky','fdr_twostage'],
    'fdr_gbs':['fdr_gbs'],
}
VECTORS = [[.04,.001,.2,.012,.7,.06], [.01,.01,.05,.2,.2], [], [None,'Inf'],
           [0], [1], [1e-200,1e-15,.3,1.0], [.001,.002,.004,.007,.01,.015],
           [.0003,None,.019,'Inf',.08], [.001,.012,.033,.06,.15,.3]]


def cases():
    rows = []
    def add(method, canonical, values):
        rows.append({'key':f'multiplicity.{len(rows)}','capability':'PyFLASH.stats_extra.adjust_pvalues',
                     'parameters':{'method':method,'pvalues':values},'canonical':canonical})
    for canonical, aliases in ALIASES.items():
        for vector in VECTORS:
            add(canonical,canonical,vector)
        for alias in aliases:
            if alias != canonical:
                add(alias,canonical,VECTORS[0])
        add(canonical.upper(),canonical,VECTORS[0])
    return rows


def _step_up(values, factors):
    return [min(F(1),*(values[j]*factors[j] for j in range(i,len(values))))
            for i in range(len(values))]


def reference(row):
    """Exact rational truth; Hommel uses exhaustive closed Simes intersections."""
    raw = row['parameters']['pvalues']
    finite = [i for i,v in enumerate(raw) if v is not None and v != 'Inf']
    order = sorted(finite,key=lambda i:raw[i])
    values = [F(str(raw[i])) for i in order]
    m, method = len(values),row['canonical']
    adjusted = []
    if m:
        if method == 'bonferroni':
            adjusted = [min(F(1),v*m) for v in values]
        elif method == 'sidak':
            adjusted = [1-(1-v)**m for v in values]
        elif method in {'holm','holm-sidak'}:
            bounds = [v*(m-i) if method=='holm' else 1-(1-v)**(m-i) for i,v in enumerate(values)]
            adjusted = [min(F(1),max(bounds[:i+1])) for i in range(m)]
        elif method == 'simes-hochberg':
            adjusted = _step_up(values,[F(m-i) for i in range(m)])
        elif method == 'hommel':
            # Closed testing: adjusted p_i is the worst Simes local p-value
            # among every intersection hypothesis containing hypothesis i.
            adjusted = [F(0)]*m
            for size in range(1,m+1):
                for subset in itertools.combinations(range(m),size):
                    local = min(F(1),*(values[index]*F(size,rank+1) for rank,index in enumerate(subset)))
                    for index in subset:
                        adjusted[index] = max(adjusted[index],local)
        elif method in {'fdr_bh','fdr_by','fdr_tsbh','fdr_tsbky'}:
            harmonic = sum((F(1,i) for i in range(1,m+1)),F(0)) if method=='fdr_by' else F(1)
            adjusted = _step_up(values,[F(m,i+1)*harmonic for i in range(m)])
            if method.startswith('fdr_ts'):
                factor = F(21,20) if method=='fdr_tsbky' else F(1)
                first_reject = sum(v <= F(1,20)/factor for v in adjusted)
                remaining = F(m-first_reject,m) if 0 < first_reject < m else F(1)
                adjusted = [min(F(1),v*factor*remaining) for v in adjusted]
        else:
            bounds = [math.inf if v==1 else F(m-i,i+1)*v/(1-v) for i,v in enumerate(values)]
            running = [max(bounds[:i+1]) for i in range(m)]
            adjusted = [min(F(1),*running[i:]) for i in range(m)]
    corrected = [math.nan]*len(raw)
    for index,value in zip(order,adjusted):
        corrected[index] = float(value)
    rejected = [False]*len(raw)
    for index,value in zip(order,adjusted):
        rejected[index] = value <= F(1,20)
    return [len(raw),*map(int,rejected),*corrected]


def r_query(row):
    raw = row['parameters']['pvalues']
    values = ','.join('NA_real_' if v is None else 'Inf' if v=='Inf' else repr(v) for v in raw)
    vector = 'c('+values+')' if raw else 'numeric(0)'
    method = row['canonical']
    native = {'bonferroni':'bonferroni','holm':'holm','simes-hochberg':'hochberg',
              'hommel':'hommel','fdr_bh':'BH','fdr_by':'BY'}
    prefix = f'local({{original <- {vector}; good <- which(is.finite(original)); p <- original[good]; m <- length(p); '
    if method in native:
        calculation = f'a <- p.adjust(p, method="{native[method]}")'
    else:
        start = 'o <- order(p); s <- p[o]; i <- seq_len(m); '
        if method == 'sidak':
            core = 'q <- -expm1(m*log1p(-s))'
        elif method == 'holm-sidak':
            core = 'q <- cummax(-expm1((m-i+1)*log1p(-s)))'
        elif method == 'fdr_gbs':
            core = 'q <- rev(cummin(rev(cummax((m+1-i)/i*s/(1-s)))))'
        else:
            factor = '1.05' if method=='fdr_tsbky' else '1'
            core = ('q <- p.adjust(s,"BH"); factor <- '+factor+'; '
                    'first <- sum(q <= 0.05/factor); '
                    'remaining <- if(first>0 && first<m) (m-first)/m else 1; q <- q*factor*remaining')
        calculation = start+core+'; a <- numeric(m); a[o] <- pmin(q,1)'
    return (prefix+'if(m) {'+calculation+'} else {a <- numeric(0)}; '
            'out <- rep(NA_real_,length(original)); out[good] <- a; '
            'rejected <- rep(FALSE,length(original)); rejected[good] <- a<=0.05; '
            'c(length(original),as.numeric(rejected),out)})')


def execute(output):
    from reproducibility.reference_runtime import ensure
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    runtime = ensure()
    queries = [{**row,'code':r_query(row)} for row in cases()]
    source,answer = output/'multiplicity-queries.json',output/'multiplicity-results.json'
    source.write_text(json.dumps(queries,indent=2)+'\n',encoding='utf-8')
    completed = subprocess.run(['node','--import',(ROOT/'reproducibility/windows_r_loader.mjs').as_uri(),
        str(ROOT/'reproducibility/run_native_r.mjs'),str(source),str(answer),str(runtime)],
        cwd=ROOT,capture_output=True,text=True,timeout=180)
    (output/'multiplicity.log').write_text(completed.stdout+completed.stderr,encoding='utf-8')
    if completed.returncode:
        raise RuntimeError('Native multiplicity reference failed; see multiplicity.log.')
    result = json.loads(answer.read_text(encoding='utf-8'))
    if any(row['status']!='executed' for row in result['rows']):
        raise RuntimeError('A native multiplicity query failed; retain results.')
    return result


def production(row):
    from PyFLASH.stats_extra import adjust_pvalues
    values = [math.nan if v is None else math.inf if v=='Inf' else v for v in row['parameters']['pvalues']]
    rejected,adjusted = adjust_pvalues(values,method=row['parameters']['method'])
    return [len(values),*map(int,rejected),*adjusted]


def freeze(output,reason):
    if FIXTURE.exists() or not reason.strip():
        raise ValueError('Preserve prior references; a scientific reason is required.')
    result = execute(output)
    import numpy as np
    for row in result['rows']:
        expected = reference(row)
        np.testing.assert_allclose([math.nan if v is None else v for v in row['values']],expected,
                                   rtol=1e-9,atol=1e-12,equal_nan=True,err_msg=row['key'])
        row['exact_benchmark'] = [v if math.isfinite(v) else None for v in expected]
        row['reference_family'] = 'native R stats::p.adjust' if row['canonical'] in {
            'bonferroni','holm','simes-hochberg','hommel','fdr_bh','fdr_by'} else 'native R published-formula implementation'
    result.update(schema_version=1,reason=reason,reference_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        convention='finite probabilities only enter the correction family; nonfinite values remain missing with reject false; alpha 0.05; two-stage adjustments are alpha-specific with one update',
        sources=['https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html',
                 'https://www.math.tau.ac.il/~yekutiel/papers/KBY%20--%20adaptive%20FDR.pdf',
                 'https://arxiv.org/abs/0903.5373'],
        alternatives=[{'candidate':'mutoss 0.1-13 two.stage, commit 83aaaa4da56d7dbf65879027303001d8ccfe5caf',
            'source':'https://github.com/cran/mutoss/blob/83aaaa4da56d7dbf65879027303001d8ccfe5caf/R/moreSUDprocedures.R',
            'outcome':'source inspected; adjusted p-values invert rejection over alpha rather than return the fixed-alpha, one-update scaled BH values; no complete-method equivalence claimed'}])
    FIXTURE.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reason',required=True)
    args = parser.parse_args()
    result = freeze(args.output,args.reason)
    print(f"{len(result['rows'])} native R and exact rational reference cases agree.")
