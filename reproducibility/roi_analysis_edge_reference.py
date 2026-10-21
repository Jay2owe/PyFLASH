"""Retain whole ROI-call storage, extreme-coordinate and refusal before-controls.

The reference independently implements the declared downward-trace policy with
Python Fraction, rounds each nine-point padded mean once, then projects using
4096-bit mpmath. Original input integers are never transported through doubles.
Ordinary finite expectations also agree with the retained native R/GEOS baseline.
No figures are saved. This extends, rather than replaces, that original baseline.
"""
from pathlib import Path
from fractions import Fraction
from itertools import product
from types import SimpleNamespace
import argparse, contextlib, copy, hashlib, io, json, math, os, shutil
os.environ.setdefault('MPLBACKEND', 'Agg')
import numpy as np
import pandas as pd
import mpmath as mp

# Configuration: original geometry tolerance is retained; outputs are new-only.
RTOL = ATOL = 1e-12
BITS = 4096


def fraction(value):
    if isinstance(value, np.generic): value = value.item()
    if isinstance(value, complex):
        if value.imag: raise ValueError('Coordinates must be real')
        value = value.real
    return Fraction(value)


def expected(x, y, points):
    coordinates = list(zip(map(fraction, x), map(fraction, y), strict=True))
    starts = sorted(range(len(coordinates)), key=lambda i: (coordinates[i][1], -coordinates[i][0], i))
    path = None
    for start in starts:
        selected = [start]
        while True:
            current = coordinates[selected[-1]]
            eligible = [i for i, candidate in enumerate(coordinates) if candidate[1] > current[1]]
            if not eligible: break
            nearest = min(eligible, key=lambda i: sum((a - b)**2 for a, b in zip(coordinates[i], current)))
            nx, ny = coordinates[nearest]
            if nx - current[0] < -2 * (ny - current[1]): break
            selected.append(nearest)
        if len(selected) > 1:
            path = [coordinates[i] for i in selected]
            break
    if path is None: raise ValueError('No downward path')
    padded = [path[0]] * 4 + path + [path[-1]] * 4
    line = [[float(sum(padded[i + j][axis] for j in range(9)) / 9)
             for axis in (0, 1)] for i in range(len(path))]
    distances, closest = [], []
    with mp.workprec(BITS):
        def number(value):
            exact = fraction(value)
            return mp.mpf(exact.numerator) / exact.denominator
        vertices = [[number(value) for value in xy] for xy in line]
        for point in points:
            point = [number(value) for value in point]
            candidates = []
            for first, last in zip(vertices[:-1], vertices[1:]):
                delta = [last[i] - first[i] for i in (0, 1)]
                length = sum(value * value for value in delta)
                weight = mp.mpf(0) if not length else min(mp.mpf(1), max(mp.mpf(0),
                    sum((point[i] - first[i]) * delta[i] for i in (0, 1)) / length))
                candidate = [first[i] + weight * delta[i] for i in (0, 1)]
                squared = sum((point[i] - candidate[i])**2 for i in (0, 1))
                candidates.append((squared, candidate))
            squared, candidate = min(candidates, key=lambda value: value[0])
            distances.append(float(mp.sqrt(squared)))
            closest.append([float(value) for value in candidate])
    return dict(line=line, distances=distances, closest=closest)


