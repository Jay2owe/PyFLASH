"""Complete status requires every actual filename-indexing obligation."""
import copy
from reproducibility import image_import_whole_contract as contract

def test_each_actual_import_requires_every_whole_call_obligation():
    from reproducibility.run import _inventory_metadata, _inventory_execution_status
    metadata=_inventory_metadata();before=copy.deepcopy(metadata)
    assert contract.COMPLETE_CAPABILITIES==contract.CAPABILITIES
    keys=set().union(*(contract.required_keys(owner) for owner in contract.CAPABILITIES))
    assert len(keys)==330
    rows={row['capability']:row for row in _inventory_execution_status(metadata,keys)}
    for owner in contract.CAPABILITIES:
        assert rows[owner]['status']=='validated-complete-contract'
        for key in sorted(contract.required_keys(owner)):
            partial={row['capability']:row for row in _inventory_execution_status(metadata,keys-{key})}
            assert partial[owner]['status']!='validated-complete-contract'
    for owner in ('PyFLASH.experiment.Experiment.processData','PyFLASH.experiment.MiniExperiment.processData','PyFLASH.batch.Batch.processData'):
        assert rows[owner]['status']!='validated-complete-contract'
    assert metadata==before
