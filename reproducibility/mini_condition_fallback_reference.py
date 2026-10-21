"""Exercise the actual flat-experiment fallback with unchanged native answers.

This covers the superclass route only. Explicit factor-column propagation,
conflicts and empty tables retain separate obligations; no whole declaration.
"""
import ast,copy,contextlib,io
from functools import lru_cache
from pathlib import Path
from reproducibility import whole_condition_contract as original,whole_condition_reference as reference

def cases():
    return [dict(key='mini-condition-fallback.'+item['key'],case=copy.deepcopy(item['case']),expected=copy.deepcopy(item['expected'])) for item in original.cases()]

@lru_cache(maxsize=1)
def _caller():
    source=Path(reference.__file__).read_text(encoding='utf-8');tree=ast.parse(source)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='production')
    body=ast.get_source_segment(source,node);old='from PyFLASH.experiment import Experiment';assert body.count(old)==1
    body=body.replace(old,'from PyFLASH.experiment import MiniExperiment as Experiment')
    scope=dict(vars(reference));exec(compile(body,'<actual-flat-experiment-native-fallback>','exec'),scope)
    return scope['production']

def production(item,observation=None):
    from PyFLASH.experiment import MiniExperiment
    row=next(row for row in original.read('original/before.json')['rows'] if row['case']==item['case'])
    assert item['expected']=={key:row[key] for key in ('expected','raw_expected','images_expected')}
    method=MiniExperiment.set_condition_list
    calls=[]
    def observe(self,conditions):
        nested=self.imagesDict;before=copy.deepcopy(nested);result=method(self,conditions)
        assert self.imagesDict is nested and nested==before;calls.append(type(self).__name__);return result
    MiniExperiment.set_condition_list=observe
    try:
        with contextlib.redirect_stdout(io.StringIO()):result=_caller()(item['case'],reference.values(row['native']))
    finally:MiniExperiment.set_condition_list=method
    assert calls==['MiniExperiment'] and result['passed'],result.get('error')
    actual={name:result[name] for name in ('summaries','raw','images')}
    expected=dict(summaries={roi:row['expected'] for roi in ('SCN','OC')[:item['case']['rois']]},raw={str(i):row['raw_expected'] for i in range(3)},images=row['images_expected'])
    assert actual==expected
    if observation is not None:observation.update(actual=actual,expected=expected)
    return actual
