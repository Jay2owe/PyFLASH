import gzip
import json
import os
import subprocess
from pathlib import Path

import pytest

from reproducibility import compact_evidence as c


@pytest.mark.skipif(os.name != "nt", reason="Windows receipt sharing semantics")
@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_receipt_replacement_recovers_transient_windows_denial(tmp_path, monkeypatch, winerror):
    target = tmp_path / "run.json"
    target.write_text('{"status":"old"}')
    replace = c.os.replace
    attempts = []
    def temporarily_locked(source, destination):
        if Path(destination) == target and len(attempts) < 2:
            attempts.append(1)
            assert json.loads(target.read_text()) == {"status": "old"}
            error = PermissionError("Sharing denial")
            error.winerror = winerror
            raise error
        return replace(source, destination)
    monkeypatch.setattr(c.os, "replace", temporarily_locked)
    monkeypatch.setattr(c.time, "sleep", lambda delay: None)
    c.atomic_json(target, {"status": "new"})
    assert json.loads(target.read_text()) == {"status": "new"}
    assert not list(tmp_path.glob(".receipt-*"))


def test_permanent_receipt_denial_preserves_previous_bytes(tmp_path, monkeypatch):
    target = tmp_path / "run.json"
    original = b'{"status":"old"}\n'
    target.write_bytes(original)
    def denied(*args):
        error = PermissionError("Permanent permission denial")
        error.winerror = 5
        raise error
    monkeypatch.setattr(c.os, "replace", denied)
    monkeypatch.setattr(c.time, "sleep", lambda delay: None)
    with pytest.raises(PermissionError, match="Permanent"):
        c.atomic_json(target, {"status": "new"})
    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".receipt-*"))


