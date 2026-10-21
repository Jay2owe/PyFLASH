"""Complete functional correlation/model record schemas, including headline text."""
from pathlib import Path
import hashlib,json
from reproducibility import regression_record_reference as reference
from reproducibility.regression_record_adapter import production,decode
FIXTURE=Path(__file__).with_name('fixtures')/'regression_record_reference.json'
CAPABILITIES={'correlation':'PyFLASH.report.build_correlation_record',
    'multivariable_regression':'PyFLASH.report.build_multivariable_regression_record',
    'linear_model':'PyFLASH.report.build_linear_model_record','stars':'PyFLASH.report.significance_stars'}


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def capability(case):return CAPABILITIES[case['kind']]


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original report-builder evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Report-builder requests or answers differ from before-correction evidence')
    if fixture['contract_kind']!='functional-supplied-input-schema':raise ValueError('Record construction is not fitted inference')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report({**case,'parameters':decode(case['parameters'])});unchanged=answer==case['expected']
        rows.append(comparison(case['key'],'literal-complete-supplied-input-record-and-headline-schema',
            'functional-complete-record-construction/no-fitted-inference-vote',actual,answer,
            unchanged and actual==answer,unchanged,'exact-fields-types-values-and-headline',0.,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'regression-record-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
