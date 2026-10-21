"""Exact binary sample geometry and independent high precision ANOVA tails.

Studentized-range/control probabilities are supplied by retained independent
reference inputs, never by a production posthoc or proposed correction.
"""
from fractions import Fraction
import math,re,unicodedata
import mpmath as mp
from reproducibility.variance_student_mathematical_reference import sample,average,sample_variance,number,f_tail

ALIASES={
 'tukey':['','auto','default','conover','conover_test','dunn','dunns','dunns_test','dunn_test','nemenyi','nemenyi_test','dscf','dwass_steel_critchlow_fligner','tukey','tukey_hsd','hsd'],
 'dunnett':['dunnett','dunnetts','dunnett_test','dunnetts_test'],
 'fisher_lsd':['fisher_lsd','fishers_lsd','fisher','lsd','least_significant_difference'],
 'scheffe':['scheffe','scheffes','scheffe_test','scheffes_test'],
 'tamhane':['tamhane','tamhanes','tamhane_t2','tamhanes_t2']}
LABELS={'tukey':'Tukey','dunnett':'Dunnett','fisher_lsd':'Fisher LSD','scheffe':'Scheffe','tamhane':'Tamhane T2'}

def normalize(value):
    text=unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().strip().lower().replace("'",'')
    for before,after in (('&',' '),('/',' '),('+',' '),('-','_'),(' ','_')):text=text.replace(before,after)
    while '__' in text:text=text.replace('__','_')
    return text.strip('_')

def posthoc(value):
    if value is None:return 'tukey'
    key=normalize(value)
    for kind,aliases in ALIASES.items():
        if key in aliases:return kind
    raise ValueError('Unknown posthoc')

def pairs(tokens,count):
    if not isinstance(tokens,(list,tuple)):raise ValueError('Ordered one-based pairs are required')
    result=[]
    for token in tokens:
        if not isinstance(token,str) or re.fullmatch(r'\s*[0-9]+\s*-\s*[0-9]+\s*',token) is None:raise ValueError('One-based pair required')
        a,b=map(int,token.split('-'))
        if not 1<=a<=count or not 1<=b<=count or a==b:raise ValueError('Two requested distinct groups are required')
        result.append((a-1,b-1))
    return result

def geometry(groups):
    k=len(groups);n=sum(map(len,groups))
    if k<2 or any(len(g)<2 for g in groups):return {'identified':False}
    means=list(map(average,groups));grand=average([v for g in groups for v in g])
    within=sum(sum((v-center)**2 for v in g) for g,center in zip(groups,means))
    between=sum(len(g)*(center-grand)**2 for g,center in zip(groups,means))
    df=n-k;mse=within/df
    with mp.workdps(80):
        if within==0:
            statistic=mp.inf if between else mp.nan;probability=mp.mpf(0) if between else mp.nan
        else:
            statistic=number(between/within*Fraction(df,k-1));probability=f_tail(statistic,k-1,df)
    return {'identified':True,'means':means,'mse':mse,'df':df,'f':float(statistic),'p':float(probability)}

def pair_geometry(groups,first,second):
    design=geometry(groups);difference=design['means'][first]-design['means'][second]
    mse=design['mse'];uncertainty=mse*(Fraction(1,len(groups[first]))+Fraction(1,len(groups[second])))
    with mp.workdps(80):
        if uncertainty==0:
            statistic=(mp.inf if difference>0 else -mp.inf) if difference else mp.nan
            probability=mp.mpf(0) if difference else mp.nan
        else:
            statistic=number(difference)/mp.sqrt(number(uncertainty));df=mp.mpf(design['df'])
            probability=mp.betainc(df/2,mp.mpf('.5'),0,df/(df+statistic**2),regularized=True)
        return float(statistic),float(probability),float(abs(statistic)*mp.sqrt(2))

def scheffe_probability(groups,first,second):
    design=geometry(groups);statistic,_,_=pair_geometry(groups,first,second)
    if math.isnan(statistic):return math.nan
    with mp.workdps(80):return float(f_tail(mp.mpf(statistic)**2/(len(groups)-1),len(groups)-1,design['df']))

def tamhane_probability(groups,first,second):
    a,b=groups[first],groups[second];va,vb=sample_variance(a),sample_variance(b)
    uncertainty=va/len(a)+vb/len(b);difference=average(a)-average(b)
    if uncertainty==0:return 0. if difference else math.nan
    degrees=uncertainty**2/((va/len(a))**2/(len(a)-1)+(vb/len(b))**2/(len(b)-1))
    with mp.workdps(80):
        df=number(degrees);statistic=number(difference)/mp.sqrt(number(uncertainty))
        probability=mp.betainc(df/2,mp.mpf('.5'),0,df/(df+statistic**2),regularized=True)
        family=len(groups)*(len(groups)-1)//2
        return float(-mp.expm1(family*mp.log1p(-probability)))

def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,mp.mpf):value=float(value)
    return str(value) if isinstance(value,float) and not math.isfinite(value) else value