def test_non_windows_receipt_error_is_not_retried(tmp_path, monkeypatch):
    calls = []
    def denied(*args):
        calls.append(1)
        raise PermissionError("Unclassified permission denial")
    monkeypatch.setattr(c.os, "replace", denied)
    with pytest.raises(PermissionError, match="Unclassified"):
        c.atomic_json(tmp_path / "run.json", {})
    assert len(calls) == 1


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows open-handle sharing")
def test_receipt_replacement_waits_for_native_reader_to_release(tmp_path):
    import ctypes
    from ctypes import wintypes
    import threading
    target = tmp_path / "run.json"
    target.write_text('{"status":"old"}')
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    handle = api.CreateFileW(str(target), 0x80000000, 1, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    closed = []
    timer = threading.Timer(0.15, lambda: closed.append(bool(api.CloseHandle(handle))))
    timer.start()
    try:
        c.atomic_json(target, {"status": "new"})
    finally:
        timer.join()
    assert closed == [True]
    assert json.loads(target.read_text()) == {"status": "new"}
    assert not list(tmp_path.glob(".receipt-*"))


def write_plan(tmp_path, versions):
    packet = tmp_path / "packet"
    packet.mkdir()
    rows = []
    for number, (root, payload) in enumerate(versions):
        root.mkdir()
        (root / "code.py").write_bytes(payload)
        terminal = root / "run.json"
        terminal.write_text('{"status":"finished"}')
        manifest = packet / f"version-{number}.jsonl.gz"
        record = {"path": "code.py", "sha256": c.digest(root / "code.py"), "size": len(payload)}
        with gzip.open(manifest, "wt") as stream:
            stream.write(json.dumps(record) + "\n")
        rows.append({"id": str(number), "snapshot": str(root), "files": 1,
                     "manifest": manifest.name, "manifest_sha256": c.digest(manifest),
                     "terminal_receipt": str(terminal), "terminal_receipt_sha256": c.digest(terminal)})
    plan = packet / "plan.json"
    c.atomic_json(plan, {"versions": rows, "peak_temporary_bytes": 100})
    return plan, packet, tmp_path / "store"


@pytest.fixture(autouse=True)
def sufficient_ram(monkeypatch):
    monkeypatch.setattr(c, "available_ram", lambda: c.RAM_FLOOR + 1024**3)


def test_deduplicates_identical_code_and_restores_independent_bytes(tmp_path):
    first, second = tmp_path / "v1", tmp_path / "v2"
    plan, packet, store = write_plan(tmp_path, [(first, b"print(1)\n"), (second, b"print(1)\n")])
    result = c.compact(plan, store, packet)
    assert result["passed"] and result["redundant_copies_removed"] == 1
    assert (first / "code.py").samefile(second / "code.py")
    restored = tmp_path / "restored"
    c.restore(packet / "version-1.jsonl.gz", store, restored)
    assert (restored / "code.py").read_bytes() == b"print(1)\n"
    assert not (restored / "code.py").samefile(second / "code.py")
    repeated = c.compact(plan, store, packet)
    assert repeated["source_files_verified"] == 2 and repeated["redundant_copies_removed"] == 1


def test_different_versions_keep_distinct_objects(tmp_path):
    first, second = tmp_path / "v1", tmp_path / "v2"
    plan, packet, store = write_plan(tmp_path, [(first, b"a"), (second, b"b")])
    c.compact(plan, store, packet)
    assert not (first / "code.py").samefile(second / "code.py")


def test_link_limit_retirement_is_opt_in_recoverable_and_resumable(tmp_path, monkeypatch):
    first, second = tmp_path / "v1", tmp_path / "v2"
    plan, packet, store = write_plan(tmp_path, [(first, b"same"), (second, b"same")])
    original_link = c.os.link
    def limited_link(source, target):
        if str(target).endswith('.packet-link'):
            error = OSError('Windows hard-link limit')
            error.winerror = 1142
            raise error
        return original_link(source, target)
    monkeypatch.setattr(c.os, 'link', limited_link)
    with pytest.raises(OSError):
        c.compact(plan, store, packet)
    assert (second / 'code.py').read_bytes() == b'same'
    result = c.compact(plan, store, packet, retire_link_limit_copies=True)
    assert result['passed'] and result['original_paths_retired'] == 1
    assert not (second / 'code.py').exists()
    assert c.compact(plan, store, packet, retire_link_limit_copies=True)['passed']
    restored = tmp_path / 'restored'
    c.restore(packet / 'version-1.jsonl.gz', store, restored)
    assert (restored / 'code.py').read_bytes() == b'same'


def test_restore_file_does_not_delete_an_existing_target(tmp_path):
    blob, target = tmp_path / 'blob', tmp_path / 'existing'
    blob.write_bytes(b'expected')
    target.write_bytes(b'keep')
    expected = {'size': 8, 'sha256': c.digest(blob)}
    with pytest.raises(FileExistsError):
        c.restore_file(blob, target, expected)
    assert target.read_bytes() == b'keep'


def test_link_ceiling_preserves_paths_reuses_backing_and_resumes(tmp_path, monkeypatch):
    roots = [tmp_path / ('v' + str(i)) for i in range(4)]
    plan, packet, store = write_plan(tmp_path, [(root, b'same') for root in roots])
    real_link = c.os.link
    def limited_link(source, target):
        if str(target).endswith('.packet-link') and Path(source).parent.parent.name == 'objects':
            error = OSError('Windows hard-link limit')
            error.winerror = 1142
            raise error
        return real_link(source, target)
    monkeypatch.setattr(c.os, 'link', limited_link)
    result = c.compact(plan, store, packet, preserve_link_limit_paths=True)
    assert result['passed'] and result['original_paths_retired'] == 0
    assert result['redundant_copies_removed'] == 2
    assert all((root / 'code.py').read_bytes() == b'same' for root in roots)
    assert (roots[1] / 'code.py').samefile(roots[3] / 'code.py')
    backings = list((store / 'consumer-links').rglob('*.bin'))
    assert len(backings) == 1
    assert not backings[0].samefile(roots[0] / 'code.py')
    assert c.compact(plan, store, packet, preserve_link_limit_paths=True)['passed']
    restored = tmp_path / 'restored-overflow'
    c.restore(packet / 'version-3.jsonl.gz', store, restored)
    assert (restored / 'code.py').read_bytes() == b'same'
    assert not (restored / 'code.py').samefile(backings[0])


def test_non_ceiling_link_error_never_uses_an_overflow_backing(tmp_path, monkeypatch):
    plan, packet, store = write_plan(tmp_path, [(tmp_path / 'v1', b'same'), (tmp_path / 'v2', b'same')])
    real_link = c.os.link
    def denied(source, target):
        if str(target).endswith('.packet-link'):
            raise PermissionError('Denied')
        return real_link(source, target)
    monkeypatch.setattr(c.os, 'link', denied)
    with pytest.raises(PermissionError):
        c.compact(plan, store, packet, preserve_link_limit_paths=True)
    assert not (store / 'consumer-links').exists()
    assert (tmp_path / 'v2' / 'code.py').read_bytes() == b'same'


def test_interrupted_retirement_before_chain_append_recovers_pending_original(tmp_path, monkeypatch):
    first, second = tmp_path / 'v1', tmp_path / 'v2'
    plan, packet, store = write_plan(tmp_path, [(first, b'same'), (second, b'same')])
    real_compact = c.compact_file
    real_link = c.os.link
    def limited_link(source, target):
        if str(target).endswith('.packet-link'):
            error = OSError('Windows hard-link limit')
            error.winerror = 1142
            raise error
        return real_link(source, target)
    def interrupted(*args):
        result = real_compact(*args)
        if result.get('original_path_retired'):
            raise c.ResourcePause('interrupted before chain append')
        return result
    monkeypatch.setattr(c.os, 'link', limited_link)
    monkeypatch.setattr(c, 'compact_file', interrupted)
    result = c.compact(plan, store, packet, retire_link_limit_copies=True)
    assert result['status'] == 'resource-paused'
    assert result['source_files_verified'] == 1
    assert not (second / 'code.py').exists()
    monkeypatch.setattr(c, 'compact_file', real_compact)
    result = c.compact(plan, store, packet, retire_link_limit_copies=True)
    assert result['passed'] and result['source_files_verified'] == 2
    assert result['original_paths_retired'] == 1
    restored = tmp_path / 'restored'
    c.restore(packet / 'version-1.jsonl.gz', store, restored)
    assert (restored / 'code.py').read_bytes() == b'same'


def test_changed_source_is_preserved_and_not_deleted(tmp_path):
    root = tmp_path / "v1"
    plan, packet, store = write_plan(tmp_path, [(root, b"old")])
    (root / "code.py").write_bytes(b"new")
    with pytest.raises(ValueError, match="Bytes differ"):
        c.compact(plan, store, packet)
    assert (root / "code.py").read_bytes() == b"new"
    assert json.loads((packet / "run.json").read_text())["status"] == "failed"


def test_corrupt_canonical_object_cannot_replace_source(tmp_path):
    root = tmp_path / "v1"
    plan, packet, store = write_plan(tmp_path, [(root, b"correct")])
    expected = next(c.entries(packet / "version-0.jsonl.gz"))
    blob = c.object_path(store, expected["sha256"])
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Bytes differ"):
        c.compact(plan, store, packet)
    assert (root / "code.py").read_bytes() == b"correct"


def test_memory_pause_after_checkpoint_can_resume(tmp_path, monkeypatch):
    first, second = tmp_path / "v1", tmp_path / "v2"
    plan, packet, store = write_plan(tmp_path, [(first, b"code"), (second, b"code")])
    real = c.compact_file
    calls = 0
    def pause_after_first(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise c.ResourcePause("RAM floor")
        return real(*args)
    monkeypatch.setattr(c, "compact_file", pause_after_first)
    result = c.compact(plan, store, packet)
    assert result["status"] == "resource-paused" and result["source_files_verified"] == 1
    assert not (store / "restore-test-scratch").exists()
    monkeypatch.setattr(c, "compact_file", real)
    assert c.compact(plan, store, packet)["passed"]


def test_waiting_for_resources_retries_only_the_pending_file(tmp_path, monkeypatch):
    first, second = tmp_path / "v1", tmp_path / "v2"
    plan, packet, store = write_plan(tmp_path, [(first, b"code"), (second, b"code")])
    real = c.compact_file
    calls = []
    def interrupted(source, *args):
        calls.append(source.parent.name)
        if len(calls) == 2:
            raise c.ResourcePause("temporary RAM pressure")
        return real(source, *args)
    monkeypatch.setattr(c, "compact_file", interrupted)
    monkeypatch.setattr(c.time, "sleep", lambda seconds: None)
    assert c.compact(plan, store, packet, wait_for_resources=True)["passed"]
    assert calls == ["v1", "v2", "v2"]


def test_waits_at_initial_preflight_before_any_source_processing(tmp_path, monkeypatch):
    plan, packet, store = write_plan(tmp_path, [(tmp_path / "v1", b"code")])
    readings = iter((0, c.RAM_FLOOR + 1024**3))
    last = c.RAM_FLOOR + 1024**3
    monkeypatch.setattr(c, "available_ram", lambda: next(readings, last))
    sleeps = []
    monkeypatch.setattr(c.time, "sleep", lambda seconds: sleeps.append(seconds))
    assert c.compact(plan, store, packet, wait_for_resources=True)["passed"]
    assert sleeps == [5]


def test_refuses_path_escape_and_existing_restore_target(tmp_path):
    with pytest.raises(ValueError, match="Unsafe"):
        c.owned(tmp_path, "../outside")
    with pytest.raises(ValueError, match="must not exist"):
        c.restore("irrelevant", tmp_path, tmp_path)


def test_corrupt_receipt_chain_prevents_resume(tmp_path):
    plan, packet, store = write_plan(tmp_path, [(tmp_path / "v1", b"code")])
    c.compact(plan, store, packet)
    journal = packet / "cleanup-chain.jsonl.gz"
    with gzip.open(journal, "wt") as output:
        output.write('{"chain_sha256":"corrupt","previous_sha256":"bad"}\n')
    with pytest.raises((ValueError, KeyError)):
        c.compact(plan, store, packet)


def test_refuses_symlinked_parent(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / "redirect").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links needs an OS privilege")
    with pytest.raises(ValueError):
        c.owned(root, "redirect/file.py")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_refuses_windows_junctioned_parent(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(root / "redirect"), str(outside)],
                   check=True, capture_output=True)
    with pytest.raises(ValueError):
        c.owned(root, "redirect/file.py")
    # rmdir removes the empty junction itself, never traverses its target.
    (root / "redirect").rmdir()


def test_preparation_reuses_verified_manifest_without_restatting_source(tmp_path, monkeypatch):
    from reproducibility import prepare_storage_packet as p
    base, packet = tmp_path / "base", tmp_path / "packet"
    base.mkdir()
    snapshot = base / "completed" / "sources"
    snapshot.mkdir(parents=True)
    source = snapshot / "code.py"
    source.write_bytes(b"frozen")
    terminal = snapshot.parent / "summary.json"
    terminal.write_text('{"passed":true}')
    audit = base / "audit"
    audit.mkdir()
    row = {"all_byte_hashes_unchanged": True, "all_paths_preserved": True,
           "snapshot": str(snapshot), "terminal_receipt": str(terminal),
           "terminal_receipt_sha256": c.digest(terminal), "files": 1,
           "source_hashes": {"code.py": c.digest(source)}}
    c.atomic_json(audit / "run.json", {"rows": [row]})
    monkeypatch.setattr(p, "AUDITS", ("audit",))
    plan = p.build_plan(base, packet, tmp_path / "store")
    assert plan["versions"][0]["files"] == 1
    # Simulate a pause after a complete manifest but before the final plan write.
    (packet / "plan.json").unlink()
    def no_source_reads(*args):
        raise AssertionError("Completed metadata was scanned again")
    monkeypatch.setattr(p, "owned", no_source_reads)
    resumed = p.build_plan(base, packet, tmp_path / "store")
    assert resumed["versions"][0]["manifest_sha256"] == plan["versions"][0]["manifest_sha256"]
