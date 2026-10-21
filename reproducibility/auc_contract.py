"""Whole per-subject time-course tables: native quadrature and exact fractions.

Neither reference imports PyFLASH, pandas, NumPy or SciPy. R parses the original
time labels itself; the rational reference separately resolves literal records.
"""
from __future__ import annotations
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
from reproducibility.reference_runtime import execute_queries, values

FIXTURE = Path(__file__).with_name('fixtures') / 'auc_contract_reference.json'


def cases():
    result = []
    for mode in ('numeric', 'mapped', 'digits'):
        times = [3, 0, 1, 1, 6, 0, 2, 5, 2, 0, None, 4]
        if mode == 'mapped':
            times = [None if t is None else 'Visit'+str(t) for t in times]
        elif mode == 'digits':
            times = [None if t is None else 'Week'+str(t)+'end' for t in times]
        for custom in (False, True):
            for grouped in (False, True):
                for baseline in (None, 2, -1.5):
                    names = ('Mouse','Visit','Reading','Cohort') if custom else ('AnimalName','Time','Signal','Group')
                    subjects = ['a']*5+['b']*3+['c']*2+['d']*2
                    groups = ['A']*4+['B']+['B']*3+['A']*4
                    observations = [7,1,3,5,11,6,-2,3,4,None,9,7]
                    records = [dict(zip(names,(s,t,v,g))) for s,t,v,g in zip(subjects,times,observations,groups)]
                    result.append(_case(f'{mode}.{custom}.{grouped}.{baseline}', records, names,
                                        grouped, baseline, {f'Visit{t}':t for t in (0,1,2,3,4,5,6)} if mode == 'mapped' else None))
    names = ('AnimalName','Time','Signal','Group')
    special = {
        'empty': [], 'singleton': [('a',0,1,'A')],
        'all_missing': [('a',None,1,'A'),('b',0,None,'B')],
        'same_time': [('a',1,2,'A'),('a',1,9,'A')],
        'nonfinite': [('a',0,1,'A'),('a',1,3,'A'),('a','Inf',4,'A'),('a',2,'Inf','A')],
        'missing_keys': [(None,0,1,'A'),(None,1,2,'A'),('b',0,1,None),('b',1,4,None)],
        'duplicate_order': [('a',0,1,'A')]+[('a',1,i,'A') for i in range(30)]+[('a',3,7,'A')],
        'mixed_numeric_labels': [('a','0',1,'A'),('a','1',3,'A'),('a','Week2',50,'A')],
        'negative_fractional_time': [('a',-.5,-2,'A'),('a',.25,3,'A'),('a',2.75,4,'A')],
    }
    for name, rows in special.items():
        result.append(_case(name,[dict(zip(names,row)) for row in rows], names,True,None,None))
    records = [dict(zip(names,row)) for row in [('a','0',1,'A'),('a','1',3,'A'),('a','Other',50,'A')]]
    result.append(_case('unmatched_map_fallback',records,names,False,None,{'absent':7}))
    records = [dict(zip(names,row)) for row in [('a','Start',1,'A'),('a','End',3,'A'),('a','Week2',50,'A')]]
    result.append(_case('partial_map',records,names,False,None,{'Start':0,'End':1}))
    return result


def _case(key, records, names, grouped, baseline, time_map):
    return {'key':'auc.'+key,'capability':'PyFLASH.stats_extra.timecourse_auc',
            'parameters':{'records':records,'columns':list(names),'animal_col':names[0],
                          'time_col':names[1],'value_col':names[2],
                          'group_col':names[3] if grouped else None,'time_map':time_map,'baseline':baseline}}


