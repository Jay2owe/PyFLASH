"""Freeze native boundary arrays and inspect the actual optional preview artists.

Inputs are authored finite two-dimensional ROI/point arrays below. Outputs retain
native R queries/results, GEOS projections, exact drawing requests and original
production observations. Preview figures remain in memory; no file is exported.
The declared domain includes empty shaped point arrays, both ROI carriers and
both visualise branches. Invalid-input behavior is a separate functional check.
Existing geometry tolerances are preserved (relative/absolute 1e-12).
"""
from pathlib import Path
from types import SimpleNamespace
from itertools import product
import argparse, contextlib, copy, hashlib, io, json, os, shutil
os.environ.setdefault('MPLBACKEND', 'Agg')
import numpy as np
import pandas as pd
from reproducibility.ventricle_native_reference import TRACE
from reproducibility.marker_nearest_reference import vector
from reproducibility.reference_runtime import execute_queries, values

# Configuration: output is new-only; authored inputs and tolerances are immutable.
RTOL = ATOL = 1e-12
SHAPES = {
 'vertical': ([5.] * 9, list(range(0, 90, 10))),
 'diagonal': (list(range(9)), list(range(9))),
 'curved': ([8, 7, 6, 6, 5, 5, 6, 7, 9], list(range(0, 90, 10))),
 'reversed': (list(reversed([8, 7, 6, 6, 5, 5, 6, 7, 9])), list(range(80, -10, -10))),
 'unordered': ([6, 9, 8, 5, 7, 6, 7, 5, 6], [30, 80, 0, 50, 10, 60, 70, 40, 20]),
 'two-vertices': ([2, 8], [0, 20]),
 'duplicate-start': ([2, 7, 7, 8, 9], [0, 0, 0, 10, 20]),
 'first-nearest-tie': ([5, 3, 7, 6, 5], [0, 10, 10, 20, 30]),
 'slope-restart': ([100, 0, 1, 2], [0, 1, 2, 3]),
 'translated-fractional': ([-10.25, -9.5, -8.75, -9.5, -10.25], [-20, -10, 0, 10, 20]),
}
POINTS = {
 'empty': [], 'single': [[3., 5.]],
 'two': [[1., 40.], [8., 40.]],
 'many': [[float(i - 15), float((i * 7) % 110 - 15)] for i in range(31)],
}

def cases():
    return [dict(key='.'.join((shape, points, carrier, str(visualise))), shape=shape,
        points=points, carrier=carrier, visualise=visualise)
        for shape, points, carrier, visualise in product(SHAPES, POINTS,
            ('series', 'one-row-frame'), (False, True))]

def query(shape, points):
    x, y = SHAPES[shape]
    commands = [TRACE, 'line<-trace_line(' + vector(x) + ',' + vector(y) + ')',
        'answer<-c(nrow(line),as.vector(t(line)))']
    for point in POINTS[points]:
        commands.append('answer<-c(answer,project(' + vector(point) + ',line))')
    commands.append('answer')
    return dict(key=shape + '.' + points, code='local({' + ';\n'.join(commands) + '})')

def decode(answer, points):
    length = int(answer[0])
    line = np.asarray(answer[1:1 + 2 * length]).reshape((-1, 2))
    projected = np.asarray(answer[1 + 2 * length:]).reshape((-1, 3))
    assert len(projected) == len(POINTS[points])
    return dict(line=line.tolist(), distances=projected[:, 0].tolist(),
        closest=projected[:, 1:].tolist())

def geos(shape, points, expected):
    from shapely.geometry import LineString, Point
    line = LineString(expected['line'])
    result = dict(distances=[], closest=[])
    for xy in POINTS[points]:
        point = Point(xy)
        result['distances'].append(line.distance(point))
        result['closest'].append(list(line.interpolate(line.project(point)).coords)[0])
    return result

