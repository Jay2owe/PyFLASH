"""Actual native-coordinate import must retain physical units and complete tables."""
import pytest
from reproducibility import marker_calibration_contract as contract


@pytest.mark.parametrize('item',contract.cases(),ids=lambda x:x['key'])
def test_native_calibration_through_actual_marker_and_csv_tables(item,tmp_path):
    contract.production(item,tmp_path/item['key'])


def test_original_native_counter_measurements_and_driver_are_unchanged():
    assert len(contract.check_identity()['cases'])==6


@pytest.mark.parametrize('unit,factor',[('micron',1.),('um',1.),('µm',1.),('μm',1.),('nm',1000.),('mm',.001)])
@pytest.mark.parametrize('axis_units',[False,True])
def test_declared_axis_units_reproduce_native_physical_centres(unit,factor,axis_units):
    from types import SimpleNamespace
    import numpy as np
    from PyFLASH.markers import objectMarker
    native=contract.cases()[0]['native'][0]
    raw=contract.frame(native)
    for dimension in ('Width','Height','Depth'):
        raw['SourcePixel'+dimension]*=factor
    for axis in ('X','Y','Z'):
        if axis_units:raw['SourcePixel'+axis+'Unit']=unit
        else:raw=raw.drop(columns='SourcePixel'+axis+'Unit')
    raw['SourcePixelUnit']=unit
    with pytest.warns(UserWarning,match='No Area Data'):
        marker=objectMarker('A',raw,SimpleNamespace(data={}),None)
    np.testing.assert_allclose(marker.df[['A_RawXM','A_RawYM','A_RawZM']].to_numpy(),
                               [native['physical_centre']],rtol=1e-12,atol=0.)


@pytest.mark.parametrize('column,value',[
    ('A_SourcePixelWidth',0.),('A_SourcePixelHeight',-1.),
    ('A_SourcePixelDepth',float('nan')),('A_SourcePixelWidth',float('inf')),
    ('A_SourcePixelZUnit','pixel'),('A_SourcePixelXUnit','unknown'),
])
def test_invalid_calibration_refuses_before_coordinate_output_changes(column,value):
    import pandas as pd
    from PyFLASH.markers import Antibody
    marker=Antibody.__new__(Antibody);marker.name='A'
    marker.df=contract.expected_frame(contract.cases()[0]['native'][0],'A',False)
    marker.df[column]=value;original=marker.df.copy(deep=True)
    with pytest.raises(ValueError,match='Source calibration'):
        marker._adjust_coordinates()
    pd.testing.assert_frame_equal(marker.df,original,check_exact=True)


def test_native_zero_depth_is_valid_and_zero_count_is_missing():
    from PyFLASH.markers import Antibody
    import pandas as pd
    marker=Antibody.__new__(Antibody);marker.name='A'
    marker.df=pd.DataFrame({'A_RawXM':[0.,1.],'A_RawYM':[0.,0.],
                            'A_RawZM':[0.,0.],'A_ZM':[0.,0.],'A_Count':[1,0]})
    _,valid=marker._spatial_coordinate_data(marker.df)
    assert valid.tolist()==[True,False]


@pytest.mark.parametrize('kind',['pitch-overflow','pitch-underflow','coordinate-overflow'])
def test_unrepresentable_physical_coordinates_refuse_without_table_mutation(kind):
    import pandas as pd
    from PyFLASH.markers import Antibody
    marker=Antibody.__new__(Antibody);marker.name='A'
    marker.df=contract.expected_frame(contract.cases()[0]['native'][0],'A',False)
    if kind=='coordinate-overflow':
        marker.df['A_XM']=1e308;marker.df['A_SourcePixelWidth']=2.
    else:
        marker.df['A_SourcePixelXUnit']='mm' if kind=='pitch-overflow' else 'nm'
        marker.df['A_SourcePixelWidth']=1e308 if kind=='pitch-overflow' else 5e-324
    original=marker.df.copy(deep=True)
    with pytest.raises(ValueError,match='Source calibration'):
        marker._adjust_coordinates()
    pd.testing.assert_frame_equal(marker.df,original,check_exact=True)


@pytest.mark.parametrize('side',['left','right'])
@pytest.mark.parametrize('backend',['tree','fallback'])
def test_nonreal_nearest_coordinate_refuses_before_either_table_mutates(side,backend):
    from PyFLASH.markers import Antibody
    from reproducibility.marker_nearest_contract import configuration
    import pandas as pd
    left=Antibody.__new__(Antibody);left.name='A'
    right=Antibody.__new__(Antibody);right.name='B'
    left.df=contract.expected_frame(contract.cases()[0]['native'][0],'A',False)
    right.df=contract.expected_frame(contract.cases()[0]['native'][1],'B',False)
    marker=left if side=='left' else right
    marker.df[marker.name+'_RawXM']=marker.df[marker.name+'_RawXM'].astype(complex)+1j
    originals=[obj.df.copy(deep=True) for obj in (left,right)]
    with configuration({'backend':backend,'threshold_source':'global','case':{'threshold':30}}),pytest.raises(ValueError,match='must be real'):
        left.find_closest_distances_between_markers(right)
    for obj,original in zip((left,right),originals,strict=True):
        pd.testing.assert_frame_equal(obj.df,original,check_exact=True)


@pytest.mark.parametrize('pitch_x,pitch_y',[(.25,.5),(2.,3.)])
@pytest.mark.parametrize('fallback',[False,True])
def test_ventricle_distances_use_declared_anisotropic_units(pitch_x,pitch_y,fallback):
    from PyFLASH.markers import Antibody
    import numpy as np
    import pandas as pd
    marker=Antibody.__new__(Antibody);marker.name='A'
    marker.df=pd.DataFrame({'Region':['SCN1'],'A_RawXM':[2*pitch_x],
        'A_RawYM':[3*pitch_y],'A_RawZM':[0.],'A_ZM':[0.],
        'A_SourcePixelWidth':[pitch_x],'A_SourcePixelHeight':[pitch_y],
        'A_SourcePixelDepth':[1.],'A_SourcePixelUnit':['micron'],'A_Count':[1]})
    original=marker.df.copy(deep=True)
    x=None if fallback else np.full(10,5.)
    rois=pd.DataFrame({'Region':['SCN1'],'name':['SCN1'],
                      'x':[x],'y':[np.arange(10,dtype=float)]})
    assert marker.find_distance_to_ventricle(rois) is None
    expected=1022*pitch_x if fallback else 3*pitch_x
    assert marker.df['A_DistToVentricle'].iloc[0]==pytest.approx(expected,rel=1e-12,abs=0.)
    pd.testing.assert_frame_equal(marker.df.drop(columns='A_DistToVentricle'),original,check_exact=True)
