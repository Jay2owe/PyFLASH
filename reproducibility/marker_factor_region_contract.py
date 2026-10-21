"""Factor-only acquired-region requests on original complete native curves."""
from pathlib import Path
import ast
import inspect
import json
ARCHIVE=Path(__file__).with_name('reference-sources')/'marker-factor-only-regions'
MANIFEST_SHA256='f1b80654a0e6e915ec94817b052bb4d30827cd81b2feb9ff1e9654b39c1e774a'
ORIGINAL='factor-only-multi-region-before-20261007-v4'
CAPABILITY_PREFIXES={'ecdf':('ecdf-factor-regions.',)}
COMPLETE_CAPABILITIES=frozenset()

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import marker_region_contract
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
    marker_region_contract.check_identity()

def cases():
    rows=json.loads((ARCHIVE/ORIGINAL/'run.json').read_text(encoding='utf-8'))['rows']
    return [dict(key='ecdf-factor-regions.'+row['item']['case']['key'],case=row['item']['case']) for row in rows]

def functions():
    from reproducibility import marker_region_contract as M
    from PyFLASH.experiment import Experiment,extract_region_base
    import pandas as pd
    functions=M.functions()
    namespace=dict(functions=functions,factory=functions['from_dataframe'],pd=pd,
                   Experiment=Experiment,extract_region_base=extract_region_base)
    path=ARCHIVE/ORIGINAL/'freeze_factor_only_multi_region_v4_20261007.py'
    node=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='factor_only_legacy')
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    functions['from_dataframe']=namespace['factor_only_legacy']
    production=inspect.getsource(functions['production'])
    assert production.count('marker = experiment.summary.copy(deep=True)')==1
    production=production.replace('marker = experiment.summary.copy(deep=True)','marker = pd.DataFrame(objects).copy(deep=True)')
    exec(compile(production,str(path),'exec'),functions)
    return functions

def production(item,output):
    from reproducibility import marker_region_contract as M
    actual=functions()['production'](item['case'],Path(output)/item['key'])
    M.check_result(item,actual)
    return actual

def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility import marker_region_contract as M
    from reproducibility.normality_association_validation import comparison
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    check_identity();M.check_native_references(output/'native-r')
    rows=[];paired=[]
    for item in cases():
        try:
            actual=production(item,output);agree=True
        except Exception as exc:
            actual=dict(error_type=type(exc).__name__,error=str(exc));agree=False
        scope='Factor-only real Experiment with acquired region metadata; full R scientific curves, original SciPy knots and group/count/ownership fields. Other whole-plot options remain open.'
        rows.append(comparison(item['key'],'Native R stats.ecdf/rank + frozen native SciPy stats.ecdf + original SQL membership',
                               'factor-only-acquired-region-scientific-and-functional',actual,item,agree,True,scope,1e-12,0))
        paired.append(dict(item=item,actual=actual,agree=agree))
    write_json(output/'factor-only-region-paired.json',dict(rows=paired,scope='This selected branch only; no whole-plot or parent completion claim.'))
    return rows
