"""Artifact path and mandatory registry boundaries must fail closed."""
from pathlib import PurePosixPath
import json
import pytest
from scripts import check_distribution_consumers as M

@pytest.mark.parametrize('name',['../escape','/absolute','C:/drive','top/a\\b','top/../../e','top/name:stream'])
def test_escaping_artifact_members_refuse(name):
    with pytest.raises(ValueError,match='escapes'):
        M.safe_name(name)

@pytest.mark.parametrize('name',['file.py','p/file.py','p/refs/carrier.json'])
def test_regular_posix_artifact_members_keep_exact_names(name):
    assert M.safe_name(name)==PurePosixPath(name)

@pytest.fixture
def contract(tmp_path):
    tests=tmp_path/'tests';tests.mkdir();(tests/'cases.py').write_text('original test source',encoding='utf-8')
    rows=[dict(id=name,kind='pytest',argv=['{python}','-m','pytest','tests/cases.py','-q'],
               min_passed=80+i,timeout_seconds=180) for i,name in enumerate(M.CHECK_IDS)]
    return tmp_path,dict(checks=rows)

def write_contract(contract):
    root,data=contract
    (root/'architecture.yaml').write_text(json.dumps(data),encoding='utf-8')
    return root

def test_selection_reads_the_existing_declared_registry(contract):
    root,data=contract
    actual=M.declared_checks(write_contract(contract))
    assert actual==[dict(id=row['id'],tests=['tests/cases.py'],min_passed=row['min_passed'],timeout=row['timeout_seconds']) for row in data['checks']]

@pytest.mark.parametrize('change',['missing-id','different-kind','no-tests','zero-required','missing-file'])
def test_required_package_contract_cannot_silently_disappear(contract,change):
    root,data=contract
    row=data['checks'][0]
    if change=='missing-id':data['checks'].pop(0)
    elif change=='different-kind':row['kind']='command'
    elif change=='no-tests':row['argv']=['{python}','-m','pytest','-q']
    elif change=='zero-required':row['min_passed']=0
    elif change=='missing-file':(root/'tests/cases.py').unlink()
    with pytest.raises((ValueError,KeyError,FileNotFoundError)):
        M.declared_checks(write_contract(contract))
