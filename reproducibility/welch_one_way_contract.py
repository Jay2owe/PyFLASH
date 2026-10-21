"""Complete unequal-variance reports and unchanged staged before answers."""
from pathlib import Path
from copy import deepcopy
import json,hashlib,warnings
from PyFLASH import stats
from reproducibility.one_way_contract import equal,clean
FIXTURE=Path(__file__).with_name('fixtures')/'welch_one_way_complete_reference.json'

def cases():return json.loads(FIXTURE.read_text())['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text());root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original unequal-variance evidence changed: '+path)
    original=[row for path in fixture['before_rounds'] for row in json.loads((root/path).read_text())['rows'] if row['family']==fixture['family']]
    if original!=fixture['rows']:raise ValueError('Unequal-variance inputs or answers differ from frozen before-correction evidence')
    return fixture

def production(case):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            p,labels,overall,result,method=stats.runWelchOWA(results_dict={'caller-note':'retained'},**deepcopy(case['parameters']))
        return clean({'pvalues':p,'annotations':labels,'overall':overall,'results_dict':result,'method':method})
    except Exception as error:return {'error':type(error).__name__}
