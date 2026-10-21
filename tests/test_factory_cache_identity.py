"""A changed scientific source must not be hidden by an existing cache."""
import os
from pathlib import Path
import pandas as pd
import pytest
from PyFLASH import factory
from PyFLASH.conditions import ConditionBuilder
from PyFLASH.serialization import save_state, load_state


class DerivedBatch:
    calls = 0
    mutate_during_run = False

    def __init__(self, name, experiment_list, conditions, batch_path):
        self.name = name
        self.experiment_list = experiment_list
        self.factor = conditions.factor
        self.data = {}

    def processData(self, **kwargs):
        type(self).calls += 1
        source = Path(self.experiment_list[0].filePath)/'source.csv'
        self.summary = pd.read_csv(source)
        if type(self).mutate_during_run:
            source.write_text('value\n900\n')


@pytest.fixture
def setup_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(factory, 'Batch', DerivedBatch)
    monkeypatch.setattr(DerivedBatch, 'calls', 0)
    monkeypatch.setattr(DerivedBatch, 'mutate_during_run', False)
    source = tmp_path/'input'
    source.mkdir()
    (source/'source.csv').write_text('value\n100\n')
    conditions = ConditionBuilder('Group').add('A', short='A').build()
    params = dict(name='cached', conditions=conditions, batch_path=str(tmp_path/'output'),
                  experiments={'one':str(source)}, pickle_path=str(tmp_path/'cache'),
                  import_images=False, progress=False)
    return source, params


def test_unchanged_sources_reuse_cache_and_preserve_saved_edits(setup_batch):
    source, params = setup_batch
    batch = factory.create_batch(**params)
    batch.manual_note = 'keep this user edit'
    save_state(batch, str(Path(params['pickle_path'])/'cached.pkl'), verbose=False)
    loaded = factory.create_batch(**params)
    assert DerivedBatch.calls == 1
    assert loaded.manual_note == 'keep this user edit'


def test_same_timestamp_and_size_changed_contents_rebuild(setup_batch):
    source, params = setup_batch
    factory.create_batch(**params)
    path = source/'source.csv'
    original = path.stat()
    path.write_text('value\n200\n')
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    result = factory.create_batch(**params)
    assert DerivedBatch.calls == 2
    assert result.summary['value'].tolist() == [200]


@pytest.mark.parametrize('change', ['threshold', 'condition', 'version', 'code'])
def test_changed_processing_identity_rebuilds(setup_batch, monkeypatch, change):
    source, params = setup_batch
    factory.create_batch(**params)
    if change == 'threshold':
        params['threshold'] = 45
    elif change == 'condition':
        params['conditions'].conditions[0].label = 'Renamed condition'
    elif change == 'version':
        monkeypatch.setattr('PyFLASH._cache_identity.version', lambda name:'changed-version')
    else:
        monkeypatch.setattr('PyFLASH._persistence.code_identity', lambda:{'changed.py':'changed'})
    factory.create_batch(**params)
    assert DerivedBatch.calls == 2


def test_unverified_legacy_cache_is_rebuilt(setup_batch):
    source, params = setup_batch
    batch = factory.create_batch(**params)
    del batch._factory_cache_identity
    save_state(batch, str(Path(params['pickle_path'])/'cached.pkl'), verbose=False)
    factory.create_batch(**params)
    assert DerivedBatch.calls == 2


def test_zero_threshold_is_a_processing_choice_and_cache_identity(setup_batch):
    source, params = setup_batch
    default = factory.create_batch(**params)
    result = factory.create_batch(**params, threshold=0)
    assert DerivedBatch.calls == 2
    assert default.experiment_list[0].threshold != 0
    assert result.experiment_list[0].threshold == 0
    factory.create_batch(**params, threshold=0)
    assert DerivedBatch.calls == 2


def test_source_change_during_processing_preserves_previous_cache(setup_batch, monkeypatch):
    source, params = setup_batch
    factory.create_batch(**params)
    cache = Path(params['pickle_path'])/'cached.pkl'
    original = cache.read_bytes()
    monkeypatch.setattr(DerivedBatch, 'mutate_during_run', True)
    with pytest.raises(RuntimeError, match='changed while building'):
        factory.create_batch(**params, rerun=True)
    assert cache.read_bytes() == original
    assert load_state(str(cache), verbose=False).summary['value'].tolist() == [100]