def original_inputs():
    for dtype, carrier, point_carrier in product(
            ('float16', 'float32', 'float64', 'int16', 'int64', 'uint64', 'object', 'complex128'),
            ('series', 'one-row-frame', 'dict'), ('array', 'list', 'readonly', 'dataframe')):
        x = np.asarray([5] * 9, dtype=dtype)
        y = np.asarray(list(range(0, 90, 10)), dtype=dtype)
        points = np.asarray([[1, 40], [8, 40]], dtype=dtype)
        yield dict(key=f'ordinary.{dtype}.{carrier}.{point_carrier}',
            x=x, y=y, points=points, carrier=carrier, point_carrier=point_carrier, invalid=False)
    for label, x, y, points in (
        ('integer-resolution', [2**53 + i for i in (3, 2, 1, 0, 1, 2, 3, 4, 5)],
            list(range(9)), [[2**53 + 7, 3], [2**53 + 1, 7]]),
        ('unsigned-integer-resolution', [2**63 + i for i in (3, 2, 1, 0, 1, 2, 3, 4, 5)],
            list(range(9)), [[2**63 + 7, 3], [2**63 + 1, 7]]),
        ('huge-floating', [1e308] * 9, [i * 1e306 for i in range(9)], [[9e307, 3e306], [1.1e308, 5e306]]),
        ('tiny-floating', [1e-308] * 9, [i * 1e-309 for i in range(9)], [[9e-309, 3e-309], [1.1e-308, 5e-309]]),
        ('cancellation', [1e308, -1e308, 1e308, -1e308, 1e308, -1e308, 1e308, -1e308, 1e308],
            [i * 1e308 / 8 for i in range(9)], [[1e307, 1e307]]),
    ):
        # The cancellation corpus is explicitly finite; avoid overflowing its authored values.
        if label == 'cancellation': y = [float(Fraction(i, 8) * Fraction(1e308)) for i in range(9)]
        dtype = 'uint64' if label == 'unsigned-integer-resolution' else 'int64' if label == 'integer-resolution' else 'float64'
        for carrier in ('series', 'one-row-frame', 'dict'):
            yield dict(key=f'{label}.{carrier}', x=np.asarray(x, dtype=dtype), y=np.asarray(y, dtype=dtype),
                points=np.asarray(points, dtype=dtype), carrier=carrier, point_carrier='array', invalid=False)
    for carrier in ('array', 'list', 'readonly', 'dataframe'):
        yield dict(key='empty-points.' + carrier, x=np.asarray([5., 5.]), y=np.asarray([0., 20.]),
            points=np.empty((0, 2)), carrier='series', point_carrier=carrier, invalid=False)
    ordinary = dict(x=np.asarray([5., 5.]), y=np.asarray([0., 20.]), points=np.asarray([[1., 5.]]),
        carrier='series', point_carrier='array', invalid=True)
    damages = {
        'imaginary-roi-x': {'x': np.asarray([5+2j, 5+2j])},
        'imaginary-roi-y': {'y': np.asarray([0+2j, 20+2j])},
        'nonfinite-roi': {'x': np.asarray([np.nan, 5.])},
        'infinite-roi': {'y': np.asarray([0., np.inf])},
        'unpaired-roi': {'y': np.asarray([0., 10., 20.])},
        'single-roi': {'x': np.asarray([5.]), 'y': np.asarray([0.])},
        'flat-roi': {'y': np.asarray([0., 0.])},
        'wrong-roi-dimension': {'x': np.asarray([[5., 5.], [5., 5.]])},
        'imaginary-point': {'points': np.asarray([[1+2j, 5.]])},
        'nonfinite-point': {'points': np.asarray([[np.nan, 5.]])},
        'infinite-point': {'points': np.asarray([[1., np.inf]])},
        'point-vector': {'points': np.asarray([1., 5.])},
        'point-three-coordinates': {'points': np.asarray([[1., 5., 99.]])},
        'point-three-dimensions': {'points': np.asarray([[[1., 5.]]])},
    }
    for name, damage in damages.items(): yield dict(ordinary, key='invalid.' + name, **damage)


def inputs():
    yield from original_inputs()
    base = 2**53
    for label, x, y, points in (
        ('mixed-roi-exact-input', np.asarray([base+1, float(base+2), base], dtype=object),
         np.asarray([0, 1, 1]), np.asarray([[base+5, 0.5]], dtype=object)),
        ('mixed-point-exact-input', np.asarray([base]*9, dtype=np.int64),
         np.asarray(list(range(9))), np.asarray([[base+1, 4.5]], dtype=object)),
    ):
        for carrier, point_carrier in product(('series', 'one-row-frame', 'dict'), ('array', 'list', 'readonly', 'dataframe')):
            yield dict(key=label+'.'+carrier+'.'+point_carrier, x=x.copy(), y=y.copy(), points=points.copy(),
                carrier=carrier, point_carrier=point_carrier, invalid=False)


