"""A source download must retain original manifest-declared resources."""
import base64
import hashlib
import json
from pathlib import Path
import pytest
from scripts.check_reproducibility_distribution import check
from test_reproducibility_distribution_resources import make_source, make_archive

def retained(root):
    files = make_source(root)
    prefix = 'reproducibility/reference-sources/native/'
    cache = '__pycache__/original.cpython-312.pyc'
    workbook = 'input.xlsx'
    raw_cache = b'original frozen Python cache\x00\xff'
    raw_book = b'original workbook bytes'
    digest = lambda data: hashlib.sha256(data).hexdigest()
    mapping = {cache: digest(raw_cache), workbook: digest(raw_book)}
    manifest = json.dumps(mapping).encode()
    payload = dict(schema_version=1, manifest_sha256={'source-manifest.json': digest(manifest)},
        entries={cache: dict(encoding='base64', sha256=digest(raw_cache), bytes=base64.b64encode(raw_cache).decode('ascii'))})
    files.update({prefix + 'source-manifest.json': manifest,
                  prefix + 'retained-runtime-cache.json': json.dumps(payload).encode(),
                  prefix + workbook: raw_book})
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return files, prefix, cache

def test_exact_cache_encoding_and_original_workbook_pass_actual_tar(tmp_path):
    files, prefix, cache = retained(tmp_path / 'source')
    path = tmp_path / 'download.tar.gz'
    make_archive(path, files)
    result = check(path, tmp_path / 'source')
    assert result['passed']
    assert result['encoded_cache_resources'] == [prefix + cache]


@pytest.mark.parametrize('change', ['none', 'missing', 'changed'])
def test_versioned_manifest_metadata_is_not_mistaken_for_resource_paths(tmp_path, change):
    root = tmp_path / 'source'
    files, prefix, cache = retained(root)
    declarations = json.loads(files[prefix + 'source-manifest.json'])
    manifest = json.dumps(dict(schema_version=1, sources=declarations,
        scope='Original native evidence', preserved_failures={'count': 8},
        reference_amendment='Recorded independently')).encode()
    files[prefix + 'source-manifest.json'] = manifest
    (root / (prefix + 'source-manifest.json')).write_bytes(manifest)
    carrier = json.loads(files[prefix + 'retained-runtime-cache.json'])
    carrier['manifest_sha256']['source-manifest.json'] = hashlib.sha256(manifest).hexdigest()
    files[prefix + 'retained-runtime-cache.json'] = json.dumps(carrier).encode()
    (root / (prefix + 'retained-runtime-cache.json')).write_bytes(files[prefix + 'retained-runtime-cache.json'])
    if change == 'missing':
        del files[prefix + 'input.xlsx']
    elif change == 'changed':
        files[prefix + 'input.xlsx'] += b'changed'
    archive = tmp_path / 'download.tar.gz'
    make_archive(archive, files)
    result = check(archive, root)
    assert result['passed'] is (change == 'none')
    if change == 'none':
        assert result['encoded_cache_resources'] == [prefix + cache]
    else:
        assert prefix + 'input.xlsx' in result['missing' if change == 'missing' else 'different']
    assert not any(name.rsplit('/', 1)[-1] in {'schema_version', 'sources', 'scope',
        'preserved_failures', 'reference_amendment'} for name in result['missing'])


@pytest.mark.parametrize('payload', [
    {'schema_version': 2, 'sources': {}},
    {'schema_version': 1, 'sources': []},
    {'input.xlsx': 'not a digest'},
    {'../outside': '0' * 64},
])
def test_malformed_or_escaping_manifest_remains_a_failure(tmp_path, payload):
    root = tmp_path / 'source'
    files, prefix, _ = retained(root)
    manifest = json.dumps(payload).encode()
    files[prefix + 'source-manifest.json'] = manifest
    (root / (prefix + 'source-manifest.json')).write_bytes(manifest)
    archive = tmp_path / 'download.tar.gz'
    make_archive(archive, files)
    result = check(archive, root)
    assert not result['passed'] and result['evidence_errors']

@pytest.mark.parametrize('name', ['input.xlsx', 'retained-runtime-cache.json', 'source-manifest.json'])
def test_missing_archive_evidence_refuses(tmp_path, name):
    files, prefix, _ = retained(tmp_path / 'source')
    del files[prefix + name]
    path = tmp_path / 'download.tar.gz'
    make_archive(path, files)
    result = check(path, tmp_path / 'source')
    assert not result['passed']
    assert prefix + name in result['missing']

def test_workbook_omitted_from_build_snapshot_cannot_pass(tmp_path):
    files, prefix, _ = retained(tmp_path / 'source')
    del files[prefix + 'input.xlsx']
    (tmp_path / 'source' / (prefix + 'input.xlsx')).unlink()
    path = tmp_path / 'download.tar.gz'
    make_archive(path, files)
    result = check(path, tmp_path / 'source')
    assert not result['passed']
    assert prefix + 'input.xlsx' in result['missing']
    assert prefix + 'input.xlsx' in result['source_missing']
    assert result['evidence_errors']

@pytest.mark.parametrize('name', ['input.xlsx', 'retained-runtime-cache.json'])
def test_archive_evidence_changes_refuse(tmp_path, name):
    files, prefix, _ = retained(tmp_path / 'source')
    files[prefix + name] += b' '
    path = tmp_path / 'download.tar.gz'
    make_archive(path, files)
    result = check(path, tmp_path / 'source')
    assert not result['passed']
    assert prefix + name in result['different']

