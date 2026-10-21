"""Partial scientific fit controls: zero features, positive penalty."""
from pathlib import Path
import hashlib,json
from reproducibility import ordinal_zero_reference as reference
from reproducibility.ordinal_zero_adapter import production,equal
FIXTURE=Path(__file__).with_name('fixtures')/'ordinal_zero_reference.json'
CAPABILITIES=('PyFLASH.modelling._PyFLASHOrdinalLogistic.fit',
 'PyFLASH.modelling._PyFLASHOrdinalLogistic.predict','PyFLASH.modelling._PyFLASHOrdinalLogistic.predict_proba')

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for name,digest in fixture['source_manifest'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('Ordinal fit evidence changed: '+name)
    before=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))
    if fixture['rows']!=before['rows']:raise ValueError('Ordinal requests or answers differ from original evidence')
    return fixture

def validate(output):
    from reproducibility.normality_association_validation import comparison
    from reproducibility.reference_runtime import execute_queries,values
    fixture=check_identity();root=Path(__file__).parent
    query_file=root/fixture['native_queries_path']
    queries=json.loads(query_file.read_text(encoding='utf-8'))
    native=execute_queries(queries,output/'ordinal-zero-native',name='ordinal-zero-count-optimum',timeout=900)
    if any(native[name]!=fixture['native_runtime'][name] for name in ('R','webR','wasm_sha256')):raise ValueError('Native ordinal reference identity changed')
    native_answers={row['key']:list(values(row)) for row in native['rows']}
    rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case)
        flat=answer['theta']+answer['probabilities'][0]+[answer['predictions'][0]-case['first_label']]
        witness=native_answers['counts.'+'.'.join(map(str,case['counts']))]
        unchanged=equal(answer,case['expected']) and equal(witness,case['native'])
        agrees=unchanged and equal(actual,answer) and equal(flat,witness)
        rows.append(comparison(case['key'],'exact-count-optimum/high-precision/native-R',
            'zero-feature-fit/all-coefficients-thresholds-classes-predictions-probabilities',actual,answer,
            agrees,unchanged,'relative-tolerance/absolute-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'native':witness})
    (output/'ordinal-zero-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows

def regressions():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    return json.loads((Path(__file__).parent/fixture['nonzero_compatibility_path']).read_text(encoding='utf-8'))['rows']
