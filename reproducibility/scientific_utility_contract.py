"""Replay retained direct utility contracts without promoting scientific parents.

Expected answers come from byte-preserved before archives. Exact arithmetic,
custom tracing and display policies remain explicitly supporting diagnostics.
"""
from pathlib import Path
import hashlib
import json
import math

ARCHIVE=Path(__file__).with_name('reference-sources')/'scientific-utilities'
MANIFEST_SHA256='921e9b4aaf01824449aaab393327c6d939599cfba5b377192b08eacf0b94752d'
COORDINATE_MANIFEST_SHA256='54cccd98e0da2c0fa54d8ecdfbd35a19c39a42806098cb23d557120c07a6a9e5'
CACHE_CARRIER_SHA256='2537f2c0fda4ee818f8a74e42874069cb7f4a7f7434f1c8b056f960c7bda381b'
SOURCES=(
    ('percentages','add_coloc_percentages','coloc-percentage-original-native-20261006-v1'),
    ('percentages-exact','add_coloc_percentages','coloc-percentage-extremes-before-20261006-v2'),
    ('trace-policy','trace_downward_nearest','downward-trace-original-native-20261006-v1'),
    ('trace-distance','trace_downward_nearest','downward-trace-extremes-native-20261006-v1'),
    ('mean','moving_average','moving-average-window-means-before-20261006-v1'),
    ('mean-complex','moving_average','moving-average-complex-native-before-20261006-v1'),
    ('volume','adjust_for_volumemm','volume-normalization-native-before-20261006-v1'),
    ('display','round_up_to_nearest_5','axis-limit-rounding-display-qualified-before-20261006-v2'),
    ('polyline','points_to_polyline_distance','polyline-extreme-native-before-20261006-v2'),
    ('polyline-real-plane','points_to_polyline_distance','polyline-complex-coordinate-before-20261006-v2'),
    ('polyline-integer','points_to_polyline_distance','polyline-integer-native-before-20261006-v3'),
    ('conversion-typed',None,'conversion-calibration-typed-before-20261006-v1'),
    ('conversion',None,'conversion-calibration-native-before-20261006-v2'),
)
CAPABILITY_PREFIXES={'PyFLASH.utils.'+owner:('scientific-utility.'+owner+'.',) for owner in (
    'add_coloc_percentages','trace_downward_nearest','moving_average','adjust_for_volumemm',
    'round_up_to_nearest_5','points_to_polyline_distance','convert_microns_to_pixels','convert_pixels_to_microns')}
# Coverage is declared only after every numerical, ownership and domain field
# is scored. No parent, custom trace, display rule or untested object/extended-precision smoother
# is given a complete independent scientific-method certificate here.
COMPLETE_CAPABILITIES=frozenset('PyFLASH.utils.'+owner for owner in (
    'add_coloc_percentages','adjust_for_volumemm','points_to_polyline_distance',
    'convert_microns_to_pixels','convert_pixels_to_microns'))


