"""Content-verified compaction of explicitly selected, terminal source snapshots.

Scientific results, runtimes and inputs are not discovered or removed here. Each
version supplies an immutable compressed file list and its terminal receipt.
Objects are local NTFS hard links: historical paths keep resolving, while each
distinct source byte sequence occupies one file. Restore makes independent files.
"""
from __future__ import annotations

import argparse
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone

BLOCK = 1024 * 1024
RAM_FLOOR = 4 * 1024**3


class ResourcePause(RuntimeError):
    """No more work may start until the declared reserve is restored."""


def available_ram():
    if os.name == "nt":
        class Memory(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in
                ("total", "available", "page_total", "page_available", "virtual_total",
                 "virtual_available", "extended")]
        value = Memory()
        value.length = ctypes.sizeof(value)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            raise OSError("Cannot establish free RAM")
        return value.available
    import psutil
    return psutil.virtual_memory().available


def memory_guard():
    if available_ram() < RAM_FLOOR:
        raise ResourcePause("Available RAM is below 4 GiB")


def guard(path, temporary_bytes=0):
    memory_guard()
    path = Path(path)
    existing = next(p for p in (path, *path.parents) if p.exists())
    if shutil.disk_usage(existing).free < temporary_bytes + BLOCK * 64:
        raise ResourcePause("Insufficient space for restoration plus the disk reserve")


def digest(path, check_resources=False):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(BLOCK):
            if check_resources:
                memory_guard()
            value.update(block)
    return value.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers (including sync clients) can briefly deny replacement.
        # Keep the old receipt intact; retry only known Windows lock errors and
        # propagate a persistent denial rather than changing its permissions.
        for attempt in range(20):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as error:
                if os.name != "nt" or getattr(error, "winerror", None) not in {5, 32, 33} or attempt == 19:
                    raise
                time.sleep(min(0.05 * 2**min(attempt, 3), 0.4))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def owned(root, relative):
    root = Path(root).resolve()
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise ValueError("Unsafe manifest path: " + str(relative))
    candidate = Path(os.path.abspath(root / part))
    resolved = candidate.resolve()
    resolved.relative_to(root)
    # A single native final-path lookup detects redirected ancestors without
    # repeatedly statting the same parent tree for every manifest file.
    if os.path.normcase(str(resolved)) != os.path.normcase(str(candidate)) or candidate.is_symlink():
        raise ValueError("Manifest path traverses a link: " + str(relative))
    return candidate