def _numeric(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def identities(row):
    p = row['parameters']
    names = [p['animal_col']]+([p['group_col']] if p['group_col'] else [])
    return names, {name:sorted({str(record[name]) for record in p['records'] if record[name] is not None}) for name in names}


def _times(p):
    source = [r[p['time_col']] for r in p['records']]
    if p['time_map'] and any(p['time_map'].get(t) is not None for t in source):
        return [_numeric(p['time_map'].get(t)) for t in source]
    numeric = [_numeric(t) for t in source]
    if any(not math.isnan(t) for t in numeric):
        return numeric
    return [_numeric(m.group(0)) if (m := re.search(r'\d+\.?\d*',str(t))) else math.nan for t in source]


def mathematical(row):
    p = row['parameters']
    names, labels = identities(row)
    groups = {}
    for record, t in zip(p['records'],_times(p)):
        v = _numeric(record[p['value_col']])
        key = tuple(record[name] for name in names)
        if not all(x is not None for x in key) or not math.isfinite(t) or not math.isfinite(v):
            continue
        groups.setdefault(key,[]).append((Fraction(str(t)),Fraction(str(v))-Fraction(str(p['baseline'] or 0))))
    answer = []
    for key, samples in sorted(groups.items()):
        if len(samples) < 2:
            continue
        samples = sorted(samples,key=lambda x:x[0])  # stable ties retain measurement order
        total = sum(((b[0]-a[0])*(a[1]+b[1])/2 for a,b in zip(samples,samples[1:])),Fraction())
        answer.append([labels[name].index(str(value)) for name,value in zip(names,key)]+[float(total)])
    return [len(answer),len(names)+1]+[value for line in answer for value in line]


def _r_vector(entries):
    return 'c('+','.join('NA_character_' if v is None else json.dumps(str(v)) for v in entries)+')' if entries else 'character()'


def r_query(row):
    p = row['parameters']
    names, labels = identities(row)
    records = p['records']
    source = _r_vector([r[p['time_col']] for r in records])
    observed = _r_vector([r[p['value_col']] for r in records])
    mapping = p['time_map'] or {}
    mapped_values = _r_vector(mapping.values())
    mapped_keys = _r_vector(mapping.keys())
    key_vectors = ','.join(_r_vector([r[name] for r in records]) for name in names)
    label_vectors = ','.join(_r_vector(labels[name]) for name in names)
    baseline = p['baseline'] if p['baseline'] is not None else 0
    return (f'local({{raw <- {source}; v <- suppressWarnings(as.numeric({observed})); '
        f'map <- setNames({mapped_values},{mapped_keys}); mapped <- unname(map[raw]); '
        'if(length(map)>0 && any(!is.na(mapped))) { t <- suppressWarnings(as.numeric(mapped)) } '
        'else { t <- suppressWarnings(as.numeric(raw)); if(!any(!is.na(t))) { '
        'hits <- regexpr("[0-9]+\\\\.?[0-9]*", raw); pieces <- regmatches(raw,hits); '
        't <- rep(NA_real_,length(raw)); t[which(hits>0)] <- as.numeric(pieces) } }; '
        f'keys <- list({key_vectors}); labels <- list({label_vectors}); v <- v-({baseline}); '
        'keep <- is.finite(t) & is.finite(v); for(k in keys) keep <- keep & !is.na(k); '
        'codes <- lapply(seq_along(keys),function(j) match(keys[[j]],labels[[j]])-1); '
        'out <- list(); if(any(keep)) { combos <- unique(as.data.frame(codes)[keep,,drop=FALSE]); '
        'combos <- combos[do.call(order,as.list(combos)),,drop=FALSE]; '
        'for(i in seq_len(nrow(combos))) { selected <- keep; '
        'for(j in seq_along(codes)) selected <- selected & !is.na(codes[[j]]) & codes[[j]]==combos[i,j]; '
        'idx <- which(selected); if(length(idx)<2) next; idx <- idx[order(t[idx],idx)]; '
        'total <- 0; for(j in seq_len(length(idx)-1)) { a <- idx[j]; b <- idx[j+1]; '
        'if(t[b]==t[a]) next; f <- function(x) v[a]+(v[b]-v[a])*(x-t[a])/(t[b]-t[a]); '
        'total <- total + integrate(f,t[a],t[b],rel.tol=1e-12,abs.tol=1e-12)$value }; '
        'out[[length(out)+1]] <- c(unlist(combos[i,,drop=FALSE]),total) } }; '
        f'c(length(out),{len(names)+1},unlist(out)) }})')


def production(row):
    import pandas as pd
    from PyFLASH.stats_extra import timecourse_auc
    p = row['parameters']
    frame = pd.DataFrame(p['records'],columns=p['columns'])
    before = frame.copy(deep=True)
    result = timecourse_auc(frame,**{k:v for k,v in p.items() if k not in ('records','columns')})
    pd.testing.assert_frame_equal(frame,before)
    names, labels = identities(row)
    assert result.columns.tolist() == names+['auc'], result.columns.tolist()
    answer = [len(result),len(result.columns)]
    for values in result.itertuples(index=False,name=None):
        answer.extend([labels[name].index(str(value)) for name,value in zip(names,values[:-1])]+[values[-1]])
    return answer


def execute(output):
    return execute_queries([{**row,'code':r_query(row)} for row in cases()],output,name='auc')


def freeze(output, reason):
    if FIXTURE.exists() or not reason.strip():
        raise ValueError('Preserve existing references; a scientific reason is required.')
    result = execute(output)
    for row in result['rows']:
        exact = mathematical(row)
        native = values(row)
        if len(native) != len(exact) or any(not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-12) for a,b in zip(native,exact)):
            raise ValueError(f'Independent references disagree: {row["key"]}: {native} / {exact}')
        row['mathematical_values'] = exact
    result.update(schema_version=1,reason=reason,
        reference_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        conventions='Piecewise-linear integral in ascending time; stable original order at duplicate times; zero-width intervals contribute zero. Nonfinite or unresolved time/value and missing subject/group keys are omitted. Fewer than two observations yields no subject row. Finite baseline subtracts from each value. Explicit mapping if any label matches, otherwise numeric parsing if any value parses, otherwise first numeric substring. Columns are subject, optional group, auc, including empty results.',
        fields=['number_of_rows','number_of_columns','complete_row_major_identity_codes_and_auc'],
        sources=['https://stat.ethz.ch/R-manual/R-devel/library/stats/html/integrate.html'])
    FIXTURE.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reason',required=True)
    freeze(**vars(parser.parse_args()))
