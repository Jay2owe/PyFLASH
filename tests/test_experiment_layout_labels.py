from pathlib import Path
import json
import pytest
from PyFLASH import experiment
FROZEN=Path(__file__).resolve().parents[1]/'reproducibility/reference-sources/experiment-layout-labels/frozen-before'
ROWS=json.loads((FROZEN/'frozen-before.json').read_text(encoding='utf-8'))['rows']

@pytest.mark.parametrize('record',ROWS,ids=[row['case']['key'] for row in ROWS])
def test_supported_lookup_preserves_paths_and_declares_the_correct_layout(tmp_path,record):
    case=record['case']
    for name in case['directories']:(tmp_path/name).mkdir(parents=True,exist_ok=True)
    for name,text in case['files'].items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    source=str((tmp_path/case['query']).resolve()) if case['query'] is not None else None
    before={str(path.relative_to(tmp_path)):path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    actual=experiment.resolve_experiment_paths(source)
    expected=case['expected']
    if expected is not None:
        expected={key:str((tmp_path/value).resolve()) if key.endswith('_path') else value for key,value in expected.items()}
    assert actual==expected
    assert experiment.resolve_experiment_data_path(source)==(expected['data_path'] if expected else None)
    assert experiment.is_experiment_folder(source)==(expected is not None)
    after={str(path.relative_to(tmp_path)):path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    assert before==after


def test_explicit_legacy_label_survives_new_export_role_overlap(tmp_path):
    legacy=tmp_path/'Data Analysis';legacy.mkdir()
    for role in ('Objects','Intensity','ROIs'):(legacy/role).mkdir()
    assert experiment.resolve_experiment_paths(str(tmp_path))['layout']=='legacy'
    assert experiment.resolve_experiment_paths(str(legacy))['layout']=='legacy'
