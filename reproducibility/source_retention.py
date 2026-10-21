"""Retain executable source bytes before retiring a final run's duplicate tree."""
from pathlib import Path
import gzip
import json
import os
import stat
import errno
import time

from reproducibility import compact_evidence as evidence


def unlink_alias(path, blob):
    try:
        path.chmod(stat.S_IREAD | stat.S_IWRITE)
        path.unlink()
    finally:
        blob.chmod(stat.S_IREAD)


def _remove_empty_snapshot_directory(directory):
    """Retry transient Windows sharing locks without broadening deletion scope."""
    for attempt in range(20):
        evidence.memory_guard()
        try:
            directory.rmdir()
            return
        except OSError as error:
            if getattr(error, 'winerror', None) not in {32, 33} or attempt == 19:
                raise
            time.sleep(min(0.05 * 2**min(attempt, 3), 0.4))


def retire_snapshot(snapshot, manifest, store, *, already_retired=(), journal_path=None,
                    directory_manifest=None, verified_objects=None, consumer_backings=None):
    """Remove only manifest-listed aliases after complete recovery verification.

    A bounded metadata walk rejects extra files or redirected directories before
    any alias is deleted. Canonical bytes and all manifests/receipts are retained.
    """
    evidence.memory_guard()
    snapshot = Path(snapshot).resolve()
    records = []
    for row in evidence.entries(manifest):
        if len(records) >= 20000:
            raise ValueError("Snapshot exceeds the explicit retirement bound")
        records.append(row)
    expected = {row["path"] for row in records}
    if len(expected) != len(records):
        raise ValueError("Duplicate paths in the source manifest")
    indexed = {row['path']: row for row in records}
    declared_backings = consumer_backings or {}
    if sum(len(paths) for paths in declared_backings.values()) > 20000:
        raise ValueError('Consumer backing list exceeds its explicit bound')
    verified_backings = set()
    def backings(row):
        for relative in declared_backings.get(row['sha256'], ()):
            if Path(relative).parts[:2] != ('consumer-links', row['sha256']):
                raise ValueError('Consumer backing is outside its declared hash namespace')
            backing = evidence.owned(store, relative)
            if relative not in verified_backings:
                evidence.validate(backing, row)
                verified_backings.add(relative)
            yield backing
    journal = Path(journal_path) if journal_path is not None else Path(manifest).parent / 'retirement-chain.jsonl.gz'
    manifest_sha = evidence.digest(manifest)
    retired, last = set(already_retired), '0' * 64
    if not retired <= expected:
        raise ValueError('Previously retired paths are outside this manifest')
    if journal.exists():
        with gzip.open(journal, 'rt', encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                sha = row.pop('chain_sha256')
                if (row['previous_sha256'] != last or sha != evidence.chain_hash(row) or
                        row['manifest_sha256'] != manifest_sha or row['path'] not in indexed or
                        row['sha256'] != indexed[row['path']]['sha256'] or row['path'] in retired):
                    raise ValueError('Retirement checkpoint does not authenticate this manifest')
                retired.add(row['path'])
                last = sha
    # An interruption between unlink and journal append is recoverable from the
    # already-tested canonical object; recreate only that missing declared alias.
    if verified_objects is None:
        verified_objects = set()
    for row in records:
        path = evidence.owned(snapshot, row['path'])
        blob = evidence.object_path(store, row['sha256'])
        if row['sha256'] not in verified_objects:
            evidence.validate(blob, row)
            verified_objects.add(row['sha256'])
        elif blob.stat().st_size != row['size']:
            raise ValueError('Canonical size differs from the manifest')
        if row['path'] in retired:
            if path.exists():
                raise ValueError('Retired alias unexpectedly exists')
        elif not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            candidates = [blob, *backings(row)]
            for candidate in candidates:
                try:
                    os.link(candidate, path)
                    break
                except OSError as exc:
                    if getattr(exc, 'winerror', None) != 1142 and exc.errno != errno.EMLINK:
                        raise
                    if candidate == candidates[-1]:
                        raise
    actual, directories = set(), []
    expected_directories = {parent.as_posix() for name in expected
                            for parent in Path(name).parents if parent != Path('.')}
    if directory_manifest is not None:
        for count, row in enumerate(evidence.entries(directory_manifest), 1):
            if count > 20000 or row.get('kind') != 'directory':
                raise ValueError('Invalid directory-state manifest')
            evidence.owned(snapshot, row['path'])
            expected_directories.add(row['path'])
    for root, subdirs, files in os.walk(snapshot, followlinks=False):
        evidence.memory_guard()
        for name in subdirs:
            path = Path(root) / name
            if path.relative_to(snapshot).as_posix() not in expected_directories:
                raise ValueError('Snapshot has an unlisted directory; preserve it')
            evidence.owned(snapshot, path.relative_to(snapshot))
            directories.append(path)
        for name in files:
            actual.add((Path(root) / name).relative_to(snapshot).as_posix())
            if len(actual) > len(expected - retired):
                raise ValueError("Snapshot has unlisted files; preserve it")
    if actual != expected - retired:
        raise ValueError("Snapshot file list changed; preserve it")
    retirement_objects = {}
    # Validate all canonical identities before deleting the first alias.
    for row in records:
        if row['path'] in retired:
            continue
        evidence.memory_guard()
        path = evidence.owned(snapshot, row["path"])
        blob = evidence.object_path(store, row["sha256"])
        # Every distinct canonical object was fully hashed above. A hard link
        # reads that same physical byte sequence; avoid hashing its aliases
        # repeatedly. Independent copies still fail this identity check.
        if not os.path.samefile(path, blob):
            matched = None
            for backing in backings(row):
                if os.path.samefile(path, backing):
                    matched = backing
                    break
            if matched is None:
                raise ValueError("Source is not the restored canonical object or a verified backing")
            blob = matched
        if path.stat().st_size != row['size']:
            raise ValueError("Source is not the restored canonical object")
        retirement_objects[row['path']] = blob
    deleted = len(retired)
    with gzip.open(journal, 'at', encoding='utf-8') as stream:
        for row in records:
            if row['path'] in retired:
                continue
            evidence.memory_guard()
            path = evidence.owned(snapshot, row["path"])
            blob = retirement_objects[row['path']]
            unlink_alias(path, blob)
            proof = dict(row, manifest_sha256=manifest_sha, previous_sha256=last)
            last = evidence.chain_hash(proof)
            proof['chain_sha256'] = last
            stream.write(json.dumps(proof, sort_keys=True, separators=(',', ':')) + '\n')
            deleted += 1
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        _remove_empty_snapshot_directory(evidence.owned(snapshot, directory.relative_to(snapshot)))
    if snapshot.exists():
        _remove_empty_snapshot_directory(snapshot)
    return deleted


def preserve_and_retire(output, snapshots, source_records, store):
    output, store = Path(output).resolve(), Path(store).resolve()
    snapshot = evidence.owned(output, "sources")
    if Path(snapshots).resolve() != snapshot:
        raise ValueError("Unexpected source-snapshot ownership")
    packet = output / "source-packet"
    packet.mkdir(exist_ok=True)
    manifest = packet / "version.jsonl.gz"
    source_records = list(source_records)
    if len(source_records) > 20000:
        raise ValueError("Source list exceeds the explicit packet bound")
    sizes = []
    if not manifest.exists():
        temporary = packet / "version.partial.gz"
        try:
            with gzip.open(temporary, "wt", encoding="utf-8") as stream:
                for row in source_records:
                    evidence.memory_guard()
                    relative = Path(row["path"]).as_posix()
                    path = evidence.owned(snapshot, relative)
                    size = path.stat().st_size
                    sizes.append(size)
                    stream.write(json.dumps({"path": relative, "sha256": row["sha256"], "size": size},
                                            sort_keys=True, separators=(",", ":")) + "\n")
            os.replace(temporary, manifest)
        finally:
            if temporary.exists():
                temporary.unlink()
    else:
        rows = list(evidence.entries(manifest))
        if [(row["path"], row["sha256"]) for row in rows] != [
                (Path(row["path"]).as_posix(), row["sha256"]) for row in source_records]:
            raise ValueError("Retained source manifest changed")
        sizes = [row["size"] for row in rows]
    started = output / "run-started.json"
    if not started.exists():
        raise ValueError("Starting source receipt is required for recovery")
    version = {"id": output.name, "snapshot": str(snapshot), "files": len(source_records),
               "manifest": manifest.name, "manifest_sha256": evidence.digest(manifest),
               "terminal_receipt": str(started), "terminal_receipt_sha256": evidence.digest(started)}
    plan_path = packet / "plan.json"
    plan = {"schema_version": 1, "versions": [version], "peak_temporary_bytes": max(sizes, default=0),
            "scope": "Finalization after all source consumers and the final source-identity check; "
                     "preserve exact producing bytes before removing duplicate source paths"}
    if not plan_path.exists():
        evidence.atomic_json(plan_path, plan)
    elif json.loads(plan_path.read_text(encoding="utf-8")) != plan:
        raise ValueError("Source-retention plan changed")
    if (packet / 'retirement-chain.jsonl.gz').exists():
        result = json.loads((packet / 'run.json').read_text(encoding='utf-8'))
        _, completed, count, _, _ = evidence.journal_state(packet/'cleanup-chain.jsonl.gz', evidence.digest(plan_path))
        if not result['passed'] or count != len(source_records) or completed.get(output.name, -1) != len(source_records)-1:
            raise ValueError('Retirement requires a complete authenticated recovery packet')
    else:
        result = evidence.compact(plan_path, store, packet, preserve_link_limit_paths=True)
    if not result["passed"]:
        raise evidence.ResourcePause("Source packet is incomplete; original snapshot retained")
    consumer_backings = {}
    for row in evidence.entries(packet / 'cleanup-chain.jsonl.gz'):
        if row.get('consumer_backing'):
            consumer_backings.setdefault(row['sha256'], set()).add(row['consumer_backing'])
    removed = retire_snapshot(snapshot, manifest, store, consumer_backings=consumer_backings)
    record = {"status": "removed-after-verified-recovery-packet", "directory_absent": not snapshot.exists(),
              "source_files_retired": removed, "object_store": str(store),
              "manifest": str(manifest.relative_to(output)), "manifest_sha256": evidence.digest(manifest),
              "receipt": str((packet / "run.json").relative_to(output)),
              "receipt_sha256": evidence.digest(packet / "run.json"),
              "restore_recipe": str(packet / result["producer_paths"][result["producer_sha256"]]),
              "source_packet_preserves_exact_bytes": True}
    evidence.atomic_json(packet / "retirement.json", record)
    return record
