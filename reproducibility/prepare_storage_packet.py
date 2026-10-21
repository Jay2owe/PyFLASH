"""Prepare a bounded source list from three pre-existing allocation/hash audits.

This only reads explicit source metadata and small terminal receipts. It does not
scan a drive, delete a file, or count current scientific coverage.
"""
from pathlib import Path
import argparse
import gzip
import json
import os
import platform
import sys

from reproducibility.compact_evidence import atomic_json, digest, entries, guard, memory_guard, owned, ResourcePause


AUDITS = (
    "terminal-source-snapshot-compression-20261010-v1",
    "terminal-source-snapshot-compression-20261010-v2",
    "terminal-source-snapshot-compression-20261010-v3",
)


def build_plan(base, packet, store):
    import ijson
    base, packet = Path(base).resolve(), Path(packet).resolve()
    packet.mkdir(parents=True, exist_ok=True)
    guard(packet)
    if (packet / "plan.json").exists():
        plan = json.loads((packet / "plan.json").read_text(encoding="utf-8"))
        for version in plan["versions"]:
            if (digest(packet / version["manifest"]) != version["manifest_sha256"] or
                    digest(version["terminal_receipt"]) != version["terminal_receipt_sha256"]):
                raise ValueError("Completed preparation checkpoint changed")
        return plan
    versions, audits = [], []
    largest = 0
    for audit_name in AUDITS:
        guard(packet)
        audit = base / audit_name / "run.json"
        audits.append({"path": str(audit), "sha256": digest(audit)})
        with audit.open("rb") as stream:
            for row in ijson.items(stream, "rows.item"):
                if not row["all_byte_hashes_unchanged"] or not row["all_paths_preserved"]:
                    raise ValueError("Prior source identity audit did not pass")
                source = Path(row["snapshot"]).resolve()
                source.relative_to(base)
                terminal = Path(row["terminal_receipt"]).resolve()
                terminal.relative_to(base)
                if digest(terminal) != row["terminal_receipt_sha256"]:
                    raise ValueError("Terminal receipt changed since the recorded audit")
                if len(row["source_hashes"]) != row["files"] or row["files"] > 20000:
                    raise ValueError("Prior audit file list is incomplete or exceeds the bound")
                key = "version-" + str(len(versions) + 1)
                manifest = packet / (key + ".jsonl.gz")
                temporary = packet / (key + ".partial.gz")
                logical_bytes = 0
                try:
                    if manifest.exists():
                        # Existing closed manifests are verified checkpoints.
                        # Match all recorded paths/hashes to the original audit.
                        for previous, (name, sha) in zip(entries(manifest), sorted(row["source_hashes"].items()), strict=True):
                            memory_guard()
                            if previous["path"] != name or previous["sha256"] != sha or previous["size"] < 0:
                                raise ValueError("Prepared manifest does not match its source audit")
                            logical_bytes += previous["size"]
                            largest = max(largest, previous["size"])
                    else:
                        with gzip.open(temporary, "wt", encoding="utf-8") as output:
                            for name, sha in sorted(row["source_hashes"].items()):
                                memory_guard()
                                path = owned(source, name)
                                size = path.stat().st_size
                                largest = max(largest, size)
                                logical_bytes += size
                                output.write(json.dumps({"path": name, "sha256": sha, "size": size},
                                                        sort_keys=True, separators=(",", ":")) + "\n")
                        os.replace(temporary, manifest)
                finally:
                    if temporary.exists():
                        temporary.unlink()
                versions.append({"id": key, "snapshot": str(source), "files": row["files"],
                                 "logical_bytes": logical_bytes, "manifest": manifest.name,
                                 "manifest_sha256": digest(manifest), "terminal_receipt": str(terminal),
                                 "terminal_receipt_sha256": row["terminal_receipt_sha256"],
                                 "audit_receipt": str(audit), "audit_receipt_sha256": digest(audit)})
                atomic_json(packet / "preparation.json", {
                    "status": "checkpoint", "versions": versions,
                    "peak_temporary_bytes": largest, "audits": audits})
                print(json.dumps({"version": key, "files": row["files"],
                                  "logical_bytes": logical_bytes}), flush=True)
    plan = {"schema_version": 1, "command": sys.argv, "versions": versions, "audits": audits,
            "tools": {"python": platform.python_version(), "ijson": ijson.__version__},
            "store": str(Path(store).resolve()), "peak_temporary_bytes": largest,
            "scope": "Six terminal source copies from existing authenticated audits; preserve all paths, "
                     "scientific outputs, failures and runtimes; replace only restored byte-identical copies"}
    atomic_json(packet / "plan.json", plan)
    print(json.dumps({"versions": len(versions), "files": sum(v["files"] for v in versions),
                      "peak_temporary_bytes": largest, "plan_sha256": digest(packet / "plan.json")}))
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    args = parser.parse_args()
    base = (Path(os.environ["LOCALAPPDATA"]) / "PyFLASH").resolve()
    try:
        build_plan(base, args.packet, args.store)
    except ResourcePause as error:
        print(json.dumps({"status": "resource-paused", "reason": str(error)}), flush=True)
        return 75
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
