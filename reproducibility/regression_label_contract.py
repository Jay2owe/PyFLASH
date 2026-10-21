"""Literal queued regression axis labels with original full artists retained."""
from pathlib import Path
import ast
import json
ARCHIVE=Path(__file__).with_name('reference-sources')/'regression-queue-labels'
MANIFEST_SHA256='b56270bc2ed37d3cb85c2f2dae08cbb0b233c2224a0b90c3dd9d26a6237665f3'
ORIGINAL='regression-queue-labels-before-20261007-v1'
def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
def originals():return json.loads((ARCHIVE/ORIGINAL/'run.json').read_text(encoding='utf-8'))['rows']
def functions():
    from PyFLASH import plotting as P,from_dataframe,ConditionBuilder
    import numpy as np
    import pandas as pd
    path=ARCHIVE/ORIGINAL/'probe_regression_queue_labels_20261007.py'
    nodes=[n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name in ('inputs','production','score')]
    namespace=dict(P=P,from_dataframe=from_dataframe,ConditionBuilder=ConditionBuilder,np=np,pd=pd)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace
def check_result(original,actual):
    functions()['score'](actual)
    before=[{k:v for k,v in row.items() if k not in ('xlabel','ylabel')} for row in original['actual']['records']]
    after=[{k:v for k,v in row.items() if k not in ('xlabel','ylabel')} for row in actual['records']]
    assert before==after,'Original scientific coordinates or annotation changed.'
def production(original,output):
    actual=functions()['production'](original['case'],Path(output)/original['case']['key'])
    check_result(original,actual);return actual
