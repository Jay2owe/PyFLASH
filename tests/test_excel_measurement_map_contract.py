"""All accepted display patterns retain descriptions and canonical Unicode units."""
from copy import deepcopy
import hashlib
import json
import shutil
import pytest
from reproducibility import excel_measurement_map_contract as reference

@pytest.mark.parametrize('row', reference.cases(), ids=lambda row: row['key'])
def test_all_declared_measurement_labels_have_exact_units_and_descriptions(row):
    assert reference.observe(row) == dict(label=row['expected_label'], description=row['expected_description'])

def test_every_public_measurement_pattern_is_in_the_frozen_inventory():
    inventory = reference.check_mapping_inventory()
    assert sum(map(len, inventory.values())) == 96
    assert not reference.COMPLETE_CAPABILITIES


@pytest.mark.parametrize('method, mappings', [
    ('export_excel', {'IF_NAME_MAP', 'RAW_NAME_MAP', 'BEHAVIOR_NAME_MAP'}),
    ('export_all_excel', {'IF_NAME_MAP', 'RAW_NAME_MAP', 'BEHAVIOR_NAME_MAP'}),
    ('export_IF_summary_excel', {'IF_NAME_MAP'}),
    ('export_unregistered_summary_excel', {'IF_NAME_MAP'}),
    ('export_extra_summary_excel', {'IF_NAME_MAP'}),
    ('export_extended_data_excel', {'RAW_NAME_MAP'}),
    ('export_behavior_summary_excel', {'BEHAVIOR_NAME_MAP'}),
])
def test_exporter_display_obligations_include_exactly_their_declared_maps(method, mappings):
    capability = 'PyFLASH.batch.Batch.' + method
    expected = {row['key'] for row in reference.cases() if row['mapping'] in mappings}
    assert expected
    assert reference.required_keys(capability) == expected
    assert not reference.COMPLETE_CAPABILITIES


def test_display_converter_family_is_registered_for_actual_execution():
    from reproducibility.validation_registry import FAMILIES
    assert FAMILIES['batch-excel-measurement-maps'] == 'reproducibility.excel_measurement_map_contract'

@pytest.mark.parametrize('name', ['measurement-map-reference.json','original-label-declarations.py','original-configuration.py','source-manifest.json'])
def test_changed_original_display_evidence_is_refused(name, tmp_path, monkeypatch):
    archive = tmp_path/'archive'; shutil.copytree(reference.ARCHIVE, archive)
    path = archive/name; path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference,'ARCHIVE',archive)
    with pytest.raises(ValueError,match='Original Excel measurement-map'):
        reference.check_identity()

def test_changed_expected_display_label_is_refused_before_call():
    row = deepcopy(reference.cases()[0]); row['expected_label'] = 'accepted from candidate'
    with pytest.raises(AssertionError, match='Declared measurement mapping changed'):
        reference.observe(row)

def test_new_measurement_pattern_requires_extended_frozen_cases(monkeypatch):
    from PyFLASH import export
    monkeypatch.setitem(export.IF_NAME_MAP, '<ab>_NewMeasurement', dict(label='New',desc='New'))
    with pytest.raises(ValueError,match='mapping inventory needs extended frozen cases'):
        reference.check_mapping_inventory()

def test_original_nine_unit_failures_remain_authenticated():
    archive = reference.ARCHIVE.parent/'original-probes/v1'
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest(archive/'source-manifest.json') == 'a4afbc6be54b133ee8794fdbd11963f92455b6d5e664e7fa9ba885792c207386'
    for name, expected in json.loads((archive/'source-manifest.json').read_text(encoding='utf-8')).items():
        assert digest(archive/name) == expected
    rows = json.loads((archive/'paired.json').read_text(encoding='utf-8'))['rows']
    assert len(rows) == 95 and sum(not row['agrees'] for row in rows) == 9
    assert all(row['error'] is None and row['observed'][1] == row['case']['expected_description'] for row in rows)


def test_original_coordinate_and_area_wording_failures_remain_authenticated():
    paired = reference.check_coordinate_area_original_failures()
    assert {row['case']['column'] for row in paired['display_controls']} == {
        'IBA1_RawXMMean', 'IBA1_RawYMMean', 'IBA1_ROI_%Area'}
    assert paired['numerical_controls'][-1]['actual'] == {'area': 50.0, 'intden': 400.0}


@pytest.mark.parametrize('name', ['declared-reference.json', 'paired.json', 'native-imagej.json'])
def test_changed_original_coordinate_area_semantics_are_refused(name, tmp_path, monkeypatch):
    archive = tmp_path/'archive'; shutil.copytree(reference.SEMANTIC_ARCHIVE, archive)
    path = archive/name; path.write_bytes(path.read_bytes()+b' ')
    monkeypatch.setattr(reference, 'SEMANTIC_ARCHIVE', archive)
    with pytest.raises(ValueError):
        reference.check_coordinate_area_original_failures()
