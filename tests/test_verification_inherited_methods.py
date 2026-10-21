"""A public inherited analysis must remain visible to the completion gate."""
import ast
from pathlib import Path
import pytest
from reproducibility.method_inventory import method_declarations


def declarations(source):
    return {(owner,node.name):(ast.unparse(node.args),defined_on)
            for owner,node,defined_on in method_declarations(ast.parse(source))}


def test_actual_lightweight_experiment_exposes_inherited_image_getter():
    path=Path(__file__).resolve().parents[1]/'PyFLASH/experiment.py'
    rows=declarations(path.read_text(encoding='utf-8'))
    assert rows['MiniExperiment','getImageTable']==rows['Experiment','getImageTable']
    assert rows['MiniExperiment','getImageTable'][1]=='Experiment'


def test_private_mixins_and_async_methods_are_visible_through_public_consumers():
    rows=declarations('class _Mixin:\n async def analyse(self,*,width=7):pass\nclass Public(_Mixin):pass\n')
    assert rows['Public','analyse']==('self, *, width=7','_Mixin')


def test_multiple_inheritance_uses_c3_resolution_for_diamond():
    rows=declarations('class A:\n def analyse(self,a=1):pass\nclass B(A):pass\nclass C(A):\n def analyse(self,c=2):pass\nclass D(B,C):pass\n')
    assert rows['D','analyse']==('self, c=2','C')


@pytest.mark.parametrize('replacement',['analyse = None','def analyse(self,new=3):pass','async def analyse(self,new=3):pass'])
def test_subclass_replacement_shadows_original_method(replacement):
    rows=declarations('class A:\n def analyse(self,old=1):pass\nclass B(A):\n '+replacement+'\n')
    if replacement=='analyse = None':assert ('B','analyse') not in rows
    else:assert rows['B','analyse']==('self, new=3','B')


def test_later_assignment_shadows_same_class_function():
    assert not declarations('class A:\n def analyse(self):pass\n analyse=None\n')


@pytest.mark.parametrize('source',[
    'class A(B):pass\nclass B(A):pass\n',
    'class X:pass\nclass Y:pass\nclass A(X,Y):pass\nclass B(Y,X):pass\nclass C(A,B):pass\n'])
def test_invalid_local_hierarchy_refuses_instead_of_omitting_methods(source):
    with pytest.raises(ValueError):declarations(source)


def test_unknown_external_base_does_not_invent_local_methods():
    rows=declarations('class A(External):\n def analyse(self):pass\n')
    assert rows=={('A','analyse'):('self','A')}
