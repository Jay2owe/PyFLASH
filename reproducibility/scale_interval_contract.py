"""Complete common-draw effect intervals retain scale and close-measurement accuracy."""
from pathlib import Path
import hashlib,json
import numpy as np
from reproducibility import scale_interval_reference as reference
def production(case):
    from reproducibility.scale_interval_adapter import production as actual
    return actual(case)

def equal(actual,expected):
    from reproducibility.scale_interval_adapter import equal as compare
    return compare(actual,expected)
FIXTURE=Path(__file__).with_name('fixtures')/'scale_interval_reference.json'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original scale-interval evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Interval requests, draws or answers differ from before-correction evidence')
    if fixture['absolute_tolerance']!=0.:raise ValueError('Positive interval endpoints cannot be accepted as zero')
    if fixture['independent_random_generator_vote'] is not False:raise ValueError('NumPy draws are a common input, not an independent generator vote')
    for case in fixture['rows']:
        p=case['parameters'];rng=np.random.RandomState(p['random_state'])
        draws=[rng.randint(0,len(group),size=(p['n_resamples'],len(group))).tolist() for group in (case['a'],case['b'])]
        if draws!=case['draws']:raise ValueError('Common subject-resampling tape changed: '+case['key'])
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);p=case['parameters'];answer=reference.interval(case['a'],case['b'],p['eftype'],p['confidence'],case['draws'])
        unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'independent-exact-measurement-effects/80-digit-root/BCa-equations/common-draws',
            'complete-two-sample-effect-interval',actual,answer,unchanged and equal(actual,answer),unchanged,'all-endpoints-and-undefinedness/atol-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'scale-interval-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
