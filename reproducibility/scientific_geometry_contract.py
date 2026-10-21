"""Retained native geometry primitives; no complete ROI or marker certificate."""
from pathlib import Path
import hashlib, json
import numpy as np

ARCHIVE = Path(__file__).with_name('reference-sources')/'scientific-geometry-primitives'
SCIENTIFIC_UTILITIES = frozenset({
    'adjust_for_volumemm', 'add_coloc_percentages', 'round_up_to_nearest_5',
    'convert_microns_to_pixels', 'convert_pixels_to_microns',
    'trace_downward_nearest', 'moving_average', 'points_to_polyline_distance',
})
CAPABILITY_PREFIXES = {
    'PyFLASH.utils.points_to_polyline_distance': ('geometry-polyline.',),
    'PyFLASH.utils.convert_microns_to_pixels': ('geometry-conversion.microns-to-pixels.',),
    'PyFLASH.utils.convert_pixels_to_microns': ('geometry-conversion.pixels-to-microns.',),
}

def read(name): return json.loads((ARCHIVE/name).read_text(encoding='utf-8'))

def check_identity():
    manifest = read('source-manifest.json')
    for name, expected in manifest.items():
        if hashlib.sha256((ARCHIVE/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Retained native evidence changed: '+name)
    before = read('polyline-native-frozen-v1/run.json')
    ties = read('polyline-native-tie-reference-v2/run.json')
    if not before['reference_only'] or not ties['reference_only'] or ties['tolerance_changed']:
        raise ValueError('Native evidence or tie policy is not preserved.')
    return before

def validate(output):
    from PyFLASH import utils
    from PyFLASH.config import Config
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    check_identity()
    output = Path(output)
    inputs = read('polyline-native-frozen-v1/inputs.json')
    answers = {r['key']:r for r in read('polyline-native-frozen-v1/shapely-answers.json')}
    symbols = {r['key']:r for r in read('polyline-native-frozen-v1/sympy-answers.json')}
    ties = {r['key']:r['nearest_candidates'] for r in read('polyline-native-tie-reference-v2/nearest-candidates.json')}
    rows, paired = [], []
    for case in inputs:
        for carrier in ('list','tuple','array'):
            key = 'geometry-polyline.'+case['key']+'.'+carrier
            item = {'key':key,'input':case,'carrier':carrier,'reference':answers[case['key']]}
            actual, error, agrees = None, None, False
            try:
                points = np.asarray(case['points'],dtype=float).reshape(-1,2)
                line = np.asarray(case['line'],dtype=float)
                arguments = [points[:,0],points[:,1],line[:,0],line[:,1]]
                if carrier=='list': arguments=[x.tolist() for x in arguments]
                if carrier=='tuple': arguments=[tuple(x) for x in arguments]
                result = utils.points_to_polyline_distance(*arguments)
                distances, closest = result
                answer = answers[case['key']]
                canonical = bool(np.allclose(closest/case['scale'],np.asarray(answer['closest_points']).reshape(-1,2)/case['scale'],rtol=1e-12,atol=1e-12))
                valid_points = all(any(np.allclose(point/case['scale'],np.asarray(candidate)/case['scale'],rtol=1e-12,atol=1e-12) for candidate in candidates)
                                   for point,candidates in zip(closest,ties[case['key']]))
                checks = {
                    'tuple-envelope':isinstance(result,tuple) and len(result)==2,
                    'array-types':isinstance(distances,np.ndarray) and isinstance(closest,np.ndarray),
                    'float64-types':str(distances.dtype)==str(closest.dtype)=='float64',
                    'shapes':[list(distances.shape),list(closest.shape)]==answer['shapes'],
                    'shapely-distances':bool(np.allclose(distances/case['scale'],np.asarray(answer['distances'])/case['scale'],rtol=1e-12,atol=1e-12)),
                    'nearest-points':valid_points,
                }
                if case['key'] in symbols:
                    checks['sympy-distances']=bool(np.allclose(distances,symbols[case['key']]['distances'],rtol=1e-12,atol=1e-12))
                actual={'distances':distances.tolist(),'closest_points':closest.tolist(),'shapes':[list(distances.shape),list(closest.shape)]}
                agrees=all(checks.values())
                item.update(checks=checks,canonical_nearest_points_agree=canonical,
                            nearest_point_category='canonical-agreement' if canonical else 'different-equally-near-point')
            except Exception as exception: error=type(exception).__name__+': '+str(exception)
            item.update(production=actual,error=error,agrees=agrees)
            paired.append(item)
            rows.append(comparison(key,'Shapely 2.1.2 / GEOS and SymPy 1.14.0 distance benchmarks',
                'scientific-geometry-primitives',actual,answers[case['key']],agrees,True,
                'full-arrays-shapes-dtypes-valid-nearest-points; normalized-input-scale',1e-12,1e-12))
            write_json(output/'scientific-geometry-paired.json',{'rows':paired})
    for case in read('native-imagej-geometry-comparisons-v1/paired.json')['conversions']:
        options={} if case['default'] else {'pixel_size':case['microns_per_pixel']}
        for index,(name,owner) in enumerate((('microns-to-pixels',utils.convert_microns_to_pixels),('pixels-to-microns',utils.convert_pixels_to_microns))):
            key='geometry-conversion.'+name+'.'+case['key']
            actual,error=None,None
            saved=Config.PIXEL_SIZE
            try:
                if case['default']: Config.PIXEL_SIZE=case['configured_pixels_per_micron']
                actual=float(owner(case['value'],**options))
            except Exception as exception: error=type(exception).__name__+': '+str(exception)
            finally: Config.PIXEL_SIZE=saved
            expected=case['native'][index]
            agrees=error is None and actual==expected
            rows.append(comparison(key,'native ImageJ 1.54p Calibration','scientific-geometry-primitives',
                actual,expected,agrees,True,'exact-scalar-conversion',0.,0.))
            paired.append({'key':key,'input':case,'production':actual,'reference':expected,'error':error,'agrees':agrees})
            write_json(output/'scientific-geometry-paired.json',{'rows':paired})
    return rows
