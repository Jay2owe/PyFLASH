"""Actual Experiment fallback compatibility on original native scientific curves."""
from pathlib import Path
import ast
import json
ARCHIVE=Path(__file__).with_name('reference-sources')/'marker-legacy-regions'
ORIGINAL='marker-legacy-regions-before-20261007-v2'
MANIFEST_SHA256='7978ab18e0b90d384bb7ed5f0eb290dbbec460dfc3150d5a6a31b32eafda5bd8'
CACHE_CARRIER_SHA256='85f114c68b04e6268bf7c06593b226c17ef61337f10799b7a9ba8c60f6f69fa5'


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import marker_region_contract
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256,cache_carrier_sha256=CACHE_CARRIER_SHA256)
    marker_region_contract.check_identity()


def originals():
    return json.loads((ARCHIVE/ORIGINAL/'frozen-before.json').read_text(encoding='utf-8'))['rows']


def functions():
    from types import SimpleNamespace
    import numpy as np
    import pandas as pd
    from PyFLASH import from_dataframe,ConditionBuilder,plotting as P
    from PyFLASH.experiment import Experiment
    from reproducibility import marker_region_contract
    namespace=dict(np=np,pd=pd,from_dataframe=from_dataframe,ConditionBuilder=ConditionBuilder,
        SimpleNamespace=SimpleNamespace,Experiment=Experiment,P=P,
        native_rows=marker_region_contract.native_rows(),
        objects=json.loads((ARCHIVE/ORIGINAL/'original-objects.json').read_text(encoding='utf-8')))
    producer=ARCHIVE/ORIGINAL/'original-input-producer.py'
    nodes=[n for n in ast.parse(producer.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name in ('encode','score')]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(producer),'exec'),namespace)
    path=ARCHIVE/ORIGINAL/'adapted-producer.py'
    exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),namespace)
    return namespace


def production(original,output):
    actual=functions()['production'](original['case'],Path(output)/original['case']['key'])
    functions()['score'](original['case'],actual)
    assert actual==original['original']['actual'], 'Supported original legacy output changed.'
    return actual
