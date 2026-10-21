"""Independent 70-digit complete least-squares slope-contrast equations."""
import math
from collections import Counter
from fractions import Fraction
import mpmath as mp

TAILS={'two':'two','two-sided':'two','2':'two','two_sided':'two','twosided':'two','both':'two','ne':'two','!=':'two',
       'one':'one','1':'one','one-sided':'one','one_sided':'one','onesided':'one',
       'less':'less','lt':'less','<':'less','smaller':'less',
       'greater':'greater','gt':'greater','>':'greater','larger':'greater'}

def reference(parameters):
    p=parameters
    empty={key:None for key in ['p','estimate','se','t','reference','other','slope_reference','slope_other']}
    empty.update(df=0,n=0)
    tail=TAILS.get(str(p.get('tail') if p.get('tail') is not None else 'two').strip().lower())
    if tail is None:return {'error_type':'ValueError'}
    if any(not isinstance(p.get(key,False),bool) for key in ['rank','standardize']):return {'error_type':'ValueError'}
    samples=[p[key] for key in ['x','y','group']]
    if any(not isinstance(a,list) or any(isinstance(x,list) for x in a) for a in samples):return {'error_type':'ValueError'}
    if len({len(a) for a in samples})!=1:return {'error_type':'ValueError'}
    cov=p.get('covariates') or {}
    if not isinstance(cov,dict) or any(len(a)!=len(samples[0]) for a in cov.values()):return {'error_type':'ValueError'}
    def finite(value):
        try:result=float(value)
        except (TypeError,ValueError):return None
        return result if math.isfinite(result) else None
    def numeric(value):
        try:float(value);return True
        except (TypeError,ValueError):return False
    numeric_cov={key:all(numeric(v) for v in a if v is not None) for key,a in cov.items()}
    retained=[]
    for i,(x,y,g) in enumerate(zip(*samples)):
        if finite(x) is None or finite(y) is None or g is None:continue
        values=[a[i] for a in cov.values()]
        if any(v is None for v in values):continue
        if any(numeric_cov[k] and finite(cov[k][i]) is None for k in cov):continue
        retained.append(i)
    if not retained:return empty
    groups=[samples[2][i] for i in retained]
    levels=list(dict.fromkeys(groups))
    if len(levels)!=2:return {'error_type':'ValueError'}
    ref=levels[0] if p.get('reference') is None else p['reference']
    if ref not in levels:return {'error_type':'ValueError'}
    other=next(g for g in levels if g!=ref)
    incomplete={**empty,'n':len(retained),'reference':ref,'other':other}
    def ranks(a):
        counts=Counter(a);position=0;lookup={}
        for value in sorted(counts):
            count=counts[value];lookup[value]=Fraction(2*position+count+1,2);position+=count
        return [lookup[v] for v in a]
    with mp.workdps(70):
        x=[mp.mpf(str(samples[0][i])) for i in retained]
        y=[mp.mpf(str(samples[1][i])) for i in retained]
        if p.get('rank'):
            x,y=[[mp.mpf(v.numerator)/v.denominator for v in ranks(a)] for a in [x,y]]
        rank_x,rank_y=x[:],y[:]
        if p.get('standardize'):
            transformed=[]
            for a in [x,y]:
                mean=mp.fsum(a)/len(a);sd=mp.sqrt(mp.fsum((v-mean)**2 for v in a)/len(a))
                transformed.append([(v-mean)/sd for v in a] if sd else a)
            x,y=transformed
        extra=[]
        for key,a in cov.items():
            values=[a[i] for i in retained]
            if numeric_cov[key]:extra.append([mp.mpf(str(v)) for v in values])
            else:
                categories=sorted(set(values),key=lambda v:(type(v).__name__,str(v)))
                for category in categories[1:]:extra.append([mp.mpf(int(v==category)) for v in values])
        design=mp.matrix([[1,xv,int(g!=ref),xv*int(g!=ref),*[column[i] for column in extra]]
                          for i,(xv,g) in enumerate(zip(x,groups))])
        n,k=design.rows,design.cols
        if n<=k or len(set(x))<2 or len(set(y))<2:return incomplete
        rational=[[Fraction(1),Fraction(str(xv)),Fraction(int(g!=ref)),
                   Fraction(str(xv))*int(g!=ref),*[Fraction(str(column[i])) for column in extra]]
                  for i,(xv,g) in enumerate(zip(rank_x,groups))]
        augmented=[[*row,Fraction(str(rank_y[i]))] for i,row in enumerate(rational)]
        pivot_row=0
        for column in range(k):
            pivot=next((i for i in range(pivot_row,n) if rational[i][column]),None)
            if pivot is None:continue
            rational[pivot_row],rational[pivot]=rational[pivot],rational[pivot_row]
            scale=rational[pivot_row][column]
            rational[pivot_row]=[v/scale for v in rational[pivot_row]]
            for i in range(pivot_row+1,n):
                factor=rational[i][column]
                rational[i]=[v-factor*u for v,u in zip(rational[i],rational[pivot_row])]
            pivot_row+=1
        if pivot_row<k:return incomplete
        # An exact fitted plane is identified even when its residual variance
        # vanishes. Its fitted coefficients remain reportable.
        pivot_row=0
        for column in range(k):
            pivot=next((i for i in range(pivot_row,n) if augmented[i][column]),None)
            augmented[pivot_row],augmented[pivot]=augmented[pivot],augmented[pivot_row]
            factor=augmented[pivot_row][column]
            augmented[pivot_row]=[v/factor for v in augmented[pivot_row]]
            for i in range(n):
                if i==pivot_row:continue
                factor=augmented[i][column]
                augmented[i]=[v-factor*u for v,u in zip(augmented[i],augmented[pivot_row])]
            pivot_row+=1
        exact_fit=all(not row[-1] for row in augmented[k:])
        exact_difference=augmented[3][-1] if exact_fit else None
        # Column units cannot determine whether a parameter exists. Normalize
        # internally and transform both coefficients and uncertainty back.
        scales=[max(abs(design[i,j]) for i in range(n)) for j in range(k)]
        normalized=mp.matrix([[design[i,j]/scales[j] for j in range(k)] for i in range(n)])
        yscale=max(abs(v) for v in y)
        normalized_y=mp.matrix([v/yscale for v in y])
        inverse=(normalized.T*normalized)**-1
        normalized_beta=inverse*normalized.T*normalized_y
        beta=mp.matrix([normalized_beta[j]*yscale/scales[j] for j in range(k)])
        residual=mp.matrix(y)-design*beta
        variance=mp.fsum(value**2 for value in residual)/(n-k)
        if exact_fit:
            difference=float(beta[3]) if exact_difference else 0.
            statistic=math.copysign(math.inf,float(exact_difference)) if exact_difference else None
            probability=(0. if tail in {'two','one'} else
                         float((exact_difference<0) if tail=='greater' else (exact_difference>0))) if exact_difference else None
            return {'p':probability,'estimate':difference,'se':0.,'t':statistic,
                    'df':n-k,'n':n,'reference':ref,'other':other,
                    'slope_reference':float(beta[1]),'slope_other':float(beta[1]+beta[3])}
        se=mp.sqrt(variance*inverse[3,3])/scales[3];stat=beta[3]/se
        sf=mp.betainc(mp.mpf(n-k)/2,mp.mpf('.5'),0,(n-k)/(n-k+stat**2),regularized=True)/2
        probability=2*sf if tail=='two' else sf if tail=='one' else (sf if stat>=0 else 1-sf) if tail=='greater' else (sf if stat<=0 else 1-sf)
        return {'p':float(probability),'estimate':float(beta[3]),'se':float(se),'t':float(stat),
                'df':n-k,'n':n,'reference':ref,'other':other,
                'slope_reference':float(beta[1]),'slope_other':float(beta[1]+beta[3])}
