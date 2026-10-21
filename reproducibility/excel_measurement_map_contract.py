"""Exact declared display labels/descriptions; no whole workbook or estimator claim."""
import hashlib
import json
from pathlib import Path

ARCHIVE = Path(__file__).with_name('reference-sources') / 'excel-measurement-maps/v6'
MANIFEST_SHA256 = '180f788d4266086e4176122dc8e591ed45d8d6da8c02cbcdaff17cc657c5a402'
SEMANTIC_ARCHIVE = Path(__file__).with_name('reference-sources') / 'excel-coordinate-area-semantics/v1'
SEMANTIC_MANIFEST_SHA256 = '58dd38b1608b4ff2ac7d4ccc836c07f5608abff3896ad635313465e9d495daf7'
COMPLETE_CAPABILITIES = frozenset()
from reproducibility.excel_literal_cell_contract import CAPABILITY_PREFIXES as EXPORT_CAPABILITIES
_METHOD_MAPS = {
    'export_IF_summary_excel': ('IF_NAME_MAP',),
    'export_extended_data_excel': ('RAW_NAME_MAP',),
    'export_behavior_summary_excel': ('BEHAVIOR_NAME_MAP',),
    'export_unregistered_summary_excel': ('IF_NAME_MAP',),
    'export_extra_summary_excel': ('IF_NAME_MAP',),
}
CAPABILITY_PREFIXES = {capability: tuple('excel-measurement-map.'+name+'.' for name in
    _METHOD_MAPS.get(capability.rsplit('.',1)[-1], ('IF_NAME_MAP','RAW_NAME_MAP','BEHAVIOR_NAME_MAP')))
    for capability in EXPORT_CAPABILITIES}

def check_identity():
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(ARCHIVE/'source-manifest.json') != MANIFEST_SHA256:
        raise ValueError('Original Excel measurement-map manifest changed')
    for name, digest in json.loads((ARCHIVE/'source-manifest.json').read_text(encoding='utf-8')).items():
        if sha(ARCHIVE/name) != digest:
            raise ValueError('Original Excel measurement-map evidence changed: ' + name)
    return json.loads((ARCHIVE/'measurement-map-reference.json').read_text(encoding='utf-8'))

def cases():
    rows = check_identity()['rows']
    for row in rows:
        row['key'] = 'excel-measurement-map.' + row['mapping'] + '.' + row['pattern']
        row['_case_digest'] = hashlib.sha256(json.dumps(row, sort_keys=True).encode('utf-8')).hexdigest()
    return rows

def observe(row):
    packet = {name: value for name, value in row.items() if name != '_case_digest'}
    assert hashlib.sha256(json.dumps(packet, sort_keys=True).encode('utf-8')).hexdigest() == row['_case_digest'], 'Declared measurement mapping changed'
    from PyFLASH import export
    if row['mapping'] == 'IF_NAME_MAP':
        value = export.convert_name(row['column'], truncate=False)
    elif row['mapping'] == 'RAW_NAME_MAP':
        value = export.convert_raw_name(row['column'])
    elif row['mapping'] == 'BEHAVIOR_NAME_MAP':
        value = export.convert_behavior_name(row['column'], truncate=False)
    else:
        raise ValueError('Unknown declared measurement map')
    return dict(label=value[0], description=value[1])


def check_coordinate_area_original_failures():
    """Authenticate original meaning controls without rescoring their failures."""
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(SEMANTIC_ARCHIVE, 'source-manifest.json', SEMANTIC_MANIFEST_SHA256)
    receipt = json.loads((SEMANTIC_ARCHIVE/'run.json').read_text(encoding='utf-8'))
    paired = json.loads((SEMANTIC_ARCHIVE/'paired.json').read_text(encoding='utf-8'))
    assert receipt['numerical_controls'] == 4 and receipt['numerical_disagreements'] == 0
    assert receipt['display_controls'] == 3 and receipt['display_disagreements'] == 3
    assert not receipt['source_changes'] and not receipt['production_source_edited']
    assert len(paired['numerical_controls']) == 4 and all(row['agrees'] for row in paired['numerical_controls'])
    assert len(paired['display_controls']) == 3 and all(not row['agrees'] for row in paired['display_controls'])
    return paired

def check_mapping_inventory():
    from PyFLASH import export
    fixture = check_identity()
    expected = {name: {row['pattern'] for row in fixture['rows'] if row['mapping'] == name}
                for name in ('IF_NAME_MAP', 'RAW_NAME_MAP', 'BEHAVIOR_NAME_MAP')}
    actual = {name: set(getattr(export, name)) for name in expected}
    if actual != expected:
        raise ValueError('Excel measurement mapping inventory needs extended frozen cases')
    return actual

def required_keys(capability):
    prefixes=CAPABILITY_PREFIXES.get(capability,())
    return {row['key'] for row in cases() if row['key'].startswith(prefixes)}

def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    paired, results = [], []
    check_mapping_inventory()
    for row in cases():
        observed = error = None
        try: observed = observe(row)
        except Exception as exception: error = type(exception).__name__ + ': ' + str(exception)
        expected = dict(label=row['expected_label'], description=row['expected_description'])
        agrees = error is None and observed == expected
        paired.append(dict(case=row, observed=observed, expected=expected, error=error, agrees=agrees))
        results.append(comparison(row['key'], 'predeclared-accepted-display-map/canonical-Unicode-units',
            'functional-display-converter-support/not-whole-workbook/no-extra-estimator-vote',
            observed, expected, agrees, True, 'exact-complete-label-and-description', 0., 0.))
    write_json(Path(output)/'excel-measurement-map-paired.json',
               dict(schema_version=1, complete_contract=False, scope=__doc__, rows=paired))
    return results
