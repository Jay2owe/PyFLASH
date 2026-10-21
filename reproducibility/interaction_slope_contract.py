"""Complete independently derived two-group slope-comparison reports."""
from functools import lru_cache
from pathlib import Path
import hashlib,json,math

FIXTURE=Path(__file__).with_name('fixtures')/'interaction_slope_reference.json'

@lru_cache(maxsize=1)
def fixture():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))

@lru_cache(maxsize=1)
def _rows():
    return {row['case']['key']:row for row in fixture()['rows']}

def cases():
    return json.loads(json.dumps([row['case'] for row in fixture()['rows']]))

def expected(case):
    return json.loads(json.dumps(_rows()[case['key']]['expected']))

def clean(value):
    if isinstance(value,dict):return {key:clean(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [clean(item) for item in value]
    if isinstance(value,float) and not math.isfinite(value):return None if math.isnan(value) else str(value)
    return value

def production(case):
    from PyFLASH.stats import interaction_slope_difference
    try:return clean(interaction_slope_difference(**case['parameters']))
    except (ValueError,TypeError,OverflowError) as error:return {'error_type':type(error).__name__}

def equal(actual,answer,*,key=None):
    if isinstance(actual,dict):return isinstance(answer,dict) and actual.keys()==answer.keys() and all(
        equal(actual[k],answer[k],key=k) for k in actual)
    if isinstance(actual,(int,float)) and isinstance(answer,(int,float)):
        return math.isclose(actual,answer,rel_tol=1e-9,abs_tol=0. if key=='p' else 1e-12)
    return actual==answer

def check_identity():
    data=fixture();root=Path(__file__).parent
    definitions=json.dumps(cases(),sort_keys=True,separators=(',',':')).encode('utf-8')
    if hashlib.sha256(definitions).hexdigest()!=data['definitions_sha256']:
        raise ValueError('Frozen slope-comparison requests changed')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=data['adapter_sha256']:
        raise ValueError('Frozen slope-comparison adapter changed')
    for path,expected in data['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Independent slope reference identity changed: '+path)
    return data
