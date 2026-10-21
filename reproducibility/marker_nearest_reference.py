"""Independent native-R whole-table nearest-marker reference.

Inputs are the original marker rows, spatial labels and threshold, not prepared
PyFLASH coordinates. R stats::dist supplies the published geometry; native R
selection/tabulation supplies the declared grouping and attribution policy.
This is a composed reference, not a second published whole-microscopy method.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

GROUP_FIELDS = ('AnimalName', 'ImageROI', 'Hemisphere', 'Region', 'ROI')
ORIGINAL = Path(__file__).with_name('reference-sources') / 'marker-distance-grouping/frozen-before/frozen-before.json'


def cases():
    original = json.loads(ORIGINAL.read_text(encoding='utf-8'))['rows']
    result = [copy.deepcopy(row['case']) for row in original if row['backend'] == 'tree']
    base = result[0]
    for count in (1, 17, 33):
        for scale in (1e-100, 1., 1e100):
            case = copy.deepcopy(base)
            case.update(key=f'marker-distance.native-scale-{count}-{scale}', coloc_column=None)
            case['left'] = [{**base['left'][0], 'point': [0., 0., scale]}]
            case['right'] = [{**base['right'][0], 'point': [scale * (j + 1), scale / 2, scale]}
                             for j in range(count)]
            result.append(case)
    for count in (17, 33):
        case = copy.deepcopy(base)
        case.update(key=f'marker-distance.native-nonidentical-ties-{count}', coloc_column=None)
        case['left'] = [{**base['left'][0], 'point': [0., 0., 1.]}]
        case['right'] = [{**base['right'][0], 'point': [1. if j % 2 else -1., 0., 1.]}
                         for j in range(count)]
        result.append(case)
    return result


def number(value):
    if value is None:
        return 'NA_real_'
    value = float(value)
    if math.isnan(value):
        return 'NaN'
    if math.isinf(value):
        return 'Inf' if value > 0 else '-Inf'
    return repr(value)


def text(value):
    return 'NA_character_' if value is None else json.dumps(str(value), ensure_ascii=True)


def vector(values, encoder=number):
    values = list(values)
    return 'c(' + ','.join(map(encoder, values)) + ')' if values else (
        'character(0)' if encoder is text else 'numeric(0)')


def query(case):
    left, right = case['left'], case['right']
    shared = [name for name in GROUP_FIELDS if name in case['left_groups'] and name in case['right_groups']]
    groups = '\n'.join(f'lg{j} <- {vector((r.get(name) for r in left), text)}; '
                       f'rg{j} <- {vector((r.get(name) for r in right), text)}'
                       for j, name in enumerate(shared))
    same = ' & '.join(f'((is.na(lg{j}[i]) & is.na(rg{j})) | '
                      f'(!is.na(lg{j}[i]) & !is.na(rg{j}) & lg{j}[i] == rg{j}))'
                      for j in range(len(shared))) or 'rep(TRUE,nr)'
    left_same = ' & '.join(f'((is.na(lg{j}[i]) & is.na(lg{j})) | '
                           f'(!is.na(lg{j}[i]) & !is.na(lg{j}) & lg{j}[i] == lg{j}))'
                           for j in range(len(shared))) or 'rep(TRUE,nl)'
    # R computes each cross-table distance from original complete 3-D points.
    # It must not impute partial coordinates using dist's missing-data scaling.
    code = f'''local({{
nl <- {len(left)}; nr <- {len(right)}
lp <- matrix({vector(v for r in left for v in r['point'])},ncol=3,byrow=TRUE)
rp <- matrix({vector(v for r in right for v in r['point'])},ncol=3,byrow=TRUE)
{groups}
raw <- {vector((r.get('coloc') for r in left), text)}
threshold <- {number(case['threshold'])}
lv <- rowSums(!is.finite(lp)) == 0 & lp[,3] != 0
rv <- rowSums(!is.finite(rp)) == 0 & rp[,3] != 0
d <- rep(Inf,nl); flags <- counts <- coloc <- rep(0,nr)
for (i in seq_len(nl)) {{
 if (!lv[i]) next
 eligible <- which(rv & ({same}))
 if (!length(eligible)) next
 dm <- as.matrix(stats::dist(rbind(lp[i,,drop=FALSE],rp[eligible,,drop=FALSE]),method="euclidean"))
 k <- which.min(dm[1,-1]); j <- eligible[k]
 d[i] <- dm[1,k+1]; flags[j] <- 1; counts[j] <- counts[j]+1
 if ({'TRUE' if case['coloc_column'] is None else 'FALSE'}) {{ coloc[j] <- coloc[j]+1; next }}
 values <- raw[which({left_same})]; nums <- suppressWarnings(as.numeric(values))
 numeric_values <- nums[!is.na(nums)]
 value <- suppressWarnings(as.numeric(raw[i]))
 if (length(numeric_values)) {{
  positive <- !is.na(value) && if (all(numeric_values %in% c(0,1))) value != 0 else value > threshold
 }} else {{
  token <- tolower(trimws(raw[i])); positive <- !is.na(token) && token %in% c("true","yes","y","t")
 }}
 if (isTRUE(positive)) coloc[j] <- coloc[j]+1
}}
c(d,flags,coloc,as.numeric(coloc>=1),counts)
}})'''
    return {'key': case['key'], 'code': code}


def unpack(case, values):
    n, m = len(case['left']), len(case['right'])
    if len(values) != n + 4*m:
        raise ValueError('Native nearest-marker output shape changed.')
    return dict(zip(('distances','closest_flags','coloc_counts','contains','closest_counts'),
                    (values[:n], values[n:n+m], values[n+m:n+2*m],
                     values[n+2*m:n+3*m], values[n+3*m:])))
