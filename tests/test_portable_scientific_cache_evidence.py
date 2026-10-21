"""Public source archives authenticate omitted historical caches without executing them."""
from pathlib import Path
import importlib.util
import json
import shutil
import pytest
from reproducibility import ordinal_constant_contract, scientific_utility_contract


@pytest.fixture(params=['science', 'ordinal'])
def portable(request, tmp_path):
    original = scientific_utility_contract if request.param == 'science' else ordinal_constant_contract
    target = tmp_path / 'unrelated-checkout-name' / 'reproducibility'
    target.mkdir(parents=True)
    archive = target / 'reference-sources' / ('scientific-utilities' if request.param == 'science' else 'ordinal-constant')
    source_archive = original.ARCHIVE if request.param == 'science' else Path(original.__file__).parent / 'reference-sources/ordinal-constant'
    shutil.copytree(source_archive, archive, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
    path = target / Path(original.__file__).name
    shutil.copyfile(original.__file__, path)
    if request.param == 'ordinal':
        fixture = json.loads(original.FIXTURE.read_text(encoding='utf-8'))
        for name in fixture['source_manifest']:
            if '/' not in name:
                shutil.copyfile(Path(original.__file__).parent / name, target / name)
        fixtures = target / 'fixtures'
        fixtures.mkdir()
        shutil.copyfile(original.FIXTURE, fixtures / original.FIXTURE.name)
    spec = importlib.util.spec_from_file_location('portable_' + request.param, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, archive


def test_complete_original_evidence_authenticates_without_physical_cache(portable):
    module, archive = portable
    assert not list(archive.rglob('*.pyc'))
    module.check_identity()
    assert not list(archive.rglob('*.pyc'))


def test_modified_encoded_original_cache_refuses(portable):
    module, archive = portable
    carrier = archive / 'retained-runtime-cache.json'
    carrier.write_bytes(carrier.read_bytes() + b' ')
    with pytest.raises(ValueError, match='evidence'):
        module.check_identity()


def test_missing_encoded_original_cache_refuses(portable):
    module, archive = portable
    (archive / 'retained-runtime-cache.json').unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        module.check_identity()
