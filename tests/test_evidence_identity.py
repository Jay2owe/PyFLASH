"""Exercise authentication and omission guards on private evidence identity code."""
from pathlib import Path
import base64
import hashlib
import importlib
import json
import pytest

from reproducibility import evidence_identity as M
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

@pytest.fixture
def evidence(tmp_path):
    original = b'original frozen Python runtime cache\x00\xff'
    science = tmp_path / 'native-result.json'
    science.write_bytes(b'{"original_native_number": 3}')
    cached = 'original/__pycache__/producer.cpython-314.pyc'
    mapping = {'native-result.json': digest(science), cached: hashlib.sha256(original).hexdigest()}
    manifest = tmp_path / 'source-manifest.json'
    manifest.write_text(json.dumps(mapping), encoding='utf-8')
    payload = dict(schema_version=1, manifest_sha256={'source-manifest.json': digest(manifest)},
                   entries={cached: dict(encoding='base64', sha256=mapping[cached], bytes=base64.b64encode(original).decode('ascii'))})
    carrier = tmp_path / M.CARRIER_NAME
    carrier.write_text(json.dumps(payload), encoding='utf-8')
    return dict(root=tmp_path, original=original, science=science, cached=cached,
                manifest=manifest, payload=payload, carrier=carrier,
                manifest_sha=digest(manifest), carrier_sha=digest(carrier))

def verify(e, *, repin_carrier=False):
    return M.verify_manifest(e['root'], 'source-manifest.json', e['manifest_sha'],
                             cache_carrier_sha256=digest(e['carrier']) if repin_carrier else e['carrier_sha'])

def write_carrier(e):
    e['carrier'].write_text(json.dumps(e['payload']), encoding='utf-8')

def test_original_encoded_bytes_pass_without_materializing_or_executing_cache(evidence):
    before = {str(p.relative_to(evidence['root'])): digest(p) for p in evidence['root'].rglob('*') if p.is_file()}
    verify(evidence)
    after = {str(p.relative_to(evidence['root'])): digest(p) for p in evidence['root'].rglob('*') if p.is_file()}
    assert before == after
    assert not (evidence['root'] / evidence['cached']).exists()

def test_original_physical_cache_passes(evidence):
    path = evidence['root'] / evidence['cached']
    path.parent.mkdir(parents=True)
    path.write_bytes(evidence['original'])
    verify(evidence)

def test_modified_physical_cache_cannot_fall_back_to_valid_carrier(evidence):
    path = evidence['root'] / evidence['cached']
    path.parent.mkdir(parents=True)
    path.write_bytes(b'altered cache')
    with pytest.raises(ValueError, match='evidence changed'):
        verify(evidence)

@pytest.mark.parametrize('resource', ['manifest', 'carrier', 'science'])
def test_modified_authenticated_resource_refuses(evidence, resource):
    evidence[resource].write_bytes(evidence[resource].read_bytes() + b' ')
    with pytest.raises(ValueError):
        verify(evidence)

@pytest.mark.parametrize('resource', ['manifest', 'carrier', 'science'])
def test_missing_resource_refuses(evidence, resource):
    evidence[resource].unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        verify(evidence)

@pytest.mark.parametrize('mutation', ['schema', 'manifest-link', 'missing-entry', 'encoding', 'entry-digest', 'encoded-bytes', 'invalid-base64', 'scientific-entry', 'escaping-entry'])
def test_carrier_semantic_guards_refuse_even_with_its_new_digest(evidence, mutation):
    p = evidence['payload']
    entry = p['entries'][evidence['cached']]
    if mutation == 'schema': p['schema_version'] = 2
    elif mutation == 'manifest-link': p['manifest_sha256']['source-manifest.json'] = '0' * 64
    elif mutation == 'missing-entry': p['entries'] = {}
    elif mutation == 'encoding': entry['encoding'] = 'hex'
    elif mutation == 'entry-digest': entry['sha256'] = '0' * 64
    elif mutation == 'encoded-bytes': entry['bytes'] = base64.b64encode(b'new cache').decode('ascii')
    elif mutation == 'invalid-base64': entry['bytes'] = '%%%%'
    elif mutation == 'scientific-entry': p['entries']['native-result.json'] = dict(entry)
    elif mutation == 'escaping-entry': p['entries']['../__pycache__/producer.pyc'] = dict(entry)
    write_carrier(evidence)
    with pytest.raises(ValueError):
        verify(evidence, repin_carrier=True)

def test_manifest_path_cannot_escape(evidence):
    with pytest.raises(ValueError, match='escapes'):
        M.verify_manifest(evidence['root'], '../source-manifest.json', evidence['manifest_sha'])

def test_missing_cache_without_declared_carrier_refuses(evidence):
    with pytest.raises(ValueError, match='missing'):
        M.verify_manifest(evidence['root'], 'source-manifest.json', evidence['manifest_sha'])

@pytest.mark.parametrize('module_name', ['association_interval_contract', 'ecdf_public_contract', 'excel_region_contract', 'marker_threshold_contract', 'ordinal_binary_glm_contract', 'outlier_request_contract'])
def test_genuine_archived_manifests_authenticate_every_original_resource(module_name):
    contract = importlib.import_module('reproducibility.' + module_name)
    contract.check_identity()
    M.verify_manifest(contract.ARCHIVE, 'source-manifest.json', contract.MANIFEST_SHA256,
                       cache_carrier_sha256=contract.CACHE_CARRIER_SHA256)
    if hasattr(contract, 'NARROW_MANIFEST_SHA256'):
        M.verify_manifest(contract.ARCHIVE, 'narrow-amendment-manifest.json', contract.NARROW_MANIFEST_SHA256,
                           cache_carrier_sha256=contract.CACHE_CARRIER_SHA256)
