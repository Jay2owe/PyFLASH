"""Published immediate-threshold reduction into native constrained logistic fits.

Rennie (2005), equation 2 supplies the two neighbouring binary events. Native
glmnet supplies the fitted logistic model, not an audit-authored loss/gradient.
Ordered thresholds are represented by nonnegative threshold increments.
The first threshold is the free native intercept. Penalty-factor normalization
and the event count preserve the original summed ridge objective exactly.
Reference qualification and complete production comparisons remain required.
"""
from itertools import product
import json

SOURCES=(
 'https://people.csail.mit.edu/jrennie/writing/olr.pdf',
 'https://glmnet.stanford.edu/articles/glmnet.html',
 'https://papers.neurips.cc/paper/3125-ordinal-regression-by-extended-binary-classification.pdf',
)

def cases():
    for classes,profile,alpha in product((2,3,4,5),('balanced','rare-middle','varying-offset'),(0.,.1,1.,10.)):
        points=[[-2.,.5],[-1.,-1.],[0.,1.],[1.,-.5],[2.,1.5],[.5,-2.]]
        x=[points[i%6][:] for i in range(classes*12)]
        y=[(i//6+i%6)%classes for i in range(len(x))]
        if profile=='rare-middle' and classes>2:
            y=[0 if i<len(x)//2 else classes-1 for i in range(len(x))]
            for level in range(1,classes-1):y[level*3]=level
        elif profile=='varying-offset':
            x=[[a+(i//6)*.125,b-1.] for i,(a,b) in enumerate(x)]
            y=[(i*7+i//classes)%classes for i in range(len(x))]
        assert set(y)==set(range(classes))
        yield dict(key=f'classes-{classes}.{profile}.alpha-{alpha}',x=x,y=y,classes=classes,alpha=alpha,heldout=[[-1.25,.25],[.75,-.75],[2.25,1.25],[0.,0.]])

def _v(values):return 'c('+','.join(repr(float(v)) for v in values)+')'
def _matrix(rows):return 'matrix('+_v([v for row in rows for v in row])+',ncol='+str(len(rows[0]))+',byrow=TRUE)'

def query(case):
    x,y=case['x'],case['y'];k=case['classes'];p=len(x[0]);events=[]
    for i,level in enumerate(y):
        if level>0:events.append((i,level-1,1))
        if level<k-1:events.append((i,level,0))
    increments=max(0,k-2)
    # glmnet requires at least two predictors; a spare zero column contributes
    # no score or penalty. Its presence is included in penalty normalization.
    dummy=max(0,2-p-increments);width=p+increments+dummy
    design=[x[i]+[-float(cut>=j) for j in range(1,k-1)]+[0.]*dummy for i,cut,binary in events]
    native_lambda=case['alpha']*p/(len(events)*width)
    statements=['x<-'+_matrix(x),'z<-'+_matrix(design),'y<-'+_v([binary for i,cut,binary in events]),
        'f<-glmnet::glmnet(z,y,family="binomial",alpha=0,lambda='+repr(native_lambda)+',intercept=TRUE,standardize=FALSE,penalty.factor='+_v([1.]*p+[0.]*(increments+dummy))+',lower.limits=c(rep(-Inf,'+str(p)+'),rep(0,'+str(increments+dummy)+')),thresh=1e-14,maxit=1000000)',
        'stopifnot(f$jerr==0,length(f$lambda)==1,f$lambda=='+repr(native_lambda)+')',
        'b<-as.numeric(coef(f)); w<-b[2:'+str(p+1)+']; theta<-cumsum(c(-b[1]'+(',b['+str(p+2)+':'+str(p+1+increments)+']' if increments else '')+'))',
        'score<-as.numeric(rbind(x,'+_matrix(case['heldout'])+')%*%w)',
        'prob<-t(vapply(score,function(s)diff(c(0,plogis(theta-s),1)),numeric('+str(k)+')))',
        'pred<-vapply(score,function(s)sum(theta<s),integer(1))',
        'c(w,theta,as.numeric(t(prob)),pred)']
    return dict(key=case['key'],code='local({'+ ';'.join(statements)+'})',binary_events=len(events),design_columns=width,lambda_glmnet=native_lambda)

def unpack(case,values):
    p=len(case['x'][0]);k=case['classes'];n=len(case['x'])+len(case['heldout']);offset=p+k-1
    assert len(values)==offset+n*k+n
    return dict(coefficients=values[:p],thresholds=values[p:offset],probabilities=[values[offset+i*k:offset+(i+1)*k] for i in range(n)],predictions=values[offset+n*k:])
