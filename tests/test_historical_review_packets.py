import json
import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Actual NTFS compression')
def test_explicit_review_list_preserves_bytes_and_tests_restoration(tmp_path):
    base = tmp_path / 'PyFLASH'
    base.mkdir()
    original = base / 'review.log'
    payload = b'preserve failure diagnostics\n' * 10000
    original.write_bytes(payload)
    selection = tmp_path / 'selected.json'
    selection.write_text(json.dumps(['review.log']))
    packet = tmp_path / 'packet'
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path))
    result = subprocess.run([sys.executable, '-m', 'reproducibility.compress_historical_reviews',
                             '--packet', str(packet), '--file-list', str(selection)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((packet / 'run.json').read_text())
    assert receipt['passed'] and receipt['restored_scratch_absent']
    assert receipt['rows'][0]['restoration_verified']
    assert receipt['files_deleted'] == 0
    assert original.read_bytes() == payload
    assert receipt['selected_relative_paths'] == ['review.log']
    assert receipt['selection_sha256']


@pytest.mark.skipif(os.name != 'nt', reason='Windows review entry point')
def test_review_list_rejects_escape_before_changing_original(tmp_path):
    (tmp_path / 'PyFLASH').mkdir()
    outsider = tmp_path / 'outside.log'
    outsider.write_bytes(b'keep')
    selection = tmp_path / 'selected.json'
    selection.write_text(json.dumps(['../outside.log']))
    result = subprocess.run([sys.executable, '-m', 'reproducibility.compress_historical_reviews',
                             '--packet', str(tmp_path / 'packet'), '--file-list', str(selection)],
                            env=dict(os.environ, LOCALAPPDATA=str(tmp_path)),
                            capture_output=True, text=True)
    assert result.returncode != 0 and 'Unsafe manifest path' in result.stderr
    assert outsider.read_bytes() == b'keep'
