"""Independent 70-digit constrained least-squares and saturated-fit conventions."""
import math
import mpmath as mp

NAMES={'linear':['slope','intercept'],'exponential':['amplitude','rate','offset'],
       'logistic':['bottom','top','ec50','hill']}

def fit(x,y,prediction_x,model,initial,fixed_hill=None,fixed_ec50=None):
    with mp.workdps(70):
        xx=list(map(lambda v:mp.mpf(float(v)),x));yy=list(map(lambda v:mp.mpf(float(v)),y))
        if model=='linear':function=lambda v,s,b:s*v+b
        elif model=='exponential':function=lambda v,a,r,o:a*mp.exp(r*v)+o
        else:function=lambda v,b,t,e,h:b+(t-b)/(1+(e/v)**h)
        names=NAMES[model];k=len(names);n=len(xx)
        fixed = {}
        if fixed_hill is not None: fixed[3] = mp.mpf(str(fixed_hill))
        if fixed_ec50 is not None: fixed[2] = mp.mpf(str(fixed_ec50))
        free = [i for i in range(k) if i not in fixed]
        def full(theta):
            result = [None]*k
            for i,value in fixed.items(): result[i]=value
            for i,value in zip(free,theta): result[i]=value
            return result
        def cost(*theta):return mp.fsum((value-function(time,*full(theta)))**2 for time,value in zip(xx,yy))
        q=len(free)
        def score(*theta):return tuple(mp.diff(cost,theta,n=tuple(int(i==j) for j in range(q))) for i in range(q))
        theta=list(mp.findroot(score,[mp.mpf(initial[i]) for i in free],tol=mp.mpf('1e-55'),maxsteps=100))
        hessian=mp.matrix([[mp.diff(cost,theta,n=tuple(int(i==z)+int(j==z) for z in range(q)))
                            for j in range(q)] for i in range(q)])
        mp.cholesky(hessian)
        parameters=full(theta)
        if model=='logistic':
            assert parameters[2]>=mp.mpf('1e-9') and mp.mpf('.1')<=parameters[3]<=10
            if fixed_hill is not None:
                derivative=mp.diff(lambda hill:mp.fsum((value-function(time,parameters[0],parameters[1],parameters[2],hill))**2
                    for time,value in zip(xx,yy)),parameters[3])
                assert derivative<0 if fixed_hill==10 else derivative>0
            if fixed_ec50 is not None:
                derivative=mp.diff(lambda midpoint:mp.fsum((value-function(time,parameters[0],parameters[1],midpoint,parameters[3]))**2
                    for time,value in zip(xx,yy)),parameters[2])
                assert derivative>0
        sse=cost(*theta);sst=mp.fsum((v-mp.fsum(yy)/n)**2 for v in yy)
        if not fixed and n>k:
            jacobian=mp.matrix([[mp.diff(lambda *p:function(time,*p),parameters,
                            n=tuple(int(i==j) for j in range(k))) for i in range(k)] for time in xx])
            covariance=(jacobian.T*jacobian)**-1*sse/(n-k)
            stderr=[float(mp.sqrt(covariance[i,i])) for i in range(k)]
        else:stderr=['nan']*k
        aic=float(n*mp.log(sse/n)+2*k) if n>k else 'nan'
        return {'model':model,'params':{name:{'value':float(v),'stderr':e} for name,v,e in zip(names,parameters,stderr)},
            'r_squared':float(1-sse/sst) if sst else 'nan','aic':aic,'n':n,
            'predictions':[float(function(mp.mpf(float(time)),*parameters)) for time in prediction_x],
            'all_models':{model:{'aic':aic}}}
