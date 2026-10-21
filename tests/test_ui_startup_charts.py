"""Initial chart assets never survive input refusal or alter saved view edits."""
from pathlib import Path

import pytest


@pytest.mark.parametrize('failure',[None,'request','input'])
def test_opening_chart_request_is_always_removed(monkeypatch,failure):
    from PyFLASH.ui import loading
    calls=[]
    class Placeholder:
        def vega_lite_chart(self,spec,**kwargs):
            assert spec['data']=={'values':[]}
            calls.append('request')
            if failure=='request': raise RuntimeError('chart request refused')
        def empty(self): calls.append('cleared')
    monkeypatch.setattr(loading.st,'empty',lambda:Placeholder())
    def open_input():
        with loading.opening_charts():
            calls.append('input')
            if failure=='input': raise ValueError('input changed while opening')
    if failure:
        with pytest.raises(RuntimeError if failure=='request' else ValueError): open_input()
    else: open_input()
    assert calls==(['request','cleared'] if failure=='request' else ['request','input','cleared'])


@pytest.mark.slow
def test_closed_appearance_retains_exact_views_and_restores_controls(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    app=AppTest.from_file(str(Path('PyFLASH/ui/app.py').resolve()),default_timeout=30)
    app.session_state['ui_explore_height']=650
    app.session_state['ui_explore_point_size']=110
    app.session_state['ui_explore_font']=17
    app.session_state['ui_explore_legend']=False
    app.session_state['ui_explore_zero']=True
    app.run()
    assert not app.exception and not app.slider
    before=[c.proto.spec for c in app.get('vega_lite_chart')]
    assert len(before)==2
    app.session_state['ui_fold_explore.appearance']=True
    app.run()
    assert not app.exception
    assert app.slider(key='ui_explore_height').value==650
    assert app.slider(key='ui_explore_point_size').value==110
    assert app.slider(key='ui_explore_font').value==17
    assert [c.proto.spec for c in app.get('vega_lite_chart')]==before
    app.slider(key='ui_explore_point_size').set_value(130).run()
    changed=[c.proto.spec for c in app.get('vega_lite_chart')]
    assert changed!=before
    app.session_state['ui_fold_explore.appearance']=False
    app.run()
    assert not app.exception and not app.slider
    assert [c.proto.spec for c in app.get('vega_lite_chart')]==changed
    app.run()
    assert [c.proto.spec for c in app.get('vega_lite_chart')]==changed
    reopened=AppTest.from_file(str(Path('PyFLASH/ui/app.py').resolve()),default_timeout=30).run()
    assert not reopened.exception
    assert [c.proto.spec for c in reopened.get('vega_lite_chart')]==changed


@pytest.mark.slow
def test_refused_source_leaves_no_loading_or_measurement_chart(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from PyFLASH.ui import loading
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    def changed(*args,**kwargs): raise ValueError('source changed before admission')
    monkeypatch.setattr(loading,'open_source',changed)
    app=AppTest.from_file(str(Path('PyFLASH/ui/app.py').resolve()),default_timeout=30).run()
    assert not app.exception
    assert not app.get('vega_lite_chart')
    assert any('source changed before admission' in item.value for item in app.warning)
