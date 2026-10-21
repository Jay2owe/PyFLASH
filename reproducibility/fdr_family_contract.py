"""Complete labelled/family correction tables at the caller's chosen alpha."""
from __future__ import annotations
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
from reproducibility import multiplicity_contract as multiplicity
from reproducibility.reference_runtime import execute_queries, values

FIXTURE = Path(__file__).with_name('fixtures')/'fdr_family_contract_reference.json'


def cases():
    rows = []
    vectors = [[.001,.01,.01,.05,.2,.8], [.0003,None,.019,'Inf',.08,1]]
    labels = ['marker-A','marker-B','marker-C','marker-D','marker-E','marker-F']
    family_options = [None, {'marker-A':'glia','marker-C':'glia'},
                      ['glia',None,'glia',None,2,2]]
    def add(method,canonical,**parameters):
        rows.append({'key':f'fdr-family.{len(rows)}','capability':'PyFLASH.stats_extra.apply_fdr',
                     'canonical':canonical,'parameters':{'method':method,**parameters}})
    for method in multiplicity.ALIASES:
        for alpha in (.01,.05,.1):
            for family in family_options:
                for representation in ('list','dict','series'):
                    for vector in vectors:
                        add(method,method,pvalues=vector,labels=labels,families=family,
                            representation=representation,alpha=alpha)
        for alias in [*multiplicity.ALIASES[method],method.upper()]:
            if alias != method:
                add(alias,method,pvalues=vectors[0],labels=labels,families=family_options[2],
                    representation='list',alpha=.1)
        for vector in ([],[None,'Inf'],[0,1],[.01,.01,.05,.2,.2]):
            names = list(range(len(vector)))
            add(method,method,pvalues=vector,labels=names,families=None,
                representation='list',alpha=.05)
        add(method,method,pvalues=[.001,.02,.2,.004],labels=['same','same',3,3],
            families=[None,'glia',None,'glia'],representation='series',alpha=.1)
        for alpha in (0,1):
            add(method,method,pvalues=[0,.02,1],labels=['zero','middle','one'],
                families=None,representation='list',alpha=alpha)
    return rows


def _decoded(raw):
    return [math.nan if v is None else math.inf if v=='Inf' else float(v) for v in raw]


def _families(parameters):
    family = parameters['families']
    labels = parameters['labels']
    return ['all']*len(labels) if family is None else (
        [family.get(label,'all') for label in labels] if isinstance(family,dict) else list(family))


def _identity(value):
    return type(value).__name__+':'+repr(value)


def _codes(items):
    vocabulary = list(dict.fromkeys(_identity(item) for item in items))
    return [vocabulary.index(_identity(item)) for item in items]


def mathematical(row):
    """Exact rational corrections, including independently grouped missing families."""
    parameters = row['parameters']
    raw,labels = parameters['pvalues'],parameters['labels']
    families = _families(parameters)
    alpha = F(str(parameters['alpha']))
    adjusted = [math.nan]*len(raw)
    rejected = [False]*len(raw)
    for family in dict.fromkeys(_identity(value) for value in families):
        positions = [i for i,value in enumerate(families) if _identity(value)==family]
        sub = [raw[i] for i in positions]
        if row['canonical'].startswith('fdr_ts'):
            order = sorted((i for i,value in enumerate(sub) if value is not None and value!='Inf'),key=lambda i:sub[i])
            m = len(order)
            exact = [F(str(sub[i])) for i in order]
            q = multiplicity._step_up(exact,[F(m,i+1) for i in range(m)])
            factor = 1+alpha if row['canonical']=='fdr_tsbky' else F(1)
            first = sum(value <= alpha/factor for value in q)
            remaining = F(m-first,m) if 0<first<m else F(1)
            for index,value in zip(order,q):
                value = min(F(1),value*factor*remaining)
                adjusted[positions[index]] = float(value)
                rejected[positions[index]] = value <= alpha
        else:
            result = multiplicity.reference({'canonical':row['canonical'],'parameters':{'pvalues':sub}})
            for index,value in zip(positions,result[1+len(sub):]):
                adjusted[index] = value
                rejected[index] = value <= float(alpha)
    labels_code,family_code = _codes(labels),_codes(families)
    result = [len(raw),5]
    for i,p in enumerate(_decoded(raw)):
        result.extend([labels_code[i],family_code[i],p,adjusted[i],int(rejected[i])])
    return result


