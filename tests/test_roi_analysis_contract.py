"""Keep complete native boundary outputs and actual callers under the same gate."""
import copy
import shutil
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from reproducibility import roi_analysis_contract as contract

CASES = contract.cases()


@pytest.fixture(scope='module', autouse=True)
def authenticate_original_geometry():
    contract.check_identity()


@pytest.mark.parametrize('item', CASES, ids=lambda item: item['key'])
def test_actual_boundary_call_retains_complete_native_and_storage_outputs(item):
    original = copy.deepcopy(item)
    contract.production(item)
    assert item == original


@pytest.mark.parametrize('name', ['source-files.json', 'native/before.json',
                                  'native/reference-runtime/whole-roi-analysis-results.json'])
def test_altered_original_geometry_cannot_pass(name, tmp_path, monkeypatch):
    archive = tmp_path / 'independent-archive'
    shutil.copytree(contract.ARCHIVE, archive)
    path = archive / name; path.write_bytes(path.read_bytes() + b' ')
    monkeypatch.setattr(contract, 'ARCHIVE', archive)
    with pytest.raises(ValueError, match='evidence'):
        contract.check_identity()


@pytest.mark.parametrize('field', ['distances', 'closest', 'line'])
def test_changed_complete_predictions_cannot_become_approved_answers(field):
    item = copy.deepcopy(next(item for item in CASES if item['kind'] == 'storage' and item['expected'] is not None))
    values = item['expected'][field]
    if field == 'distances': values[0] += 1
    else: values[0][0] += 1
    with pytest.raises(AssertionError):
        contract.production(item)


@pytest.mark.parametrize('damage', ['value', 'dtype', 'shape', 'caller-input'])
def test_wrong_public_output_or_mutated_input_is_rejected(damage, monkeypatch):
    from PyFLASH import markers
    method = markers.Antibody.analyse_roi
    def damaged(self, roi, points, visualise=False):
        distance, closest, line = method(self, roi, points, visualise=visualise)
        if damage == 'value': distance[0] += 1
        elif damage == 'dtype': line = line.astype(object)
        elif damage == 'shape': closest = closest.ravel()
        else: roi['x'][0] += 1
        return distance, closest, line
    monkeypatch.setattr(markers.Antibody, 'analyse_roi', damaged)
    item = next(item for item in CASES if item['kind'] == 'storage' and
                item['case'] == 'ordinary.float16.series.array' and not item['visualise'])
    with pytest.raises(AssertionError):
        contract.production(item)


def test_coverage_keeps_parent_and_saved_export_obligations_separate():
    assert len(CASES) == 466
    assert len(contract.required_keys(contract.CAPABILITY)) == 467
    assert not contract.required_keys('PyFLASH.markers.Antibody.find_distance_to_ventricle')
    assert not contract.required_keys('PyFLASH.experiment.Experiment.processData')


@pytest.mark.parametrize('shape', ['vertical', 'diagonal', 'curved', 'reversed', 'unordered',
    'two-vertices', 'duplicate-start', 'first-nearest-tie', 'slope-restart', 'translated-fractional'])
def test_actual_preview_keeps_readable_ticks_at_package_font_size(shape, monkeypatch):
    from PyFLASH import markers
    from PyFLASH.aesthetics import pyflash_style_context
    from matplotlib import pyplot as plt
    from reproducibility import roi_analysis_reference as reference
    measured = []
    def capture(figure, *args, **kwargs):
        figure.canvas.draw(); renderer = figure.canvas.get_renderer(); axes = figure.axes[0]
        low, high = sorted(axes.get_xlim())
        labels = [label for value, label in zip(axes.get_xticks(), axes.get_xticklabels())
                  if low <= value <= high and label.get_visible() and label.get_text()]
        assert labels and all(label.get_fontsize() == 20 for label in labels)
        boxes = [label.get_window_extent(renderer) for label in labels]
        assert not any(a.overlaps(b) for index, a in enumerate(boxes) for b in boxes[index+1:])
        measured.append(True)
    monkeypatch.setattr(markers, 'save_fig', capture)
    marker = object.__new__(markers.Antibody)
    marker.name = 'M'; marker.experiment = SimpleNamespace(fig_path='in-memory-only')
    x, y = reference.SHAPES[shape]
    roi = pd.Series(dict(x=np.asarray(x), y=np.asarray(y), name='boundary'))
    try:
        with pyflash_style_context({'tick_label_size': 20}):
            marker.analyse_roi(roi, np.asarray([[1., 40.], [8., 40.]]), visualise=True)
        assert measured == [True]
    finally:
        plt.close('all')
