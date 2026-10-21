"""Every model report, retained request, answer and source lineage."""
from pathlib import Path
from copy import deepcopy
import json,hashlib,warnings
import pandas as pd
import numpy as np
from PyFLASH import stats
from reproducibility.one_way_contract import clean,equal

FIXTURE=Path(__file__).with_name('fixtures')/'linear_model_complete_reference.json'
def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']
def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original model evidence changed: '+path)
    original=[row for path in fixture['before_rounds'] for row in json.loads((root/path).read_text(encoding='utf-8'))['rows']]
    if fixture['rows']!=original:raise ValueError('Model requests or answers differ from frozen before-correction evidence')
    return fixture
def production(case):
    parameters=deepcopy(case['parameters']);kwargs=parameters.get('cov_kwds') or {}
    for key in ('groups','time'):
        if key in kwargs:kwargs[key]=np.asarray(kwargs[key])
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            probabilities,annotations,overall,result,method=stats.runLinearModel(pd.DataFrame(deepcopy(case['data'])),results_dict={'caller-note':'retained'},**parameters)
        return clean({'pvalues':probabilities,'annotations':annotations,'overall':overall,'results_dict':result,'method':method})
    except Exception as error:return {'error':type(error).__name__}
