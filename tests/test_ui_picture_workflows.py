"""Picture homes, exact owner arguments and editable/running/result boundaries."""
from dataclasses import replace

import pytest

from PyFLASH.ui import function_contracts as fc, function_editor as editor, function_workbench as fw, function_workflows as flow


def test_live_registry_has_unique_picture_homes_and_explicit_required_roles():
    from PyFLASH.spec import PLOT_REGISTRY
    assert not flow.validate_map()
    assert {a for h in flow.HOMES for a in h.actions} == set(PLOT_REGISTRY)
    for c in fc.catalogue_contracts():
        assert set(flow.argument_locations(c)) == {f.name for f in c.fields}
    original=fc.catalogue_contracts()[0]
    unknown=replace(original,entry=replace(original.entry,action='new_unclassified_action'))
    assert flow.validate_map((*fc.catalogue_contracts(),unknown))


def test_picture_markup_routes_all_variants_and_excludes_supporting_helpers():
    import json
    from html import unescape
    import re
    from PyFLASH.ui.function_cards import picture_markup
    markup=picture_markup(fc.catalogue_contracts())
    variants=[v for encoded in re.findall('data-variants="([^"]*)"',markup) for v in json.loads(unescape(encoded))]
    assert {v['key'] for v in variants} == {c.entry.key for c in fc.catalogue_contracts()}
    assert len(variants)==len({v['key'] for v in variants})
    assert 'export_all_excel' not in markup and 'set_pyflash_style' not in markup
    assert '<svg' in markup and 'data-home="distributions"' in markup


def test_presentation_preserves_owner_defaults_and_different_alpha_meanings():
    histogram=fc.find('histograms')
    pipeline=fc.find('group_comparison_pipeline')
    for contract in (histogram,pipeline,fc.find('regressions')):
        for f in contract.fields:
            assert flow.field(contract,f).parameter is f.parameter
    opacity=next(f for f in histogram.fields if f.name=='alpha')
    significance=next(f for f in pipeline.fields if f.name=='alpha')
    assert flow.field(histogram,opacity).label=='Opacity'
    assert flow.is_appearance(histogram,opacity)
    assert flow.field(pipeline,significance).label=='Significance threshold'
    assert not flow.is_appearance(pipeline,significance)


def test_widget_roundtrip_preserves_none_empty_omission_and_tuple_defaults():
    f=next(f for f in fc.find('mean_bars').fields if f.name=='data_cols')
    untouched={}
    editor.remember_value(untouched,f,[])
    assert untouched=={}
    for saved in (None,[], ''):
        values={'data_cols':saved}
        editor.remember_value(values,f,[])
        assert values=={'data_cols':saved}
    values={'data_cols':['Signal']}
    editor.remember_value(values,f,[])
    assert values=={'data_cols':[]}
    effect=next(f for f in fc.find('power_curve').fields if f.name=='effect_sizes')
    values={}
    editor.remember_value(values,effect,list(fc.default_value(effect.parameter)))
    assert values=={}


def test_result_comparison_ignores_worker_region_binding_but_detects_scope_and_style():
    contract=fc.find('mean_bars')
    result={'parameters':{'data_cols':['Signal'],'roi':'SCN','save':True},'style':{}}
    assert not editor.result_changed(contract,{'data_cols':['Signal']},{},result,'SCN')
    assert editor.result_changed(contract,{'data_cols':['Volume']},{},result,'SCN')
    assert editor.result_changed(contract,{'data_cols':['Signal']},{},result,'Other')
    assert editor.result_changed(contract,{'data_cols':['Signal']},{'point_size':12},result,'SCN')


@pytest.fixture
def gui(monkeypatch,tmp_path):
    import pandas as pd
    from PyFLASH import from_dataframe
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import function_cards, jobs, job_status
    table=pd.DataFrame({'AnimalName':['a','b','c','d','e','f'],'Condition':['Control']*3+['Treated']*3,
                        'Signal':[1.,2.,3.,4.,5.,6.],'Volume':[3.,4.,5.,7.,9.,10.]})
    batch=from_dataframe(table,group_col='Condition',subject_col='AnimalName',file_path=str(tmp_path),source_paths=[])
    monkeypatch.setattr(function_cards,'render',lambda *a,**k:None)
    monkeypatch.setattr(jobs,'latest_job',lambda:None)
    calls=[]
    monkeypatch.setattr(job_status,'submit',lambda *a,**k:calls.append(a))
    app=AppTest.from_file('PyFLASH/ui/pages/9_functions.py',default_timeout=30)
    app.session_state['batch']=batch
    app.session_state['ui_function_selection']='action:mean_bars'
    app.run()
    assert not app.exception
    return app,calls


def test_variants_change_in_place_and_restore_each_draft(gui):
    app,calls=gui
    bars=fc.find('mean_bars')
    app.multiselect(key=fw._key(bars.entry,'data_cols')).set_value(['Signal']).run()
    app.selectbox(key='ui_workflow_variant_bars').set_value('superplot').run()
    assert app.session_state['ui_function_selection']=='action:superplot'
    app.selectbox(key='ui_workflow_variant_bars').set_value('mean_bars').run()
    assert app.multiselect(key=fw._key(bars.entry,'data_cols')).value==['Signal']
    assert not calls and not app.exception


