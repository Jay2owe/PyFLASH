"""Losslessly compress a bounded explicit historical review list, preserving paths."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from reproducibility.compact_evidence import (
    ResourcePause, allocation, atomic_json, digest, guard, owned, restore_file,
)

NAMES = (
    "build-alias-review.log",
    "build-isolation-review.log",
    "build-uv-review.log",
    "inherited-spatial-permanent-20261008-v1.log",
    "inherited-spatial-permanent-20261008-v1.xml",
    "whole-marker-cleaning-legacy-domain-private-20261008-v2.console.log",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--file-list", type=Path,
                        help="JSON list of at most 20 paths relative to the PyFLASH validation cache")
    args = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("This recipe requires NTFS compression on Windows")
    base = Path(os.environ["LOCALAPPDATA"]) / "PyFLASH"
    packet = args.packet.resolve()
    store = Path(os.environ["LOCALAPPDATA"]) / "PyFLASH-evidence"
    packet.mkdir(parents=True, exist_ok=True)
    store.mkdir(parents=True, exist_ok=True)
    names = json.loads(args.file_list.read_text(encoding="utf-8")) if args.file_list else list(NAMES)
    if not isinstance(names, list) or not 0 < len(names) <= 20 or not all(isinstance(n, str) for n in names):
        raise ValueError("Review selection must contain 1 to 20 explicit relative paths")
    if len(set(names)) != len(names):
        raise ValueError("Review selection repeats a path")
    paths = [owned(base, name) for name in names]
    selection_sha = digest(args.file_list) if args.file_list else None
    guard(store, max(p.stat().st_size for p in paths))
    receipt_path = packet / "run.json"
    previous = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else None
    producer = digest(Path(__file__))
    if previous and previous["producer_sha256"] != producer:
        raise ValueError("Review producer changed; preserve the earlier receipt")
    if previous and previous.get("selection_sha256") != selection_sha:
        raise ValueError("Review selection changed; preserve the earlier receipt")
    recipe = packet / "producer.py"
    if not recipe.exists():
        shutil.copyfile(__file__, recipe)
    elif digest(recipe) != producer:
        raise ValueError("Frozen review recipe changed")
    rows = list(previous["rows"]) if previous else []
    scratch = store / "review-restore-scratch"
    scratch.mkdir(exist_ok=True)
    if any(scratch.iterdir()):
        raise ValueError("Review scratch contains unexpected files")
    receipt = {"schema_version": 1, "command": sys.argv, "producer_sha256": producer,
               "helper_sha256": digest(Path(__file__).with_name("compact_evidence.py")),
               "selection_sha256": selection_sha,
               "selected_relative_paths": names,
               "settings": {"minimum_free_ram_bytes": 4 * 1024**3, "lossless": True},
               "versions": {"python": sys.version, "windows": str(sys.getwindowsversion())},
               "rows": rows, "status": "running", "files_deleted": 0,
               "scope": "Historical reviews only; preserve original paths and unresolved diagnostics"}
    try:
        for path in paths:
            prior = next((row for row in rows if row["path"] == str(path)), None)
            if prior:
                if digest(path, True) != prior["sha256"] or path.stat().st_size != prior["size"]:
                    raise ValueError("Completed review checkpoint changed")
                continue
            guard(store, path.stat().st_size)
            expected = {"sha256": digest(path, True), "size": path.stat().st_size}
            before = allocation(path)
            command = ["compact.exe", "/C", "/I", "/Q", str(path)]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            if digest(path, True) != expected["sha256"] or path.stat().st_size != expected["size"]:
                raise ValueError("Compression changed bytes")
            restored = owned(scratch, "review.bin")
            try:
                restore_file(path, restored, expected)
            finally:
                if restored.exists():
                    restored.unlink()
            after = allocation(path)
            rows.append({"path": str(path), **expected, "command": command, "returncode": result.returncode,
                         "output_excerpt": result.stdout[-1000:], "restoration_verified": True,
                         "allocated_before": before, "allocated_after": after,
                         "recovered_allocation_bytes": before - after})
            atomic_json(receipt_path, receipt)
        receipt.update(status="finished", passed=True)
    except ResourcePause as error:
        receipt.update(status="resource-paused", passed=False, reason=str(error))
    except BaseException as error:
        receipt.update(status="failed", passed=False, error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        scratch.rmdir()
        receipt.update(finished_at=datetime.now(timezone.utc).isoformat(),
                       restored_scratch_absent=not scratch.exists(),
                       recovered_allocation_bytes=sum(row["recovered_allocation_bytes"] for row in rows))
        atomic_json(receipt_path, receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k not in ("rows", "command", "versions")}))
    return 0 if receipt["passed"] else 75


if __name__ == "__main__":
    raise SystemExit(main())
