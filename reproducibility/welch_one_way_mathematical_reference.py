"""Independent exact weighted ANOVA and high precision unequal-variance pairs."""
from fractions import Fraction
import math,mpmath as mp
from reproducibility.variance_student_mathematical_reference import sample,average,sample_variance,number,f_tail

def geometry(groups):
    count=len(groups)
    if count<2 or any(len(g)<2 for g in groups):return {'identified':False}
    means=list(map(average,groups));variances=list(map(sample_variance,groups))
    if any(not v for v in variances):
        return {'identified':True,'f':math.nan,'p':math.nan,'df':[float(count-1),math.nan]}
    weights=[len(g)/v for g,v in zip(groups,variances)];total=sum(weights)
    center=sum(w*m for w,m in zip(weights,means))/total
    sum_terms=sum((1-w/total)**2/(len(g)-1) for w,g in zip(weights,groups))
    numerator=sum(w*(m-center)**2 for w,m in zip(weights,means))/(count-1)
    statistic=numerator/(1+Fraction(2*(count-2),count**2-1)*sum_terms)
    degrees=Fraction(count**2-1,3)/sum_terms
    with mp.workdps(80):probability=f_tail(number(statistic),count-1,number(degrees))
    return {'identified':True,'f':float(statistic),'p':float(probability),'df':[float(count-1),float(degrees)]}

def pair_geometry(groups,first,second):
    a,b=groups[first],groups[second];na,nb=len(a),len(b)
    va,vb=sample_variance(a),sample_variance(b);difference=average(a)-average(b)
    uncertainty=va/na+vb/nb
    if not uncertainty:return (math.inf,0.,math.nan) if difference else (math.nan,math.nan,math.nan)
    degrees=uncertainty**2/((va/na)**2/(na-1)+(vb/nb)**2/(nb-1))
    with mp.workdps(80):
        q=abs(number(difference))/mp.sqrt(number(uncertainty)/2)
        df=number(degrees);t2=number(difference**2/uncertainty)
        probability=mp.betainc(df/2,mp.mpf('.5'),0,df/(df+t2),regularized=True)
    return float(q),float(probability),float(degrees)
