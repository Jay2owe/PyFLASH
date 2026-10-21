"""Classifier selection, exact constructor compatibility and shared consumers."""
from pathlib import Path
import hashlib,json
import pytest
from reproducibility.classifier_selection_observer import observe
from PyFLASH.modelling import _classification_model_configs
from PyFLASH import _optional
from PyFLASH._classifier_registry import CLASSIFIER_FAMILIES,PRESETS

ROOT=Path(__file__).resolve().parents[1]/'reproducibility/reference-sources/classifier-selections'
FIXTURE=ROOT/'before/frozen-before.json'
CASES=json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

@pytest.mark.parametrize('case',CASES,ids=lambda row:row['key'])
def test_declared_selection_refusal_and_all_valid_constructor_fields(case,monkeypatch):
    request=case['request'];original=_optional.optional_import
    def available(module):
        if module=='mord':return object() if request['ordinal_dependency_available'] else None
        return original(module)
    monkeypatch.setattr(_optional,'optional_import',available)
    actual,full=observe(_classification_model_configs,request['preset'],request['selection'],request['ordinal_dependency_available'])
    assert actual==case['expected']
    if case['original']==case['expected'] and 'families' in case['expected']:
        assert full==case['full_original_configurations']

def test_all_original_requests_sources_and_failures_are_preserved():
    receipt=json.loads(FIXTURE.read_text(encoding='utf-8'))
    assert len(receipt['rows'])==96 and sum(c['original_failure'] for c in receipt['rows'])==24
    for name,digest in receipt['source_manifest'].items():
        assert hashlib.sha256((ROOT/'before'/name).read_bytes()).hexdigest()==digest

def test_form_options_and_feature_dependencies_read_the_same_registry():
    from PyFLASH.actions import required_dependency_groups
    from PyFLASH.ui.function_contracts import contracts
    contract=next(c for c in contracts() if c.entry.action=='iterative_model_sweep')
    fields={f.name:f for f in contract.fields}
    assert fields['model_families'].choices==tuple(CLASSIFIER_FAMILIES)
    assert fields['model_preset'].choices==PRESETS
    assert required_dependency_groups('iterative_model_sweep')==('classification',)
    assert required_dependency_groups('PyFLASH.modelling.iterative_model_sweep')==('classification',)
    assert required_dependency_groups('iterative_model_sweep',{'model_families':['ridge_multinomial_logistic']})==()
    assert required_dependency_groups('iterative_model_sweep',{'model_families':['ordinal_logistic']})==('classification',)
    assert required_dependency_groups('mean_bars')==()

def test_ordinal_dependency_has_declared_install_requirement():
    from PyFLASH.dependencies import check
    from packaging.specifiers import SpecifierSet
    entries=check('classification')
    assert any(e['package']=='mord' and SpecifierSet(e['specifier'])==SpecifierSet('>=0.7,<0.8') for e in entries)
