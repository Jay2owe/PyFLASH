"""Selected acquired-region shared regression display range contract."""
from pathlib import Path
import ast
import json
ARCHIVE=Path(__file__).with_name('reference-sources')/'regression-region-ranges'
MANIFEST_SHA256='c9aac227c22cf418a4527bdcf0978d987183d364d7277e4a1abdbc8a40aff7a1'
ORIGINAL='regression-region-ranges-before-20261007-v2'
def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
def originals():return json.loads((ARCHIVE/ORIGINAL/'run.json').read_text(encoding='utf-8'))['rows']
def functions():
    from PyFLASH import plotting as P,from_dataframe,ConditionBuilder
    import numpy as np
    import pandas as pd
    path=ARCHIVE/ORIGINAL/'probe_regression_region_ranges_v2_20261007.py'
    names={'inputs','production','score'}
    nodes=[n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name in names]
    namespace=dict(P=P,from_dataframe=from_dataframe,ConditionBuilder=ConditionBuilder,np=np,pd=pd)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace
def check_result(original,actual):
    functions()['score'](actual)
    strip=lambda rows:[{k:v for k,v in row.items() if k not in ('xlim','ylim')} for row in rows]
    assert strip(original['actual']['records'])==strip(actual['records']),'Scientific coordinates or annotations changed.'
    case=original['case']
    if not (case['queued'] and case['share_axes']):assert original['actual']==actual
def production(original,output):
    actual=functions()['production'](original['case'],Path(output)/original['case']['key'])
    check_result(original,actual);return actual
