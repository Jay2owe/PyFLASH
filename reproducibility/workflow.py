"""PyFLASH adapter for scoped verification and authenticated family restart.

Use --plan to see selection reasons without running scientific engines.
Registered families retain their own assertions and original expected answers.
"""
from __future__ import annotations
import argparse
from contextvars import ContextVar
from functools import partial
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from reproducibility.workflow_engine import Runner, Stage, atomic_json, preflight, select_stages, source_identity

ROOT = Path(__file__).resolve().parents[1]
_REQUEST = ContextVar('verification_request', default=None)


def cache_root():
    return Path(os.environ.get('PYFLASH_VERIFICATION_CACHE',
        str(Path(os.environ.get('LOCALAPPDATA', Path.home() / '.cache')) / 'PyFLASH/verification-cache')))


def family_identity(receipt=None):
    from reproducibility.run import verification_sources, versions
    if receipt is None:
        sources = source_identity(ROOT, verification_sources())
        environment = versions()
    else:
        sources = {item['path'].replace('\\', '/'): item['sha256'] for item in receipt['sources']}
        environment = receipt['versions']
    return {'sources': {name: digest for name, digest in sources.items()
            if (name.startswith('PyFLASH/') and not name.startswith('PyFLASH/ui/'))
            or name.startswith('reproducibility/') or name == 'scripts/benchmark_verification.py'}, 'versions': environment,
            'scope': 'registered-reference-families/full-original-output-contracts'}


def configure(output, receipt, *, previous=None, workers=1, fresh=False):
    request = {'output': str(output), 'identity': family_identity(receipt),
               'run_identity': {'sources': receipt['sources'], 'versions': receipt['versions']},
               'previous': str(previous) if previous else None, 'workers': workers, 'fresh': fresh}
    atomic_json(Path(output) / 'workflow-request.json', request)
    return _REQUEST.set(request)


def request(output):
    current = _REQUEST.get()
    return current if current and Path(current['output']).resolve() == Path(output).resolve() else None


RESUMABLE_COMMANDS = {'demo', 'readme-example', 'fresh-ui-replay', 'full-tests', 'docs',
                      'build', 'distribution-reproduction-resources', 'built-distribution-consumers'}


def command_stage(output, name, args, stages, env=None, timeout=None):
    """Reuse hermetic executable checks; live-state and performance gates stay fresh."""
    from reproducibility import run
    options = request(output)
    if not options or name not in RESUMABLE_COMMANDS:
        return run._command_stage(output, name, args, stages, env, timeout)
    from reproducibility.workflow_engine import digest_value
    output = Path(output)
    def normalized(value):
        return str(value).replace(str(output), '<OUTPUT>')
    normalized_args = [normalized(value) for value in args]
    normalized_env = {key: normalized(value) for key, value in (env or os.environ).items()}
    if name == 'full-tests':
        # These directories are allocated for this check and contain no inputs.
        for key in ('TEMP', 'TMP', 'TMPDIR'):
            if key in normalized_env:
                normalized_env[key] = '<OWNED-TEST-SCRATCH>'
        if '--basetemp' in normalized_args:
            normalized_args[normalized_args.index('--basetemp') + 1] = '<OWNED-PYTEST-SCRATCH>'
    identity = {'sources': options['run_identity'], 'command': normalized_args,
                'environment_sha256': digest_value(normalized_env), 'timeout': timeout}
    # Distribution consumers also depend on the actual built artifact bytes.
    if name in {'distribution-reproduction-resources', 'built-distribution-consumers'}:
        identity['distribution'] = source_identity(output, (output / 'dist').glob('*'))
    runner = Runner(output / 'command-workflow' / name, identity,
                    resume=options['previous'] is not None,
                    previous=Path(options['previous']) / 'command-workflow' / name if options['previous'] else None)
    def action(directory):
        local_args = [str(value).replace(str(output), str(directory)) for value in args]
        # A consumer reads distributions created by a different stage, not its own directory.
        if '--dist-dir' in local_args:
            local_args[local_args.index('--dist-dir') + 1] = str(output / 'dist')
        local = []
        result = run._command_stage(directory, name, local_args, local, env, timeout)
        return result
    result = runner.run(name, action, fresh=options['fresh'], passing=lambda record: record['status'] == 'pass')
    proof = runner.records[-1]
    materialize(proof, output)
    record = dict(result, reused=proof['reused'], original_receipt=proof.get('original_receipt'))
    if proof['reused']:
        record.update(original_elapsed_seconds=record['elapsed_seconds'], elapsed_seconds=0.)
    stages.append(record)
    run.write_json(output / 'progress.json', stages)
    return record


