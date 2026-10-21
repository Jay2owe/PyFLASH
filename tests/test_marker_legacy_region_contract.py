"""Supported legacy objects retain original full scientific curves and group fields."""
import pytest
import pandas as pd
from types import SimpleNamespace
from PyFLASH.iteration import Context
from PyFLASH.plotting import _filter_marker_df_for_context
from reproducibility import marker_legacy_region_contract as contract
CASES=contract.originals()

@pytest.fixture(scope='module',autouse=True)
def retained_evidence():
    contract.check_identity()

@pytest.mark.parametrize('original',CASES,ids=[r['case']['key'] for r in CASES])
def test_actual_experiment_fallback_and_factor_only_summary_remain_compatible(original,tmp_path):
    contract.production(original,tmp_path)


@pytest.mark.parametrize('roi,declared,expected',[('SCN',False,[0,1]),('OC',False,[]),('SCN',True,[])])
def test_only_implicit_unmapped_flat_csv_region_preserves_categorical_rows(roi,declared,expected):
    frame=pd.DataFrame({'Condition':['Group','Group'],'AnimalName':['1','1'],
                        'Region':['CA1','DG'],'measurement':[2.,5.]})
    columns=['AnimalName','Region','ImageROI']+(['ROI'] if declared else [])
    experiment=SimpleNamespace(summary=frame.copy(),master_region=pd.DataFrame(columns=columns),
        getRegionDict=lambda roi_base:{'Group':{'1':[]}})
    context=Context(experiment,condition='Group',roi_base=roi)
    original=frame.copy(deep=True)
    actual=_filter_marker_df_for_context(context,frame)
    pd.testing.assert_frame_equal(actual,original.iloc[expected],check_exact=True)
    pd.testing.assert_frame_equal(frame,original,check_exact=True)
