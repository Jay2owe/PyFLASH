"""Verify that a source distribution retains executable reproduction resources."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import tarfile

REQUIRED=(
    '.streamlit/config.toml',
    'architecture.yaml','architecture.lock.json','architecture.schema.json',
    'scripts/verify.py','scripts/project_contract.py','scripts/contracts-requirements.txt',
    'scripts/check_ui_real_data.py','scripts/check_ui_responsiveness.py','scripts/ui_readiness.py',
    'reproducibility/check_bootstrap.py','reproducibility/run.py',
    'reproducibility/reference_runtime.py','reproducibility/run_native_r.mjs',
    'reproducibility/windows_r_loader.mjs','reproducibility/package.json',
    'reproducibility/package-lock.json','demo/run_demo.py','demo/expected_result.json',
)

def _digest(stream):
    value=hashlib.sha256()
    for block in iter(lambda:stream.read(1024**2),b''):value.update(block)
    return value.hexdigest()

def check(sdist,source_root):
    """Compare every declared reproduction resource with its supplied source."""
    source_root=Path(source_root).resolve()
    required=set(REQUIRED)
    for folder in ('reproducibility','tests','demo'):
        required.update(path.relative_to(source_root).as_posix()
                        for path in (source_root/folder).rglob('*')
                        if path.is_file() and '__pycache__' not in path.parts
                        and path.suffix not in ('.pyc','.pyo')
                        and not (len(path.relative_to(source_root/folder).parts)>1
                                 and path.relative_to(source_root/folder).parts[0]
                                 in ({'results'} if folder=='reproducibility' else {'output'} if folder=='demo' else set())))
    required.update(path.relative_to(source_root).as_posix()
                    for path in (source_root/'scripts').glob('*.py'))
    different=[];source_missing=[];verified=[];duplicates=[];forbidden_cache_files=[];expected={};seen=set()
    evidence_errors=[];portable_cache={};declared_cache=set()
    for name in sorted(required):
        source=source_root/name
        if not source.is_file():source_missing.append(name);continue
        with source.open('rb') as stream:expected[name]=_digest(stream)
    # Frozen manifests retain declared resources even when a flawed snapshot
    # omitted them before the build. Cache bytes may travel in a hashed carrier;
    # original workbooks and native scientific inputs must remain actual files.
    from reproducibility.evidence_identity import CARRIER_NAME, _cache_name, manifest_resources, verify_manifest
    evidence_root=source_root/'reproducibility/reference-sources'
    primary_manifests = sorted(set(evidence_root.glob('*/source-manifest.json'))
                               | set(evidence_root.glob('*/*-amendment-manifest.json')))
    for manifest in primary_manifests:
        evidence=manifest.parent
        carrier=evidence/CARRIER_NAME
        with manifest.open('rb') as stream:manifest_sha=_digest(stream)
        carrier_sha=None
        if carrier.is_file():
            with carrier.open('rb') as stream:carrier_sha=_digest(stream)
        try:
            mapping,encoded=manifest_resources(evidence,manifest.name,manifest_sha,
                                               cache_carrier_sha256=carrier_sha)
            for relative,digest in mapping.items():
                name=(evidence/relative).relative_to(source_root).as_posix()
                required.add(name)
                if name in expected and expected[name]!=digest:
                    evidence_errors.append('Source differs from retained manifest: '+name)
                expected[name]=digest
                if _cache_name(relative):
                    declared_cache.add(name)
                    if encoded.get(relative)==digest:
                        portable_cache[name]=carrier.relative_to(source_root).as_posix()
                elif not (source_root/name).is_file() and name not in source_missing:
                    source_missing.append(name)
            verify_manifest(evidence,manifest.name,manifest_sha,cache_carrier_sha256=carrier_sha)
        except (ValueError,FileNotFoundError,KeyError,TypeError) as error:
            evidence_errors.append(manifest.relative_to(source_root).as_posix()+': '+str(error))
    # A compressed archive must be read once, in stored order. Random seeking
    # repeatedly inflates gigabytes of retained evidence for each small file.
    with tarfile.open(sdist,'r|gz') as archive:
        for member in archive:
            if not member.isfile() or '/' not in member.name:continue
            archive_parts=PurePosixPath(member.name).parts
            relative_parts=archive_parts[1:]
            name='/'.join(relative_parts)
            filename=PurePosixPath(name).name.lower()
            compiled_suffix=filename.endswith(('.pyc','.pyo','.pyd')) or any(
                f'.{suffix}.' in filename for suffix in ('pyc','pyo','pyd'))
            if '__pycache__' in relative_parts or compiled_suffix:
                forbidden_cache_files.append(name)
            if name not in expected:continue
            if name in seen:duplicates.append(name)
            seen.add(name)
            with archive.extractfile(member) as stream:actual=_digest(stream)
            if actual!=expected[name]:different.append(name)
            else:verified.append(name)
    encoded_verified=sorted(name for name,carrier in portable_cache.items()
                            if name not in seen and carrier in verified)
    missing=sorted(set(expected)-seen-set(encoded_verified))
    return {'passed':not missing and not different and not source_missing and not duplicates and
            not evidence_errors and not forbidden_cache_files,
            'required_files':len(required),'verified_files':len(verified)+len(encoded_verified),
            'encoded_cache_resources':encoded_verified,'evidence_errors':evidence_errors,
            'missing':missing,'different':different,'source_missing':source_missing,'duplicates':duplicates,
            'forbidden_cache_files':sorted(forbidden_cache_files),
            'scope':'Executable reproduction resources, every original manifest-declared input and byte-identical physical or losslessly encoded runtime-cache evidence; no scientific or performance completion certificate.'}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    selection=parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--sdist',type=Path)
    selection.add_argument('--dist-dir',type=Path)
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args(argv)
    if args.dist_dir is not None:
        archives=sorted(args.dist_dir.glob('*.tar.gz'))
        if len(archives)!=1:
            parser.error('--dist-dir must contain exactly one source archive.')
        args.sdist=archives[0]
    report=check(args.sdist,args.source_root)
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
