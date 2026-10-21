"""Complete raw-table refresh and unchanged-state refusal on original CSV fields."""
from pathlib import Path
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'mini-csv-refresh-native'
MANIFEST_SHA256 = '5d473008d1d3fc84257e93fb1f22cf7b4f31dcf9bf671dfae3c56a756e75fc0b'
COMPLETE_CAPABILITIES = frozenset()
CAPABILITY_PREFIXES = {'PyFLASH.experiment.MiniExperiment.importCSVs': ('mini-csv-refresh.',)}


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import mini_csv_refresh_reference as reference
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    assert Path(reference.__file__).read_bytes() == (ARCHIVE / 'csv_refresh_reference_v2.py').read_bytes()
    assert list(reference.cases()) == [row['case'] for row in read('csv-refresh-original-v2/before.json')['rows']]


def cases():
    return [dict(key='mini-csv-refresh.' + row['case']['key'], case=row['case'], expected=row['expected'])
            for row in read('csv-refresh-original-v2/before.json')['rows']]


def production(item, output, observation=None):
    from reproducibility import mini_csv_refresh_reference as reference
    from reproducibility.reference_runtime import values
    original = next(row for row in read('csv-refresh-original-v2/before.json')['rows'] if row['case'] == item['case'])
    answers = values(original['native'])
    expected = {name: reference.table(frame) for name, frame in reference.expected(item['case'], answers).items()}
    assert expected == original['expected'] == item['expected']
    result = reference.production(item['case'], answers, output)
    if observation is not None:
        observation.update(actual=result, expected=item['expected'])
    assert result['passed'], result.get('error')
    return result, item['expected']


def validate(output):
    from reproducibility import mini_csv_refresh_reference as reference
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity()
    queries = [reference.query(item['case']) for item in cases()]
    assert queries == read('csv-refresh-original-v2/native/csv-refresh-fields-queries.json')
    native = execute_queries(queries, Path(output) / 'native', name='csv-refresh-fields')
    assert native['rows'] == read('csv-refresh-original-v2/native/csv-refresh-fields-results.json')['rows']
    return replay(cases(), lambda item, observed, path: production(item, path, observed), output,
        reference='Native R CSV fields and original/refreshed condition-label mapping; declared atomic refresh and provenance policy',
        family='native-R/full-flat-CSV-refresh-and-unchanged-state-refusal',
        shape='every-raw-table-field-dtype-carrier-mapping-label-summary-and-provenance-owner')
