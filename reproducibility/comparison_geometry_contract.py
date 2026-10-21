"""Complete in-memory group uncertainty and comparison drawing contracts."""
from pathlib import Path
import hashlib,json
from reproducibility import comparison_geometry_reference as reference
def production(case):
    from reproducibility.comparison_geometry_adapter import production as actual
    return actual(case)
equal=reference.same
FIXTURE=Path(__file__).with_name('fixtures')/'comparison_geometry_reference.json'
CAPABILITIES=('PyFLASH.stats.draw_comparison_brackets',
 'PyFLASH.stats.plot_comparison_lines_from_figdata','PyFLASH.stats.plot_comparison_lines_from_fig_data')


def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']


def required_keys():return {row['key'] for row in cases()}


def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original drawing evidence changed: '+path)
    original=json.loads((root/fixture['before_path']).read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=original:raise ValueError('Drawing requests or answers differ from before-correction evidence')
    return fixture


def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);answer=reference.report(case);unchanged=equal(answer,case['expected'])
        rows.append(comparison(case['key'],'independent-rational-moments/literal-geometric-equations',
            'complete-helper-returns/all-lines-labels-colors-anchors-axis-limits',actual,answer,
            unchanged and equal(actual,answer),unchanged,'all-drawing-fields/absolute-tolerance-zero',1e-9,0.))
        paired.append({'case':case,'production':actual,'reference':answer,'frozen_reference':case['expected']})
    (output/'comparison-geometry-paired.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
