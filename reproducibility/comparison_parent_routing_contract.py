"""Complete automatic/two-group reports; other parent options remain open."""
from pathlib import Path
import hashlib,json
from reproducibility.one_way_contract import clean,equal
from reproducibility import comparison_parent_routing_reference as reference
from reproducibility.comparison_parent_routing_adapter import production
FIXTURE=Path(__file__).with_name('fixtures')/'comparison_parent_routing_reference.json'
ARCHIVE=Path(__file__).with_name('reference-sources')/'comparison-parent-routing'


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original comparison-routing evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:
        raise ValueError('Routing requests or answers differ from before-correction evidence')
    previous=json.loads((root/fixture['previous_before_path']).read_text(encoding='utf-8'))['rows']
    if original[:len(previous)]!=previous:
        raise ValueError('Earlier routing requests, answers or original failures were replaced')
    if fixture['scientific_parent_complete'] is not False:
        raise ValueError('This routing round cannot certify every public-parent option')
    frozen=(ARCHIVE/'before/mathematical_reference.py').read_text()
    relocated=frozen.replace("Path(__file__).parent/'comparison-parent-routing-native-before/frozen-before.json'",
        "Path(__file__).parent/'reference-sources/comparison-parent-routing/native/frozen-before.json'")
    if Path(reference.__file__).read_text()!=relocated:
        raise ValueError('Independent routing equations changed during installation')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    from reproducibility.reference_runtime import execute_queries,values
    check_identity()
    native_fixture=json.loads((ARCHIVE/'native/frozen-before.json').read_text())
    queries=json.loads((ARCHIVE/'native/published-native/published-routing-range-queries.json').read_text())
    native=execute_queries(queries,output/'routing-native',name='published-routing-range',timeout=900)
    for key,expected in native_fixture['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Published routing-tail runtime changed: '+key)
    answers={row['key']:list(values(row))[0] for row in native['rows']}
    for row in native_fixture['rows']:
        if not equal(answers[row['key']],row['published_native'],('pvalues',)):
            raise ValueError('Published native routing tail changed: '+row['key'])
    rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'independent-routing/equations/500-digit-KS-witness/unchanged-native-R-range',
            'complete-returned-routing-report/remaining-parent-options-not-certified',actual,answer,
            unchanged and equal(actual,answer),unchanged,'all-returned-fields/positive-probability-atol-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'comparison-parent-routing-paired.json').write_text(json.dumps({'rows':paired,
        'published_native_tails':native_fixture,'native_vote_scope':'Freshly replayed external tail inputs; no extra scientific vote for repeated use.'},indent=2,allow_nan=False),encoding='utf-8')
    return rows
