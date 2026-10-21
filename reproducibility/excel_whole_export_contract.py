"""Complete declared workbook obligations; execution approval remains separate."""
import json
from pathlib import Path

ARCHIVE = Path(__file__).with_name('reference-sources') / 'excel-whole-export/v1'
MANIFEST_SHA256 = '6a1bd7f1cdffd8ec11fcc6fcf0605293f950a0930e05fbd3b218973f72ca6d98'
METHODS = ('export_excel', 'export_all_excel', 'export_IF_summary_excel',
           'export_unregistered_summary_excel', 'export_extra_summary_excel',
           'export_behavior_summary_excel', 'export_extended_data_excel')
# These are complete predeclared obligations, not passing-execution claims.
COMPLETE_CAPABILITIES = frozenset('PyFLASH.batch.Batch.' + method for method in METHODS)


def declaration():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256)
    return json.loads((ARCHIVE / 'declaration.json').read_text())


def required_keys(capability):
    return set(declaration()['required'].get(capability, ()))


def coverage(rows):
    """Reject missing, disagreeing or duplicated evidence without inventing cases."""
    d = declaration()
    expected = {key for family in d['families'] for key in family['keys']}
    prefixes = tuple({prefix for values in d['prefixes'].values() for prefix in values})
    evidence, duplicate, unknown = {}, set(), set()
    for row in rows:
        key = row['contract']
        if key not in expected:
            if key.startswith(prefixes): unknown.add(key)
            continue
        if key in evidence: duplicate.add(key)
        evidence[key] = row
    accepted = {key for key, row in evidence.items() if row['status'] == 'agree'
                and row['frozen_reference_agrees'] in (True, 'True')
                and row['missingness_equal'] in (True, 'True')}
    missing = expected - set(evidence)
    invalid = set(evidence) - accepted
    return dict(passed=not (missing or invalid or duplicate or unknown),
                expected_cases=len(expected), observed_cases=len(evidence),
                missing=sorted(missing), disagreements=sorted(invalid),
                duplicate=sorted(duplicate), undeclared=sorted(unknown),
                methods={cap: bool(set(keys) <= accepted and not (duplicate or unknown))
                         for cap, keys in d['required'].items()},
                scientific_estimator_claim=False)
