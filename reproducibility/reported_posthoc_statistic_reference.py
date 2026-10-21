"""Independent 80-digit actual Scheffe F and Tamhane signed t statistics."""
import math
import mpmath as mp
from reproducibility import one_way_mathematical_reference as geometry
from reproducibility.variance_student_mathematical_reference import sample_variance,number,average

def pair_statistic(groups,first,second,kind):
    if kind=='scheffe':
        design=geometry.geometry(groups);difference=design['means'][first]-design['means'][second]
        from fractions import Fraction
        variance=design['mse']*(Fraction(1,len(groups[first]))+Fraction(1,len(groups[second])))
        if not variance:return math.inf if difference else math.nan
        return float(difference**2/(variance*(len(groups)-1)))
    a,b=groups[first],groups[second];difference=average(a)-average(b)
    variance=sample_variance(a)/len(a)+sample_variance(b)/len(b)
    if not variance:return (math.inf if difference>0 else -math.inf) if difference else math.nan
    with mp.workdps(80):return float(number(difference)/mp.sqrt(number(variance)))

def expected_report(case,baseline,welch=False):
    from copy import deepcopy
    answer=deepcopy(baseline)
    if 'error' in answer:return answer
    key={'Scheffe':'Scheffe','Tamhane T2':'Tamhane-T2'}.get(answer['method'])
    if key is None or key not in answer['results_dict']:return answer
    groups=list(map(geometry.sample,case['parameters']['df_list']))
    requested=geometry.pairs(case['parameters']['comparisons'],len(groups))
    kind='scheffe' if answer['method']=='Scheffe' else 'tamhane'
    answer['results_dict'][key][0]=geometry.clean([pair_statistic(groups,a,b,kind) for a,b in requested])
    return answer
