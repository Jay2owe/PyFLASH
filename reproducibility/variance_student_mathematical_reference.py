"""Independent exact observations and 80-digit variance/Student inference.

No production imports or SciPy kernels. The return schema is composed from
literal public report fields; invalid requests are separate functional rules.
"""
from fractions import Fraction
import math,unicodedata
import mpmath as mp

METHODS={
 'brown_forsythe':'Brown-Forsythe','levene':'Levene','levene_trimmed':'Levene trimmed',
 'bartlett':'Bartlett','fligner':'Fligner-Killeen','none':'Not checked'}
ALIASES={
 'brown_forsythe':['auto','default','brown_forsythe','brown_forsyth','bf','levene_median','median'],
 'levene':['levene','levene_mean','mean'],
 'levene_trimmed':['levene_trimmed','trimmed','trimmed_mean'],
 'bartlett':['bartlett','bartletts'],
 'fligner':['fligner','fligner_killeen','fligner_killeen_test'],
 'none':['','none','raw','p','uncorrected','unadjusted','no_correction','no_adjustment',
         'false','no','n','off','0','skip','disabled']}

def method(value):
    if value is None or value is False:return 'none'
    text=unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().strip().lower().replace("'",'')
    for first,second in (('&',' '),('/',' '),('+',' '),('-','_'),(' ','_')):text=text.replace(first,second)
    while '__' in text:text=text.replace('__','_')
    text=text.strip('_')
    for name,aliases in ALIASES.items():
        if text in aliases:return name
    raise ValueError('Unknown variance screen')

