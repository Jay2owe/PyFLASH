"""A selected region determines the group count and complete saved points."""
from copy import deepcopy
import pytest
from reproducibility import region_factor_finalization_contract as M


@pytest.mark.parametrize('kind',['regression','scatter3d'])
@pytest.mark.parametrize('more',['SCN','OC'])
@pytest.mark.parametrize('roi',['SCN','OC'])
@pytest.mark.parametrize('combine',[False,True])
def test_selected_region_groups_finalize_complete_figures(kind,more,roi,combine,tmp_path):
    case=dict(kind=kind,more=more,roi=roi,combine=combine)
    M.check_result(case,M.production(case,tmp_path))


@pytest.mark.parametrize('damage',['missing-save','point','group-count'])
def test_wrong_finalization_or_points_are_rejected(damage,tmp_path):
    case=dict(kind='regression',more='SCN',roi='OC',combine=True)
    actual=deepcopy(M.production(case,tmp_path))
    if damage=='missing-save':actual['writes']=[]
    elif damage=='point':actual['writes'][0]['points'][0][0][0]+=1
    else:actual['events'][0]['total']+=1
    with pytest.raises(AssertionError):M.check_result(case,actual)
