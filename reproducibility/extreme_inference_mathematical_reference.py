"""Independent 80-digit full reports for contrasts beyond float geometry range."""
from fractions import Fraction
import math,mpmath as mp
from reproducibility import one_way_mathematical_reference as maths
from reproducibility import welch_one_way_mathematical_reference as welch_maths
from reproducibility.variance_student_mathematical_reference import number,sample_variance,average,f_tail,student_report
from reproducibility.one_way_report_reference import annotation

def report(case,range_probabilities):
    if case['family']=='student':return student_report(case['parameters'])
    p=case['parameters'];raw=p['df_list'];groups=list(map(maths.sample,raw));k=len(groups)
    family=case['family'];label=p['posthoc'];design=maths.geometry(groups)
    overall=welch_maths.geometry(groups) if family=='welch' else design
    pairs=maths.pairs(p['comparisons'],k);statistics=[];probabilities=[]
    with mp.workdps(80):
        for first,second in pairs:
            a,b=groups[first],groups[second];difference=average(a)-average(b)
            variance=design['mse']*(Fraction(1,len(a))+Fraction(1,len(b)))
            tvalue=number(difference)/mp.sqrt(number(variance)) if variance else (mp.inf if difference>0 else -mp.inf) if difference else mp.nan
            degrees=mp.mpf(design['df']);probability=mp.betainc(degrees/2,mp.mpf('.5'),0,degrees/(degrees+tvalue**2),regularized=True)
            statistic=tvalue
            if label=='Tukey':statistic=number(difference)
            elif label=='Scheffe':statistic=tvalue**2/(k-1);probability=f_tail(statistic,k-1,design['df'])
            elif label in ('Tamhane T2','Games-Howell'):
                va,vb=sample_variance(a),sample_variance(b);uncertainty=va/len(a)+vb/len(b)
                if not uncertainty:
                    statistic=(mp.inf if difference>0 else -mp.inf) if difference else mp.nan
                    probability=mp.mpf(0) if difference else mp.nan
                else:
                    degrees=number(uncertainty**2/((va/len(a))**2/(len(a)-1)+(vb/len(b))**2/(len(b)-1)))
                    statistic=number(difference)/mp.sqrt(number(uncertainty))
                    probability=mp.betainc(degrees/2,mp.mpf('.5'),0,degrees/(degrees+statistic**2),regularized=True)
                if label=='Tamhane T2':probability=-mp.expm1(k*(k-1)//2*mp.log1p(-probability)) if probability!=1 else mp.mpf(1)
                else:
                    statistic=abs(statistic)*mp.sqrt(2)
                    if k>2:probability=mp.mpf(range_probabilities[f'extreme-range.{case["dataset"]}.{first}.{second}'])
            statistics.append(float(statistic));probabilities.append(float(probability))
    result={'caller-note':'retained'}
    result['OWA' if family=='ordinary' else 'Welch ANOVA']=[overall['f'],overall['p']]
    result['_group_test']={'symbol':'F','df':[k-1,design['df']] if family=='ordinary' else overall['df']}
    result[label.replace(' ','-')]=[statistics,probabilities];result['Posthoc-Uncorrected']=[1,probabilities]
    if label=='Fisher LSD':result['_audit_inputs']={'basis':'raw','family':'value','statistic':'lsd','groups':raw,'pairs':pairs,'correction':'Uncorrected'}
    elif family=='ordinary':result['_audit_inputs']={'basis':'self_adjusted','family':'value_unsupported','reason':f'{label} already accounts for multiplicity; no permutation null is implemented for this method.'}
    else:result['_audit_inputs']={'basis':'self_adjusted','family':'unequal_variance','reason':'Permuting values across groups imposes equal variance, which is the assumption Welch ANOVA is chosen to avoid, so a permutation null here would be wrong rather than approximate. Games-Howell and Tamhane T2 carry their own correction; a studentised bootstrap would be needed for a calibrated alternative.'}
    return maths.clean({'pvalues':probabilities,'annotations':[annotation(probability,p['ns']) for probability in probabilities],
        'overall':[overall['f'],overall['p']],'results_dict':result,'method':label})
