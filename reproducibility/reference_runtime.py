"""Install verification-only pinned R under the user's local cache."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone


def root():
    return Path(os.environ.get('PYFLASH_WEBR_ROOT',
        str(Path(os.environ.get('LOCALAPPDATA', Path.home()/'.cache'))/'PyFLASH/reference-runtime/webr')))


def ensure():
    destination = root()
    metadata = destination/'node_modules/webr/package.json'
    if metadata.is_file() and json.loads(metadata.read_text())['version'] == '0.6.0':
        return destination
    estimated_peak = 300*1024**2
    existing = next(parent for parent in (destination, *destination.parents) if parent.exists())
    if shutil.disk_usage(existing).free < estimated_peak:
        raise RuntimeError('Pinned reference runtime needs 300 MB of free local space.')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm:
        raise RuntimeError('Node.js 22.15 or newer and npm are required for independent R references.')
    destination.mkdir(parents=True,exist_ok=True)
    source = Path(__file__).parent
    for name in ('package.json','package-lock.json'):
        shutil.copyfile(source/name,destination/name)
    result = subprocess.run([npm,'ci','--prefix',str(destination),
        '--ignore-scripts','--no-audit','--no-fund'],capture_output=True,text=True,timeout=180)
    (destination/'install.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Reference runtime installation failed; see '+str(destination/'install.log'))
    return destination


def _needs_local_staging(output):
    return os.name == 'nt' and 'dropbox' in str(output.resolve()).casefold()


def _execute_queries(queries, output, *, name, timeout=180):
    """Retain the exact native expressions, results, runtime identity and log."""
    # Missing expressions can otherwise execute native NULL and look successful.
    for index, query in enumerate(queries):
        if not isinstance(query, dict) or not isinstance(query.get('code'), str) or not query['code'].strip():
            raise ValueError(f'Native query {index} requires a nonempty code expression.')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    runtime = ensure()
    source = output / (name+'-queries.json')
    answer = output / (name+'-results.json')
    source.write_text(json.dumps(queries, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    # A synced folder can lock the rapidly replaced progress checkpoint even
    # after bounded rename retries. Keep the active journal in an owned local
    # job directory and copy its retained files back once the process stops.
    staging = None
    execution_source, execution_answer = source, answer
    if _needs_local_staging(output):
        local = Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir()))/'PyFLASH/reference-jobs'
        local.mkdir(parents=True, exist_ok=True)
        estimated_peak = 100*1024**2+3*source.stat().st_size
        if shutil.disk_usage(local).free < estimated_peak:
            raise RuntimeError('Insufficient free space for independent reference staging.')
        staging = Path(tempfile.mkdtemp(prefix=name+'-', dir=local))
        execution_source, execution_answer = staging/source.name, staging/answer.name
        shutil.copyfile(source, execution_source)
        (output/(name+'-staging.json')).write_text(json.dumps({
            'directory':str(staging), 'purpose':'owned active native-reference journal; preserve failures',
            'queries_file':str(execution_source), 'results_file':str(execution_answer)},indent=2),encoding='utf-8')
    scripts = Path(__file__).parent
    command = ['node', '--import', (scripts / 'windows_r_loader.mjs').as_uri(),
               str(scripts / 'run_native_r.mjs'), str(execution_source), str(execution_answer), str(runtime)]
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    def execution_receipt(status, returncode=None):
        (output/(name+'-execution.json')).write_text(json.dumps({
            'status':status,'started_at':started_at,'elapsed_seconds':time.perf_counter()-started,
            'timeout_seconds':timeout,'requested_queries':len(queries),'command':command,
            'returncode':returncode,'queries_file':str(source),'results_file':str(answer)},indent=2),encoding='utf-8')
    def retain_staged_files():
        if staging is not None:
            for path in staging.iterdir():
                if path.is_file() and path.name != source.name:
                    shutil.copyfile(path, output/path.name)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        retain_staged_files()
        execution_receipt('timed-out')
        def decoded(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')
        stdout, stderr = decoded(error.stdout), decoded(error.stderr)
        (output / (name+'.log')).write_text(stdout+stderr, encoding='utf-8')
        (output / (name+'-timeout.json')).write_text(json.dumps({
            'status':'timed-out', 'timeout_seconds':timeout,
            'queries_file':str(source), 'results_file':str(answer),
            'partial_results_file':str(answer.with_suffix('.partial.json')),
            'stdout':stdout, 'stderr':stderr}, indent=2), encoding='utf-8')
        raise
    retain_staged_files()
    execution_receipt('completed' if result.returncode==0 else 'failed',result.returncode)
    (output / (name+'.log')).write_text(result.stdout+result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Native R failed; see '+str(output / (name+'.log')))
    payload = json.loads(answer.read_text(encoding='utf-8'))
    if any(row['status'] != 'executed' for row in payload['rows']):
        raise RuntimeError('A native query failed; retain '+str(answer))
    return payload


def execute_queries(queries, output, *, name, timeout=180):
    """Reuse independent native answers only inside an explicit verified workflow."""
    from reproducibility.workflow import _REQUEST, cache_root
    options = _REQUEST.get()
    if options is None or options.get('fresh'):
        return _execute_queries(queries, output, name=name, timeout=timeout)
    for index, query in enumerate(queries):
        if not isinstance(query, dict) or not isinstance(query.get('code'), str) or not query['code'].strip():
            raise ValueError(f'Native query {index} requires a nonempty code expression.')
    from reproducibility.workflow_engine import Runner, digest_file, digest_value, atomic_json
    runtime = ensure()
    package = runtime / 'node_modules/webr'
    scripts = Path(__file__).parent
    # The exact native expressions contain the source bodies and effective inputs.
    # Candidate Python changes deliberately do not invalidate this independent engine.
    identity = {'queries': queries, 'timeout': timeout, 'name': name,
        'producer': {p.name: digest_file(p) for p in (scripts / 'run_native_r.mjs',
            scripts / 'windows_r_loader.mjs', Path(__file__), scripts / 'workflow_engine.py')},
        'runtime': {p.relative_to(package).as_posix(): digest_file(p)
                    for p in sorted(package.rglob('*')) if p.is_file()},
        'node': subprocess.run(['node', '--version'], capture_output=True, text=True, check=True).stdout.strip()}
    cache = cache_root() / 'native'
    # Bound admission, preserve previous proofs, and bypass a full cache. Current
    # output copies retain original execution evidence independently of this cache.
    cache_bytes = sum(p.stat().st_size for p in cache.rglob('*') if p.is_file()) if cache.exists() else 0
    if cache_bytes >= 2 * 1024 ** 3:
        return _execute_queries(queries, output, name=name, timeout=timeout)
    runner = Runner(cache / digest_value(identity), identity, resume=True)
    def action(directory):
        return _execute_queries(queries, directory, name=name, timeout=timeout)
    try:
        payload = runner.run('native', action,
            passing=lambda result: len(result['rows']) == len(queries) and all(row['status'] == 'executed' for row in result['rows']))
    finally:
        if runner.records:
            record = runner.records[-1]
            origin = Path(record['directory'])
            output = Path(output)
            output.mkdir(parents=True, exist_ok=True)
            for path in origin.iterdir():
                if path.is_file() and path.name not in {'result.json', 'receipt.json'}:
                    shutil.copyfile(path, output / path.name)
            # This is archived execution proof, never a new native execution claim.
            atomic_json(output / (name + '-reuse.json'), record)
    return payload


def values(row):
    """JSON null cannot distinguish R NaN from either infinity by itself."""
    import math
    classifications = row.get('nonfinite', [])
    result = []
    for index, value in enumerate(row['values']):
        flag = classifications[index] if classifications else None
        result.append(math.inf if flag == 'positive_infinity' else -math.inf if flag == 'negative_infinity'
                      else math.nan if value is None else value)
    return result


if __name__ == '__main__':
    print(ensure())
