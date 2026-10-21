import json
from pathlib import Path

from reproducibility.run_pytest_shards import run


def test_sharded_runner_executes_each_test_once_and_merges_junit(tmp_path):
    tests = tmp_path / 'mini-suite'
    tests.mkdir()
    (tests / 'test_four.py').write_text('''
import os
from pathlib import Path

def test_a(): assert 1 == 1
def test_b(): assert 2 == 2
def test_c(): assert 3 == 3
def test_d(): assert 4 == 4

def test_worker_temp_root_is_owned():
    root = Path(os.environ['TEMP'])
    assert root == Path(os.environ['TMP']) == Path(os.environ['TMPDIR'])
    assert root.is_dir()
    assert root.name == f'shard-{int(os.environ["PYFLASH_TEST_SHARD_INDEX"]) + 1:02d}'
    (root / 'worker-temp-marker.txt').write_text(str(root), encoding='utf-8')
''', encoding='utf-8')
    (tests / 'test_two.py').write_text('''
import os
from pathlib import Path

def test_e(): assert 5 == 5
def test_f(): assert 6 == 6

def test_worker_temp_root_is_owned():
    root = Path(os.environ['TEMP'])
    assert root == Path(os.environ['TMP']) == Path(os.environ['TMPDIR'])
    assert root.is_dir()
    assert root.name == f'shard-{int(os.environ["PYFLASH_TEST_SHARD_INDEX"]) + 1:02d}'
    (root / 'worker-temp-marker.txt').write_text(str(root), encoding='utf-8')
''', encoding='utf-8')
    (tests / 'test_three.py').write_text('''
def test_g(): assert 7 == 7
def test_h(): assert 8 == 8
''', encoding='utf-8')
    output = tmp_path / 'workflow'
    basetemp = tmp_path / 'pytest-temp'
    basetemp.mkdir()

    result = run(output, basetemp, 3, tests_path=tests)

    assert result['status'] == 'pass'
    assert result['collected_count'] == result['executed_count'] == 10
    assert sum(result['shard_counts']) == 10
    assert result['worker_temp_roots_unique']
    assert all(len(shard['nodeids_sha256']) == 64 for shard in result['shards'])
    assert sum(shard['junit']['tests'] for shard in result['shards']) == 10
    assert result['cleanup']['status'] == 'complete'
    observed_roots = list((basetemp.parent / 'framework-temporary').glob('shard-*/worker-temp-marker.txt'))
    assert len(observed_roots) == 2
    assert len({path.read_text(encoding='utf-8') for path in observed_roots}) == 2
    assert not (output / 'tests.xml').exists()
    assert not list((output / 'test-shards').glob('shard-*'))
    compact = json.loads((output / 'test-shards' / 'run.json').read_text(encoding='utf-8'))
    assert compact['status'] == 'pass'
    assert compact['executed_count'] == 10
    assert all('log' not in shard and 'manifest' not in shard for shard in compact['shards'])


def test_sharded_runner_keeps_diagnostics_when_a_shard_fails(tmp_path):
    tests = tmp_path / 'failing-suite'
    tests.mkdir()
    (tests / 'test_ok.py').write_text('def test_ok(): assert True\n', encoding='utf-8')
    (tests / 'test_fail.py').write_text('def test_failure(): assert False\n', encoding='utf-8')

    output = tmp_path / 'failed-output'
    result = run(output, tmp_path / 'failed-temp', workers=2, tests_path=tests)

    assert result['status'] == 'fail'
    assert result['cleanup']['status'] == 'preserved-after-failure'
    assert (output / 'tests.xml').is_file()
    assert all(Path(shard['manifest']).is_file() for shard in result['shards'])
    assert all(Path(shard['log']).is_file() for shard in result['shards'])
    assert len(list((output / 'test-shards').glob('shard-*/pytest.log'))) == 2
