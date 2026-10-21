"""Complete literal image geometry/pixels and environmental helper contracts."""
import json,hashlib
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from PyFLASH import image_io
from reproducibility import image_io_contract as reference

@pytest.mark.parametrize('case',reference.cases(),ids=lambda r:r['key'])
def test_declared_image_contract_against_independently_frozen_answers(case):
    expected=reference.expected(case);actual=reference.production(case)
    assert actual==expected
    assert not image_io._READ_OBSERVERS

def test_image_reference_identity_and_preserved_failures():
    fixture=reference.check_identity();previous=reference.FIXTURE.with_name('image_io_reference_v3.json')
    assert hashlib.sha256(previous.read_bytes()).hexdigest()==fixture['previous_fixture_sha256']
    third=json.loads(previous.read_text(encoding='utf-8'))
    assert fixture['rows'][:len(third['rows'])]==third['rows']
    assert all(fixture['input_manifest'][name]==sha for name,sha in third['input_manifest'].items())
    fixture=third;previous=reference.FIXTURE.with_name('image_io_reference_v2.json')
    assert hashlib.sha256(previous.read_bytes()).hexdigest()==fixture['previous_fixture_sha256']
    original=json.loads(previous.read_text(encoding='utf-8'))
    preserved=json.loads(json.dumps(fixture['rows'][:len(original['rows'])]))
    for row in preserved:
        if 'previous_key' in row:
            row['key']=row.pop('previous_key');row['case']['key']=row['key']
    assert preserved==original['rows']
    assert all(fixture['input_manifest'][name]==sha for name,sha in original['input_manifest'].items())
    first=reference.FIXTURE.with_name('image_io_reference.json')
    assert hashlib.sha256(first.read_bytes()).hexdigest()==original['previous_fixture_sha256']
    assert json.loads(first.read_text(encoding='utf-8'))['rows']==original['rows']
    assert len(fixture['rows'])==2564 and len(fixture['input_manifest'])==112
    assert sum(len(r['original_failures']) for r in fixture['original_reference_receipts'].values())==927
    latest=reference.check_identity()
    assert len(latest['rows'])==2772 and len(latest['input_manifest'])==152
    assert sum(len(r['original_failures']) for r in latest['original_reference_receipts'].values())==1012


def test_floating_colour_header_reads_metadata_without_loading_pixels(monkeypatch):
    import tifffile
    case=next(r for r in reference.cases() if r['kind']=='header')
    def forbidden(*args,**kwargs):raise AssertionError('header decoded pixel samples')
    monkeypatch.setattr(tifffile.TiffPage,'asarray',forbidden)
    actual=reference.production(case)
    assert actual==reference.expected(case)


def test_image_coverage_requires_every_declared_case():
    from reproducibility.run import inventory
    keys=[case['key'] for case in reference.cases()]
    complete={r['capability']:r for r in inventory(keys) if r['capability'].startswith('PyFLASH.image_io.')}
    assert len(complete)==7
    assert all(r['status']=='validated-complete-contract' for r in complete.values())
    partial={r['capability']:r for r in inventory([keys[0]]) if r['capability'].startswith('PyFLASH.image_io.')}
    assert all(r['status']!='validated-complete-contract' for r in partial.values())

@pytest.mark.parametrize('options',[{'backend':'unknown'},{'preview_max_dim':'bad'},{'preview_max_dim':float('nan')}])
def test_invalid_settings_cannot_record_unread_file_as_an_input(options,tmp_path):
    path=tmp_path/'not-read.png';events=[]
    with image_io.observe_image_reads(events.append):
        with pytest.raises(ValueError):image_io.read_image_array(path,**options)
    assert events==[] and not image_io._READ_OBSERVERS

def test_missing_image_keeps_attempted_input_and_original_failure_cause(tmp_path):
    path=tmp_path/'missing.png';events=[]
    with image_io.observe_image_reads(events.append):
        with pytest.raises(RuntimeError) as error:image_io.read_image_array(path,backend='pil')
    assert isinstance(error.value.__cause__,FileNotFoundError)
    assert events==[str(path)] and not image_io._READ_OBSERVERS

def test_nested_observers_receive_each_input_and_cleanup_after_failure(tmp_path):
    path=tmp_path/'literal.png';Image.fromarray(np.full((4,5),17,dtype=np.uint8)).save(path)
    first=[];second=[]
    with image_io.observe_image_reads(first.append):
        image_io.get_image_shape(path)
        with image_io.observe_image_reads(second.append):
            image_io.read_image_array(path,backend='pil')
            with pytest.raises(RuntimeError):image_io.read_image_array(tmp_path/'missing.png',backend='pil')
        image_io.get_image_shape(path)
    assert first==[str(path),str(path),str(tmp_path/'missing.png'),str(path)]
    assert second==[str(path),str(tmp_path/'missing.png')]
    assert not image_io._READ_OBSERVERS

def test_input_observer_failure_propagates_and_cleanup_is_guaranteed(tmp_path):
    def failed(path):raise LookupError('receipt could not be recorded')
    with pytest.raises(LookupError,match='receipt'):
        with image_io.observe_image_reads(failed):image_io.read_image_array(tmp_path/'pixels.png',backend='pil')
    assert not image_io._READ_OBSERVERS

def test_header_rechecks_replaced_input_instead_of_reusing_old_path(tmp_path):
    path=tmp_path/'pixels.png';Image.fromarray(np.zeros((4,5),dtype=np.uint8)).save(path)
    assert image_io.get_image_shape(path)==(4,5)
    Image.fromarray(np.zeros((1,7),dtype=np.uint8)).save(path)
    assert image_io.get_image_shape(path)==(1,7)

def test_reference_answers_are_caller_owned():
    case=next(r for r in reference.cases() if r['kind']=='pixels')
    original=reference.expected(case);changed=reference.expected(case);changed['pixels'].clear()
    assert reference.expected(case)==original

def test_single_page_volume_cannot_silently_change_slice_without_required_decoder(monkeypatch):
    case=next(r for r in reference.cases() if r['kind']=='volume')
    original=image_io._optional_import
    monkeypatch.setattr(image_io,'_optional_import',lambda name:None if name=='tifffile' else original(name))
    with pytest.raises(RuntimeError) as error:
        image_io.read_image_array(reference.INPUTS/case['input_name'],backend='pil')
    assert isinstance(error.value.__cause__,ImportError)
