"""Complete declared outlier-parent obligations; passing execution is separately gated."""
import ast
import importlib
import json
from pathlib import Path

ARCHIVE=Path(__file__).with_name('reference-sources')/'outlier-requests/whole-contract-v1'
MANIFEST_SHA256='568617cfec35a7951760e923f4c4bc8b510ae1ee9535bf2ab1379ab2bba1cb25'
COMPLETE_CAPABILITIES=frozenset('PyFLASH.exclusions.'+api for api in ('mark_outliers','exclude_outliers'))


def declaration():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility.compact_evidence import digest
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
    result=json.loads((ARCHIVE/'declaration.json').read_text())
    for family in result['families']:
        module=importlib.import_module(family['module'])
        if digest(Path(module.__file__))!=family['module_sha256']:
            raise ValueError('Whole outlier obligations require a new version after component changes')
    source=Path(__file__).resolve().parents[1]/'PyFLASH/exclusions.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    actual={node.name:ast.unparse(node.args) for node in tree.body
            if isinstance(node,ast.FunctionDef) and node.name in result['public_signatures']}
    assert actual==result['public_signatures'],'Public arguments/defaults changed outside the frozen obligations'
    return result


def coverage(rows):
    d=declaration();expected={key for f in d['families'] for key in f['keys']}
    observed={};duplicates=set();unknown=set()
    for row in rows:
        key=row['contract']
        if key not in expected:unknown.add(key);continue
        if key in observed:duplicates.add(key)
        observed[key]=row
    accepted={key for key,row in observed.items() if row['status']=='agree'
              and row['frozen_reference_agrees'] in (True,'True')
              and row['missingness_equal'] in (True,'True')}
    missing=expected-set(observed);invalid=set(observed)-accepted
    return dict(passed=not(missing or invalid or duplicates or unknown),
        expected_cases=len(expected),observed_cases=len(observed),missing=sorted(missing),
        disagreements=sorted(invalid),duplicates=sorted(duplicates),undeclared=sorted(unknown),
        methods={api:bool(set(keys)<=accepted and not(duplicates or unknown)) for api,keys in d['required'].items()},
        independent_estimator_votes_added=0,whole_package_approval=False)
