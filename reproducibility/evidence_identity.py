"""Authenticate retained evidence, including lossless portable cache artifacts.

Python's build tools omit runtime caches. Frozen historical caches can remain
evidence without becoming executable package files: their exact original bytes
travel in a separately hashed, versioned carrier. No cached code is executed.
"""
from pathlib import Path
import base64
import hashlib
import json

CARRIER_NAME = 'retained-runtime-cache.json'


def _digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            value.update(block)
    return value.hexdigest()


def _safe_path(archive, name):
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Evidence path escapes the retained archive.')
    path = (archive / relative).resolve()
    if not path.is_relative_to(archive):
        raise ValueError('Evidence path escapes the retained archive.')
    return path


def _cache_name(name):
    path = Path(name)
    return '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo')


def manifest_resources(archive, manifest_name, expected_sha256, *, cache_carrier_sha256=None):
    """Return unchanged declared hashes and authenticated lossless cache hashes."""
    archive = Path(archive).resolve()
    manifest = _safe_path(archive, manifest_name)
    if _digest(manifest) != expected_sha256:
        raise ValueError('Retained evidence manifest changed.')
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Retained evidence manifest must be an object.')
    if 'sources' in payload:
        if payload.get('schema_version') != 1:
            raise ValueError('Unsupported retained evidence manifest schema.')
        expected = payload['sources']
    else:
        expected = payload
    if not isinstance(expected, dict):
        raise ValueError('Retained evidence sources must be a path-to-digest mapping.')
    for name, digest in expected.items():
        if not isinstance(name, str) or not isinstance(digest, str) or len(digest) != 64 or any(
            character not in '0123456789abcdef' for character in digest
        ):
            raise ValueError('Invalid retained evidence source declaration.')
    for name in expected:
        _safe_path(archive, name)
    encoded = {}
    if cache_carrier_sha256 is not None:
        carrier = archive / CARRIER_NAME
        if _digest(carrier) != cache_carrier_sha256:
            raise ValueError('Retained cache evidence carrier changed.')
        payload = json.loads(carrier.read_text(encoding='utf-8'))
        if payload['schema_version'] != 1 or payload['manifest_sha256'].get(manifest_name) != expected_sha256:
            raise ValueError('Retained cache evidence identity changed.')
        for name, entry in payload['entries'].items():
            _safe_path(archive, name)
            if not _cache_name(name):
                raise ValueError('Scientific evidence cannot be substituted by a cache carrier.')
            if entry['encoding'] != 'base64':
                raise ValueError('Retained cache evidence encoding changed: ' + name)
            actual = hashlib.sha256(base64.b64decode(entry['bytes'], validate=True)).hexdigest()
            if actual != entry['sha256'] or (name in expected and actual != expected[name]):
                raise ValueError('Retained cache evidence digest changed: ' + name)
            encoded[name] = actual
    return expected, encoded


def verify_manifest(archive, manifest_name, expected_sha256, *, cache_carrier_sha256=None):
    """Retain every original file digest; use only authenticated cache encodings."""
    archive = Path(archive).resolve()
    expected, encoded = manifest_resources(archive, manifest_name, expected_sha256,
                                           cache_carrier_sha256=cache_carrier_sha256)
    for name, digest in expected.items():
        path = _safe_path(archive, name)
        if path.is_file():
            actual = _digest(path)
        elif _cache_name(name) and name in encoded:
            actual = encoded[name]
        else:
            raise ValueError('Retained evidence missing: ' + name)
        if actual != digest:
            raise ValueError('Retained evidence changed: ' + name)


def verify_sources(root, fixture):
    root=Path(root)
    retained_cache = {}
    for folder, declaration in fixture.get('cache_carriers', {}).items():
        archive = _safe_path(root.resolve(), folder)
        mapping, encoded = manifest_resources(archive, 'source-manifest.json',
            declaration['manifest_sha256'], cache_carrier_sha256=declaration['carrier_sha256'])
        verify_manifest(archive, 'source-manifest.json', declaration['manifest_sha256'],
            cache_carrier_sha256=declaration['carrier_sha256'])
        for name, expected in mapping.items():
            if not _cache_name(name) or encoded.get(name) != expected:
                raise ValueError('Fixture cache carrier must retain only original runtime cache bytes')
            retained_cache[(Path(folder)/name).as_posix()] = expected
    def digest(path):
        actual = _safe_path(root.resolve(), path)
        if actual.is_file():
            return hashlib.sha256(actual.read_bytes()).hexdigest()
        if _cache_name(path) and Path(path).as_posix() in retained_cache:
            return retained_cache[Path(path).as_posix()]
        return hashlib.sha256(actual.read_bytes()).hexdigest()
    revisions=fixture.get('source_revisions',{})
    if revisions:
        if digest(fixture['previous_fixture_path'])!=fixture['previous_fixture_sha256']:
            raise ValueError('Previous fixture identity changed')
        previous=json.loads((root/fixture['previous_fixture_path']).read_text(encoding='utf-8'))
        if previous['rows']!=fixture['rows'] or previous['source_manifest']!=fixture['source_manifest']:
            raise ValueError('Original answers or source declarations changed during revision')
        if set(revisions)-set(fixture['source_manifest']):
            raise ValueError('Source revision has no original declaration')
    for path,expected in fixture['source_manifest'].items():
        revision=revisions.get(path)
        if revision is None:
            if digest(path)!=expected:raise ValueError('Original evidence changed: '+path)
            continue
        if digest(revision['original_path'])!=expected:
            raise ValueError('Original adapter archive changed: '+path)
        for item in revision['evidence']:
            if digest(item['path'])!=item['sha256']:
                raise ValueError('Adapter revision evidence changed: '+item['path'])
        if digest(path)!=revision['current_sha256'] or digest(revision['candidate_path'])!=revision['current_sha256']:
            raise ValueError('Installed adapter differs from accepted candidate: '+path)
        proof=json.loads((root/revision['proof_path']).read_text(encoding='utf-8'))
        if not all(proof.get(name) is True for name in ('complete_outputs_unchanged','source_unchanged','exception_preserved')):
            raise ValueError('Adapter revision lacks accepted unchanged-output evidence')
