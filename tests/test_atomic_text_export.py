"""An interrupted text export never replaces the last complete result."""
import pytest
from PyFLASH import _persistence as persistence

@pytest.mark.parametrize('stage',['writing','replacement'])
def test_failed_text_export_retains_previous_bytes_and_cleans_its_temporary(tmp_path,monkeypatch,stage):
    target=tmp_path/'accepted.csv';previous=b'previous accepted result\n';target.write_bytes(previous)
    if stage=='replacement':
        def stopped(*args):raise OSError('controlled replacement failure')
        monkeypatch.setattr(persistence,'atomic_replace',stopped)
    with pytest.raises((ValueError,OSError)):
        with persistence.atomic_text(target,newline='') as stream:
            stream.write('partial replacement')
            if stage=='writing':raise ValueError('controlled write failure')
    assert target.read_bytes()==previous
    assert list(tmp_path.iterdir())==[target]

def test_complete_text_is_published_with_requested_newlines(tmp_path):
    target=tmp_path/'new'/'complete.csv'
    with persistence.atomic_text(target,newline='') as stream:stream.write('Δ complete\r\n')
    assert target.read_bytes()=='Δ complete\r\n'.encode()
    assert list(target.parent.iterdir())==[target]
