"""Complete boundary-call arrays, drawing requests and coordinate admission.

The custom tracing policy is checked by an independently implemented native R
program. GEOS checks projections separately; exact rational and high-precision
controls extend storage and scale. These are computational contracts, not
biological segmentation validation. Saved export has its own reproduction gate.
"""
from pathlib import Path
from functools import lru_cache
from types import SimpleNamespace
import contextlib
import copy
import io
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'roi-analysis-whole'
MANIFEST_SHA256 = '82e9b3efc3a08cda6220d8e615760a8fcd662490c2650c4797245c1d62854bc8'
CAPABILITY = 'PyFLASH.markers.Antibody.analyse_roi'
CAPABILITY_PREFIXES = {CAPABILITY: ('roi-analysis.',)}
# Fresh native answers, every storage/drawing branch and the separate saved
# carrier passed together before enabling this method's 467 obligations.
COMPLETE_CAPABILITIES = frozenset({CAPABILITY})


@lru_cache(maxsize=8)
def _retained(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read(name):
    return _retained((ARCHIVE / name).resolve())


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import roi_analysis_reference as ordinary, roi_analysis_edge_reference as edges
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    assert Path(ordinary.__file__).read_bytes() == (ARCHIVE / 'native/original-0-roi_analysis_whole_reference_20261008.py').read_bytes()
    assert Path(edges.__file__).read_bytes() == (ARCHIVE / 'edges/original-0-roi_analysis_mixed_storage_reference_20261008.py').read_bytes()
    original = read('native/before.json')
    assert original['actual_calls'] == 160 and original['failed'] == 0 and not original['source_changes']
    assert ordinary.cases() == [row['case'] for row in original['rows']]
    queries = [ordinary.query(shape, points) for shape in ordinary.SHAPES for points in ordinary.POINTS]
    assert queries == read('native/reference-runtime/whole-roi-analysis-queries.json')
    before = read('edges/before.json')
    assert before['actual_calls'] == 153 and before['failed'] == 24 and not before['source_changes']
    first = read('first-edges/before.json')
    assert before['rows'][:129] == first['rows']
    for item, row in zip(edges.inputs(), before['rows'], strict=True):
        assert item['key'] == row['key']
        assert (None if item['invalid'] else edges.expected(item['x'], item['y'], item['points'])) == row['expected']


def cases():
    items = [dict(key='roi-analysis.native.' + row['case']['key'], kind='native',
                  case=row['case'], expected=row['expected']) for row in read('native/before.json')['rows']]
    items += [dict(key='roi-analysis.storage.' + row['key'] + '.preview-' + str(visualise),
                   kind='storage', case=row['key'], visualise=visualise, expected=row['expected'])
              for row in read('edges/before.json')['rows'] for visualise in (False, True)]
    return items


def required_keys(capability):
    from reproducibility.roi_preview_contract import KEY
    return {item['key'] for item in cases()} | {KEY} if capability == CAPABILITY else set()


def production(item, observation=None, *, marker_class=None):
    import numpy as np
    import pandas as pd
    from matplotlib import pyplot as plt
    from PyFLASH import markers
    from reproducibility import roi_analysis_reference as ordinary, roi_analysis_edge_reference as edges
    if item['kind'] == 'native':
        original = next(row for row in read('native/before.json')['rows'] if row['case'] == item['case'])
        assert item['expected'] == original['expected']
        if marker_class is None:
            actual = ordinary.observation(item['case'], item['expected'])
        else:
            from reproducibility.inherited_roi_reference_adapter import native_observation
            actual = native_observation(marker_class.__name__, item['case'], item['expected'])
        if observation is not None:
            observation.update(actual=actual, expected=item['expected'])
        assert actual['passed'], actual.get('error')
        return actual
    supplied = next(case for case in edges.inputs() if case['key'] == item['case'])
    original = next(row for row in read('edges/before.json')['rows'] if row['key'] == item['case'])
    assert item['expected'] == original['expected']
    x, y, points = supplied['x'].copy(), supplied['y'].copy(), supplied['points'].copy()
    roi = dict(x=x.copy(), y=y.copy(), name='boundary')
    if supplied['carrier'] == 'series':
        roi = pd.Series(roi)
    elif supplied['carrier'] == 'one-row-frame':
        roi = pd.DataFrame([roi])
    if supplied['point_carrier'] == 'list':
        points = points.tolist()
    elif supplied['point_carrier'] == 'readonly':
        points.flags.writeable = False
    elif supplied['point_carrier'] == 'dataframe':
        points = pd.DataFrame(points, columns=['x', 'y'])
    before_points = copy.deepcopy(points)
    marker = object.__new__(marker_class or markers.Antibody)
    marker.name = 'M'; marker.experiment = SimpleNamespace(fig_path='in-memory-geometry-control')
    marker._unrelated_state = object()
    state = dict(marker.__dict__)
    saved = []
    save = markers.save_fig
    def capture(figure, path, name, **kwargs):
        assert len(figure.axes) == 1
        axes = figure.axes[0]
        saved.append(dict(path=path, name=name, options=kwargs, inverted=axes.yaxis_inverted(),
                          aspect=axes.get_aspect(), artists=list(axes.lines)))
    markers.save_fig = capture
    returned = error = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                returned = marker.analyse_roi(roi, points, visualise=item['visualise'])
            except (ValueError, TypeError) as caught:
                error = caught
        assert marker.__dict__ == state
        rx = roi['x'].iloc[0] if isinstance(roi, pd.DataFrame) else roi['x']
        ry = roi['y'].iloc[0] if isinstance(roi, pd.DataFrame) else roi['y']
        np.testing.assert_array_equal(rx, x); np.testing.assert_array_equal(ry, y)
        if isinstance(points, pd.DataFrame):
            pd.testing.assert_frame_equal(points, before_points, check_exact=True)
        else:
            np.testing.assert_array_equal(points, before_points)
        if supplied['point_carrier'] == 'readonly':
            assert not points.flags.writeable
        if supplied['invalid']:
            assert error is not None and returned is None and saved == []
            actual = dict(refused=True, input_unchanged=True, output_count=0)
        else:
            assert error is None, error
            assert isinstance(returned, tuple) and len(returned) == 3
            distances, closest, line = returned
            assert all(isinstance(array, np.ndarray) and array.dtype == np.float64 for array in returned)
            assert distances.shape == (len(supplied['points']),) and closest.shape == (len(supplied['points']), 2)
            expected = item['expected']
            for observed, reference in ((distances, expected['distances']),
                    (closest, np.asarray(expected['closest']).reshape((-1, 2))), (line, expected['line'])):
                np.testing.assert_allclose(observed, reference, rtol=1e-12, atol=1e-12)
                if item['case'].startswith('tiny-floating'):
                    reference = np.asarray(reference)
                    np.testing.assert_array_equal(observed == 0, reference == 0)
                    np.testing.assert_array_equal(np.signbit(observed), np.signbit(reference))
                    np.testing.assert_allclose(observed, reference, rtol=1e-12, atol=0)
            if item['visualise']:
                assert len(saved) == 1
                request = saved[0]
                assert request['path'] == 'in-memory-geometry-control'
                assert request['name'] == f'Ventricle Analysis {roi["name"]} M'
                assert request['options'] == {'subfolder': 'Ventricle Analysis'}
                assert request['inverted'] and request['aspect'] == 1.
                artists = request['artists']; count = len(distances)
                assert len(artists) == 2 + 3 * count
                np.testing.assert_array_equal(artists[0].get_xdata(), x)
                np.testing.assert_array_equal(artists[0].get_ydata(), y)
                np.testing.assert_allclose(np.asarray(artists[1].get_xdata(), dtype=float), np.asarray(expected['line'])[:, 0], rtol=1e-12, atol=1e-12)
                np.testing.assert_allclose(np.asarray(artists[1].get_ydata(), dtype=float), np.asarray(expected['line'])[:, 1], rtol=1e-12, atol=1e-12)
                assert artists[0].get_color() == 'yellow' and artists[1].get_color() == 'g'
                for index in range(count):
                    raw, projected, connector = artists[2+index], artists[2+count+index], artists[2+2*count+index]
                    assert raw.get_color() == 'yellow' and raw.get_marker() == 'x'
                    assert projected.get_color() == 'r' and projected.get_marker() == 'x'
                    assert connector.get_color() == 'r' and connector.get_linestyle() == '--'
                    for axis, access in enumerate(('get_xdata', 'get_ydata')):
                        np.testing.assert_array_equal(getattr(raw, access)()[0], supplied['points'][index, axis])
                        assert getattr(projected, access)()[0] == closest[index, axis]
                        np.testing.assert_array_equal(getattr(connector, access)()[0], supplied['points'][index, axis])
                        assert getattr(connector, access)()[1] == closest[index, axis]
            else:
                assert saved == []
            actual = dict(distances=distances.tolist(), closest=closest.tolist(), line=line.tolist(),
                          input_unchanged=True, preview_requested=item['visualise'],
                          artists_checked=2+3*len(distances) if item['visualise'] else 0)
        if observation is not None:
            observation.update(actual=actual, expected=item['expected'])
        return actual
    finally:
        markers.save_fig = save
        plt.close('all')


def validate(output):
    from reproducibility.table_family_validation import replay
    from reproducibility import roi_analysis_reference as ordinary
    from reproducibility.reference_runtime import execute_queries
    check_identity()
    native = execute_queries([ordinary.query(shape, points) for shape in ordinary.SHAPES for points in ordinary.POINTS],
                             Path(output) / 'native', name='whole-roi-analysis')
    assert native['rows'] == read('native/reference-runtime/whole-roi-analysis-results.json')['rows']
    rows = replay(cases(), lambda item, observed, path: production(item, observed), output,
        reference='Independently implemented custom tracing in native R plus GEOS projections; exact rational/4096-bit arithmetic storage controls; literal caller ownership and drawing contracts',
        family='whole-custom-boundary-analysis', shape='every-distance-projection-line-coordinate-dtype-input-and-drawing-request',
        rtol=1e-12, atol=1e-12)
    from reproducibility import roi_preview_contract
    return rows + roi_preview_contract.validate(Path(output) / 'saved-preview')
