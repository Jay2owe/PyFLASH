"""Installed sklearn parameter protocol; functional, not scientific inference."""
from copy import deepcopy
from sklearn.base import BaseEstimator

class Reference(BaseEstimator):
    def __init__(self,alpha=1.,max_iter=10000):self.alpha=alpha;self.max_iter=max_iter

def observe(cls,case):
    model=cls(**deepcopy(case['initial']));events=[]
    for update in case['updates']:
        before=model.get_params(deep=False)
        try:
            returned=model.set_params(**deepcopy(update));result={'returns_self':returned is model}
        except Exception as error:result={'error':type(error).__name__}
        events.append({'before':before,'edit':update,'result':result,
            'shallow':model.get_params(deep=False),'deep':model.get_params(deep=True),
            'unknown_attributes':sorted(key for key in model.__dict__ if key not in {'alpha','max_iter'})})
    return {'events':events,'defaults':cls().get_params(),'after':model.get_params()}