def observation(item, expected):
    from PyFLASH import markers
    from matplotlib import pyplot as plt
    x, y = SHAPES[item['shape']]
    roi = pd.Series(dict(x=np.asarray(x, dtype=float), y=np.asarray(y, dtype=float), name='boundary'))
    if item['carrier'] == 'one-row-frame':
        roi = pd.DataFrame([roi.to_dict()])
    original_roi = copy.deepcopy(roi)
    points = np.asarray(POINTS[item['points']], dtype=float).reshape((-1, 2))
    original_points = points.copy()
    marker = object.__new__(markers.Antibody)
    sentinel = object()
    marker.name = 'M'; marker.experiment = SimpleNamespace(fig_path='owned-preview-request')
    marker._unrelated_state = sentinel
    original_state = dict(marker.__dict__)
    saved = []
    original_save = markers.save_fig
    def capture(fig, path, name, **kwargs):
        axes = fig.axes
        assert len(axes) == 1
        ax = axes[0]
        saved.append(dict(path=path, name=str(name), kwargs=kwargs,
            inverted=bool(ax.yaxis_inverted()), aspect=ax.get_aspect(),
            lines=[dict(x=np.asarray(line.get_xdata()).tolist(), y=np.asarray(line.get_ydata()).tolist(),
                        colour=line.get_color(), marker=line.get_marker(), style=line.get_linestyle(),
                        width=line.get_linewidth()) for line in ax.lines]))
    markers.save_fig = capture
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            distances, closest, line = marker.analyse_roi(roi, points, visualise=item['visualise'])
        np.testing.assert_allclose(distances, expected['distances'], rtol=RTOL, atol=ATOL)
        np.testing.assert_allclose(closest, np.asarray(expected['closest']).reshape((-1, 2)), rtol=RTOL, atol=ATOL)
        np.testing.assert_allclose(line, expected['line'], rtol=RTOL, atol=ATOL)
        assert distances.shape == (len(points),) and closest.shape == (len(points), 2)
        assert line.ndim == 2 and line.shape[1] == 2
        assert marker.__dict__ == original_state and marker._unrelated_state is sentinel
        np.testing.assert_array_equal(points, original_points)
        if isinstance(roi, pd.Series): pd.testing.assert_series_equal(roi, original_roi, check_exact=True)
        else: pd.testing.assert_frame_equal(roi, original_roi, check_exact=True)
        if item['visualise']:
            assert len(saved) == 1
            request = saved[0]
            assert request['path'] == 'owned-preview-request'
            assert request['kwargs'] == {'subfolder': 'Ventricle Analysis'}
            assert request['name'] == f'Ventricle Analysis {roi["name"]} M'
            assert request['inverted'] and request['aspect'] == 1.
            artists = request['lines']
            assert len(artists) == 2 + 3 * len(points), len(artists)
            np.testing.assert_allclose(artists[0]['x'], x, rtol=RTOL, atol=ATOL)
            np.testing.assert_allclose(artists[0]['y'], y, rtol=RTOL, atol=ATOL)
            np.testing.assert_allclose(np.column_stack((artists[1]['x'], artists[1]['y'])), expected['line'], rtol=RTOL, atol=ATOL)
            assert artists[0]['colour'] == 'yellow' and artists[1]['colour'] == 'g'
            n = len(points)
            for index in range(n):
                actual, projected, connector = artists[2 + index], artists[2 + n + index], artists[2 + 2 * n + index]
                assert actual['colour'] == 'yellow' and actual['marker'] == 'x'
                assert projected['colour'] == 'r' and projected['marker'] == 'x'
                assert connector['colour'] == 'r' and connector['style'] == '--'
                np.testing.assert_allclose([actual['x'][0], actual['y'][0]], points[index], rtol=RTOL, atol=ATOL)
                np.testing.assert_allclose([projected['x'][0], projected['y'][0]], expected['closest'][index], rtol=RTOL, atol=ATOL)
                np.testing.assert_allclose(np.column_stack((connector['x'], connector['y'])), [points[index], expected['closest'][index]], rtol=RTOL, atol=ATOL)
        else: assert saved == []
        return dict(passed=True, distances=distances.tolist(), closest=closest.tolist(), line=line.tolist(), drawing=saved)
    except Exception as error:
        return dict(passed=False, error=type(error).__name__ + ': ' + str(error), drawing=saved)
    finally:
        markers.save_fig = original_save
        plt.close('all')

def freeze(output):
    from PyFLASH import markers, utils
    import shapely
    paths = [Path(__file__), Path(markers.__file__), Path(utils.__file__)]
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    hashes = {str(path): digest(path) for path in paths}
    assert not output.exists() and shutil.disk_usage(output.parent).free >= 200 * 1024**2
    output.mkdir(); (output / 'rows').mkdir()
    items = cases()
    (output / 'inputs.json').write_text(json.dumps(dict(shapes=SHAPES, points=POINTS, cases=items), indent=2) + '\n')
    queries = [query(shape, points) for shape, points in product(SHAPES, POINTS)]
    native = execute_queries(queries, output / 'native', name='whole-roi-analysis', timeout=180)
    answers = {row['key']: list(values(row)) for row in native['rows']}
    expectations = {}
    for shape, points in product(SHAPES, POINTS):
        key = shape + '.' + points
        expected = decode(answers[key], points)
        independent = geos(shape, points, expected)
        np.testing.assert_allclose(expected['distances'], independent['distances'], rtol=RTOL, atol=ATOL)
        np.testing.assert_allclose(np.asarray(expected['closest']).reshape((-1, 2)), np.asarray(independent['closest']).reshape((-1, 2)), rtol=RTOL, atol=ATOL)
        expectations[key] = dict(expected=expected, geos=independent)
    rows = []
    for item in items:
        expected = expectations[item['shape'] + '.' + item['points']]
        row = dict(case=item, **expected, **observation(item, expected['expected']))
        rows.append(row)
        (output / 'rows' / (item['key'] + '.json')).write_text(json.dumps(row, indent=2, allow_nan=False) + '\n')
    changes = [str(path) for path in paths if digest(path) != hashes[str(path)]]
    assert not changes, changes
    for index, path in enumerate(paths): (output / ('original-' + str(index) + '-' + path.name)).write_bytes(path.read_bytes())
    record = dict(actual_calls=len(rows), failed=sum(not row['passed'] for row in rows), source_hashes=hashes,
        source_changes=changes, shapely=shapely.__version__, geos=shapely.geos_version_string,
        rtol=RTOL, atol=ATOL, rows=rows,
        scope='Full native distance/closest-point/smoothed-line arrays and actual optional artist requests on the declared ordinary finite domain. No file export is intercepted as a scientific answer; actual retained export is separately required.')
    (output / 'before.json').write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: record[key] for key in ('actual_calls', 'failed', 'source_changes')}), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    freeze(args.output)