def read(name):return json.loads((ARCHIVE/name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256, cache_carrier_sha256=CACHE_CARRIER_SHA256)
    verify_manifest(ARCHIVE, 'coordinate-amendment-manifest.json', COORDINATE_MANIFEST_SHA256, cache_carrier_sha256=CACHE_CARRIER_SHA256)


def cases():
    rows=[]
    for kind,owner,name in SOURCES:
        for row in read(name+'/frozen-before.json')['rows']:
            resolved=owner
            if kind in ('conversion','conversion-typed'):
                resolved='convert_microns_to_pixels' if row['case']['direction']=='microns-to-pixels' else 'convert_pixels_to_microns'
            rows.append({'key':'scientific-utility.'+resolved+'.'+row['case'].get('key', row.get('key')),
                'kind':kind,'owner':resolved,'capability':'PyFLASH.utils.'+resolved,'reference':row})
    return rows


def required_keys(capability):
    return {row['key'] for row in cases() if row['capability']==capability}


def encode(value):
    import numpy as np
    if isinstance(value,np.ndarray):return encode(value.tolist())
    if isinstance(value,np.generic):return encode(value.item())
    if isinstance(value,(tuple,list)):return [encode(v) for v in value]
    if isinstance(value,dict):return {str(k):encode(v) for k,v in value.items()}
    if isinstance(value,float) and not math.isfinite(value):return 'NaN' if math.isnan(value) else 'Inf' if value>0 else '-Inf'
    return value


def table(frame):
    return {'columns':list(frame.columns),'index':list(frame.index),'index_name':frame.index.name,
        'dtypes':list(frame.dtypes.astype(str)),'attrs':encode(frame.attrs),
        'rows':encode(list(frame.itertuples(index=False,name=None)))}


def production(item, observation):
    from PyFLASH import utils
    from PyFLASH.config import Config
    import numpy as np
    import pandas as pd
    ref=item['reference'];case=ref['case'];kind=item['kind'];owner=getattr(utils,item['owner'])
    scope='Direct utility only; no whole-parent or whole-package certificate.'
    if kind=='percentages':
        frame=pd.DataFrame({name:case['values'][name] for name in case['columns']},index=pd.Index(case['index'],name=case['index_name']))
        original=frame.copy(deep=True)
        expected=pd.DataFrame([[np.nan if v=='__nan__' else v for v in values] for values in ref['expected']['rows']],
            columns=ref['expected']['columns'],index=frame.index)
        returned=owner(frame)
        actual={'returned_original':returned is frame,'table':table(frame)}
        answer={'returned_original':True,'table':table(expected)}
        observation.update(production=actual,reference=answer)
        pd.testing.assert_frame_equal(frame[case['columns']],original,check_exact=True)
        pd.testing.assert_frame_equal(frame,expected,rtol=1e-12,atol=1e-12)
        assert returned is frame
        return actual,answer,'Native R 4.6.0 complete row proportions + literal column ownership',scope
    if kind=='percentages-exact':
        frame=pd.DataFrame({'A_ColocCountB':[case['positive']],'A_NonColocCountB':[case['negative']]})
        owner(frame)
        actual=frame[['A_ColocCountB%','A_NonColocCountB%']].iloc[0].tolist()
        observation.update(production=actual,reference=ref['expected'])
        native=next(row for row in read('coloc-percentage-native-exact-qualified-20261006-v1/run.json')['rows'] if row['case']['key']==case['key'])
        assert native['same_original_integer_and_float_inputs'] and native['agrees_with_retained_diagnostic']
        dimensional=next(row for row in read('coloc-percentage-native-pint-qualified-20261006-v1/run.json')['rows'] if row['key']==case['key'])
        assert dimensional['domain']=='native-dimensional-percent-conversion' and dimensional['agrees']
        assert dimensional['native_percentages']==native['values']==ref['expected'] and actual==native['values']
        return actual,native['values'],'Native SymPy 1.14.0 exact L1 vector norm and native Pint 0.25.2 percentage quantities','Direct native proportion primitive qualifies raw R arithmetic/transport outliers; no whole colocalization detector or extra published-method vote.'
    if kind=='trace-policy':
        points=np.asarray(case['points']);expected=ref['expected']
        try:result=owner(points[:,0],points[:,1])
        except ValueError as exc:
            if expected:raise
            return {'refused':True},{'refused':True},'Literal unavailable-path control','Functional path refusal; not a numerical agreement vote.'
        actual={'x':result[0].tolist(),'y':result[1].tolist(),'indices':result[2].tolist()}
        answer={'x':[r[0] for r in expected],'y':[r[1] for r in expected],'indices':[int(r[2]) for r in expected]}
        observation.update(production=actual,reference=answer)
        assert actual==answer and result[2].dtype.kind in 'iu'
        np.testing.assert_array_equal(points[result[2]],np.column_stack(result[:2]))
        return actual,answer,'Audit-authored tracing policy executed through native R primitives','Complete declared trajectory envelope; custom policy is supporting evidence, not an independently published whole-trace procedure.'
    if kind=='trace-distance':
        answer={'x':ref['expected_x'],'y':ref['expected_y'],'indices':ref['expected_indices']}
        try:result=owner(case['x'],case['y'])
        except ValueError:
            if answer['indices']:raise
            return {'refused':True},{'refused':True},'Literal unavailable-path control','Functional path refusal; not a numerical agreement vote.'
        actual={'x':result[0].tolist(),'y':result[1].tolist(),'indices':result[2].tolist()}
        observation.update(production=actual,reference=answer)
        assert actual==answer and result[2].dtype.kind in 'iu'
        return actual,answer,'Native SymPy 1.14.0 represented-input point distances + custom trajectory policy','Distance primitive independently qualified; custom whole-trace scientific method remains open.'
    if kind=='mean-complex':
        def decode(values):
            return np.asarray([math.nan if value=='NaN' else math.inf if value=='Inf' else -math.inf if value=='-Inf' else value for value in values])
        signal=np.empty(len(case['real']),dtype=np.complex128)
        signal.real=decode(case['real']);signal.imag=decode(case['imaginary'])
        snapshot=signal.copy();result=owner(signal,case['width'])
        actual={'real':encode(result.real),'imaginary':encode(result.imag),'shape':list(result.shape),'dtype':str(result.dtype)}
        answer=ref['expected'];observation.update(production=actual,reference=answer)
        assert ref['native_same_input'] and result.shape==tuple(answer['shape']) and result.dtype==np.complex128
        np.testing.assert_allclose(result.real,decode(answer['real']),rtol=1e-12,atol=0.,equal_nan=True)
        np.testing.assert_allclose(result.imag,decode(answer['imaginary']),rtol=1e-12,atol=0.,equal_nan=True)
        np.testing.assert_array_equal(signal.real,snapshot.real)
        np.testing.assert_array_equal(signal.imag,snapshot.imag)
        qualified=next(row for row in read('moving-average-complex-native-qualified-20261006-v1/run.json')['rows'] if row['key']==case['key'])
        assert qualified['agrees'] and qualified['native_R_received_original_inputs']
        return actual,answer,'Native R 4.6.0 complex colMeans; qualified native SciPy window filters','Complete direct complex64/complex128 component arrays; object/extended-precision legacy branches and whole ventricle procedures stay open.'
    if kind=='mean':
        assert ref['native_same_input'] and ref['native_r_exact_agreement']
        values=[np.nan if v is None else v for v in case['values']]
        expected=np.array([np.nan if v is None else v for v in ref['native_r_colMeans']['values']])
        result=owner(values,w=case['width'])
        observation.update(production=encode(result),reference=encode(expected))
        assert result.dtype==np.float64 and result.shape==expected.shape
        np.testing.assert_array_equal(result,expected)
        return {'values':encode(result),'shape':list(result.shape),'dtype':str(result.dtype)}, {'values':encode(expected),'shape':list(expected.shape),'dtype':'float64'}, 'Native R 4.6.0 complete edge-padded window means', 'Complete real binary64 primitive outputs; object/extended-precision legacy branches and whole ventricle procedures remain open.'
    if kind=='volume':
        frame=pd.DataFrame(ref['original_input'],index=pd.Index(ref['index'],name=ref['index_name']))
        frame.attrs=ref['attrs'];expected=frame.copy(deep=True)
        for name,values in ref['expected'].items():expected[name]=[np.nan if v is None else v for v in values]
        previous=Config.SECTION_THICKNESS_UM
        try:
            Config.SECTION_THICKNESS_UM=case['thickness'];returned=owner(frame,case['columns'],'Area')
        finally:Config.SECTION_THICKNESS_UM=previous
        observation.update(production={'returned_original':returned is frame,'table':table(frame)},reference={'returned_original':True,'table':table(expected)})
        assert returned is frame
        pd.testing.assert_frame_equal(frame,expected,rtol=1e-12,atol=0.)
        return {'returned_original':returned is frame,'table':table(frame)}, {'returned_original':True,'table':table(expected)}, 'Native Pint 0.25.2 Decimal quantities; independently qualified Astropy conversions', 'Complete direct original-area/unique-target dimensional normalization; no recorded acquisition-volume certificate.'
    if kind=='display':
        value=np.nan if case['value']=='NaN' else case['value']
        try:result=owner(value)
        except ValueError:
            if ref['domain']!='refuse-unrepresentable-output':raise
            return {'refused':True},{'refused':True},'Literal unrepresentable display-bound control','Functional display refusal; not a numerical agreement vote.'
        observation.update(production=result,reference=ref['expected'])
        assert ref['domain']=='finite-output' and result==ref['expected']
        return result,ref['expected'],'Audit-authored binary64 display rule with native Decimal primitives','Display-supporting diagnostic, not an independent scientific estimator vote.'
    if kind=='polyline-real-plane':
        values=[[complex(v['real'],v['imaginary']) for v in array] for array in case['inputs']]
        carrier=case['carrier']
        if carrier=='tuple':values=list(map(tuple,values))
        elif carrier not in ('list','tuple'):
            values=[np.array(array,dtype=object if 'object' in carrier else getattr(np,carrier)) for array in values]
            if carrier=='readonly-object':
                for value in values:value.flags.writeable=False
        snapshots=[np.array(value,dtype=object,copy=True) for value in values]
        import warnings
        answer=ref['expected'];actual=None
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            try:
                result=owner(*values)
            except ValueError:
                actual={'refused':True}
            else:
                assert isinstance(result,tuple) and len(result)==2
                assert result[0].shape==(3,) and result[1].shape==(3,2)
                assert all(value.dtype==np.float64 for value in result)
                actual={'distances':result[0].tolist(),'closest_points':result[1].tolist()}
        observation.update(production=actual,reference=answer)
        for value,snapshot in zip(values,snapshots):np.testing.assert_array_equal(value,snapshot)
        assert bool(ref['native_error'])==bool(case['imaginary']) and actual==answer
        return actual,answer,'Native SymPy real-plane Point eligibility, Line projections and Point distances','Functional real-plane eligibility and zero-imaginary carrier preservation only; no extra independent whole-method vote.'
    if kind=='polyline-integer':
        # Lists retain original integers. A NumPy inferred dtype can round them
        # before the method is called, invalidating a same-input comparison.
        inputs=[[point[axis] for point in case[name]] for name in ('points','line') for axis in (0,1)]
        snapshot=[list(values) for values in inputs]
        with np.errstate(all='raise'):
            result=owner(*inputs)
        actual={'distances':encode(result[0]),'closest_points':encode(result[1]),'shapes':[list(v.shape) for v in result]}
        answer={'distances':ref['expected_distances'],'closest_points':ref['expected_closest_points'],'shapes':[[len(case['points'])],[len(case['points']),2]]};observation.update(production=actual,reference=answer)
        assert ref['native_received_original_integers'] and ref['production_received_original_integer_lists'] and inputs==snapshot
        assert isinstance(result,tuple) and len(result)==2 and all(v.dtype==np.float64 for v in result)
        assert result[0].shape==(len(case['points']),) and result[1].shape==(len(case['points']),2)
        np.testing.assert_allclose(result[0],answer['distances'],rtol=1e-12,atol=0.)
        np.testing.assert_array_equal(result[1],answer['closest_points'])
        return actual,answer,'Native SymPy exact Integer points, segment projections and point distances','Original integer geometry; binary64 nearest coordinates are explicitly rounded only after exact geometry. No whole ventricle certificate.'
    if kind=='polyline':
        points=np.asarray(case['points']);line=np.asarray(case['line'])
        try:result=owner(points[:,0],points[:,1],line[:,0],line[:,1])
        except ValueError:
            if ref['domain']!='refuse-unrepresentable-output':raise
            return {'refused':True},{'refused':True},'Literal unrepresentable distance control','Functional distance refusal; not a numerical agreement vote.'
        observation.update(production=encode(result),reference={'distances':ref['expected_distances'],'closest_points':ref['expected_closest_points']})
        assert ref['domain']=='finite-output'
        for actual,expected in zip(result,(ref['expected_distances'],ref['expected_closest_points'])):
            actual=actual.reshape(-1);expected=np.asarray(expected).reshape(-1)
            assert len(actual)==len(expected)
            assert all(a==b or math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=0.) for a,b in zip(actual,expected))
        assert isinstance(result,tuple) and result[0].dtype==result[1].dtype==np.float64
        assert result[0].shape==(len(points),) and result[1].shape==(len(points),2)
        actual={'distances':encode(result[0]),'closest_points':encode(result[1]),'shapes':[list(v.shape) for v in result]}
        answer={'distances':ref['expected_distances'],'closest_points':ref['expected_closest_points'],'shapes':[[len(points)],[len(points),2]]}
        return actual,answer,'Native SymPy projections/point distances; raw segment and GEOS answers retained', 'Complete direct finite polyline arrays and first-segment tie policy; no whole ventricle procedure certificate.'
    if kind in ('conversion','conversion-typed'):
        values=np.asarray(case['values'],dtype=case.get('dtype',np.int64 if case.get('carrier')=='int64' else float))
        options={'pixel_size':case['calibration']} if case['mode']=='explicit-um-per-pixel' else {}
        previous=Config.PIXEL_SIZE
        try:
            Config.PIXEL_SIZE=case['calibration']
            try:result=owner(values,**options)
            except ValueError:
                if ref['domain']!='refuse-unrepresentable-output':raise
                return {'refused':True},{'refused':True},'Literal unrepresentable coordinate control','Functional conversion refusal; not a numerical agreement vote.'
        finally:Config.PIXEL_SIZE=previous
        observation.update(production=encode(result),reference=ref['expected'])
        assert ref['domain']=='finite-output' and result.shape==values.shape and result.dtype==np.float64
        assert all(a==b or math.isclose(float(a),b,rel_tol=1e-12,abs_tol=0.) for a,b in zip(result,ref['expected']))
        return {'values':encode(result),'shape':list(result.shape),'dtype':str(result.dtype)}, {'values':ref['expected'],'shape':list(values.shape),'dtype':'float64'}, 'Native Pint calibrated-unit conversion; previous exact ImageJ results retained', 'Complete direct real coordinate arrays; unavailable numeric output is refused through separate functional controls.'
    raise ValueError('Unknown scientific utility contract kind: '+kind)


def validate(output):
    from reproducibility.normality_association_validation import comparison
    from PyFLASH._persistence import write_json
    check_identity();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rows=[];paired=[]
    for item in cases():
        actual=None;answer=None;error=None;agrees=False;label='Retained native or supporting utility evidence';scope='Direct utility only'
        observation={}
        try:
            result=production(item,observation)
            actual,answer,label,scope=result
            agrees=True
        except Exception as exc:
            error=type(exc).__name__+': '+str(exc)
            actual=observation.get('production');answer=observation.get('reference')
        rows.append(comparison(item['key'],label,'direct-scientific-utilities',actual,answer,agrees,True,scope,1e-12,0.))
        paired.append({'key':item['key'],'capability':item['capability'],'input':item['reference']['case'],
            'production':encode(actual),'reference':encode(answer),'error':error,'agrees':agrees,'reference_scope':scope})
        write_json(output/'scientific-utility-paired.json',{'rows':paired})
    return rows
