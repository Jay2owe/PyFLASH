"""One pinned published native field reference shared by both ANOVA parents."""
from pathlib import Path
import json
from reproducibility import one_way_contract as contract
from reproducibility.normality_association_validation import comparison
from reproducibility.reference_runtime import execute_queries,values
FIXTURE=Path(__file__).with_name('fixtures')/'anova_reported_fields_native_reference.json'

def cases(family):return [r for r in json.loads(FIXTURE.read_text())['rows'] if r['family']==family]

def validate(family,output):
    fixture=json.loads(FIXTURE.read_text());selected=cases(family)
    native=execute_queries([r['query'] for r in selected],output,name='native-'+family+'-anova-report-fields',timeout=900)
    for key,expected in fixture['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Native report-field runtime changed: '+key)
    observed={r['key']:values(r) for r in native['rows']};rows=[];diagnostics=[]
    for case in selected:
        actual=contract.clean(observed[case['query']['key']]);expected=case['expected']
        if case['role']!='independent-native-corroboration':diagnostics.append({'case':case,'native':actual});continue
        prefix=2 if family=='ordinary' else 4
        agrees=len(actual)==len(expected) and all(contract.equal(a,b,('pvalues',) if i==1 or i>=prefix+case['statistic_count'] else ()) for i,(a,b) in enumerate(zip(actual,expected)))
        rows.append(comparison(case['query']['key'],'unchanged-R-stats/pinned-PMCMRplus/native-statistic-fields',
            'published-parent-report-field-corroboration/common-units-and-declared-signs/no-extra-engine-vote',actual,expected,agrees,True,
            'all-numeric-report-fields/probability-atol-zero',1e-9,1e-12))
    (output/'diagnostics.json').write_text(json.dumps(diagnostics,indent=2,allow_nan=False),encoding='utf-8')
    return rows
