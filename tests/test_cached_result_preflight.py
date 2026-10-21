"""A later bad result cannot start an earlier cell or overwrite its progress."""
from dataclasses import replace
import json
from pathlib import Path
import pickle
import numpy as np
import pytest
from PyFLASH import actions, queue


def execute(root, **kwargs):
    return queue.run_action_grid(None,'PyFLASH.stats.bonferroni_correction', {'n_tests':2},
        {'p_value':[.01,.02]},root/'progress.json', **kwargs)


def test_future_result_schema_is_rejected_before_any_cell_or_progress(tmp_path, monkeypatch):
    first = execute(tmp_path)
    first_main = Path(first['results'][0]['receipt']).parent.parent/'cell.json'
    earlier = json.loads(first_main.read_text())
    earlier['status'] = 'failed'
    first_main.write_text(json.dumps(earlier))
    second_main = Path(first['results'][1]['receipt']).parent.parent/'cell.json'
    record = json.loads(second_main.read_text())
    result = second_main.parent/record['result']
    value = pickle.loads(result.read_bytes())
    result.write_bytes(pickle.dumps(replace(value,schema_version=2)))
    for row in record['outputs']:
        if row['path'] == record['result']:
            row['sha256'] = queue._digest_file(result)
    second_main.write_text(json.dumps(record))
    before = (tmp_path/'progress.json').read_bytes()
    calls = []
    monkeypatch.setattr(actions,'call_action',lambda *args:calls.append(args))
    with pytest.raises(ValueError,match='schema'):
        execute(tmp_path)
    assert calls == []
    assert (tmp_path/'progress.json').read_bytes() == before


def test_cached_result_memory_is_checked_before_unpickling_or_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(actions,'call_action',lambda *args:np.arange(128*1024,dtype=float))
    execute(tmp_path)
    before = (tmp_path/'progress.json').read_bytes()
    def unexpected_read(*args):
        pytest.fail('Cached result was read before its resource estimate was accepted')
    monkeypatch.setattr(queue,'_read_grid_value',unexpected_read)
    with pytest.raises(ValueError,match='(?i)(memory|available)'):
        execute(tmp_path,memory_budget_bytes=18*1024**2)
    assert (tmp_path/'progress.json').read_bytes() == before
