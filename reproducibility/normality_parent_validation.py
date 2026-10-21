"""Replay full reports and unchanged published R kernels; retain native limits."""
from pathlib import Path
import json
from reproducibility import normality_parent_contract as contract
from reproducibility.reference_runtime import execute_queries,values
from reproducibility.normality_association_validation import comparison
ARCHIVE=Path(__file__).with_name('reference-sources')/'normality-parent'

def native_cases():return json.loads((ARCHIVE/'native/frozen-before.json').read_text(encoding='utf-8'))['rows']

def required_keys():
    from reproducibility.comparison_parent_routing_contract import cases as routing_cases
    return ({row['key'] for row in contract.cases()}
            |{row['key'] for row in native_cases() if row['role']=='independent-native-corroboration'}
            |{row['key'] for row in routing_cases() if row.get('high_precision_ks')})

def validate(output):
    rows=contract.validate(output)
    fixture=json.loads((ARCHIVE/'native/frozen-before.json').read_text(encoding='utf-8'))
    queries=json.loads((ARCHIVE/'native/published-native-queries.json').read_text(encoding='utf-8'))
    native=execute_queries(queries,output/'published-native',name='published-pooled-normality',timeout=900)
    for key,expected in fixture['native_runtime'].items():
        if native[key]!=expected:raise ValueError('Published normality runtime changed: '+key)
    fresh={row['key']:contract.clean(list(values(row))) for row in native['rows']};paired=[]
    for case in native_cases():
        answer=fresh[case['key']];unchanged=contract.equal(answer,case['published_native'])
        if not unchanged:raise ValueError('Published normality kernel result changed: '+case['key'])
        if case['role']=='independent-native-corroboration':
            actual=contract.production({'parameters':{'df_list':[case['native_input_values']],'make_plot':False}})['results_dict'][case['method']]
            rows.append(comparison(case['key'],'unchanged-pinned-R/fBasics4032.96',
                'native-statistic-and-probability/no-extra-vote-for-equivalent-units',actual,answer,
                contract.equal(actual,answer,('results_dict',case['method'])),unchanged,'positive-probability-atol-zero',1e-9,0.))
        else:actual=None
        paired.append({'case':case,'production':actual,'published_native':answer,'unchanged':unchanged})
    (output/'normality-parent-native-paired-data.json').write_text(json.dumps({'rows':paired,
        'bounded_native_diagnostics':fixture['bounded_native_diagnostics']},indent=2,allow_nan=False),encoding='utf-8')
    return rows
