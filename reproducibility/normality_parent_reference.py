"""Complete independent pooled-normality reports and histogram/quantile arrays."""
from fractions import Fraction as Q
from functools import lru_cache
import math
import mpmath as mp
from reproducibility.anderson_mathematical_reference import mathematical as anderson
from reproducibility.one_way_mathematical_reference import clean

def finite_groups(groups):
    if not isinstance(groups,(list,tuple)):raise ValueError('Ordered groups required')
    answer=[]
    for group in groups:
        if not isinstance(group,(list,tuple)):raise ValueError('One-dimensional samples required')
        retained=[]
        for value in group:
            if isinstance(value,(list,tuple,dict,complex)):raise ValueError('One-dimensional real samples required')
            try:value=float(value)
            except (TypeError,ValueError,OverflowError):continue
            if math.isfinite(value):retained.append(value)
        answer.append(retained)
    return answer
def number(value):return mp.mpf(value.numerator)/value.denominator
def polynomial(coefficients,x):return mp.fsum(mp.mpf(v)*x**i for i,v in enumerate(coefficients))
@lru_cache(maxsize=128)
def shapiro_coefficients(n):
    with mp.workdps(80):
        half=n//2
        quantiles=[mp.sqrt(2)*mp.erfinv(2*(mp.mpf(i)-mp.mpf('.375'))/(n+mp.mpf('.25'))-1) for i in range(1,half+1)]
        total=2*mp.fsum(v*v for v in quantiles);root=mp.sqrt(total);r=1/mp.sqrt(n)
        first=polynomial(['0','.221157','-.147981','-2.07119','4.434685','-2.706056'],r)-quantiles[0]/root
        if n>5:
            second=polynomial(['0','.042981','-.293762','-1.752461','5.682633','-3.582633'],r)-quantiles[1]/root
            factor=mp.sqrt((total-2*quantiles[0]**2-2*quantiles[1]**2)/(1-2*first**2-2*second**2));fixed=[first,second];offset=2
        else:
            factor=mp.sqrt((total-2*quantiles[0]**2)/(1-2*first**2));fixed=[first];offset=1
        positive=fixed+[-v/factor for v in quantiles[offset:]]
        return tuple([-v for v in positive]+([mp.mpf(0)] if n%2 else [])+list(reversed(positive)))
@lru_cache(maxsize=256)
def shapiro(values):
    n=len(values);q=[Q(v) for v in sorted(values)];center=sum(q,Q())/n;ss=sum(((v-center)**2 for v in q),Q())
    if not ss:return [math.nan,math.nan]
    with mp.workdps(80):
        if n==3:
            W=(q[-1]-q[0])**2/(2*ss);w=number(W)
            # Rational numerator preserves positive endpoint tails far below a rounded W.
            delta=mp.asin(number(4*W-3)/(2*(mp.sqrt(w)+mp.sqrt(3*(1-w)))))
            return [float(W),float(max(mp.mpf(0),6/mp.pi*delta))]
        coefficients=shapiro_coefficients(n)
        numerator=mp.fsum(a*number(v-center) for a,v in zip(coefficients,q))
        denominator=mp.fsum(a*a for a in coefficients)*number(ss);one_minus=(denominator-numerator*numerator)/denominator
        W=1-one_minus
        if n>5000:return [float(W),math.nan]
        if one_minus<=0:return [float(W),1.]
        y=mp.log(one_minus)
        if n<=11:
            gamma=polynomial(['-2.273','.459'],n)
            if y>=gamma:return [float(W),1e-99]
            y=-mp.log(gamma-y);location=polynomial(['.544','-.39978','.025054','-.0006714'],n)
            scale=mp.exp(polynomial(['1.3822','-.77857','.062767','-.0020322'],n))
        else:
            ln=mp.log(n);location=polynomial(['-1.5861','-.31082','-.083751','.0038915'],ln)
            scale=mp.exp(polynomial(['-.4803','-.082676','.0030302'],ln))
        return [float(W),float(mp.erfc((y-location)/(scale*mp.sqrt(2)))/2)]
@lru_cache(maxsize=256)
def dagostino(values):
    n=len(values)
    if n<8:return [math.nan,math.nan]
    q=[Q(v) for v in values];center=sum(q,Q())/n;moments={j:sum(((v-center)**j for v in q),Q())/n for j in (2,3,4)}
    if not moments[2]:return [math.nan,math.nan]
    with mp.workdps(80):
        variance=number(moments[2]);skew=number(moments[3])/variance**mp.mpf('1.5');kurt=number(moments[4])/variance**2
        beta=mp.mpf(3)*(n*n+27*n-70)*(n+1)*(n+3)/((n-2)*(n+5)*(n+7)*(n+9))
        w2=mp.sqrt(2*(beta-1))-1;delta=mp.sqrt(2/mp.log(w2));a=mp.sqrt(2/(w2-1))
        z3=delta*mp.asinh(skew*mp.sqrt(mp.mpf((n+1)*(n+3))/(6*(n-2)))/a)
        sd4=mp.sqrt(mp.mpf(24*(n-2)*(n-3)*n)/((n+1)**2*(n+3)*(n+5)))
        u4=(kurt-3+mp.mpf(6)/(n+1))/sd4
        B=mp.mpf(6)*(n*n-5*n+2)/((n+7)*(n+9))*mp.sqrt(mp.mpf(6*(n+3)*(n+5))/(n*(n-2)*(n-3)))
        A=6+8/B*(2/B+mp.sqrt(1+4/B**2));ratio=(1-2/A)/(1+u4*mp.sqrt(2/(A-4)))
        z4=(1-2/(9*A)-mp.sign(ratio)*mp.root(abs(ratio),3))/mp.sqrt(2/(9*A))
        statistic=z3*z3+z4*z4
        return [float(statistic),float(mp.exp(-statistic/2))]
