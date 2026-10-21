"""The real scientific inventory requires every constructor functional domain."""
import pytest
from reproducibility import dataframe_whole_contract as reference
from reproducibility import run


@pytest.fixture(scope='module')
def metadata():
    return run._build_inventory()


def status(metadata,api,executed):
    name='PyFLASH.dataframe.'+api
    rows=run._inventory_execution_status(metadata,executed)
    return next(row for row in rows if row['capability']==name)


@pytest.mark.parametrize('api',['from_dataframe','coerce_dataframe_input'])
def test_only_the_whole_declared_constructor_can_pass(metadata,api):
    capability='PyFLASH.dataframe.'+api
    keys=reference.required_keys(capability)
    assert keys==set(metadata['required'][capability])
    row=status(metadata,api,keys)
    assert row['status']=='validated-complete-contract'
    assert row['kind']=='functional-whole-dataframe-input-adaptation'


@pytest.mark.parametrize('api',['from_dataframe','coerce_dataframe_input'])
@pytest.mark.parametrize('prefix',['dataframe-whole.','dataframe-identifier.',
    'dataframe-recoding.','dataframe-metadata.','dataframe-comparisons.','dataframe-lifecycle.'])
def test_one_missing_domain_result_prevents_constructor_completion(metadata,api,prefix):
    keys=reference.required_keys('PyFLASH.dataframe.'+api)
    removed=next(key for key in sorted(keys) if key.startswith(prefix))
    assert status(metadata,api,keys-{removed})['status']!='validated-complete-contract'


def test_constructor_helpers_do_not_promote_fitted_or_plotted_parents(metadata):
    keys=set().union(*(reference.required_keys(name) for name in reference.COMPLETE_CAPABILITIES))
    rows=run._inventory_execution_status(metadata,keys)
    for row in rows:
        if row['kind'] in ('registered-plot-or-pipeline','unregistered-public-plot') or row['capability'].startswith(('PyFLASH.pipeline.','PyFLASH.modelling.')):
            assert row['status']!='validated-complete-contract',row['capability']
