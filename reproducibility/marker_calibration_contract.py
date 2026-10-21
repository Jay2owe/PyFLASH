"""Original Fiji coordinates through actual marker construction and CSV import.

The native fixture records the installed published counter and ImageJ's own
Calibration coordinate conversion. Full prepared tables are literal adapter
contracts; they do not certify complete microscopy processing or summaries.
"""
from pathlib import Path
from types import SimpleNamespace
import contextlib, hashlib, io, json, math, tempfile, warnings

ARCHIVE=Path(__file__).with_name('reference-sources')/'marker-calibration'
MANIFEST_SHA256='41372aab18fc5d1457d76a08f75dd3a5662dc6290672c79ed916cbe2b2f27bbb'
DISTANCE_MANIFEST_SHA256='28dd757dbe02929af6c42920d452c7a279d89b8185d4d2d3b0c27c97b7945953'
CAPABILITY_PREFIXES={
 'PyFLASH.markers.Antibody.clean_df':('marker-calibration.',),
 'PyFLASH.experiment.Experiment.importCSVs':('marker-calibration.import.',),
 'PyFLASH.markers.Antibody.find_closest_distances_between_markers':('marker-calibration.',),
}
COMPLETE_CAPABILITIES=frozenset()


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
    verify_manifest(ARCHIVE,'native-distance-manifest.json',DISTANCE_MANIFEST_SHA256)
    fixture=json.loads((ARCHIVE/'native-imagej-v1/fixture.json').read_text(encoding='utf-8'))
    native=json.loads((ARCHIVE/'native-imagej-v1/native.json').read_text(encoding='utf-8'))
    if fixture['answers']!=native:raise ValueError('Native calibration answers changed.')
    from reproducibility import marker_calibration_reference as reference
    distances=json.loads((ARCHIVE/'native-r-v1/frozen.json').read_text(encoding='utf-8'))
    root=Path(__file__).resolve().parents[1]
    for name,digest in distances['sources'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Native calibration reference source changed: '+name)
    if [row['case'] for row in distances['rows']]!=reference.cases():
        raise ValueError('Native calibration distance inputs changed.')
    frozen_queries=json.loads((ARCHIVE/'native-r-v1/calibrated-native-distances-queries.json').read_text(encoding='utf-8'))
    if frozen_queries!=[reference.query(case) for case in reference.cases()]:
        raise ValueError('Native calibration distance expressions changed.')
    return native


def cases():
    native=json.loads((ARCHIVE/'native-imagej-v1/native.json').read_text(encoding='utf-8'))
    return [dict(key=f'marker-calibration.{mode}.pitch-{pitch}.area-{area}.{backend}',
                 mode=mode,pitch=pitch,area=area,backend=backend,
                 native=native['cases'][2*pitch:2*pitch+2])
            for pitch in range(3) for mode in ('object','cell','import')
            for area in (False,True) for backend in ('tree','fallback')]


def frame(native):
    import pandas as pd
    x,y,z=native['raw_centre_double'];sx,sy,sz=native['pitch']
    return pd.DataFrame({
      'Region':['SCN1'],'Animal Name':['Subject1'],
      'Volume (micron^3)':[native['calibrated_volume']],
      'Surface':[native['surface']],'IntDen':[native['intensity_sum']],
      'Mean':[native['mean_gray']],'XM':[x],'YM':[y],'ZM':[z],
      'SourcePixelWidth':[sx],'SourcePixelHeight':[sy],'SourcePixelDepth':[sz],
      'SourcePixelUnit':['micron'],'SourcePixelXUnit':['micron'],
      'SourcePixelYUnit':['micron'],'SourcePixelZUnit':['micron'],
    })


def expected_frame(native,name,area,imported=False):
    import pandas as pd
    raw=frame(native)
    # Complete column identities are a literal declared import policy, not a
    # call into production's cleaner or coordinate preparation.
    columns=['Region','AnimalName',name+'_Volume',name+'_Surface',name+'_IntDen',
             name+'_MeanIntDen',name+'_XM',name+'_YM',name+'_ZM',
             name+'_SourcePixelWidth',name+'_SourcePixelHeight',name+'_SourcePixelDepth',
             name+'_SourcePixelUnit',name+'_SourcePixelXUnit',name+'_SourcePixelYUnit',name+'_SourcePixelZUnit']
    result=raw.copy();result.columns=columns
    if imported:
        result['Hemisphere']=''
        result['ROI']='SCN'
    result[name+'_Count']=1
    result['Condition']='Subject'
    result[name+'_SAtoVolumeRatio']=native['surface']/native['calibrated_volume']
    x,y,z=native['physical_centre']
    result[name+'_RawYM']=y
    result[name+'_RawXM']=x
    result[name+'_RawZM']=z
    if area:
        result[name+'_XM']=native['raw_centre_double'][0]*(500/1024)
        result[name+'_YM']=native['raw_centre_double'][1]*(-800/1024)
    return result.set_index('Region')


def production(item,folder=None,observation=None):
    import numpy as np
    import pandas as pd
    from PyFLASH import markers
    from PyFLASH.experiment import Experiment
    from reproducibility.marker_nearest_contract import configuration,table
    if item['mode']=='import':
        if folder is None:raise ValueError('Actual CSV import requires its owned input folder.')
        folder=Path(folder);(folder/'Objects').mkdir(parents=True,exist_ok=True)
        for native,name in zip(item['native'],('A','B'),strict=True):
            frame(native).to_csv(folder/'Objects'/(name+'.csv'),index=False,float_format='%.17g')
        exp=Experiment('native-calibration',str(folder))
        with warnings.catch_warnings(),contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter('ignore');returned=exp.importCSVs(progress=False)
        left,right=returned['A'],returned['B']
        import_returns_own_data=returned is exp.data
        # The area route deliberately tests the public constructor separately;
        # actual CSV imports retain their actual no-area behavior here.
        if item['area']:
            exp.data['ROI Properties']=SimpleNamespace(df=pd.DataFrame({'AnimalName':['Subject1'],'Region':['SCN1']}))
            left=markers.objectMarker('A',frame(item['native'][0]),exp,None)
            right=markers.objectMarker('B',frame(item['native'][1]),exp,None)
    else:
        exp=SimpleNamespace(data={})
        if item['area']:exp.data['ROI Properties']=SimpleNamespace(df=pd.DataFrame({'AnimalName':['Subject1'],'Region':['SCN1']}))
        cls=markers.objectMarker if item['mode']=='object' else markers.cellMarker
        with warnings.catch_warnings(),contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter('ignore')
            left=cls('A',frame(item['native'][0]),exp,None)
            right=cls('B',frame(item['native'][1]),exp,None)
        import_returns_own_data=None
    imported=item['mode']=='import' and not item['area']
    expected_left=expected_frame(item['native'][0],'A',item['area'],imported)
    expected_right=expected_frame(item['native'][1],'B',item['area'],imported)
    prepared={'left':table(left.df),'right':table(right.df)}
    expected_prepared={'left':table(expected_left),'right':table(expected_right)}
    config={'backend':item['backend'],'threshold_source':'global','case':{'threshold':30}}
    with configuration(config),contextlib.redirect_stdout(io.StringIO()):
        returned=left.find_closest_distances_between_markers(right)
    native_answer=json.loads((ARCHIVE/'native-r-v1/frozen.json').read_text(encoding='utf-8'))['rows'][item['pitch']]['expected']
    expected_left['A_DistToClosest_B']=np.asarray(native_answer['distances'],dtype=float)
    for name,field,dtype in (
        ('B_ClosestTo_A','closest_flags',float),('B_VolNumColoc_A','coloc_counts',float),
        ('B_VolContains_A','contains',np.int8),('B_NumColoc_A','coloc_counts',float),
        ('B_Contains_A','contains',np.int8),('B_NumClosestTo_A','closest_counts',float)):
        values=native_answer[field]
        if not all(math.isfinite(value) and value>=0 and value==int(value) for value in values):
            raise ValueError('Native calibration attribution must contain exact integer counts.')
        expected_right[name]=np.asarray(values,dtype=dtype)
    actual={'prepared':prepared,'left':table(left.df),'right':table(right.df),
            'return_alias':returned is left.df,'import_returns_own_data':import_returns_own_data}
    answer={'prepared':expected_prepared,'left':table(expected_left),'right':table(expected_right),
            'return_alias':True,'import_returns_own_data':True if item['mode']=='import' else None}
    if observation is not None:observation.update(actual=actual,expected=answer)
    assert prepared==expected_prepared, 'Complete prepared native tables must agree exactly.'
    assert actual['return_alias'] is True
    assert actual['import_returns_own_data']==answer['import_returns_own_data']
    assert left.df.attrs==expected_left.attrs and right.df.attrs==expected_right.attrs
    pd.testing.assert_frame_equal(left.df,expected_left,check_exact=False,rtol=1e-12,atol=0.)
    pd.testing.assert_frame_equal(right.df,expected_right,check_exact=True)
    return actual,answer


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    from reproducibility import marker_calibration_reference as reference
    from reproducibility.reference_runtime import execute_queries,values
    from reproducibility.marker_nearest_contract import equal
    check_identity();output=Path(output)
    frozen=json.loads((ARCHIVE/'native-r-v1/frozen.json').read_text(encoding='utf-8'))
    native=execute_queries([reference.query(item['case']) for item in frozen['rows']],
                           output/'calibrated-native-r',name='calibrated-native-distances',timeout=180)
    for key,value in frozen['runtime'].items():
        if native[key]!=value:raise ValueError('Native calibration runtime changed: '+key)
    for item,row in zip(frozen['rows'],native['rows'],strict=True):
        equal(reference.unpack(item['case'],list(values(row))),item['expected'])
    from reproducibility.paired_checkpoint import PairedCheckpoint
    journal=PairedCheckpoint(output,'marker-calibration')
    rows=[];paired=[]
    for item in cases():
        observation={};error=None
        try:production(item,output/'marker-calibration-inputs'/item['key'],observation)
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        actual,answer=observation.get('actual'),observation.get('expected')
        rows.append(comparison(item['key'],'Installed Fiji 3D Objects Counter 2.0.1, ImageJ 1.54p Calibration and native R 4.6.0 distance/attribution',
            'native-coordinate-conversion/complete-composed-table-contract',actual,answer,error is None,True,
            'all-imported-measurements-calibration-columns-derived-coordinates-and-counts',1e-12,0.))
        paired.append({'item':item,'actual':actual,'expected':answer,'error':error})
        journal.append(paired[-1])
    write_json(output/'marker-calibration-paired.json',{'rows':paired,'scope':'Full calibrated table adapter and native R nearest output; no certificate for complete microscopy processing or summaries.'})
    return rows
