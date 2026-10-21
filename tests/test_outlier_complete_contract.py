"""Complete subject-level outlier arrays/reports and invalid request boundaries."""
import copy
import numpy as np
import pandas as pd
import pytest
from PyFLASH.stats_extra import flag_outliers, rout_outlier_stats
from reproducibility import outlier_contract as reference


@pytest.mark.parametrize('case',reference.cases(),ids=lambda row:row['key'])
def test_full_outlier_answer_against_independently_frozen_fields(case):
    assert reference.equal(case,reference.production(case),reference.expected(case))


def test_outlier_frozen_sources_inputs_and_original_failures():
    fixtures=reference.check_identity()
    assert len(fixtures['rout']['rows'])==672 and len(fixtures['rout']['original_failures'])==129
    assert len(fixtures['report']['rows'])==2880 and len(fixtures['report']['original_failures'])==1471


@pytest.mark.parametrize('setting',[
    {'q':-1},{'q':101},{'q':np.nan},{'q':np.inf},{'q':True},{'q':None},{'q':'1'},
    {'n_params':0},{'n_params':-1},{'n_params':1.5},{'n_params':True},{'n_params':None},
    {'max_fraction':0},{'max_fraction':-1},{'max_fraction':1.1},{'max_fraction':np.nan},
    {'max_fraction':np.inf},{'max_fraction':True},{'max_fraction':None},
])
@pytest.mark.parametrize('values',[[],[1,2,3,2,1,50]])
def test_outlier_settings_fail_before_any_fit(setting,values,monkeypatch):
    import PyFLASH.stats_extra as owning
    def forbidden(*args,**kwargs):raise AssertionError('Invalid request reached fitting')
    monkeypatch.setattr(owning,'_rout_robust_center_and_rsdr',forbidden)
    with pytest.raises(ValueError):rout_outlier_stats(values,**setting)


@pytest.mark.parametrize('setting',[
    {'methods':'unknown'},{'methods':['rout','unknown']},{'methods':[1]},{'methods':42},
    {'columns':'missing'},{'columns':['signal','missing']},{'columns':['signal','signal']},
    {'columns':[['signal']]},{'columns':42},{'columns':None},
    {'iqr_k':-1},{'iqr_k':np.inf},{'iqr_k':True},{'iqr_k':None},
    {'mad_threshold':-1},{'mad_threshold':np.nan},{'mad_threshold':True},
    {'rout_q':-1},{'rout_q':101},{'rout_q':True},
    {'min_rows':0},{'min_rows':1.5},{'min_rows':True},{'min_rows':None},
])
@pytest.mark.parametrize('values',[[],[1,2,3,2,1,50]])
def test_report_request_validation_is_independent_of_data_size(setting,values):
    df=pd.DataFrame({'signal':values});parameters={'columns':['signal'],**setting}
    with pytest.raises(ValueError):flag_outliers(df,**parameters)


@pytest.mark.parametrize('values',[42,[[1,2],[3,4]]])
def test_outlier_inputs_must_be_one_dimensional(values):
    with pytest.raises(ValueError):rout_outlier_stats(values)


def test_subject_and_group_identity_ambiguity_is_rejected():
    with pytest.raises(ValueError):flag_outliers(pd.DataFrame({'signal':[1,2]},index=['a','a']),['signal'])
    df=pd.DataFrame({'signal':[1,2,3,4]},index=['a','b','c','d'])
    with pytest.raises(ValueError):flag_outliers(df,['signal'],group_labels=[1,'1',1,'1'])
    with pytest.raises(ValueError):flag_outliers(df,['signal'],group_labels=['A'])
    with pytest.raises(ValueError):flag_outliers(df,['signal'],group_labels='A')
    with pytest.raises(ValueError):flag_outliers(df,['signal'],group_labels=pd.Series(['A','B'],index=['a','a']))


def test_empty_outlier_report_keeps_all_fields():
    answer=flag_outliers(pd.DataFrame({'signal':[]}),['signal'])
    assert answer.empty and len(answer.columns)==15


def test_zeroed_positive_outlier_probability_cannot_pass_absolute_tolerance():
    case=next(c for c in reference.cases() if reference.kind(c)=='rout')
    answer=reference.expected(case);changed=copy.deepcopy(answer)
    changed[1]=[1e-25 if value is not None else None for value in changed[1]]
    zeroed=copy.deepcopy(changed);zeroed[1]=[0. if value is not None else None for value in zeroed[1]]
    assert not reference.equal(case,changed,zeroed)


def test_outlier_reports_do_not_change_the_inputs():
    df=pd.DataFrame({'signal':[1,2,3,2,1,50]});original=df.copy(deep=True)
    groups=['A']*6;columns=['signal'];methods=['rout','iqr']
    flag_outliers(df,columns,group_labels=groups,methods=methods)
    pd.testing.assert_frame_equal(df,original)
    assert groups==['A']*6 and columns==['signal'] and methods==['rout','iqr']