def definitions():
    from reproducibility.validation_registry import FAMILIES
    # Exact top-level module names avoid '*' swallowing UI subdirectories.
    core = tuple('PyFLASH/' + path.name for path in (ROOT / 'PyFLASH').glob('*.py'))
    stages = [Stage('guard', always=True), Stage('fast', ('architecture*', 'scripts/verify.py')),
              Stage('tests', ('tests/*',)), Stage('docs', ('docs/*', 'mkdocs.yml', 'mkdocs.yaml')),
              Stage('ui', ('PyFLASH/ui/*', 'scripts/check_ui*', 'tests/test_ui*', '.streamlit/*')),
              Stage('numerical', core + ('reproducibility/*', 'pyproject.toml'))]
    # Shared scientific code conservatively invalidates all registered families.
    stages.extend(Stage(name, core + (module.replace('.', '/') + '.py',
                               'reproducibility/fixtures/*', 'reproducibility/reference-sources/*',
                               'reproducibility/workflow*.py', 'pyproject.toml'))
                  for name, module in FAMILIES.items())
    return stages


def _family_action(name, output):
    from reproducibility.check_bootstrap import native_windows_information
    native_windows_information()
    from reproducibility.validation_registry import validate_family
    from contextlib import redirect_stdout, redirect_stderr
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'execution.log').open('w', encoding='utf-8') as log:
        with redirect_stdout(log), redirect_stderr(log):
            rows = validate_family(name, output)
    if not rows:
        raise ValueError('Required reference family produced no comparisons.')
    return rows


