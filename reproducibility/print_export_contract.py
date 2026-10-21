"""Frozen report presentation, ordered export cells and failure ownership."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import csv,hashlib,json
from PyFLASH import stats
from reproducibility.report_functional_reference import unpack
FIXTURE=Path(__file__).with_name('fixtures')/'print_export_complete_reference.json'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((Path(__file__).parent/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Original report/export evidence changed: '+path)
    original=json.loads((Path(__file__).parent/'reference-sources/print-export/frozen-before.json').read_text(encoding='utf-8'))
    if fixture['rows']!=original['rows']:
        raise ValueError('Report inputs or answers differ from frozen before-correction evidence')
    return fixture

def print_production(case):
    from PyFLASH.aesthetics import pyflash_style_context
    style = {**case['style'], 'significance_thresholds': {float(k): v for k, v in case['style']['significance_thresholds'].items()}}
    names = [SimpleNamespace(name=name) for name in case['names']] if case['objects'] else case['names']
    try:
        with pyflash_style_context(**style):
            answer = stats.print_comparison_results(condition_list=names, **case['parameters'])
        return {'result': list(answer)}
    except Exception as error:
        return {'error': type(error).__name__}

def export_production(case, output):
    directory = output / case['key']
    legacy = directory / 'legacy'
    override = directory / 'override'
    legacy.mkdir(parents=True, exist_ok=False)
    override.mkdir()
    p = unpack(deepcopy(case['parameters']))
    original = deepcopy(p)
    target = (override if case['override'] else legacy) / (p['save_name'] + '.csv')
    target.write_bytes(b'accepted previous report\n')
    try:
        returned = stats.results_to_excel(experiment_save_path=legacy, output_dir=override if case['override'] else None, **p)
        with target.open(encoding='utf-8', newline='') as stream:
            rows = list(csv.reader(stream))
        return {'result': returned, 'rows': rows, 'output_override_used': target.parent == override, 'input_unchanged': repr(p) == repr(original)}
    except Exception as error:
        return {'error': type(error).__name__, 'previous_file_preserved': target.read_bytes() == b'accepted previous report\n', 'input_unchanged': repr(p) == repr(original)}

def production(case,output):
    return print_production(case) if case['kind']=='print' else export_production(case,output)

def validate(output):
    from reproducibility import report_functional_reference as reference
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case,output/'report-outputs')
        expected=reference.print_reference(case) if case['kind']=='print' else reference.export_reference(case)
        unchanged=expected==case['expected'];agrees=unchanged and actual==expected
        rows.append(comparison(case['key'],'literal-ordered-captions-and-exported-cells',
            'functional-report-presentation-and-atomic-export/no-inference-vote',actual,expected,agrees,unchanged,
            'all-captions-cells-output-ownership-and-typed-errors',0.,0.))
        paired.append({'case':case,'production':actual,'reference':expected,'agrees':agrees})
    (output/'report-export-paired-data.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