def test_bad_encoded_cache_cannot_hide_behind_valid_physical_source_cache(tmp_path):
    root = tmp_path / 'source'
    files, prefix, cache = retained(root)
    original = root / (prefix + cache)
    original.parent.mkdir()
    original.write_bytes(b'original frozen Python cache\x00\xff')
    payload = json.loads(files[prefix + 'retained-runtime-cache.json'])
    payload['entries'][cache]['bytes'] = base64.b64encode(b'changed').decode('ascii')
    changed = json.dumps(payload).encode()
    (root / (prefix + 'retained-runtime-cache.json')).write_bytes(changed)
    files[prefix + 'retained-runtime-cache.json'] = changed
    path = tmp_path / 'download.tar.gz'
    make_archive(path, files)
    result = check(path, root)
    assert not result['passed'] and result['evidence_errors']

def test_physical_cache_change_is_not_hidden_by_encoding(tmp_path):
    files, prefix, cache = retained(tmp_path / 'source')
    files[prefix + cache] = b'changed cache'
    path = tmp_path / 'download.tar.gz'
    make_archive(path, files)
    result = check(path, tmp_path / 'source')
    assert not result['passed'] and prefix + cache in result['different']

def test_scientific_file_cannot_be_carried_as_cache(tmp_path):
    root = tmp_path / 'source'
    files, prefix, _ = retained(root)
    payload = json.loads(files[prefix + 'retained-runtime-cache.json'])
    payload['entries']['input.xlsx'] = dict(encoding='base64', sha256=hashlib.sha256(files[prefix + 'input.xlsx']).hexdigest(), bytes=base64.b64encode(files[prefix + 'input.xlsx']).decode('ascii'))
    files[prefix + 'retained-runtime-cache.json'] = json.dumps(payload).encode()
    (root / (prefix + 'retained-runtime-cache.json')).write_bytes(files[prefix + 'retained-runtime-cache.json'])
    path = tmp_path / 'download.tar.gz'
    make_archive(path, files)
    result = check(path, root)
    assert not result['passed'] and result['evidence_errors']


@pytest.mark.parametrize('manifest_name', ['coordinate-amendment-manifest.json', 'narrow-amendment-manifest.json'])
@pytest.mark.parametrize('missing_input', [False, True])
def test_amendment_original_input_survives_source_snapshot_omission(tmp_path, manifest_name, missing_input):
    root = tmp_path / 'source'
    files, prefix, _ = retained(root)
    original_manifest = files[prefix + 'source-manifest.json']
    files[prefix + manifest_name] = original_manifest
    files[prefix + 'source-manifest.json'] = b'{}'
    payload = json.loads(files[prefix + 'retained-runtime-cache.json'])
    payload['manifest_sha256'] = {
        'source-manifest.json': hashlib.sha256(b'{}').hexdigest(),
        manifest_name: hashlib.sha256(original_manifest).hexdigest(),
    }
    files[prefix + 'retained-runtime-cache.json'] = json.dumps(payload).encode()
    if missing_input:
        del files[prefix + 'input.xlsx']
        (root / (prefix + 'input.xlsx')).unlink()
    for name, data in files.items():
        (root / name).write_bytes(data)
    archive = tmp_path / 'download.tar.gz'
    make_archive(archive, files)
    result = check(archive, root)
    assert result['passed'] is not missing_input
    if missing_input:
        assert prefix + 'input.xlsx' in result['source_missing']
        assert prefix + 'input.xlsx' in result['missing']
        assert result['evidence_errors']


@pytest.mark.parametrize('kind', ['saved-object', 'preserved-negative-fixture'])
def test_nested_manifests_are_original_files_not_primary_input_declarations(tmp_path, kind):
    root = tmp_path / 'source'
    files, prefix, _ = retained(root)
    name = ('results/original/manifest.json' if kind == 'saved-object' else 'negative-test/source-manifest.json')
    content = (b'{"run_label":"original run","n_rows":6}' if kind == 'saved-object' else b'{"intentionally-missing.xlsx":"0000000000000000000000000000000000000000000000000000000000000000"}')
    files[prefix + name] = content
    path = root / (prefix + name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    mapping = json.loads(files[prefix + 'source-manifest.json'])
    mapping[name] = hashlib.sha256(content).hexdigest()
    files[prefix + 'source-manifest.json'] = json.dumps(mapping).encode()
    (root / (prefix + 'source-manifest.json')).write_bytes(files[prefix + 'source-manifest.json'])
    payload = json.loads(files[prefix + 'retained-runtime-cache.json'])
    payload['manifest_sha256']['source-manifest.json'] = hashlib.sha256(files[prefix + 'source-manifest.json']).hexdigest()
    files[prefix + 'retained-runtime-cache.json'] = json.dumps(payload).encode()
    (root / (prefix + 'retained-runtime-cache.json')).write_bytes(files[prefix + 'retained-runtime-cache.json'])
    archive = tmp_path / 'download.tar.gz'
    make_archive(archive, files)
    assert check(archive, root)['passed']
    del files[prefix + name]
    make_archive(archive, files)
    result = check(archive, root)
    assert not result['passed'] and prefix + name in result['missing']