@lru_cache(maxsize=512)
def ks(values):
    n=len(values)
    with mp.workdps(80):
        # Mills' bound at |x|=40 is below 4e-350, below binary64's minimum
        # subnormal. This retains the rounded law while avoiding an overflowing
        # mpmath erfc selector on the declared 2**600 physical-unit inputs.
        distribution=[mp.mpf(0) if v < -40 else mp.mpf(1) if v > 40
                      else mp.erfc(-mp.mpf(v)/mp.sqrt(2))/2 for v in sorted(values)]
        d=max(max(mp.mpf(i+1)/n-u,u-mp.mpf(i)/n) for i,u in enumerate(distribution))
        if d>=1:probability=mp.mpf(0)
        elif d>=mp.mpf('.5'):
            upper=math.floor(n*(1-d));terms=[]
            for j in range(upper+1):
                left=mp.mpf(j)/n+d;right=1-d-mp.mpf(j)/n
                terms.append(mp.binomial(n,j)*left**(j-1)*right**(n-j))
            probability=2*d*mp.fsum(terms)
        else:
            k=math.ceil(n*d);m=2*k-1;h=k-n*d;H=mp.matrix(m)
            for i in range(m):
                for j in range(m):
                    exponent=i-j+1
                    H[i,j]=1/mp.factorial(exponent) if exponent>=0 else 0
            # Build every row first: otherwise subsequent initialization of the
            # last row overwrites earlier right-boundary corrections.
            for i in range(m):
                H[i,0]-=h**(i+1)/mp.factorial(i+1)
                H[m-1,i]-=h**(m-i)/mp.factorial(m-i)
            if 2*h>1:H[m-1,0]+=(2*h-1)**m/mp.factorial(m)
            cdf=(H**n)[k-1,k-1]*mp.factorial(n)/n**n
            probability=1-cdf
        return [float(d),float(min(mp.mpf(1),max(mp.mpf(0),probability)))]
@lru_cache(maxsize=256)
def scientific(values):
    a=anderson({'values':list(values)})
    a=[math.nan if value is None else value for value in a]
    return {'DA':dagostino(values),'A':a,'KS':ks(values),'SW_all':shapiro(values)}
def empty_axis():return {'xlabel':'','ylabel':'','patches':[],'lines':[],'texts':[]}
def figure(values,results):
    n=len(values)
    if n<3:return {'size':[10.,5.],'axes':[empty_axis(),empty_axis()]}
    sorted_values=sorted(values);low=Q(sorted_values[0]);high=Q(sorted_values[-1]);high=high if high>low else low+1
    bins=max(8,min(32,int(math.sqrt(n)*2)));edges=[low+(high-low)*Q(i,bins) for i in range(bins+1)]
    counts=[sum(edge<=Q(v)<end or i==bins-1 and Q(v)==end for v in values) for i,(edge,end) in enumerate(zip(edges,edges[1:]))]
    hist={'xlabel':'','ylabel':'Count','patches':[[float(edges[i]),float(edges[i+1]-edges[i]),counts[i]] for i in range(bins)],'lines':[],'texts':[]}
    def display(value):return str(round(value,2))
    k2=display(results['DA'][1]) if math.isfinite(results['DA'][1]) else 'n<8' if n<8 else 'n/a'
    hist['texts']=[f'K2: {k2}\nA: {display(results["A"][1])}\nKS: {display(results["KS"][1])}\nW: {display(results["SW_all"][1])}']
    qq={'xlabel':'Theoretical Quantiles','ylabel':'Sample Quantiles','patches':[],'lines':[],'texts':[]}
    q=[Q(v) for v in sorted_values];center=sum(q,Q())/n;variance=sum(((v-center)**2 for v in q),Q())/n
    if variance:
        with mp.workdps(80):
            x=[float(mp.sqrt(2)*mp.erfinv(2*mp.mpf(i)/(n+1)-1)) for i in range(1,n+1)]
            y=[float(number(v-center)/mp.sqrt(number(variance))) for v in q]
        xspan=x[-1]-x[0];yspan=y[-1]-y[0]
        ends=[min(x[0]-.02*xspan,y[0]-.05*yspan),max(x[-1]+.02*xspan,y[-1]+.05*yspan)]
        qq['lines']=[{'x':x,'y':y},{'x':ends,'y':ends}]
    return {'size':[10.,5.],'axes':[hist,qq]}
def report(case):
    try:
        groups=finite_groups(case['parameters']['df_list']);values=tuple(v for group in groups for v in group)
        results=scientific(values) if len(values)>=3 else {};valid=[row[1] for row in results.values() if math.isfinite(row[1])]
        normal=bool(valid) and sum(p>.05 for p in valid)>=max(1,(len(valid)+1)//2)
        plot=figure(values,results) if case['parameters']['make_plot'] else None
        if plot is not None and len(values)>=3 and case.get('group_names'):
            retained_names=[name for name,group in zip(case['group_names'],groups) if group]
            label=retained_names[0] if retained_names and all(name==retained_names[0] for name in retained_names) else None
            plot['axes'][0]['xlabel']='' if label is None else str(label)
        return clean({'normal':normal,'results_dict':results,'figure':plot})
    except (ValueError,TypeError):return {'error':'ValueError'}