def alpha(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
        raise ValueError('Alpha is a finite real probability')
    return float(value)

def sample(values):
    if not isinstance(values,(list,tuple)):raise ValueError('Each sample has one dimension')
    output=[]
    for value in values:
        if isinstance(value,(list,tuple,dict,complex)):raise ValueError('Each sample has one real dimension')
        try:number=float(value)
        except (TypeError,ValueError,OverflowError):continue
        if math.isfinite(number):output.append(Fraction(number))
    return output

def average(values):return sum(values)/len(values)
def median(values):
    ordered=sorted(values);size=len(ordered)
    return ordered[size//2] if size%2 else (ordered[size//2-1]+ordered[size//2])/2
def sample_variance(values):
    center=average(values)
    return sum((value-center)**2 for value in values)/(len(values)-1)
def number(value):return mp.mpf(value.numerator)/value.denominator if isinstance(value,Fraction) else mp.mpf(value)
def f_tail(statistic,first,second):
    if mp.isinf(statistic):return mp.mpf(0)
    return mp.betainc(mp.mpf(second)/2,mp.mpf(first)/2,0,
        mp.mpf(second)/(second+first*statistic),regularized=True)
def chi_tail(statistic,degrees):
    if mp.isinf(statistic):return mp.mpf(0)
    return mp.gammainc(mp.mpf(degrees)/2,statistic/2,mp.inf,regularized=True)

def variance_numbers(groups,kind):
    count=len(groups);total=sum(map(len,groups))
    if kind.startswith('levene') or kind=='brown_forsythe':
        if kind=='levene_trimmed':
            groups=[sorted(group)[len(group)//20:len(group)-len(group)//20] for group in groups]
            total=sum(map(len,groups))
        centers=[median(group) if kind=='brown_forsythe' else average(group) for group in groups]
        absolute=[[abs(value-center) for value in group] for group,center in zip(groups,centers)]
        means=list(map(average,absolute));grand=average([v for group in absolute for v in group])
        between=sum(len(group)*(center-grand)**2 for group,center in zip(absolute,means))
        within=sum(sum((value-center)**2 for value in group) for group,center in zip(absolute,means))
        if within==0:
            return (mp.inf,mp.mpf(0)) if between else (mp.nan,mp.nan)
        statistic=number(between/within*Fraction(total-count,count-1))
        return statistic,f_tail(statistic,count-1,total-count)
    if kind=='bartlett':
        variances=list(map(sample_variance,groups))
        pooled=sum((len(group)-1)*variance for group,variance in zip(groups,variances))/(total-count)
        if pooled==0:return mp.nan,mp.nan
        if any(v==0 for v in variances):return mp.inf,mp.mpf(0)
        numerator=(total-count)*mp.log(number(pooled))-mp.fsum(
            (len(group)-1)*mp.log(number(variance)) for group,variance in zip(groups,variances))
        denominator=1+number((sum(Fraction(1,len(group)-1) for group in groups)-Fraction(1,total-count))
                             / (3*(count-1)))
        statistic=numerator/denominator
        # Identical rational variances have an exact zero statistic.
        if len(set(variances))==1:statistic=mp.mpf(0)
        return statistic,chi_tail(statistic,count-1)
    if kind=='fligner':
        centers=list(map(median,groups))
        absolute=[[abs(value-center) for value in group] for group,center in zip(groups,centers)]
        flat=[v for group in absolute for v in group]
        ranks={value:Fraction(2*sum(v<value for v in flat)+sum(v==value for v in flat)+1,2)
               for value in set(flat)}
        scores={value:mp.sqrt(2)*mp.erfinv(number(rank/Fraction(total+1))) for value,rank in ranks.items()}
        if len(scores)==1:return mp.nan,mp.nan
        score_groups=[[scores[v] for v in group] for group in absolute]
        score_flat=[v for group in score_groups for v in group]
        grand=mp.fsum(score_flat)/total
        variance=mp.fsum((v-grand)**2 for v in score_flat)/(total-1)
        statistic=mp.fsum(len(group)*(mp.fsum(group)/len(group)-grand)**2 for group in score_groups)/variance
        return statistic,chi_tail(statistic,count-1)
    raise ValueError(kind)

def clean(value):
    if isinstance(value,dict):return {key:clean(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [clean(item) for item in value]
    if isinstance(value,mp.mpf):value=float(value)
    return str(value) if isinstance(value,float) and not math.isfinite(value) else value

def variance_report(parameters):
    try:
        kind=method(parameters.get('method','brown-forsythe'));level=alpha(parameters.get('alpha',.05))
        groups=[sample(group) for group in parameters['df_list']]
        raw={'caller-note':'retained'}
        label=METHODS[kind]
        output={'method':label,'statistic':mp.nan,'pvalue':mp.nan,'equal_var':None,'alpha':level}
        if kind=='none':
            output['equal_var']=True;raw['Variance check']=[label,mp.nan]
        elif len(groups)<2 or any(len(group)<2 for group in groups):
            raw['Variance '+label]=[mp.nan,mp.nan];raw['Equal variance']=['insufficient data',mp.nan]
        else:
            with mp.workdps(80):statistic,probability=variance_numbers(groups,kind)
            output['statistic']=statistic;output['pvalue']=probability
            output['equal_var']=None if mp.isnan(probability) else bool(probability>=level)
            raw['Variance '+label]=[statistic,probability];raw['Equal variance']=[output['equal_var'],probability]
        return clean({'output':output,'results_dict':raw})
    except (ValueError,TypeError):return {'error':'ValueError'}

def student_numbers(first,second,pooled):
    count1,count2=len(first),len(second)
    if min(count1,count2)<2:return mp.nan,mp.nan,mp.nan
    difference=average(first)-average(second)
    v1,v2=sample_variance(first),sample_variance(second)
    if pooled:
        degrees=Fraction(count1+count2-2)
        uncertainty=((count1-1)*v1+(count2-1)*v2)/degrees*(Fraction(1,count1)+Fraction(1,count2))
    else:
        uncertainty=v1/count1+v2/count2
        denominator=(v1/count1)**2/(count1-1)+(v2/count2)**2/(count2-1)
        degrees=uncertainty**2/denominator if denominator else None
    if uncertainty==0:
        return ((mp.inf if difference>0 else -mp.inf),mp.mpf(0),number(degrees) if degrees else mp.nan) if difference else (mp.nan,mp.nan,number(degrees) if degrees else mp.nan)
    statistic=number(difference)/mp.sqrt(number(uncertainty));df=number(degrees)
    probability=mp.betainc(df/2,mp.mpf('.5'),0,df/(df+statistic**2),regularized=True)
    return statistic,probability,df

def annotation(probability,ns):
    if ns is None:ns='ns'
    if not mp.isnan(probability):
        for threshold,label in ((.0001,'****'),(.001,'***'),(.01,'**'),(.05,'*')):
            if probability<mp.mpf(threshold):return label
    return float(round(float(probability),3)) if ns=='p' else ns

def student_report(parameters):
    try:
        choice=parameters.get('equal_var')
        if choice is not None and type(choice) is not bool:raise ValueError('Variance choice is Boolean or auto')
        screen=method(parameters.get('variance_test','brown-forsythe'))
        level=alpha(parameters.get('variance_alpha',.05))
        first,second=sample(parameters['group1']),sample(parameters['group2'])
        raw={'caller-note':'retained'}
        if choice is None:
            screened=variance_report({'df_list':[parameters['group1'],parameters['group2']],
                'method':parameters.get('variance_test','brown-forsythe'),'alpha':level})
            if 'error' in screened:return screened
            raw=screened['results_dict']
            selected=screened['output']['equal_var']
            choice=bool(selected) if selected is not None else False
        with mp.workdps(80):statistic,probability,degrees=student_numbers(first,second,choice)
        label="Student's t-test" if choice else "Welch's t-test"
        key="Student's T Test" if choice else "Welch's T Test"
        raw[key]=[statistic,probability]
        raw['_group_test']={'symbol':'t','df':[degrees]}
        raw['Independent T Test']=[statistic,probability]
        raw['Posthoc-Uncorrected']=[1,[probability]]
        raw['_audit_inputs']={'basis':'raw'}
        return clean({'pvalues':[probability],'annotations':[annotation(probability,parameters.get('ns','ns'))],
            'overall':[statistic,probability],'results_dict':raw,'method':label})
    except (ValueError,TypeError):return {'error':'ValueError'}