def run(output):
    from PyFLASH import markers
    from reproducibility.scientific_utility_contract import encode as scalar_encode
    def encode(value):
        if isinstance(value, np.ndarray): return encode(value.tolist())
        if isinstance(value, np.generic): return encode(value.item())
        if isinstance(value, complex): return {'real': scalar_encode(value.real), 'imaginary': scalar_encode(value.imag)}
        if isinstance(value, (list, tuple)): return [encode(entry) for entry in value]
        if isinstance(value, dict): return {key: encode(entry) for key, entry in value.items()}
        return scalar_encode(value)
    paths = [Path(__file__), Path(markers.__file__)]
    digests = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    assert not output.exists() and shutil.disk_usage(output.parent).free >= 200 * 1024**2
    output.mkdir(); (output / 'rows').mkdir()
    rows = []
    for item in inputs():
        x, y, supplied = item['x'], item['y'], item['points']
        prediction = None if item['invalid'] else expected(x, y, supplied)
        roi = dict(x=x.copy(), y=y.copy(), name='boundary')
        if item['carrier'] == 'series': roi = pd.Series(roi)
        elif item['carrier'] == 'one-row-frame': roi = pd.DataFrame([roi])
        points = supplied.copy()
        if item['point_carrier'] == 'list': points = points.tolist()
        elif item['point_carrier'] == 'readonly': points.flags.writeable = False
        elif item['point_carrier'] == 'dataframe': points = pd.DataFrame(points, columns=['x', 'y'])
        marker = object.__new__(markers.Antibody)
        marker.name = 'M'; marker.experiment = SimpleNamespace(fig_path='unused-no-preview')
        state = dict(marker.__dict__)
        before_points = copy.deepcopy(points)
        record = dict(key=item['key'], invalid=item['invalid'], expected=prediction,
            input=dict(x=encode(x), y=encode(y), points=encode(supplied),
                dtype=str(x.dtype), carrier=item['carrier'], point_carrier=item['point_carrier']))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                distances, closest, line = marker.analyse_roi(roi, points, visualise=False)
            record['actual'] = encode(dict(distances=distances.tolist(), closest=closest.tolist(), line=line.tolist()))
            assert not item['invalid'], 'Invalid coordinates were silently accepted'
            # Tiny cases additionally require represented nonzero magnitudes;
            # the standing absolute tolerance must not turn underflow into success.
            for actual, expected_values in ((distances, prediction['distances']),
                    (closest, np.asarray(prediction['closest']).reshape((-1, 2))), (line, prediction['line'])):
                np.testing.assert_allclose(actual, expected_values, rtol=RTOL, atol=ATOL)
                expected_array = np.asarray(expected_values)
                if item['key'].startswith('tiny-floating'):
                    np.testing.assert_array_equal(np.signbit(actual), np.signbit(expected_array))
                    np.testing.assert_array_equal(actual == 0, expected_array == 0)
                    np.testing.assert_allclose(actual, expected_array, rtol=RTOL, atol=0)
            assert distances.shape == (len(supplied),) and closest.shape == (len(supplied), 2)
            record['passed'] = True
        except (ValueError, TypeError) as error:
            record.update(passed=item['invalid'], error=type(error).__name__ + ': ' + str(error))
        except Exception as error:
            record.update(passed=False, error=type(error).__name__ + ': ' + str(error))
        try:
            assert marker.__dict__ == state
            rx = roi['x'].iloc[0] if isinstance(roi, pd.DataFrame) else roi['x']
            ry = roi['y'].iloc[0] if isinstance(roi, pd.DataFrame) else roi['y']
            np.testing.assert_array_equal(rx, x); np.testing.assert_array_equal(ry, y)
            if isinstance(points, pd.DataFrame): pd.testing.assert_frame_equal(points, before_points, check_exact=True)
            else: np.testing.assert_array_equal(points, before_points)
            if item['point_carrier'] == 'readonly': assert not points.flags.writeable
        except Exception as error:
            record.update(passed=False, ownership_error=type(error).__name__ + ': ' + str(error))
        rows.append(record)
        (output / 'rows' / (item['key'] + '.json')).write_text(json.dumps(record, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    changes = [str(path) for path in paths if hashlib.sha256(path.read_bytes()).hexdigest() != digests[str(path)]]
    record = dict(status='finished', actual_calls=len(rows), failed=sum(not row['passed'] for row in rows),
        source_changes=changes, source_hashes=digests, rows=rows, rtol=RTOL, atol=ATOL,
        reference='Exact Fraction authored-input trace and padded means; 4096-bit mpmath projection. Literal functional shape/real-coordinate refusal requirements.')
    for index, path in enumerate(paths): (output / f'original-{index}-{path.name}').write_bytes(path.read_bytes())
    (output / 'before.json').write_text(json.dumps(record, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: record[key] for key in ('actual_calls', 'failed', 'source_changes')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); run(args.output)
