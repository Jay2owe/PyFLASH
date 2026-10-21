"""Repeat the real package export and compare its separately saved carrier."""
from pathlib import Path
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'roi-preview-export'
MANIFEST_SHA256 = '20c4388341c755b03e9a994463df2ce2084e964fe7d27ad63db137f36bfc74df'
KEY = 'roi-analysis.saved-preview-reproduction'


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reprofig import verify_proof
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    bundle = ARCHIVE / 'Ventricle Analysis'
    master = bundle / 'Ventricle Analysis boundary M.svg'
    proof = verify_proof(master, required=['figure_reproduced'],
                         reproduction_report=bundle / 'verification/reproduction-report.json')
    assert proof.valid, proof.to_dict()
    return bundle, master


def production(output, observation=None):
    from reprofig import reproduce_figure, verify_proof
    bundle, master = check_identity()
    output = Path(output)
    report_path = output / 'reproduction-report.json'
    report = reproduce_figure(master, bundle_root=bundle, output_dir=output / 'reproduced',
                              report_path=report_path, execute_trusted_producer=True)
    assert report.valid, report.to_dict()
    assert verify_proof(master, required=['figure_reproduced'], reproduction_report=report_path).valid
    actual = {'execution': report.execution_status, **report.comparisons}
    expected = {'execution': 'pass', 'data_tables': 'pass', 'display': 'pass', 'statistics': 'pass'}
    assert actual == expected
    if observation is not None:
        observation.update(actual=actual, expected=expected)
    return actual


def validate(output):
    from reproducibility.table_family_validation import replay
    return replay([{'key': KEY}], lambda item, observed, path: production(path, observed), output,
        reference='Retained native-reference geometry, actual public package export and separate trusted-producer reproduction; no additional scientific implementation vote',
        family='whole-custom-boundary-saved-export', shape='embedded-tables-statistics-semantic-marks-carrier-binding-and-retained-separate-carrier')
