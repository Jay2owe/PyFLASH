"""Select the actual class in an authenticated observation, retaining all checks."""
from functools import lru_cache
import ast
from pathlib import Path

@lru_cache(maxsize=2)
def _native_observer(owner):
    from PyFLASH import markers
    from reproducibility import roi_analysis_reference as reference
    tree=ast.parse(Path(reference.__file__).read_text(encoding='utf-8'))
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='observation')
    class SelectActualClass(ast.NodeTransformer):
        count=0
        def visit_Attribute(self,node):
            if isinstance(node.value,ast.Name) and node.value.id=='markers' and node.attr=='Antibody':
                self.count+=1
                return ast.copy_location(ast.Name(id='actual_marker_class',ctx=ast.Load()),node)
            return self.generic_visit(node)
    selection=SelectActualClass();function=selection.visit(function)
    assert selection.count==1, 'Original observation constructor changed.'
    module=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]))
    scope=dict(vars(reference),actual_marker_class=getattr(markers,owner))
    exec(compile(module,str(reference.__file__)+' [actual inherited class]', 'exec'),scope)
    return scope['observation']

def native_observation(owner,item,expected):
    assert owner in ('objectMarker','cellMarker')
    return _native_observer(owner)(item,expected)
