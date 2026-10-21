"""Complete pooled normality reports, including every returned plot coordinate."""
from pathlib import Path
import hashlib,json
from reproducibility.one_way_contract import clean,equal
from reproducibility import normality_parent_reference as reference
FIXTURE=Path(__file__).with_name('fixtures')/'normality_parent_complete_reference.json'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original pooled normality evidence changed: '+path)
    before=json.loads((root/fixture['before_round']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=before:raise ValueError('Normality inputs or answers differ from frozen before-correction evidence')
    previous=json.loads((root/fixture['superseded_before_round']).read_text(encoding='utf-8'))['rows']
    for old,new in zip(previous,before):
        if any(old.get(key)!=new.get(key) for key in ('key','dataset','parameters','original')):
            raise ValueError('Original normality requests or application failures were replaced')
        old_answer=json.loads(json.dumps(old['expected']));new_answer=json.loads(json.dumps(new['expected']))
        # The sole scientific revision corrects an overwritten matrix boundary
        # in the independent KS reference; it precedes application changes.
        for answer in (old_answer,new_answer):
            if 'KS' in answer.get('results_dict',{}):answer['results_dict']['KS'][1]=None
            if answer.get('figure') and answer.get('results_dict'):
                texts=answer['figure']['axes'][0]['texts']
                texts[:]=['\n'.join(line for line in text.splitlines() if not line.startswith('KS:')) for text in texts]
        if old_answer!=new_answer:raise ValueError('Normality reference revision changed an unrelated field')
    return fixture

def production(case):
    # The adapter itself was exercised before correction and is retained byte
    # for byte, with its package import as the sole mechanical difference.
    from reproducibility.normality_parent_adapter import production as observe
    return observe(case)

def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'exact-moments/80-digit-published-normality-laws/complete-histogram-and-QQ-arrays',
            'whole-pooled-normality-report',actual,answer,unchanged and equal(actual,answer),unchanged,'positive-probability-atol-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'normality-parent-paired-data.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
