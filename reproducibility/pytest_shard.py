"""Stable, dependency-free pytest partitioning for complete local runs."""
from __future__ import annotations

import json
import os
from pathlib import Path


def partition_nodeids(nodeids, workers: int) -> dict[str, int]:
    """Balance whole test modules across shards, preserving their test order."""
    modules = {}
    for nodeid in nodeids:
        module = nodeid.split('::', 1)[0]
        modules.setdefault(module, []).append(nodeid)
    loads = [0] * workers
    assignment = {}
    for module, members in sorted(modules.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        index = min(range(workers), key=lambda candidate: (loads[candidate], candidate))
        loads[index] += len(members)
        for nodeid in members:
            assignment[nodeid] = index
    return assignment


def pytest_collection_modifyitems(config, items):
    """Run only this process's stable share and retain its collection manifest."""
    try:
        index = int(os.environ['PYFLASH_TEST_SHARD_INDEX'])
        workers = int(os.environ['PYFLASH_TEST_SHARD_COUNT'])
        manifest_path = Path(os.environ['PYFLASH_TEST_SHARD_MANIFEST'])
    except (KeyError, ValueError) as exc:
        raise RuntimeError('PyFLASH pytest shard settings are incomplete or invalid.') from exc
    if workers < 2 or not 0 <= index < workers:
        raise RuntimeError(f'Invalid pytest shard {index}/{workers}.')

    all_nodeids = [item.nodeid for item in items]
    assignments = partition_nodeids(all_nodeids, workers)
    selected = [item for item in items if assignments[item.nodeid] == index]
    deselected = [item for item in items if assignments[item.nodeid] != index]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_suffix(manifest_path.suffix + '.tmp')
    temporary.write_text(json.dumps({
        'index': index,
        'workers': workers,
        'collected_count': len(all_nodeids),
        'selected_count': len(selected),
        'nodeids': [item.nodeid for item in selected],
    }, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temporary, manifest_path)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected

