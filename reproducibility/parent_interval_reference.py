"""Accepted complete point reports plus independent full interval equations."""
from copy import deepcopy
from functools import lru_cache
import numpy as np
from reproducibility.normality_parent_reference import finite_groups
from reproducibility.scale_interval_reference import interval


@lru_cache(maxsize=256)
def endpoints(a,b,resamples,seed):
    if min(len(a),len(b))<2:return ['nan','nan']
    rng=np.random.RandomState(seed)
    draws=[rng.randint(0,len(group),size=(resamples,len(group))).tolist() for group in (a,b)]
    return interval(list(a),list(b),'hedges',.95,draws)


def report(case):
    answer=deepcopy(case['point_expected'])
    if 'error' in answer:return answer
    groups=None
    for label,value in answer['results_dict'].items():
        if label.startswith('Effect ') and label.endswith('(hedges_g)'):
            if groups is None:groups=finite_groups(case['point_case']['parent']['groups'])
            token=label[len('Effect '):-len(' (hedges_g)')].strip();a,b=map(int,token.split('-'))
            value[1]=endpoints(tuple(groups[a-1]),tuple(groups[b-1]),case['resamples'],case['seed'])
    return answer