def entries(manifest):
    with gzip.open(manifest, "rt", encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def object_path(store, sha):
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Invalid SHA-256 object key")
    return owned(Path(store) / "objects", sha[:2] + "/" + sha + ".bin")


def validate(path, expected, check_resources=True):
    if path.stat().st_size != expected["size"] or digest(path, check_resources) != expected["sha256"]:
        raise ValueError("Bytes differ from the retained manifest: " + str(path))


def allocation(path):
    if os.name != "nt":
        return path.stat().st_size
    high = ctypes.c_ulong()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = kernel.GetCompressedFileSizeW
    function.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    function.restype = ctypes.c_ulong
    ctypes.set_last_error(0)
    low = function(str(path), ctypes.byref(high))
    if low == 0xffffffff and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    return high.value << 32 | low


def restore_file(blob, target, expected):
    """Materialise independent bytes; validate the actual file after closing it."""
    guard(target.parent, expected["size"])
    target.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with blob.open("rb") as source, target.open("xb") as output:
            created = True
            while block := source.read(BLOCK):
                memory_guard()
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        validate(target, expected)
    except BaseException:
        if created and target.exists():
            target.unlink()
        raise


def consumer_link(source, temporary, expected, store):
    """Reuse the minimum backing files needed beyond NTFS's link ceiling.

    The SHA-addressed object remains canonical. Each additional backing uses an
    already existing, verified consumer file; it creates no new data copy.
    """
    folder = owned(store, 'consumer-links/' + expected['sha256'])
    folder.mkdir(parents=True, exist_ok=True)
    for number in range(1, 4097):
        backing = owned(folder, 'backing-' + str(number) + '.bin')
        if not backing.exists():
            validate(source, expected)
            os.link(source, backing)
            backing.chmod(stat.S_IREAD)
            validate(backing, expected)
            return backing, False
        validate(backing, expected)
        if os.path.samefile(source, backing):
            return backing, False
        try:
            os.link(backing, temporary)
            return backing, True
        except OSError as error:
            if getattr(error, 'winerror', None) != 1142:
                raise
    raise ValueError('Consumer backing selection exceeds its declared bound')


def compact_file(source, expected, store, scratch, retire_link_limit_copy=False,
                 preserve_link_limit_paths=False):
    guard(store, expected["size"])
    validate(source, expected)
    blob = object_path(store, expected["sha256"])
    blob.parent.mkdir(parents=True, exist_ok=True)
    if not blob.exists():
        os.link(source, blob)
    validate(blob, expected)
    # Keep canonical bytes immutable. Restoration makes writable independent files.
    blob.chmod(stat.S_IREAD)
    restored = owned(scratch, "restored.bin")
    try:
        restore_file(blob, restored, expected)
        # A second source checksum covers changes during restoration.
        validate(source, expected)
        if os.path.samefile(source, blob):
            return {"redundant_copy_removed": False, "reclaimed_allocation_bytes": 0,
                    "restored_sha256": expected["sha256"], "restored_size": expected["size"]}
        previous = source.stat()
        reclaim = allocation(source) if previous.st_nlink == 1 else 0
        guard(store)
        temporary = source.with_name(source.name + ".packet-link")
        if temporary.exists():
            raise ValueError("Unexpected existing link temporary: " + str(temporary))
        backing = blob
        try:
            try:
                os.link(blob, temporary)
            except OSError as error:
                if preserve_link_limit_paths and getattr(error, "winerror", None) == 1142:
                    backing, replacement = consumer_link(source, temporary, expected, store)
                    if not replacement:
                        return {"redundant_copy_removed": False, "reclaimed_allocation_bytes": 0,
                                "consumer_backing": str(backing.relative_to(store)),
                                "backing_reason": "NTFS link ceiling; required original consumer paths",
                                "restored_sha256": expected["sha256"], "restored_size": expected["size"]}
                else:
                    if not retire_link_limit_copy or getattr(error, "winerror", None) != 1142:
                        raise
                # Only opt in after consumers can resolve the retained packet.
                # The canonical bytes and independent restoration were verified
                # above; recheck the original immediately before retiring it.
                    validate(source, expected)
                    source.chmod(stat.S_IREAD | stat.S_IWRITE)
                    source.unlink()
                    return {"redundant_copy_removed": True,
                        "reclaimed_allocation_bytes": reclaim,
                        "original_path_retired": True,
                        "retirement_reason": "Windows hard-link limit; resolve through version manifest",
                        "restored_sha256": expected["sha256"], "restored_size": expected["size"]}
            # Windows needs write permission to remove an older read-only copy.
            source.chmod(stat.S_IREAD | stat.S_IWRITE)
            os.replace(temporary, source)
        finally:
            if temporary.exists():
                temporary.unlink()
        if not os.path.samefile(source, backing):
            raise ValueError("Replacement did not resolve the canonical object")
        validate(source, expected)
        result = {"redundant_copy_removed": True, "reclaimed_allocation_bytes": reclaim,
                  "restored_sha256": expected["sha256"], "restored_size": expected["size"]}
        if backing != blob:
            result.update(consumer_backing=str(backing.relative_to(store)),
                          backing_reason="NTFS link ceiling; required original consumer paths")
        return result
    finally:
        if restored.exists():
            restored.unlink()


def chain_hash(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def journal_state(path, identity, retired_paths=None, consumer_backings=None):
    last = "0" * 64
    completed = {}
    count = removed = reclaimed = 0
    if not path.exists():
        return last, completed, count, removed, reclaimed
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            sha = row.pop("chain_sha256")
            if row["previous_sha256"] != last or sha != chain_hash(row) or row["plan_sha256"] != identity:
                raise ValueError("Receipt chain does not authenticate this plan")
            if row["item"] != completed.get(row["version"], -1) + 1:
                raise ValueError("Receipt chain skips or repeats a file")
            completed[row["version"]] = row["item"]
            if retired_paths is not None and row.get("original_path_retired"):
                retired_paths.add((row["version"], row["item"]))
            if consumer_backings is not None and row.get('consumer_backing'):
                consumer_backings[row['version'], row['item']] = row['consumer_backing']
            count += 1
            removed += int(row["redundant_copy_removed"])
            reclaimed += row["reclaimed_allocation_bytes"]
            last = sha
    return last, completed, count, removed, reclaimed


def compact(plan_path, store, packet, wait_for_resources=False, retire_link_limit_copies=False,
            preserve_link_limit_paths=False):
    if retire_link_limit_copies and preserve_link_limit_paths:
        raise ValueError('Choose retirement or preservation, not both')
    plan_path, store, packet = Path(plan_path), Path(store).resolve(), Path(packet).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    store.mkdir(parents=True, exist_ok=True)
    packet.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            guard(store, plan["peak_temporary_bytes"])
            break
        except ResourcePause as pause:
            if not wait_for_resources:
                raise
            print(json.dumps({"status": "resource-paused", "reason": str(pause)}), flush=True)
            time.sleep(5)
    identity = digest(plan_path)
    journal = packet / "cleanup-chain.jsonl.gz"
    retired_paths = set()
    consumer_backings = {}
    last, completed, count, removed, reclaimed = journal_state(journal, identity, retired_paths, consumer_backings)
    scratch = store / "restore-test-scratch"
    scratch.mkdir(exist_ok=True)
    if any(scratch.iterdir()):
        raise ValueError("Restore scratch contains unverified prior files")
    producer = digest(Path(__file__))
    previous_path = packet / "run.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    producer_paths = dict(previous.get("producer_paths", {}))
    old = previous.get("producer_sha256")
    if old and old not in producer_paths:
        original = packet / "producer.py"
        if not original.exists() or digest(original) != old:
            raise ValueError("Previous producing code is not recoverable")
        producer_paths[old] = original.name
    if producer not in producer_paths:
        recipe = packet / ("producer-" + producer[:12] + ".py")
        if not recipe.exists():
            shutil.copyfile(__file__, recipe)
        if digest(recipe) != producer:
            raise ValueError("Frozen producer differs")
        producer_paths[producer] = recipe.name
    if previous:
        with gzip.open(packet / "execution-history.jsonl.gz", "at", encoding="utf-8") as history:
            history.write(json.dumps(previous, sort_keys=True, separators=(",", ":")) + "\n")
    receipt = {"schema_version": 1, "plan_sha256": identity, "command": sys.argv,
               "settings": {"minimum_free_ram_bytes": RAM_FLOOR, "block_bytes": BLOCK,
                            "wait_for_resources": wait_for_resources,
                            "retire_link_limit_copies": retire_link_limit_copies,
                            "preserve_link_limit_paths": preserve_link_limit_paths},
               "versions": {"python": sys.version}, "producer_sha256": producer,
               "producer_paths": producer_paths,
               "status": "running", "source_files_verified": count,
               "redundant_copies_removed": removed, "reclaimed_allocation_bytes": reclaimed,
               "free_disk_before": shutil.disk_usage(store).free,
               "scientific_tolerances_changed": False, "scientific_cases_rerun": 0,
               "failures": [], "undefined_results": "unchanged in original scientific receipts",
               "unresolved_differences": "preserved; storage compaction makes no scientific approval",
               "original_receipts": plan["versions"]}
    atomic_json(packet / "run.json", receipt)
    try:
        for version in plan["versions"]:
            manifest = packet / version["manifest"]
            if digest(manifest) != version["manifest_sha256"]:
                raise ValueError("Per-version manifest changed")
            terminal = Path(version["terminal_receipt"])
            if digest(terminal) != version["terminal_receipt_sha256"]:
                raise ValueError("Terminal receipt changed")
            total = 0
            # Independent gzip members are closed/fsynced every 100 verified files.
            writer = None
            try:
                for item, expected in enumerate(entries(manifest)):
                    total += 1
                    source = owned(version["snapshot"], expected["path"])
                    if item <= completed.get(version["id"], -1):
                        blob = object_path(store, expected["sha256"])
                        while True:
                            try:
                                if (version["id"], item) in retired_paths:
                                    validate(blob, expected)
                                    if source.exists():
                                        raise ValueError("Retired source path unexpectedly exists")
                                else:
                                    validate(source, expected)
                                    backing = blob
                                    if (version['id'], item) in consumer_backings:
                                        validate(blob, expected)
                                        backing = owned(store, consumer_backings[version['id'], item])
                                    if not os.path.samefile(source, backing):
                                        raise ValueError("Completed checkpoint no longer resolves its object")
                                break
                            except ResourcePause:
                                if not wait_for_resources:
                                    raise
                                receipt.update(status="resource-paused", passed=False,
                                               pause_reason="Available RAM is below 4 GiB during checkpoint verification")
                                atomic_json(packet / "run.json", receipt)
                                time.sleep(5)
                        continue
                    while True:
                        try:
                            if retire_link_limit_copies:
                                # Recover a verified original if interruption
                                # occurred between retirement and chain append.
                                if not source.exists():
                                    blob = object_path(store, expected["sha256"])
                                    validate(blob, expected)
                                    restore_file(blob, source, expected)
                                result = compact_file(source, expected, store, scratch, True)
                            elif preserve_link_limit_paths:
                                result = compact_file(source, expected, store, scratch,
                                                      preserve_link_limit_paths=True)
                            else:
                                result = compact_file(source, expected, store, scratch)
                            break
                        except ResourcePause as pause:
                            if writer is not None:
                                writer.close()
                                writer = None
                            receipt.update(status="resource-paused", passed=False,
                                           pause_reason=str(pause), source_files_verified=count,
                                           redundant_copies_removed=removed,
                                           reclaimed_allocation_bytes=reclaimed,
                                           last_chain_sha256=last)
                            atomic_json(packet / "run.json", receipt)
                            if not wait_for_resources:
                                raise
                            print(json.dumps({"status": "resource-paused", "files_verified": count,
                                              "reason": str(pause)}), flush=True)
                            while True:
                                time.sleep(5)
                                try:
                                    guard(store, expected["size"])
                                except ResourcePause:
                                    continue
                                break
                            # The failed pending file is reverified from its
                            # original bytes; completed chained proofs stay done.
                            receipt.update(status="running", passed=False)
                            atomic_json(packet / "run.json", receipt)
                    row = dict(result, version=version["id"], item=item,
                               path=expected["path"], sha256=expected["sha256"], size=expected["size"],
                               plan_sha256=identity, previous_sha256=last, producer_sha256=producer)
                    last = chain_hash(row)
                    row["chain_sha256"] = last
                    if writer is None:
                        writer = gzip.open(journal, "at", encoding="utf-8")
                    writer.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
                    count += 1
                    removed += int(result["redundant_copy_removed"])
                    reclaimed += result["reclaimed_allocation_bytes"]
                    if result.get("original_path_retired"):
                        retired_paths.add((version["id"], item))
                    if count % 100 == 0:
                        writer.close()
                        writer = None
                        receipt.update(source_files_verified=count, redundant_copies_removed=removed,
                                       reclaimed_allocation_bytes=reclaimed, last_chain_sha256=last)
                        atomic_json(packet / "run.json", receipt)
                    if count % 1000 == 0:
                        print(json.dumps({"files_verified": count, "redundant_copies_removed": removed,
                                          "reclaimed_allocation_bytes": reclaimed}), flush=True)
                if total != version["files"]:
                    raise ValueError("Manifest case count changed")
            finally:
                if writer is not None:
                    writer.close()
        receipt.update(status="finished", passed=True)
    except ResourcePause as error:
        receipt.update(status="resource-paused", passed=False, pause_reason=str(error))
    except BaseException as error:
        receipt.update(status="failed", passed=False,
                       failures=[type(error).__name__ + ": " + str(error)])
        raise
    finally:
        scratch.rmdir()
        receipt.update(source_files_verified=count, redundant_copies_removed=removed,
                       reclaimed_allocation_bytes=reclaimed, last_chain_sha256=last,
                       original_paths_retired=len(retired_paths),
                       free_disk_after=shutil.disk_usage(store).free,
                       cleanup={"restore_scratch_absent": not scratch.exists(),
                                "original_paths_resolve": not retired_paths if receipt["status"] != "failed" else None,
                                "retired_path_index": "cleanup-chain.jsonl.gz: original_path_retired records; version manifests reconstruct these paths"},
                       finished_at=datetime.now(timezone.utc).isoformat())
        atomic_json(packet / "run.json", receipt)
    return receipt


def restore(manifest, store, target, directories=None):
    target = Path(target)
    if target.exists():
        raise ValueError("Restore target must not exist")
    directory_rows = []
    if directories is not None:
        memory_guard()
        for count, item in enumerate(entries(directories), 1):
            if count > 20000 or item.get('kind') != 'directory':
                raise ValueError('Invalid or oversized directory-state manifest')
            owned(target, item['path'])
            directory_rows.append(item)
    guard(Path(store), sum(item["size"] for item in entries(manifest)))
    target.mkdir(parents=True)
    for item in entries(manifest):
        path = owned(target, item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        restore_file(object_path(store, item["sha256"]), path, item)
    for item in directory_rows:
        memory_guard()
        owned(target, item['path']).mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    pack = sub.add_parser("sources")
    pack.add_argument("--plan", type=Path, required=True)
    pack.add_argument("--store", type=Path, required=True)
    pack.add_argument("--packet", type=Path, required=True)
    pack.add_argument("--wait-for-resources", action="store_true")
    pack.add_argument("--retire-link-limit-copies", action="store_true",
                      help="Only after all consumers can resolve the retained packet: retire verified originals when Windows cannot add another hard link")
    unpack = sub.add_parser("restore")
    unpack.add_argument("--manifest", type=Path, required=True)
    unpack.add_argument("--store", type=Path, required=True)
    unpack.add_argument("--target", type=Path, required=True)
    unpack.add_argument("--directories", type=Path,
                        help="Optional bounded directory-state manifest retained with a version")
    args = parser.parse_args()
    if args.action == "sources":
        result = compact(args.plan, args.store, args.packet, args.wait_for_resources,
                         args.retire_link_limit_copies)
        print(json.dumps({key: value for key, value in result.items()
                          if key not in {"original_receipts", "command", "versions"}}), flush=True)
        return 0 if result["passed"] else 75
    restore(args.manifest, args.store, args.target, args.directories)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
