from types import SimpleNamespace
import pickle
import pandas as pd
import pytest
from PyFLASH import exclusions


def experiment(tmp_path):
    frames={base:pd.DataFrame({'AnimalName':['S01','S02'],'A':[1.,2.],'B':[10.,20.]}) for base in ('SCN','CTX')}
    return SimpleNamespace(summary=frames['SCN'],summaries=frames,data=object(),condition_list=[],
                           data_path=str(tmp_path),fig_path=str(tmp_path))


@pytest.mark.parametrize('operation',['mark_outliers','exclude_outliers'])
@pytest.mark.parametrize('roi',['SCN','CTX'])
def test_precomputed_outlier_ledger_retains_region(tmp_path,operation,roi):
    exp=experiment(tmp_path)
    flags=pd.DataFrame([{'AnimalName':'S02','column':'A','group':'literal','value':2.,'iqr_outlier':True}])
    clean=getattr(exclusions,operation)(exp,outliers=flags,roi=roi,methods=('iqr',),verbose=False)
    assert clean.exclusions.attrs['_pyflash_exclusion_rois']==[roi]
    if operation=='mark_outliers':
        for base in exp.summaries:pd.testing.assert_frame_equal(clean.summaries[base],exp.summaries[base])
        clean=exclusions.apply_exclusions(clean)
    assert clean.summaries[roi].loc[1,'A']=='EXCLUDED_OUTLIER:iqr'
    other='CTX' if roi=='SCN' else 'SCN'
    pd.testing.assert_frame_equal(clean.summaries[other],exp.summaries[other])


def test_pickled_stacked_ledger_keeps_each_region(tmp_path):
    exp=experiment(tmp_path)
    first=exclusions.mark_exclusions(exp,cells=[('S02','A')],roi='SCN',reason='one')
    marked=exclusions.mark_exclusions(first,cells=[('S02','B')],roi='CTX',reason='two')
    loaded=pickle.loads(pickle.dumps(marked))
    clean=exclusions.apply_exclusions(loaded)
    assert clean.summaries['SCN'].loc[1,'A']=='EXCLUDED_MANUAL:one'
    assert clean.summaries['SCN'].loc[1,'B']==20.
    assert clean.summaries['CTX'].loc[1,'A']==2.
    assert clean.summaries['CTX'].loc[1,'B']=='EXCLUDED_MANUAL:two'
    assert clean.exclusions.attrs['_pyflash_exclusion_rois']==['SCN','CTX']
    assert clean.exclusion_summary['roi']=='multiple' and clean.exclusion_summary['rois']==['CTX','SCN']
    assert marked.exclusions.attrs['_pyflash_exclusion_rois']==['SCN','CTX']


def test_exported_csv_retains_region_without_dataframe_attributes(tmp_path):
    exp=experiment(tmp_path)
    clean=exclusions.exclude_subjects(exp,'S02',roi='SCN',columns=['A'],reason='review',save=True,verbose=False)
    path=tmp_path/'Exclusions/animal_SCN.csv'
    # The writer retains the existing exclusion filename convention.
    path=next((tmp_path/'Exclusions').glob('*.csv'))
    loaded=pd.read_csv(path)
    assert loaded['roi'].tolist()==['SCN'] and loaded.attrs=={}
    exp.exclusions=loaded
    applied=exclusions.apply_exclusions(exp)
    assert applied.summaries['SCN'].loc[1,'A']=='EXCLUDED_MANUAL:review'
    assert applied.summaries['CTX'].loc[1,'A']==2.
    assert clean.exclusions.attrs['_pyflash_exclusion_rois']==['SCN']


def test_explicit_override_moves_all_stacked_requests_to_the_chosen_region(tmp_path):
    exp=experiment(tmp_path)
    marked=exclusions.mark_exclusions(exp,cells=[('S02','A')],roi='SCN')
    marked=exclusions.mark_exclusions(marked,cells=[('S02','B')],roi='CTX')
    clean=exclusions.apply_exclusions(marked,roi='SCN')
    assert clean.exclusions.attrs['_pyflash_exclusion_rois']==['SCN','SCN']
    assert clean.summaries['SCN'].loc[1,'A']=='EXCLUDED_MANUAL'
    assert clean.summaries['SCN'].loc[1,'B']=='EXCLUDED_MANUAL'
    pd.testing.assert_frame_equal(clean.summaries['CTX'],exp.summaries['CTX'])


@pytest.mark.parametrize('problem',['wrong-count','contradictory-column','unknown-region','mixed-unknown'])
def test_invalid_region_metadata_refuses_instead_of_changing_another_table(tmp_path,problem):
    exp=experiment(tmp_path)
    marked=exclusions.mark_exclusions(exp,cells=[('S02','A'),('S02','B')],roi='SCN')
    if problem=='wrong-count':marked.exclusions.attrs['_pyflash_exclusion_rois']=['SCN']
    elif problem=='contradictory-column':marked.exclusions['roi']=['CTX','CTX']
    elif problem=='unknown-region':marked.exclusions.attrs['_pyflash_exclusion_rois']=['unknown','unknown']
    else:
        marked.exclusions.attrs['_pyflash_exclusion_rois']=['SCN',None]
        del marked.exclusion_summary
    with pytest.raises(ValueError):exclusions.apply_exclusions(marked)
    for base in exp.summaries:pd.testing.assert_frame_equal(marked.summaries[base],exp.summaries[base])
    assert not list(tmp_path.rglob('*.csv'))


@pytest.mark.parametrize('operation',['apply_exclusions','mark_exclusions','exclude_subjects'])
def test_unknown_requested_region_cannot_fall_back_to_a_different_region(tmp_path,operation):
    exp=experiment(tmp_path)
    with pytest.raises(ValueError):
        if operation=='exclude_subjects':exclusions.exclude_subjects(exp,'S02',roi='missing',verbose=False)
        else:getattr(exclusions,operation)(exp,cells=[('S02','A')],roi='missing')
    assert exp.summaries['SCN'].loc[1,'A']==2. and exp.summaries['CTX'].loc[1,'A']==2.
