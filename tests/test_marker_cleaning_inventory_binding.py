"""Every complete cleaner requires every original, option, edge and constructor case."""
import copy
from reproducibility import marker_cleaning_whole_contract as contract

def test_each_cleaner_requires_every_owning_case_without_promoting_parents():
    from reproducibility.run import _inventory_metadata,_inventory_execution_status,inventory
    from reproducibility import marker_cleaning_options_contract as options,marker_cleaning_edges_contract as edges,marker_calibration_contract as calibration
    metadata=_inventory_metadata();before=copy.deepcopy(metadata)
    assert len(metadata['rows'])==292
    from reproducibility import dataframe_whole_contract as dataframe
    constructor_contracts={'PyFLASH.dataframe.from_dataframe','PyFLASH.dataframe.coerce_dataframe_input'}
    assert dataframe.COMPLETE_CAPABILITIES==constructor_contracts
    assert all(metadata['required'].get(name) for name in constructor_contracts)
    # Qualified constructor and region-label contracts extend the historical
    # 212 declarations; this count is not a fresh global execution verdict.
    from reproducibility import region_assignment_contract as region_assignment
    assert len(region_assignment.COMPLETE_CAPABILITIES)==2
    assert sum(bool(metadata['required'].get(row['capability'])) for row in metadata['rows'])==212+len(constructor_contracts)+len(region_assignment.COMPLETE_CAPABILITIES)
    assert contract.COMPLETE_CAPABILITIES==contract.CAPABILITIES
    owner_counts={owner:len(contract.required_keys('PyFLASH.markers.'+owner+'.clean_df')) for owner in ('Antibody','cellMarker','objectMarker')}
    assert owner_counts=={'Antibody':44,'cellMarker':664,'objectMarker':2008}
    keys=set().union(*(contract.required_keys(owner) for owner in contract.CAPABILITIES));assert len(keys)==2716
    public={row['capability']:row for row in inventory(keys)}
    selected=dict(rows=[row for row in metadata['rows'] if row['capability'] in contract.CAPABILITIES],prefixes=metadata['prefixes'],required=metadata['required'])
    for owner in contract.CAPABILITIES:
        assert set(metadata['required'][owner])==contract.required_keys(owner)
        assert public[owner]['status']=='validated-complete-contract'
        for key in sorted(contract.required_keys(owner)):
            partial={row['capability']:row for row in _inventory_execution_status(selected,keys-{key})}
            assert partial[owner]['status']!='validated-complete-contract'
    for parent in ('PyFLASH.experiment.Experiment.importCSVs','PyFLASH.experiment.Experiment.processData','PyFLASH.experiment.MiniExperiment.processData','PyFLASH.batch.Batch.processData'):
        assert public[parent]['status']!='validated-complete-contract'
    for owner in contract.CAPABILITIES:
        base={row['key'] for row in contract.cases() if row['case']['owner']==owner.split('.')[-2]}
        native={row['key'] for row in calibration.cases() if row['mode']=={'cellMarker':'cell','objectMarker':'object'}.get(owner.split('.')[-2])}
        assert contract.required_keys(owner)==base|options.required_keys(owner)|edges.required_keys(owner)|native
    assert metadata==before
