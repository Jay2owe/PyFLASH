"""Focused runners save work without promoting stale or partial evidence."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from reproducibility import run, workflow
from reproducibility.workflow_engine import MetadataCache


def test_source_cleanup_waits_for_resource_recovery_and_preserves_other_errors(monkeypatch, tmp_path):
    from reproducibility import compact_evidence, source_retention
    output = tmp_path / 'run'
    snapshot = output / 'sources'
    snapshot.mkdir(parents=True)
    calls = []
    def retire(*args):
        calls.append(args)
        if len(calls) == 1:
            raise compact_evidence.ResourcePause('Available RAM is below 4 GiB')
        return {'status': 'removed-after-verified-recovery-packet'}
    monkeypatch.setattr(source_retention, 'preserve_and_retire', retire)
    sleeps = []
    monkeypatch.setattr(run.time, 'sleep', sleeps.append)
    records = [{'path': 'source.py', 'sha256': 'frozen'}]
    result = run.cleanup_verified_source_snapshot(output, snapshot, [], records)
    assert result['status'] == 'removed-after-verified-recovery-packet'
    assert len(calls) == 2 and calls[0] == calls[1]
    assert sleeps == [2]
    progress = json.loads((output / 'source-cleanup-progress.json').read_text())
    assert progress['status'] == 'completed' and progress['pauses'] == 1
    def broken(*args):
        raise ValueError('Corrupt scientific source evidence')
    monkeypatch.setattr(source_retention, 'preserve_and_retire', broken)
    with pytest.raises(ValueError, match='Corrupt scientific source evidence'):
        run.cleanup_verified_source_snapshot(output, snapshot, [], records)
    assert sleeps == [2]


@pytest.mark.parametrize('source_changed', [False, True])
def test_focused_run_retires_sources_only_after_consumers_and_identity_check(monkeypatch, tmp_path, source_changed):
    source = tmp_path / 'producer.py'
    source.write_text('source')
    events = []
    monkeypatch.setattr(workflow, 'ROOT', tmp_path)
    monkeypatch.setattr(workflow, 'definitions', lambda: [])
    monkeypatch.setattr(workflow, 'select_stages', lambda *args: {'selected': ['fast']})
    monkeypatch.setattr(workflow, 'preflight', lambda *args: {'passed': True})
    monkeypatch.setattr(run, 'verification_sources', lambda: [source])
    monkeypatch.setattr(run, 'versions', lambda: {'python': 'test'})
    monkeypatch.setattr(run, 'run_space_requirement', lambda paths: {'total_bytes': 6})
    def identity(root, sources):
        events.append('identity')
        return {'producer.py': 'after' if source_changed and events.count('identity') == 2 else 'before'}
    monkeypatch.setattr(workflow, 'source_identity', identity)
    def snapshot(sources, destination, **kwargs):
        events.append('snapshot')
        assert kwargs['workers'] == 4
        return [{'path': str(source), 'sha256': 'before', 'size_bytes': 6}]
    monkeypatch.setattr(run, 'snapshot_sources', snapshot)
    monkeypatch.setattr(workflow, 'configure', lambda *args, **kwargs: workflow._REQUEST.set({}))
    def consume(output, name, command, stages):
        events.append('consumer')
        stages.append({'name': name, 'status': 'pass'})
    monkeypatch.setattr(run, 'command_stage', consume)
    def cleanup(output, snapshots, changed, records):
        events.append('cleanup')
        assert events == ['identity', 'snapshot', 'consumer', 'identity', 'cleanup']
        assert records == [{'path': 'producer.py', 'sha256': 'before'}]
        assert changed == (['producer.py'] if source_changed else [])
        return {'status': 'preserved-after-source-change' if changed else 'removed-after-verified-recovery-packet'}
    monkeypatch.setattr(run, 'cleanup_verified_source_snapshot', cleanup)
    monkeypatch.setattr(workflow.sys, 'argv', ['workflow', '--fast', '--output', str(tmp_path / 'runs')])
    if source_changed:
        with pytest.raises(SystemExit):
            workflow.main()
    else:
        workflow.main()
    receipts = list((tmp_path / 'runs').glob('*/source-cleanup.json'))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())['status'].startswith('preserved' if source_changed else 'removed')


def test_inventory_builds_once_and_returns_independent_status(monkeypatch, tmp_path):
    calls = []
    def build():
        calls.append(1)
        return {'rows': [{'capability': 'public', 'status': 'not-fully-independently-validated'}],
                'prefixes': {'public': ['case.']}, 'required': {'public': ['case.a', 'case.b']}}
    identity = {'source': 'one'}
    monkeypatch.setattr(run, '_INVENTORY_CACHE', MetadataCache(tmp_path))
    monkeypatch.setattr(run, '_inventory_identity', lambda: dict(identity))
    monkeypatch.setattr(run, '_build_inventory', build)
    complete = run.inventory(['case.a', 'case.b'])
    complete[0]['capability'] = 'caller mutation'
    assert run.inventory(['case.a'])[0]['status'] == 'partially-validated-contract'
    assert run.inventory()[0]['status'] == 'not-fully-independently-validated'
    assert len(calls) == 1
    identity['source'] = 'two'
    run.inventory()
    assert len(calls) == 2


def test_interface_only_never_executes_numerical_or_inventory(monkeypatch, tmp_path):
    def forbidden(*args):
        raise AssertionError('Unrelated numerical work executed')
    monkeypatch.setattr(run, 'inventory', forbidden)
    monkeypatch.setattr(run, 'numerical_pass', forbidden)
    monkeypatch.setattr(run, 'browser_checks', lambda output, stages, port: stages.append({'name': 'browser', 'status': 'pass'}))
    stages = []
    assert run.execute_requested_checks(tmp_path, stages, ui_only=True) == ([], [], None)
    assert stages == [{'name': 'browser', 'status': 'pass'}]


def test_catalogue_discovers_changed_fixture_dependencies_and_rejects_corrupt_index(monkeypatch, tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    fixture = root / 'fixture.json'
    fixture.write_text(json.dumps({'input': 'a.txt'}))
    (root / 'a.txt').write_text('first')
    (root / 'b.txt').write_text('second')
    index = tmp_path / 'index.json'
    calls = []
    def build():
        calls.append(1)
        name = json.loads(fixture.read_text())['input']
        return {'rows': [{'capability': (root / name).read_text(), 'status': 'unchecked'}],
                'prefixes': {}, 'required': {}}
    monkeypatch.setattr(run, 'ROOT', root)
    monkeypatch.setattr(run, '_inventory_base_identity', lambda: {'sources': {'definition.py': 'one'}})
    monkeypatch.setattr(run, '_inventory_index_path', lambda: index)
    monkeypatch.setattr(run, '_INVENTORY_CACHE', MetadataCache(tmp_path / 'cache'))
    monkeypatch.setattr(run, '_build_inventory', build)
    assert run.inventory()[0]['capability'] == 'first'
    assert run.inventory()[0]['capability'] == 'first'
    assert len(calls) == 1
    fixture.write_text(json.dumps({'input': 'b.txt'}))
    assert run.inventory()[0]['capability'] == 'second'
    (root / 'b.txt').write_text('edited')
    assert run.inventory()[0]['capability'] == 'edited'
    assert len(calls) == 3
    index.write_text('{corrupt')
    assert run.inventory()[0]['capability'] == 'edited'
    assert len(calls) == 4


def test_failed_benchmark_records_failure_instead_of_active_checkpoint(monkeypatch, tmp_path):
    from scripts import benchmark_verification as benchmark
    path = tmp_path / 'benchmark.json'
    path.write_text(json.dumps({'status': 'running', 'stage': 'comparison', 'passed': False}))
    def failure():
        raise AssertionError('retained mismatch')
    monkeypatch.setattr(benchmark, '_main', failure)
    monkeypatch.setattr(benchmark.sys, 'argv', ['benchmark', '--output', str(tmp_path)])
    with pytest.raises(AssertionError, match='retained mismatch'):
        benchmark.main()
    record = json.loads(path.read_text())
    assert record['status'] == 'failed' and record['passed'] is False
    assert 'retained mismatch' in record['traceback']


def test_resume_family_reuses_all_fields_and_artifacts(monkeypatch, tmp_path):
    calls = []
    def action(name, output):
        calls.append(name)
        (output / 'full-arrays.json').write_text(json.dumps([1, None, 3]))
        return [{'contract': name, 'status': 'agree', 'complete_values': [1, None, 3]}]
    monkeypatch.setattr(workflow, '_family_action', action)
    previous, current = tmp_path / 'previous', tmp_path / 'current'
    previous.mkdir(); current.mkdir()
    identity = {'sources': {'producer.py': 'one'}, 'versions': {'python': 'test'}}
    rows = workflow.run_families(previous, ['owned'], identity)
    assert workflow.run_families(current, ['owned'], identity, previous=previous) == rows
    assert calls == ['owned']
    assert json.loads((current / 'full-arrays.json').read_text()) == [1, None, 3]
    summary = json.loads((current / 'family-workflow/summary.json').read_text())
    assert summary['reused'] == 1 and not summary['complete']
    from reproducibility.workflow_engine import digest_value
    manifest = json.loads((current / 'family-workflow/input-identity.json').read_text())
    assert manifest['identity'] == identity and manifest['sha256'] == digest_value(identity)
    assert summary['stages'][0]['identity']['run'] == {'family_inputs_sha256': digest_value(identity)}
    workflow.run_families(tmp_path / 'changed', ['owned'], {'sources': {'producer.py': 'two'}}, previous=previous)
    assert calls == ['owned', 'owned']


def test_failed_family_is_retried_and_good_family_is_preserved(monkeypatch, tmp_path):
    from reproducibility.validation_registry import ReferenceFamilyFailure
    calls = []
    broken = [True]
    def action(name, output):
        calls.append(name)
        if name == 'broken' and broken[0]:
            raise RuntimeError('original error')
        return [{'contract': name, 'status': 'agree'}]
    monkeypatch.setattr(workflow, '_family_action', action)
    with pytest.raises(ReferenceFamilyFailure) as captured:
        workflow.run_families(tmp_path, ['good', 'broken'], {'source': 1})
    assert captured.value.partial_rows == [{'contract': 'good', 'status': 'agree'}]
    broken[0] = False
    workflow.run_families(tmp_path, ['good', 'broken'], {'source': 1}, previous=tmp_path)
    assert calls == ['good', 'broken', 'broken']


def test_ui_change_plan_contains_no_scientific_work():
    from reproducibility.workflow_engine import select_stages
    selected = select_stages(workflow.definitions(), ['PyFLASH/ui/pages/6_plots.py'])
    assert selected['selected'] == ['guard', 'ui']


def test_changed_tests_and_documentation_run_their_actual_checks(monkeypatch, tmp_path):
    from reproducibility.workflow_engine import select_stages
    assert select_stages(workflow.definitions(), ['docs/usage.md'])['selected'] == ['guard', 'docs']
    assert select_stages(workflow.definitions(), ['tests/test_slow_contract.py'])['selected'] == ['guard', 'tests']
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/test_slow_contract.py').write_text('pass')
    monkeypatch.setattr(workflow, 'ROOT', tmp_path)
    assert workflow.changed_test_targets(['tests/test_slow_contract.py']) == ['tests/test_slow_contract.py']
    assert workflow.changed_test_targets(['tests/test_removed.py']) == ['tests']
    with pytest.raises(ValueError):
        workflow.changed_test_targets(['tests/../../outside.py'])


def test_native_reuse_is_independent_of_candidate_and_invalidates_inputs(monkeypatch, tmp_path):
    from reproducibility import reference_runtime as native
    package = tmp_path / 'runtime/node_modules/webr'
    package.mkdir(parents=True)
    binary = package / 'R.wasm'
    binary.write_bytes(b'original native runtime')
    monkeypatch.setattr(native, 'ensure', lambda: tmp_path / 'runtime')
    monkeypatch.setattr(workflow, 'cache_root', lambda: tmp_path / 'cache')
    monkeypatch.setattr(native.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout='node-owned'))
    calls = []
    def execute(queries, output, *, name, timeout):
        output.mkdir(parents=True, exist_ok=True)
        calls.append(queries[0]['code'])
        payload = {'rows': [{'status': 'executed', 'values': [1, None, 2]}]}
        (output / (name + '-results.json')).write_text(json.dumps(payload))
        return payload
    monkeypatch.setattr(native, '_execute_queries', execute)
    token = workflow._REQUEST.set({'fresh': False})
    try:
        queries = [{'key': 'owned', 'code': 'c(1,NA,2)'}]
        first = native.execute_queries(queries, tmp_path / 'first', name='owned')
        assert native.execute_queries(queries, tmp_path / 'second', name='owned') == first
        assert calls == ['c(1,NA,2)']
        assert json.loads((tmp_path / 'second/owned-reuse.json').read_text())['reused']
        binary.write_bytes(b'changed native runtime')
        native.execute_queries(queries, tmp_path / 'third', name='owned')
        assert len(calls) == 2
        native.execute_queries([{'key': 'owned', 'code': 'c(2,NA,3)'}], tmp_path / 'fourth', name='owned')
        assert len(calls) == 3
        workflow._REQUEST.set({'fresh': True})
        native.execute_queries(queries, tmp_path / 'fresh', name='owned')
        assert len(calls) == 4
    finally:
        workflow._REQUEST.reset(token)


def test_command_resume_checks_environment_and_preserves_outputs(monkeypatch, tmp_path):
    calls = []
    def execute(output, name, args, stages, env=None, timeout=None):
        calls.append(name)
        (output / (name + '.log')).write_text('original passing evidence')
        record = {'name': name, 'command': args, 'status': 'pass', 'log': name + '.log', 'elapsed_seconds': 9.}
        stages.append(record)
        return record
    monkeypatch.setattr(run, '_command_stage', execute)
    receipt = {'sources': [{'path': 'producer.py', 'sha256': 'one'}], 'versions': {'python': 'owned'}}
    previous, current, changed = tmp_path / 'previous', tmp_path / 'current', tmp_path / 'changed'
    previous.mkdir(); current.mkdir(); changed.mkdir()
    token = workflow.configure(previous, receipt)
    try:
        run.command_stage(previous, 'docs', ['owned-command', str(previous / 'site')], [], {'OPTION': 'one'})
    finally:
        workflow._REQUEST.reset(token)
    token = workflow.configure(current, receipt, previous=previous)
    try:
        record = run.command_stage(current, 'docs', ['owned-command', str(current / 'site')], [], {'OPTION': 'one'})
        assert record['reused'] and record['elapsed_seconds'] == 0.
        assert record['original_elapsed_seconds'] == 9.
        assert (current / 'docs.log').read_text() == 'original passing evidence'
    finally:
        workflow._REQUEST.reset(token)
    token = workflow.configure(changed, receipt, previous=previous)
    try:
        run.command_stage(changed, 'docs', ['owned-command', str(changed / 'site')], [], {'OPTION': 'two'})
        assert calls == ['docs', 'docs']
    finally:
        workflow._REQUEST.reset(token)


def test_budget_checks_never_resume(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(run, '_command_stage', lambda *args: calls.append(args[1]) or {'status': 'pass'})
    receipt = {'sources': [], 'versions': {}}
    token = workflow.configure(tmp_path, receipt, previous=tmp_path)
    try:
        run.command_stage(tmp_path, 'development-loop', ['owned'], [])
        run.command_stage(tmp_path, 'real-data-interaction-budgets', ['owned'], [])
        assert calls == ['development-loop', 'real-data-interaction-budgets']
    finally:
        workflow._REQUEST.reset(token)
