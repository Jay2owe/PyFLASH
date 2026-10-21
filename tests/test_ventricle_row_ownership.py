from pathlib import Path
from types import SimpleNamespace
import json,math
import numpy as np
import pandas as pd
import pytest
from PyFLASH.config import Config
from PyFLASH.markers import Antibody

FROZEN=Path(__file__).resolve().parents[1]/'reproducibility/reference-sources/ventricle-row-ownership/ventricle-row-controls-frozen-before-v2/frozen-before.json'
import hashlib
assert hashlib.sha256(FROZEN.read_bytes()).hexdigest()=='b13869ea1a2ce65b682ee8b7e6a5f21c7e4da672692b318ad6d15d2d66292344'
ROWS=json.loads(FROZEN.read_text(encoding='utf-8'))['rows']

def marker_and_rois(case):
    marker=Antibody.__new__(Antibody);marker.name='M'
    marker.df=pd.DataFrame({'Region':[r['region'] for r in case['rows']],
        'M_RawXM':[r['x'] for r in case['rows']], 'M_RawYM':[r['y'] for r in case['rows']],
        'M_ZM':[r['z'] for r in case['rows']]},index=case.get('index'))
    if case.get('region_index'):marker.df=marker.df.set_index('Region')
    marker.df.attrs={'owned-input':'retained'}
    def frame(records):return pd.DataFrame({'Region':[r['region'] for r in records],
        'x':[np.asarray(r['x']) if r['x'] is not None else None for r in records],
        'y':[np.asarray(r['y']) for r in records],'name':[r['region'] for r in records]})
    roi_frame=frame(case['rois'])
    marker.experiment=SimpleNamespace(data={'ROIs':SimpleNamespace(df=roi_frame)})
    return marker,frame(case.get('argument_rois',case['rois']))

@pytest.mark.parametrize('record',ROWS,ids=[r['case']['key'] for r in ROWS])
def test_original_distance_answers_and_row_ownership(record,monkeypatch):
    case=record['case'];monkeypatch.setattr(Config,'PIXEL_SIZE',case['pixels_per_micron'])
    marker,rois=marker_and_rois(case)
    original=marker.df.copy(deep=True);roi_original=rois.copy(deep=True)
    expected=np.asarray([math.inf if v=='__inf__' else v for v in record['reference']],dtype=float)
    assert marker.find_distance_to_ventricle(rois) is None
    np.testing.assert_allclose(marker.df['M_DistToVentricle'].to_numpy(),expected,rtol=1e-12,atol=1e-12)
    pd.testing.assert_frame_equal(marker.df.drop(columns='M_DistToVentricle'),original)
    pd.testing.assert_frame_equal(rois,roi_original)
    assert list(marker.df.columns)==list(original.columns)+['M_DistToVentricle']
    assert marker.df.attrs==original.attrs

@pytest.mark.parametrize('bad_x,bad_y', [([4.],[2.]),([4.,5.],[2.]),([4.,float('nan')],[2.,3.]),([4.,float('inf')],[2.,3.]),([[4.,5.],[6.,7.]],[[2.,3.],[4.,5.]]),(['bad','good'],[2.,3.])])
def test_malformed_later_roi_keeps_original_marker_output(monkeypatch,bad_x,bad_y):
    case=next(r['case'] for r in ROWS if r['case']['key']=='interleaved-regions.density-1.0')
    marker,rois=marker_and_rois(case)
    marker.df['M_DistToVentricle']=[91.,92.,93.,94.]
    original=marker.df.copy(deep=True)
    rois.at[1,'x']=np.asarray(bad_x)
    rois.at[1,'y']=np.asarray(bad_y)
    monkeypatch.setattr(Config,'PIXEL_SIZE',1.)
    with pytest.raises(ValueError):marker.find_distance_to_ventricle(rois)
    pd.testing.assert_frame_equal(marker.df,original)
