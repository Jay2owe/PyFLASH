"""Literal display controls and original scientific-artist preservation."""
from pathlib import Path
import ast
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'distribution-labels'
MANIFEST_SHA256 = '14d957ac0cb1d47c2a5908b659131e551a37c7dbd73774d170aa0cf0ae3346fb'
CACHE_CARRIER_SHA256 = '70a98cb4c2931691a056786da400de244b3147f94736b6a5cedfc49e9b33e8e5'
ORIGINAL = 'distribution-queue-labels-before-20261007-v3'


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256,
                    cache_carrier_sha256=CACHE_CARRIER_SHA256)


def originals():
    return json.loads((ARCHIVE / ORIGINAL / 'frozen-before.json').read_text(encoding='utf-8'))['rows']


def functions():
    from types import SimpleNamespace
    import numpy as np
    import pandas as pd
    from PyFLASH import from_dataframe, ConditionBuilder, plotting as P
    namespace = dict(P=P, np=np, pd=pd, from_dataframe=from_dataframe,
                     ConditionBuilder=ConditionBuilder, SimpleNamespace=SimpleNamespace)
    original = ARCHIVE / ORIGINAL / 'freeze_distribution_queue_labels_v3_20261007.py'
    tree = ast.parse(original.read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('score', 'scalar_json')]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(original), 'exec'), namespace)
    path = ARCHIVE / ORIGINAL / 'adapted-producer.py'
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), namespace)
    return namespace


def check_result(original, actual):
    functions()['score'](original['case'], actual)
    fields = ('condition', 'factor_value', 'finished', 'lines', 'patches')
    before = [{k: row[k] for k in fields} for row in original['actual']['records']]
    after = [{k: row[k] for k in fields} for row in actual['records']]
    assert before == after, 'Original scientific artists or groups changed.'


def production(original, output):
    actual = functions()['production'](original['case'], Path(output) / original['case']['key'])
    check_result(original, actual)
    return actual
