"""Run the complete collected pytest suite in deterministic bounded shards."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def merge_junit(paths: list[Path], destination: Path) -> None:
    merged = ET.Element('testsuites')
    for path in paths:
        root = ET.parse(path).getroot()
        if root.tag == 'testsuite':
            merged.append(root)
        elif root.tag == 'testsuites':
            merged.extend(list(root))
        else:
            raise ValueError(f'Unexpected JUnit root {root.tag!r} in {path}')
    ET.indent(merged, space='  ')
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    ET.ElementTree(merged).write(temporary, encoding='utf-8', xml_declaration=True)
    os.replace(temporary, destination)


def junit_summary(path: Path) -> dict:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == 'testsuite' else list(root.findall('.//testsuite'))
    return {key: sum(int(suite.get(key, '0')) for suite in suites)
            for key in ('tests', 'failures', 'errors', 'skipped')}


def compact_success_artifacts(output: Path, records: list[dict], manifests: list[dict],
                              summaries: list[dict]) -> list[dict]:
    """Retain compact pass proof; keep detailed files on every non-pass path."""
    compact = []
    removed_per_shard = ('collection.json', 'tests.xml', 'pytest.log')
    for record, manifest, summary in zip(records, manifests, summaries):
        shard_dir = Path(record['manifest']).parent
        compact.append({
            'index': record['index'],
            'status': record['status'],
            'returncode': record['returncode'],
            'elapsed_seconds': record['elapsed_seconds'],
            'selected_count': manifest['selected_count'],
            'nodeids_sha256': hashlib.sha256(
                '\n'.join(manifest['nodeids']).encode('utf-8')).hexdigest(),
            'junit': summary,
        })
        for name in removed_per_shard:
            (shard_dir / name).unlink(missing_ok=True)
        shard_dir.rmdir()
    (output / 'tests.xml').unlink(missing_ok=True)
    return compact


def run(output: Path, basetemp: Path, workers: int = 3, *, tests_path: Path | None = None) -> dict:
    if workers < 2:
        raise ValueError('At least two shards are required to shorten the full suite.')
    output.mkdir(parents=True, exist_ok=True)
    basetemp = basetemp.resolve()
    basetemp.mkdir(parents=True, exist_ok=True)
    tests_path = tests_path or Path(__file__).resolve().parents[1] / 'tests'
    tests_path = tests_path.resolve()
    shard_root = output / 'test-shards'
    shard_root.mkdir(exist_ok=True)
    processes = []
    records = []
    framework_temps = []
    base_env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    for index in range(workers):
        shard_dir = shard_root / f'shard-{index + 1:02d}'
        shard_dir.mkdir(exist_ok=True)
        manifest = shard_dir / 'collection.json'
        junit = shard_dir / 'tests.xml'
        log_path = shard_dir / 'pytest.log'
        shard_basetemp = basetemp / f'shard-{index + 1:02d}'
        shard_basetemp.mkdir(parents=True, exist_ok=True)
        framework_temp = basetemp.parent / 'framework-temporary' / f'shard-{index + 1:02d}'
        framework_temp.mkdir(parents=True, exist_ok=True)
        framework_temps.append(str(framework_temp.resolve()))
        shard_env = dict(base_env,
            PYFLASH_TEST_SHARD_INDEX=str(index),
            PYFLASH_TEST_SHARD_COUNT=str(workers),
            PYFLASH_TEST_SHARD_MANIFEST=str(manifest),
            TEMP=str(framework_temp), TMP=str(framework_temp), TMPDIR=str(framework_temp))
        command = [sys.executable, '-B', '-X', 'utf8', '-m', 'pytest',
            '-p', 'reproducibility.pytest_shard', str(tests_path), '-q', '--durations=25',
            '-c', str(Path(__file__).resolve().parents[1] / 'pyproject.toml'),
            '--rootdir', str(tests_path), '--confcutdir', str(tests_path),
            '-o', 'faulthandler_timeout=180', '--junitxml', str(junit),
            '--basetemp', str(shard_basetemp)]
        log = log_path.open('w', encoding='utf-8')
        process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
            env=shard_env, stdout=log, stderr=subprocess.STDOUT)
        processes.append((index, process, log, command, manifest, junit, log_path))
        records.append({'index': index, 'pid': process.pid, 'status': 'running',
            'command': command, 'manifest': str(manifest), 'junit': str(junit),
            'log': str(log_path)})

    write_json(shard_root / 'run.json', {'status': 'running', 'workers': workers, 'shards': records})
    started = time.monotonic()
    try:
        for index, process, log, command, manifest, junit, log_path in processes:
            returncode = process.wait()
            log.close()
            records[index].update(returncode=returncode,
                status='pass' if returncode == 0 else 'fail',
                elapsed_seconds=round(time.monotonic() - started, 3))
            write_json(shard_root / 'run.json', {'status': 'running', 'workers': workers, 'shards': records})

        manifests = [json.loads(Path(record['manifest']).read_text(encoding='utf-8')) for record in records]
        collected = {item['collected_count'] for item in manifests}
        if len(collected) != 1:
            raise RuntimeError(f'Shards collected different suite sizes: {sorted(collected)}')
        ids = [nodeid for manifest in manifests for nodeid in manifest['nodeids']]
        if len(ids) != len(set(ids)):
            raise RuntimeError('At least one collected test was assigned to multiple shards.')
        expected_count = collected.pop()
        if len(ids) != expected_count:
            raise RuntimeError(f'Shard union contains {len(ids)} tests; pytest collected {expected_count}.')
        from reproducibility.pytest_shard import partition_nodeids
        assignments = partition_nodeids(ids, workers)
        for manifest in manifests:
            if any(assignments[nodeid] != manifest['index'] for nodeid in manifest['nodeids']):
                raise RuntimeError(f'Shard {manifest["index"]} contains a misassigned test.')
        junit_paths = [Path(record['junit']) for record in records]
        have_all_junit = all(path.is_file() for path in junit_paths)
        if have_all_junit:
            merge_junit(junit_paths, output / 'tests.xml')
        passed = all(record['status'] == 'pass' for record in records)
        if passed and not have_all_junit:
            raise RuntimeError('A passing shard did not produce its JUnit result.')
        summaries = [junit_summary(path) for path in junit_paths] if have_all_junit else []
        compacted_shards = records
        cleanup = {'status': 'preserved-after-failure'}
        if passed:
            compacted_shards = compact_success_artifacts(output, records, manifests, summaries)
            cleanup = {
                'status': 'complete',
                'removed': ['per-shard collection manifests', 'per-shard JUnit files',
                            'per-shard logs', 'merged JUnit file'],
                'retained': 'test-shards/run.json',
            }
        result = {'status': 'pass' if passed else 'fail', 'workers': workers,
            'collected_count': expected_count, 'executed_count': sum(m['selected_count'] for m in manifests),
            'shard_counts': [m['selected_count'] for m in manifests],
            'elapsed_seconds': round(time.monotonic() - started, 3), 'shards': compacted_shards,
            'worker_temp_roots_unique': len(set(framework_temps)) == workers,
            'cleanup': cleanup}
        write_json(shard_root / 'run.json', result)
        print(json.dumps({key: result[key] for key in ('status', 'workers', 'collected_count',
            'executed_count', 'shard_counts', 'elapsed_seconds')}), flush=True)
        return result
    except BaseException as exc:
        for index, process, log, *_ in processes:
            if process.poll() is None:
                process.terminate()
        for index, process, log, *_ in processes:
            try:
                returncode = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = process.wait()
            if not log.closed:
                log.close()
            records[index].update(returncode=returncode, status='interrupted')
        write_json(shard_root / 'run.json', {'status': 'fail', 'workers': workers,
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'error': f'{type(exc).__name__}: {exc}', 'shards': records})
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--basetemp', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--tests', type=Path)
    args = parser.parse_args()
    result = run(args.output.resolve(), args.basetemp.resolve(), args.workers, tests_path=args.tests)
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
