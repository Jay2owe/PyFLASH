"""Partial ordinal response contract over explicitly supplied finite model states."""
from pathlib import Path
import hashlib,json
from reproducibility import ordinal_response_reference as reference
from reproducibility.ordinal_response_adapter import production,equal
FIXTURE=Path(__file__).with_name('fixtures')/'ordinal_response_reference.json'
CAPABILITIES=('PyFLASH.modelling._PyFLASHOrdinalLogistic.predict',
 'PyFLASH.modelling._PyFLASHOrdinalLogistic.predict_proba')

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for name,digest in fixture['source_manifest'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Ordinal response evidence changed: '+name)
    before=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))
    extra=json.loads((root/fixture['additional_before_path']).read_text(encoding='utf-8'))
    if fixture['rows']!=before['rows']+extra['rows']:
        raise ValueError('Ordinal response requests or answers differ from original evidence')
    return fixture

def validate(output):
    from reproducibility.normality_association_validation import comparison
    from reproducibility.reference_runtime import execute_queries,values
    fixture=check_identity();root=Path(__file__).parent
    queries=json.loads((root/fixture['native_queries_path']).read_text(encoding='utf-8'))
    native=execute_queries(queries,output/'ordinal-response-native',name='ordinal-response-logistic-laws',timeout=900)
    if any(native[name]!=fixture['native_runtime'][name] for name in ('R','webR','wasm_sha256')):
        raise ValueError('Native ordinal response identity changed')
    native_answers={row['key']:list(values(row)) for row in native['rows']}
    rows=[];paired=[]
    for row in cases():
        case=row['case'];actual=production(case);answer=reference.report(case)
        unchanged=equal(answer,row['expected']);witness=None
        if 'native' in row:
            witness=native_answers[case['profile']]
            unchanged=unchanged and equal(witness,row['native'])
            if row['native_agrees']:
                flat=[p-case['first_label'] for p in answer['predictions']]+[p for r in answer['probabilities'] for p in r]
                unchanged=unchanged and equal(witness,flat)
        rows.append(comparison(case['key'],'exact-input/500-digit-logistic-law',
            'supplied-model-state/all-predictions-and-probabilities',actual,answer,
            unchanged and equal(actual,answer),unchanged,'relative-tolerance/absolute-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'native':witness,
                       'native_role':'corroboration' if row.get('native_agrees') else 'diagnostic-or-not-applicable'})
    (output/'ordinal-response-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
