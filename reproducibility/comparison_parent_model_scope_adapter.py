from copy import deepcopy
from reproducibility import comparison_parent_inference_adapter as base

def production(case):
    raw=deepcopy(case);raw['groups']=raw['raw_groups']
    return base.production(raw)
