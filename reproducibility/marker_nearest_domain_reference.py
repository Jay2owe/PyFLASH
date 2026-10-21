"""Original-coordinate scale/noise controls for published native R distances.

Raw stats::dist outcomes are retained separately from translated and rescaled
calls to the unchanged published kernel. Scaling is per pair, so a very distant
point cannot erase a nearby small distance. No PyFLASH code supplies answers.
"""
from copy import deepcopy
import random
from reproducibility.marker_nearest_reference import cases as original_cases, query as original_query


def cases():
    base=original_cases()[0];result=[]
    for scale in (1e-200,1e200):
        for count in (1,17):
            case=deepcopy(base);case.update(key=f'marker-distance.extreme-{scale}-{count}',coloc_column=None)
            case['left']=[{**base['left'][0],'point':[0.,0.,scale]}]
            case['right']=[{**base['right'][0],'point':[(j+1)*scale,scale/2,scale]} for j in range(count)]
            result.append(case)
    case=deepcopy(base);case.update(key='marker-distance.mixed-tiny-large',coloc_column=None)
    case['left']=[{**base['left'][0],'point':[0.,0.,1e-200]}]
    case['right']=[{**base['right'][0],'point':[1e-200,1e-200,1e-200]},
                   {**base['right'][0],'point':[1e200,1e200,1e200]}]
    result.append(case)
    generator=random.Random(71903)
    for seed_case in range(8):
        case=deepcopy(base);case.update(key=f'marker-distance.noisy-{seed_case}',seed=71903)
        case['left']=[{**base['left'][0],'point':[generator.gauss(0,13),generator.gauss(0,17),generator.uniform(1,50)],
                       'coloc':generator.choice([0.,1.,30.,31.,100.])} for _ in range(11)]
        case['right']=[{**base['right'][0],'point':[generator.gauss(0,13),generator.gauss(0,17),generator.uniform(1,50)]}
                       for _ in range(23)]
        result.append(case)
    return result


def query(case, *, aligned):
    row=original_query(case)
    row['key']=case['key']+('.aligned' if aligned else '.raw')
    if aligned:
        original='dm <- as.matrix(stats::dist(rbind(lp[i,,drop=FALSE],rp[eligible,,drop=FALSE]),method="euclidean"))'
        replacement='''cross <- vapply(eligible,function(target) {
 delta <- lp[i,]-rp[target,]
 if (any(!is.finite(delta))) return(Inf)
 scale <- max(abs(delta))
 if (scale==0) return(0)
 as.numeric(stats::dist(rbind(c(0,0,0),delta/scale),method="euclidean"))*scale
},numeric(1))
 dm <- matrix(0,nrow=length(eligible)+1,ncol=length(eligible)+1); dm[1,-1] <- cross'''
        if original not in row['code']:raise ValueError('Native distance preparation source changed.')
        row['code']=row['code'].replace(original,replacement)
    return row
