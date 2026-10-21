"""Independent 80-digit log-Gaussian normality benchmark, frozen before correction."""
import math
import mpmath as mp

def finite_values(a):
    output=[]
    for v in a:
        try:v=float(v)
        except (TypeError,ValueError):continue
        if math.isfinite(v):output.append(v)
    return sorted(output)

def mathematical(case):
    a=finite_values(case['values']);n=len(a)
    if n<3 or len(set(a))<2:return [None,None]
    with mp.workdps(80):
        x=list(map(mp.mpf,a));mean=mp.fsum(x)/n;sd=mp.sqrt(mp.fsum((v-mean)**2 for v in x)/(n-1));z=[(v-mean)/sd for v in x]
        def logphi(z):
            return mp.log1p(-mp.erfc(z/mp.sqrt(2))/2) if z>0 else mp.log(mp.erfc(-z/mp.sqrt(2))/2)
        A=-n-mp.fsum((2*i+1)*(logphi(u)+logphi(-v)) for i,(u,v) in enumerate(zip(z,reversed(z))))/n
        AA=A*(1+mp.mpf('.75')/n+mp.mpf('2.25')/n**2)
        if n<8:return [float(AA),None]
        if AA<mp.mpf('.2'):p=-mp.expm1(mp.mpf('-13.436')+mp.mpf('101.14')*AA-mp.mpf('223.73')*AA**2)
        elif AA<mp.mpf('.34'):p=-mp.expm1(mp.mpf('-8.318')+mp.mpf('42.796')*AA-mp.mpf('59.938')*AA**2)
        elif AA<mp.mpf('.6'):p=mp.exp(mp.mpf('.9177')-mp.mpf('4.279')*AA-mp.mpf('1.38')*AA**2)
        elif AA<10:p=mp.exp(mp.mpf('1.2937')-mp.mpf('5.709')*AA+mp.mpf('.0186')*AA**2)
        else:p=mp.mpf('3.7e-24')
        return [float(AA),float(p)]
