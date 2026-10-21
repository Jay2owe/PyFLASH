"""Independent arbitrary-precision benchmark of the declared constant-fit variant.

This is not GraphPad Prism equivalence: the published ROUT fit uses a different
nonlinear optimisation procedure. This benchmark checks the exposed IRLS variant,
the stated percentile/degrees-of-freedom correction and truncated BH thresholds.
"""
import math
import mpmath as mp

def reference(case):
    p=case['parameters'];raw=p['values'];indices=[];a=[]
    for i,value in enumerate(raw):
        try:value=float(value)
        except (TypeError,ValueError):continue
        if math.isfinite(value):indices.append(i);a.append(value)
    size=len(raw);n=len(a);flags=[False]*size;probabilities=[None]*size;thresholds=[None]*size;tvalues=[None]*size
    k=p.get('n_params',1)
    if n<3 or n<=k:return [flags,probabilities,thresholds,tvalues,None,None]
    with mp.workdps(70):
        a=[mp.mpf(v) for v in a]
        def quantile(values,probability):
            values=sorted(values);coordinate=(len(values)-1)*probability;i=int(mp.floor(coordinate));f=coordinate-i
            return values[i]*(1-f)+values[min(i+1,len(values)-1)]*f
        center=quantile(a,mp.mpf('.5'))
        def scale(center):
            p68=quantile([abs(v-center) for v in a],mp.mpf('.6827'))
            return p68*n/(n-k) if p68>0 else None
        rsdr=scale(center)
        for _ in range(50):
            if rsdr is None:break
            weights=[1/(1+((v-center)/rsdr)**2) for v in a]
            updated=mp.fsum(w*v for w,v in zip(weights,a))/mp.fsum(weights)
            if abs(updated-center)<=mp.mpf('1e-10')*max(1,abs(center)):
                center=updated;break
            center=updated;rsdr=scale(center)
        rsdr=scale(center)
        if rsdr is None:return [flags,probabilities,thresholds,tvalues,float(center),None]
        local_t=[abs(v-center)/rsdr for v in a];df=n-k
        local_p=[mp.betainc(mp.mpf(df)/2,mp.mpf('.5'),0,df/(df+t*t),regularized=True) for t in local_t]
        order=sorted(range(n),key=lambda i:(local_p[i],i))
        maximum=min(n,max(1,int(math.floor(float(p.get('max_fraction',.30))*n))))
        q=mp.mpf(str(p.get('q',1.0)))/100;cutoff=0
        for rank,position in enumerate(order[:maximum],1):
            threshold=q*rank/n;thresholds[indices[position]]=float(threshold)
            if local_p[position]<=threshold:cutoff=rank
        for position in order[:cutoff]:flags[indices[position]]=True
        for i,t,prob in zip(indices,local_t,local_p):tvalues[i]=float(t);probabilities[i]=float(prob)
        return [flags,probabilities,thresholds,tvalues,float(center),float(rsdr)]
