"""Independent high-precision objective stationarity and analytic covariance.

No PyFLASH curve, solver or fitted answer supplies the reference values.
"""
import math
import mpmath as mp

STARTS = {'exponential_growth':[2.,.12,1.7], 'exponential_decay':[5.,-.15,2.],
          'logistic_growth':[1.,9.,4.,1.5], 'logistic_decay':[8.,1.,5.,2.1]}


def reference(row):
    with mp.workdps(60):
        parameters = row['parameters']
        pairs = sorted((mp.mpf(float(x)),mp.mpf(float(y)))
            for x,y in zip(parameters['x'],parameters['y'])
            if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y)))
        x,y = [v[0] for v in pairs],[v[1] for v in pairs]
        n = len(x)
        model = parameters['model']
        if model=='exponential':
            function = lambda v,a,r,o: a*mp.exp(r*v)+o
        elif model=='logistic':
            function = lambda v,b,t,e,h: b+(t-b)/(1+(e/v)**h)
        else: raise ValueError('This reference covers nonlinear whole-fit cases only')
        def cost(*theta): return mp.fsum((value-function(v,*theta))**2 for v,value in zip(x,y))
        start = next(values for name,values in STARTS.items() if row['key'].startswith('growth.'+name+'.'))
        def gradient(*theta):
            return tuple(mp.diff(cost,theta,n=tuple(int(j==i) for j in range(len(theta))))
                         for i in range(len(theta)))
        theta = list(mp.findroot(gradient,start,tol=mp.mpf('1e-45'),maxsteps=100))
        # A stationary point must be a local minimum, not just a root.
        hessian = mp.matrix([[mp.diff(cost,theta,n=tuple(int(k==i)+int(k==j) for k in range(len(theta))))
                              for j in range(len(theta))] for i in range(len(theta))])
        mp.cholesky(hessian)
        if model=='logistic' and not (theta[2]>=mp.mpf('1e-9') and mp.mpf('.1')<=theta[3]<=10):
            raise ValueError('Interior reference violates declared parameter bounds')
        predictions = [function(v,*theta) for v in x]
        residual = mp.fsum((a-b)**2 for a,b in zip(y,predictions))
        total = mp.fsum((v-mp.fsum(y)/n)**2 for v in y)
        jacobian = mp.matrix([[mp.diff(lambda *t:function(v,*t),theta,
                         n=tuple(int(j==i) for j in range(len(theta))))
                         for i in range(len(theta))] for v in x])
        covariance = (jacobian.T*jacobian)**-1 * residual/(n-len(theta))
        errors = [mp.sqrt(covariance[i,i]) for i in range(len(theta))]
        aic = n*mp.log(residual/n)+2*len(theta)
        xx = [mp.mpf(float(v)) for v in parameters['prediction_x']]
        return [2 if model=='exponential' else 3,n,*map(float,theta),*map(float,errors),
                float(1-residual/total),float(aic),*[float(function(v,*theta)) for v in xx],float(aic)]
