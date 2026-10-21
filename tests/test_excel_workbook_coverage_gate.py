"""Full original schemas and literal text controls cannot certify untested domains."""
import pytest
from reproducibility import run
from reproducibility import excel_workbook_schema_contract as schema
from reproducibility import excel_literal_cell_contract as literal
from reproducibility import excel_orchestration_contract as orchestration
from reproducibility import excel_coupled_contract as coupled
from reproducibility import excel_measurement_map_contract as measurement_maps
from reproducibility import excel_all_mapping_workbook_contract as all_mapping_workbooks
from reproducibility import excel_positive_label_semantics_contract as positive_labels
from reproducibility import excel_mean_wording_semantics_contract as mean_wording
from reproducibility import excel_distance_presentation_contract as distance_presentation
from reproducibility import excel_destination_contract as destinations
from reproducibility import excel_region_selection_contract as regions


@pytest.mark.parametrize('module', [destinations, regions], ids=['destinations', 'regions'])
def test_added_direct_controls_remain_partial_until_whole_contract_is_declared(inventory, module):
    assert not module.COMPLETE_CAPABILITIES
    for capability in module.CAPABILITY_PREFIXES:
        keys = module.required_keys(capability)
        row = next(row for row in run._inventory_execution_status(inventory, keys)
                   if row['capability'] == capability)
        assert row['status'] == 'partially-validated-contract'
        assert keys <= set(row['executed_subcontracts'].split(';'))


@pytest.fixture(scope='module')
def inventory():
    return run._build_inventory()


@pytest.mark.parametrize('capability', sorted(literal.CAPABILITY_PREFIXES))
def test_real_inventory_records_new_export_controls_without_whole_certification(inventory, capability):
    assert not schema.COMPLETE_CAPABILITIES and not literal.COMPLETE_CAPABILITIES and not coupled.COMPLETE_CAPABILITIES and not measurement_maps.COMPLETE_CAPABILITIES and not all_mapping_workbooks.COMPLETE_CAPABILITIES and not positive_labels.COMPLETE_CAPABILITIES and not mean_wording.COMPLETE_CAPABILITIES
    keys = literal.required_keys(capability) | schema.required_keys(capability) | coupled.required_keys(capability) | measurement_maps.required_keys(capability) | all_mapping_workbooks.required_keys(capability) | positive_labels.required_keys(capability) | mean_wording.required_keys(capability) | distance_presentation.required_keys(capability)
    if capability in orchestration.CAPABILITY_PREFIXES:
        keys |= orchestration.required_keys(capability)
    row = next(row for row in run._inventory_execution_status(inventory, keys)
               if row['capability'] == capability)
    assert row['status'] == 'partially-validated-contract'
    assert literal.required_keys(capability) <= set(row['executed_subcontracts'].split(';'))
    assert coupled.required_keys(capability) <= set(row['executed_subcontracts'].split(';'))
    assert measurement_maps.required_keys(capability) <= set(row['executed_subcontracts'].split(';'))
    assert all_mapping_workbooks.required_keys(capability) <= set(row['executed_subcontracts'].split(';'))
    assert positive_labels.required_keys(capability) <= set(row['executed_subcontracts'].split(';'))
    assert mean_wording.required_keys(capability) <= set(row['executed_subcontracts'].split(';'))
    assert distance_presentation.required_keys(capability) <= set(row['executed_subcontracts'].split(';'))


def test_workbook_transport_does_not_promote_any_fitted_or_plotting_parent(inventory):
    keys = {row['key'] for module in (schema, literal, orchestration, coupled, measurement_maps, all_mapping_workbooks, positive_labels, mean_wording, distance_presentation) for row in module.cases()}
    for row in run._inventory_execution_status(inventory, keys):
        if row['kind'] in ('registered-plot-or-pipeline', 'unregistered-public-plot') or row['capability'].startswith(('PyFLASH.pipeline.', 'PyFLASH.modelling.')):
            assert row['status'] != 'validated-complete-contract', row['capability']


@pytest.mark.parametrize('capability',sorted(positive_labels.CAPABILITY_PREFIXES))
def test_real_inventory_keeps_positive_label_truth_as_supporting_evidence(inventory,capability):
    keys=positive_labels.required_keys(capability)
    assert len(keys)==10
    row=next(row for row in run._inventory_execution_status(inventory,keys) if row['capability']==capability)
    assert row['status']=='partially-validated-contract'
    assert keys<=set(row['executed_subcontracts'].split(';'))


@pytest.mark.parametrize('required_passed',[False,True])
def test_required_contract_does_not_hide_executed_supporting_controls(required_passed):
    metadata=dict(rows=[dict(capability='example',status='not-fully-independently-validated')],
        prefixes={'example':('whole.','support.')},required={'example':{'whole.answer'}})
    executed={'support.label'}|({'whole.answer'} if required_passed else set())
    row=run._inventory_execution_status(metadata,executed)[0]
    assert set(row['executed_subcontracts'].split(';'))==executed
    assert row['status']==('validated-complete-contract' if required_passed else 'partially-validated-contract')


@pytest.mark.parametrize('capability',sorted(mean_wording.CAPABILITY_PREFIXES))
def test_real_inventory_attaches_mean_controls_without_whole_certification(inventory,capability):
    keys=mean_wording.required_keys(capability)
    assert len(keys)==(3 if capability.endswith('export_extended_data_excel') else 5)
    row=next(row for row in run._inventory_execution_status(inventory,keys) if row['capability']==capability)
    assert row['status']=='partially-validated-contract'
    assert keys<=set(row['executed_subcontracts'].split(';'))

@pytest.mark.parametrize('capability',sorted(distance_presentation.CAPABILITY_PREFIXES))
def test_real_inventory_attaches_distance_controls_without_whole_certification(inventory,capability):
    assert not distance_presentation.COMPLETE_CAPABILITIES
    keys=distance_presentation.required_keys(capability)
    assert keys
    row=next(row for row in run._inventory_execution_status(inventory,keys) if row['capability']==capability)
    assert row['status']=='partially-validated-contract'
    assert keys<=set(row['executed_subcontracts'].split(';'))
