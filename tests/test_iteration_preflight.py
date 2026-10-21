"""Invalid nested plans must fail before invoking any user's callback."""
from types import SimpleNamespace
import pandas as pd
import pytest
from PyFLASH.iteration import run


@pytest.mark.parametrize('kwargs',[
    {'over':['conditions','unknown']},
    {'over':['conditions',None]},
    {'over':['conditions','columns']},
    {'over':['conditions','columns'],'columns':'Value'},
    {'over':['conditions','factors']},
    {'over':['conditions','factors'],'factor':'missing'},
    {'over':['conditions'],'setup':False},
    {'over':['conditions'],'teardown':False},
    {'over':['conditions'],'action':None},
    {'over':['conditions','regions']},
    {'over':None},
    {'over':['conditions','columns'],'columns':['Value'],'column_labels':['one','two']},
])
def test_invalid_plan_never_starts_hooks_or_mutates_summary(kwargs):
    frame = pd.DataFrame({'Value':[1.,2.],'Sex':['female','male']})
    target = SimpleNamespace(summary=frame,condition_list=[SimpleNamespace(name='female')])
    before = frame.copy(deep=True)
    events = []
    arguments = {'action':lambda *_: events.append('action'),
                 'setup':lambda *_: events.append('setup'),
                 'teardown':lambda *_: events.append('teardown'),
                 'specificity':('Sex','female'),**kwargs}
    with pytest.raises((ValueError,TypeError)):
        run(target,**arguments)
    assert events == []
    assert target.summary is frame
    pd.testing.assert_frame_equal(frame,before)