def materialize(record, output):
    """Preserve existing final-report file paths using verified stage artifacts."""
    origin, output = Path(record['directory']), Path(output)
    for artifact in record['artifacts']:
        if artifact['path'] == 'result.json':
            continue
        source = origin / artifact['path']
        target = output / artifact['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def run_families(output, names, identity, *, previous=None, workers=1, fresh=False):
    """Isolated family outputs; merge retained rows in registry order."""
    from reproducibility.validation_registry import ReferenceFamilyFailure
    from reproducibility.workflow_engine import digest_value
    # Retain the source map once. Repeating it in every stage and every progress
    # checkpoint would make bookkeeping grow quadratically with family count.
    identity_hash = digest_value(identity)
    atomic_json(Path(output) / 'family-workflow/input-identity.json',
                {'schema_version': 1, 'identity': identity, 'sha256': identity_hash})
    identity = {'family_inputs_sha256': identity_hash}
    runner = Runner(Path(output) / 'family-workflow', identity, resume=previous is not None,
                    previous=Path(previous) / 'family-workflow' if previous else None)
    rows, failures = [], []
    if workers < 1 or workers > 4:
        raise ValueError('Use between one and four isolated workers')
    # Serial is the default. Each family owns its mutable collector/configuration.
    if workers == 1:
        for name in names:
            try:
                completed = runner.run(name, partial(_family_action, name), fresh=fresh,
                    passing=lambda values: bool(values) and all(row['status'] == 'agree' for row in values))
                rows.extend(completed)
                materialize(runner.records[-1], output)
            except Exception as error:
                failures.append({'name': name, 'module': 'registered-reference-family',
                                 'status': 'execution-failure', 'error': str(error)})
    else:
        from concurrent.futures import ProcessPoolExecutor
        # The child entrypoint initializes native Windows metadata before heavy imports.
        with ProcessPoolExecutor(max_workers=workers) as pool:
            jobs = {name: pool.submit(_run_worker, str(output), name, identity, previous, fresh) for name in names}
            for name in names:
                try:
                    completed, record = jobs[name].result()
                    rows.extend(completed)
                    runner.records.append(record)
                    materialize(record, output)
                except Exception as error:
                    failures.append({'name': name, 'module': 'registered-reference-family',
                                     'status': 'execution-failure', 'error': str(error)})
    summary = runner.summary(list(names), scope='focused')
    atomic_json(Path(output) / 'reference-family-progress.json', summary['stages'])
    if failures:
        raise ReferenceFamilyFailure(rows, failures)
    return rows


def _run_worker(output, name, identity, previous, fresh):
    # Avoid nested BLAS pools; explicit process count is the concurrency limit.
    for variable in ('OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'OMP_NUM_THREADS'):
        os.environ[variable] = '1'
    from reproducibility.check_bootstrap import native_windows_information
    native_windows_information()
    _REQUEST.set({'fresh': fresh})
    runner = Runner(Path(output) / 'family-workflow' / 'workers' / name, identity,
                    resume=previous is not None,
                    previous=Path(previous) / 'family-workflow' / 'workers' / name if previous else None)
    rows = runner.run(name, partial(_family_action, name), fresh=fresh,
        passing=lambda values: bool(values) and all(row['status'] == 'agree' for row in values))
    return rows, runner.records[-1]


def main():
    from reproducibility import run
    from reproducibility.run import python_command, versions, verification_sources, run_space_requirement
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='Write selected checks and reasons without execution')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--changed', nargs='+', help='Changed project-relative paths, including deleted files')
    selection.add_argument('--families', nargs='+', help='Explicit registered family names')
    selection.add_argument('--ui-only', action='store_true', help='Actual interface checks without numerical references')
    selection.add_argument('--fast', action='store_true', help='Existing project contract development checks')
    parser.add_argument('--output', type=Path, default=cache_root() / 'runs')
    parser.add_argument('--resume-from', type=Path)
    parser.add_argument('--workers', type=int, default=1, choices=range(1, 5))
    parser.add_argument('--fresh-references', action='store_true')
    args = parser.parse_args()
    requested = args.families or (['ui'] if args.ui_only else ['fast'] if args.fast else None)
    selected = select_stages(definitions(), args.changed, requested)
    # This development adapter cannot certify distribution/docs/final-figure gates.
    selected['scope'] = 'focused'
    if args.plan:
        print(json.dumps(selected, indent=2))
        return
    from datetime import datetime, timezone
    output = args.output.resolve() / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    scientific = any(name not in {'guard', 'fast', 'ui', 'tests', 'docs'} for name in selected['selected'])
    sources = verification_sources()
    if not scientific:
        sources = [p for p in sources if 'reference-sources' not in p.parts and 'fixtures' not in p.parts]
    admission = preflight(output, run_space_requirement(sources)['total_bytes'] if scientific else 100 * 1024 ** 2,
                          ('node',) if scientific else ())
    if not admission['passed']:
        raise RuntimeError('; '.join(admission['errors']))
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / 'selection.json', selected)
    atomic_json(output / 'preflight.json', admission)
    identity = {'sources': source_identity(ROOT, sources), 'versions': versions()}
    # One source snapshot serves every selected family, not one copy per family.
    snapshot_records = run.snapshot_sources(sources, output / 'sources', workers=4,
                                           progress_path=output / 'snapshot-progress.json')
    for source, record in zip(sources, snapshot_records):
        if record['sha256'] != identity['sources'][source.relative_to(ROOT).as_posix()]:
            raise RuntimeError('Source changed while taking verification snapshot: ' + str(source))
    atomic_json(output / 'run-started.json', {'schema_version': 1, 'identity': identity, 'scope': 'focused',
        'passed': False, 'owner_pid': os.getpid(), 'required': selected['selected']})
    from reproducibility.validation_registry import FAMILIES
    rows, errors, stages = [], [], []
    names = [name for name in selected['selected'] if name in FAMILIES]
    if 'numerical' in selected['selected']:
        # The original complete numerical pass already includes every family.
        names = []
    receipt = {'sources': [{'path': key, 'sha256': value} for key, value in identity['sources'].items()],
               'versions': identity['versions']}
    token = configure(output, receipt, previous=args.resume_from, workers=args.workers, fresh=args.fresh_references)
    try:
        if names:
            rows.extend(run_families(output, names, family_identity(), previous=args.resume_from,
                                     workers=args.workers, fresh=args.fresh_references))
        if 'fast' in selected['selected']:
            run.command_stage(output, 'fast', python_command(native_metadata=True) + ['scripts/verify.py'], stages)
        if 'tests' in selected['selected']:
            targets = changed_test_targets(args.changed)
            scratch, test_env = run.full_test_environment(output, dict(os.environ, MPLBACKEND='Agg', PYTHONIOENCODING='utf-8'))
            try:
                test_record=run.command_stage(output, 'selected-tests', python_command(native_metadata=True) +
                    ['-m', 'pytest', '--disable-plugin-autoload', '-q', '--basetemp', str(scratch)] + targets,
                    stages, test_env)
            except BaseException:
                run.finalize_full_test_scratch(output,scratch,False)
                raise
            run.finalize_full_test_scratch(output,scratch,test_record.get('status')=='pass')
        if 'docs' in selected['selected']:
            run.command_stage(output, 'docs', python_command() +
                ['-m', 'mkdocs', 'build', '--strict', '--site-dir', str(output / 'site')], stages)
        if 'ui' in selected['selected']:
            run.browser_checks(output, stages, 8581)
        if 'numerical' in selected['selected']:
            rows, _ = run.numerical_pass(output)
        errors.extend(item['name'] for item in stages if item['status'] != 'pass')
    except Exception as error:
        rows.extend(getattr(error, 'partial_rows', ()))
        errors.append(type(error).__name__ + ': ' + str(error))
    finally:
        _REQUEST.reset(token)
    current_sources = verification_sources()
    if not scientific:
        current_sources = [p for p in current_sources if 'reference-sources' not in p.parts and 'fixtures' not in p.parts]
    after = source_identity(ROOT, current_sources)
    changed = sorted(name for name in identity['sources'].keys() | after.keys() if identity['sources'].get(name) != after.get(name))
    failures = [row for row in rows if row['status'] != 'agree']
    atomic_json(output / 'comparisons.json', rows)
    if rows:
        # Row schemas differ across families; the grid owns only common facts.
        run.write_csv(output / 'outcome-grid.csv', [{key: row.get(key, '') for key in
            ('contract', 'reference', 'family', 'status')} for row in rows])
    atomic_json(output / 'summary.json', {'schema_version': 1, 'scope': 'focused', 'complete': False,
        'passed': not errors and not changed and not failures and (bool(rows) or bool(stages)),
        'selection': selected, 'comparisons': len(rows), 'disagreements': len(failures),
        'errors': errors, 'source_changes': changed, 'stages': stages})
    lines = ['# Focused verification', '', f'{len(rows) - len(failures)} comparisons agree.',
             'Scope: selected checks only; no full-library or release certification.', '', '## Differences']
    lines.extend(json.dumps(row, sort_keys=True) for row in failures)
    lines.extend(errors)
    lines.extend('Source changed: ' + name for name in changed)
    (output / 'DIFFERENCES.md').write_text('\n\n'.join(lines) + '\n', encoding='utf-8')
    # Failed scientific answers remain intact. Only recoverable, unchanged source
    # duplicates can retire after all families and the final source check finish.
    cleanup = run.cleanup_verified_source_snapshot(output, output / 'sources', changed,
                                                   receipt['sources'])
    atomic_json(output / 'source-cleanup.json', cleanup)
    print(str(output / 'summary.json'))
    if errors or changed or failures or (not rows and not stages):
        raise SystemExit(1)


def changed_test_targets(changed):
    """Run changed existing test modules; deletion/unknown test inputs broaden to all tests."""
    names = [str(name).replace('\\', '/') for name in changed or ()
             if str(name).replace('\\', '/').startswith('tests/')]
    if not names:
        return ['tests']
    for name in names:
        path = (ROOT / name).resolve()
        path.relative_to((ROOT / 'tests').resolve())
        if not path.is_file() or path.suffix != '.py' or not path.name.startswith('test_'):
            return ['tests']
    return sorted(set(names))


if __name__ == '__main__':
    main()