def test_group_scope_survives_advanced_render_and_submission(gui):
    app,calls=gui
    bars=fc.find('mean_bars')
    app.multiselect(key=fw._key(bars.entry,'data_cols')).set_value(['Signal'])
    app.multiselect(key=fw._key(bars.entry,'selected_groups')).set_value(['Control']).run()
    app.button(key=fw._key(bars.entry,'run')).click().run()
    assert calls[-1][1]['kwargs']=={'data_cols':['Signal'],'filter_by':{'Condition':['Control']}}
    app.multiselect(key=fw._key(bars.entry,'advanced_fields')).set_value(['variance_alpha']).run()
    app.number_input(key=fw._key(bars.entry,'variance_alpha')).set_value(.1).run()
    assert app.session_state['ui_function_drafts'][bars.entry.key]['values']['variance_alpha']==.1
    app.multiselect(key=fw._key(bars.entry,'advanced_fields')).set_value([]).run()
    assert 'variance_alpha' not in app.session_state['ui_function_drafts'][bars.entry.key]['values']
    assert app.session_state['ui_function_drafts'][bars.entry.key]['values']['filter_by']=={'Condition':['Control']}


def test_pipeline_outputs_are_real_arguments_and_fdr_requires_screen(gui):
    app,calls=gui
    app.session_state['ui_function_selection']='action:group_comparison_pipeline'
    app.run()
    contract=fc.find('group_comparison_pipeline')
    app.multiselect(key=fw._key(contract.entry,'data_cols')).set_value(['Signal'])
    app.checkbox(key=fw._key(contract.entry,'plot_bars')).set_value(False).run()
    app.button(key=fw._key(contract.entry,'run')).click().run()
    assert calls[-1][1]['kwargs']=={'data_cols':['Signal'],'plot_bars':False}
    app.selectbox(key=fw._key(contract.entry,'gate')).set_value('fdr').run()
    assert app.button(key=fw._key(contract.entry,'run')).disabled
    app.checkbox(key=fw._key(contract.entry,'screen')).set_value(True).run()
    assert not app.button(key=fw._key(contract.entry,'run')).disabled
    assert not app.exception


def test_background_run_blocks_only_submission_and_saved_result_is_preserved(gui,monkeypatch):
    app,calls=gui
    from PyFLASH.ui import jobs
    contract=fc.find('mean_bars')
    result={'parameters':{'data_cols':['Signal']},'style':{},'value':{'verified':1}}
    app.session_state[fw._key(contract.entry,'result')]=result
    monkeypatch.setattr(jobs,'latest_job',lambda:{'status':'running'})
    app.multiselect(key=fw._key(contract.entry,'data_cols')).set_value(['Volume']).run()
    assert app.button(key=fw._key(contract.entry,'run')).disabled
    assert app.session_state[fw._key(contract.entry,'result')]==result
    assert any('Inputs changed' in c.value for c in app.caption)
    assert not calls and not app.exception


def test_relationship_pipeline_requires_explicit_measurement_scope(gui):
    app,calls=gui
    app.session_state['ui_function_selection']='action:adjusted_correlation_pipeline'
    app.run()
    contract=fc.find('adjusted_correlation_pipeline')
    assert app.button(key=fw._key(contract.entry,'run')).disabled
    assert any('Choose the measurements to compare' in e.value for e in app.error)
    app.multiselect(key=fw._key(contract.entry,'data_cols')).set_value(['Signal','Volume']).run()
    assert not app.button(key=fw._key(contract.entry,'run')).disabled
    assert not calls and not app.exception


@pytest.mark.parametrize('normalization',[None,False])
def test_reopening_saved_run_preserves_explicit_nulls_and_empty_overrides(gui,normalization):
    app,calls=gui
    contract=fc.find('mean_bars')
    values={'data_cols':['Signal'],'y_range':None,'normalize':normalization,'dataframe_kwargs':None,'covariates':[]}
    result={'parameters':values,'style':{},'value':{'checked':1}}
    app.session_state['ui_function_results']={'mean_bars':result}
    app.run()
    app.selectbox(key='ui_saved_workflow_run').set_value('mean_bars').run()
    app.button(key='_function_event_reopen_workflow').click().run()
    assert app.session_state['ui_function_drafts'][contract.entry.key]['values']==values
    app.button(key=fw._key(contract.entry,'run')).click().run()
    assert calls[-1][1]['kwargs']==values
    assert not app.exception


def test_saved_regression_queues_remain_queues_and_missing_measurements_are_retained(gui):
    app,calls=gui
    contract=fc.find('regressions')
    values={'x':['Signal','Volume'],'y':['Volume']}
    app.session_state['ui_function_selection']=contract.entry.key
    app.session_state['ui_function_drafts']={contract.entry.key:{'schema_version':1,'values':values,'style':{}}}
    app.run()
    assert app.multiselect(key=fw._key(contract.entry,'x')).value==values['x']
    app.button(key=fw._key(contract.entry,'run')).click().run()
    assert calls[-1][1]['kwargs']==values
    batch=app.session_state['batch']
    app=type(app).from_file('PyFLASH/ui/pages/9_functions.py',default_timeout=30)
    app.session_state['batch']=batch
    app.session_state['ui_function_selection']=contract.entry.key
    app.session_state['ui_function_drafts']={contract.entry.key:{'schema_version':1,'values':{'x':['Missing measurement'],'y':['Volume']},'style':{}}}
    app.run()
    assert app.session_state['ui_function_drafts'][contract.entry.key]['values']['x']==['Missing measurement']
    assert app.button(key=fw._key(contract.entry,'run')).disabled
    assert not app.exception
