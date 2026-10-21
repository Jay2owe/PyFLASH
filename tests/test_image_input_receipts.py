"""Pixel replacement invalidates cached results even with unchanged filenames."""
import json
import os
from pathlib import Path
import numpy as np
from PIL import Image
from PyFLASH import actions, image_io, queue
from PyFLASH.ui import workspace


def test_actual_image_reads_are_observed_across_loader_threads(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path / 'pixels.png'
    Image.fromarray(np.arange(64,dtype=np.uint8).reshape(8,8)).save(path)
    seen = []
    with image_io.observe_image_reads(seen.append):
        with ThreadPoolExecutor(max_workers=2) as pool:
            arrays = list(pool.map(lambda _:image_io.read_image_array(path,backend='pil'),range(2)))
    assert seen == [str(path),str(path)]
    assert all(np.array_equal(array,np.arange(64,dtype=np.uint8).reshape(8,8)) for array in arrays)
    assert not image_io._READ_OBSERVERS


def test_grid_rechecks_external_pixels_and_preserves_prior_receipts(tmp_path, monkeypatch):
    path = tmp_path / 'pixels.png'
    Image.fromarray(np.full((8,8),10,dtype=np.uint8)).save(path)
    def analyze(action, data, parameters):
        return float(image_io.read_image_array(path,backend='pil').mean())*parameters['n_tests']
    monkeypatch.setattr(actions, 'call_action', analyze)
    def run():
        return queue.run_action_grid(None,'PyFLASH.stats.bonferroni_correction', {'p_value':.01},
            {'n_tests':[2,3]},tmp_path / 'grid.json')
    first = run()
    receipts = {row['receipt']:workspace.content_hash(row['receipt']) for row in first['results']}
    stamps = path.stat()
    Image.fromarray(np.full((8,8),20,dtype=np.uint8)).save(path)
    os.utime(path,ns=(stamps.st_atime_ns,stamps.st_mtime_ns))
    second = run()
    assert [row['result'] for row in first['results']] == [20,30]
    assert [row['result'] for row in second['results']] == [40,60]
    assert not any(row['reused'] for row in second['results'])
    assert [row['key'] for row in first['results']] != [row['key'] for row in second['results']]
    assert all(workspace.content_hash(name) == digest for name,digest in receipts.items())
    third = run()
    assert all(row['reused'] for row in third['results'])
    assert all(row['input_files'][0]['sha256'] == workspace.content_hash(path) for row in third['results'])
