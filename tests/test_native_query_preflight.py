"""Invalid native expressions must refuse before output creation or runtime launch."""
from pathlib import Path
import importlib.util
import json
import pytest
ROOT = Path(__file__).resolve().parents[1]
from reproducibility import reference_runtime as M
INVALID = [None, [], True, 1, 'code', {}, {'key': 'absent'}, {'key': 'null', 'code': None},
           {'key': 'empty', 'code': ''}, {'code': '  \n  '}, {'code': 7}, {'code': False}]

@pytest.mark.parametrize('item', INVALID)
def test_invalid_native_query_refuses_before_any_runtime_or_output(item, tmp_path, monkeypatch):
    def forbidden():
        pytest.fail('Invalid native query attempted a runtime launch.')
    monkeypatch.setattr(M, 'ensure', forbidden)
    output = tmp_path / 'not-created'
    with pytest.raises(ValueError, match='requires a nonempty code expression'):
        M.execute_queries([item], output, name='invalid')
    assert not output.exists()

def test_entire_query_batch_is_checked_before_launch(tmp_path, monkeypatch):
    def forbidden():
        pytest.fail('Partially valid query batch attempted a runtime launch.')
    monkeypatch.setattr(M, 'ensure', forbidden)
    output = tmp_path / 'not-created'
    with pytest.raises(ValueError, match='Native query 1'):
        M.execute_queries([{'key': 'valid', 'code': '{c(2,3)}'}, {'key': 'invalid', 'expr': '{c(2,3)}'}], output, name='mixed')
    assert not output.exists()

def test_healthy_literal_query_executes_with_original_runtime_and_dispatch(tmp_path, monkeypatch):
    # The adapter's native scripts travel beside it in a source package.
    # This private module uses exact copies of those scripts alongside itself.
    monkeypatch.setattr(M, '__file__', str(tmp_path / 'reference_runtime.py'))
    for name in ('run_native_r.mjs', 'windows_r_loader.mjs', 'package.json', 'package-lock.json'):
        (tmp_path / name).write_bytes((ROOT / 'reproducibility' / name).read_bytes())
    queries = [{'key': 'healthy', 'code': '{c(2,3)}'}]
    actual = M.execute_queries(queries, tmp_path / 'actual', name='healthy')
    assert actual['webR'] == '0.6.0'
    assert actual['R'] == ['R version 4.6.0 (2026-04-24)']
    assert actual['wasm_sha256'] == '5df459fb222d332e358cf08e4019c0e114398579ed8c62242bfcceeda81222ba'
    assert actual['rows'] == [dict(key='healthy', code='{c(2,3)}', values=[2,3], nonfinite=[None,None], status='executed')]
    assert queries == [{'key': 'healthy', 'code': '{c(2,3)}'}]
    assert json.loads((tmp_path / 'actual/healthy-queries.json').read_text(encoding='utf-8')) == queries
