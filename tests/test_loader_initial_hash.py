"""Import-time hashing retains the loader's after-read content guard."""
import pytest
from PyFLASH.ui import loading, workspace


def test_precomputed_initial_identity_still_requires_matching_final_contents(tmp_path):
    source = tmp_path/'input.csv'
    source.write_bytes(workspace.DEMO_PATH.read_bytes())
    identity = workspace.source_version(source)
    source.write_text('AnimalName,Condition,Signal\nA,Control,2\n')
    with pytest.raises(ValueError,match='changed while'):
        loading.open_source({'kind':'csv','path':str(source)},initial_identity=identity)


def test_initial_identity_avoids_only_the_already_completed_hash(tmp_path, monkeypatch):
    source = tmp_path/'input.csv'
    source.write_bytes(workspace.DEMO_PATH.read_bytes())
    identity = workspace.source_version(source)
    original = workspace.source_version
    calls = []
    def checked(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(workspace,'source_version',checked)
    batch = loading.open_source({'kind':'csv','path':str(source)},initial_identity=identity)
    assert len(calls) == 1
    assert batch._ui_source_version == identity