def r_query(row):
    parameters = row['parameters']
    raw = parameters['pvalues']
    codes = _codes(_families(parameters))
    def vector(items):
        return 'c('+','.join('NA_real_' if item is None else 'Inf' if item=='Inf' else repr(item) for item in items)+')' if items else 'numeric(0)'
    alpha = parameters['alpha']
    # Reuse the frozen native method definitions, changing only the calculation
    # suffix. Literal input probabilities must never be rewritten with alpha.
    template = multiplicity.r_query({'canonical':row['canonical'],'parameters':{'pvalues':[]}})
    suffix = template.split('; good <- which(',1)[1]
    suffix = suffix.replace('1.05',repr(1+alpha)).replace('0.05',repr(alpha))
    # Integer factors first avoid a verified one-ulp boundary artifact at
    # p=.2, rank=5, m=6: (.4*.2)/.8 rounds above the exact adjusted p=.1.
    suffix = suffix.replace('(m+1-i)/i*s/(1-s)','(m+1-i)*s/(i*(1-s))')
    expression = 'local({original <- original[index]; good <- which('+suffix
    return ('local({original <- '+vector(raw)+'; family <- '+vector(codes)+'; '
            'label <- '+vector(_codes(parameters['labels']))+'; n <- length(original); '
            'adjusted <- rep(NA_real_,n); rejected <- rep(FALSE,n); '
            'for(group in unique(family)) {index <- which(family==group); z <- '+expression+'; '
            'k <- length(index); rejected[index] <- z[1+seq_len(k)]; '
            'adjusted[index] <- z[1+k+seq_len(k)]}; '
            'c(n,5,as.vector(t(cbind(label,family,original,adjusted,as.numeric(rejected)))))})')


def execute(output):
    return execute_queries([{**row,'code':r_query(row)} for row in cases()],output,name='fdr-family')


def production(row):
    import pandas as pd
    from PyFLASH.stats_extra import apply_fdr
    parameters = row['parameters']
    raw = _decoded(parameters['pvalues'])
    labels = parameters['labels']
    representation = parameters['representation']
    pvalues = dict(zip(labels,raw)) if representation=='dict' else (
        pd.Series(raw,index=labels,dtype=float) if representation=='series' else raw)
    before = pvalues.copy()
    table = apply_fdr(pvalues,labels=labels,families=parameters['families'],
                      method=parameters['method'],alpha=parameters['alpha'])
    assert list(table.columns)==['label','family','p_value','p_adjusted','reject']
    assert table['label'].tolist()==labels
    family = _families(parameters)
    assert table['family'].tolist()==family
    if representation=='series':
        pd.testing.assert_series_equal(pvalues,before,check_exact=True)
    else:
        assert [_identity(v) for v in pvalues]==[_identity(v) for v in before]
    labels_code,family_code = _codes(labels),_codes(family)
    result = [len(table),len(table.columns)]
    for index,record in enumerate(table.itertuples(index=False)):
        result.extend([labels_code[index],family_code[index],record.p_value,record.p_adjusted,int(record.reject)])
    return result


def freeze(output,reason):
    if FIXTURE.exists() or not reason.strip():
        raise ValueError('A reason and a new fixture are required; preserve accepted references.')
    import numpy as np
    result = execute(output)
    for row in result['rows']:
        expected = mathematical(row)
        np.testing.assert_allclose(values(row),expected,rtol=1e-9,atol=1e-12,equal_nan=True,err_msg=row['key'])
        row['mathematical_values'] = [v if math.isfinite(v) else None for v in expected]
        row['mathematical_nonfinite'] = [None if math.isfinite(v) else 'positive_infinity' if v==math.inf else 'nan' for v in expected]
    result.update(schema_version=1,reason=reason,
        reference_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        multiplicity_code_sha256=hashlib.sha256(Path(multiplicity.__file__).read_bytes()).hexdigest(),
        convention='Input order and label/family identities retained; None is one correction family; nonfinite probabilities do not enter family size. Alpha is caller-specific, including two-stage fixed-alpha one-update corrections. GBS integer factors multiply before division to avoid the verified one-ulp adjusted-p=0.1 rejection artifact; original native round retained in .runtime/fdr-family-independent-reference.',
        reference_families=['native R stats::p.adjust for six methods; native R published formulas for five others',
                            'exact rational closed testing and polynomial benchmarks'],
        alternatives=json.loads(multiplicity.FIXTURE.read_text())['alternatives'],
        sources=json.loads(multiplicity.FIXTURE.read_text())['sources'])
    FIXTURE.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reason',required=True)
    arguments = parser.parse_args()
    result = freeze(arguments.output,arguments.reason)
    print(f"{len(result['rows'])} complete family correction references agree.")
