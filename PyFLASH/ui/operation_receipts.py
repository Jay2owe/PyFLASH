"""One input verification and replay contract for every background result."""
from pathlib import Path
from PyFLASH.ui import workspace


def inputs(request, records=None):
    """Capture inputs before any save or export can replace a file."""
    records = [] if records is None else records
    source = request.get('source')
    if source:
        path = Path(source['path']).resolve()
        records.append({'parameter':'source', 'path':str(path), 'sha256':workspace.content_hash(path)})
    if request.get('kind') != 'save':  # filename is a destination, even if it exists.
        records.extend(workspace.parameter_inputs(request.get('parameters', {}),action=request.get('action')))
    if request.get('kind', 'processing') == 'processing':
        from PyFLASH.experiment import resolve_experiment_paths, ATTRIBUTE_DICT
        project = request['project']
        roots = list(project.get('experiments', {}).values())
        if not roots:
            parent = Path(project['batch_path'])
            if parent.is_dir():
                roots = [str(parent)] if resolve_experiment_paths(str(parent)) else [
                    str(child) for child in sorted(parent.iterdir()) if child.is_dir()]
        for root in roots:
            layout = resolve_experiment_paths(root)
            if layout is None:
                continue
            data = Path(layout['data_path'])
            for child in sorted(data.iterdir()):
                paths = [child] if child.is_file() else (
                    sorted(child.iterdir()) if child.is_dir() and child.name in ATTRIBUTE_DICT else [])
                for path in paths:
                    if path.is_file() and path.suffix.lower() in {'.csv', '.zip'}:
                        records.append({'parameter':'raw_table', 'path':str(path.resolve()),
                                        'sha256':workspace.content_hash(path)})
    return list({row['path']: row for row in records}.values())


def verify(records):
    for row in records:
        if workspace.content_hash(row['path']) != row['sha256']:
            raise ValueError('Input content changed: ' + row['path'])


def script(request, records):
    """Replay via the registered synchronous adapter, with fresh output ownership."""
    # Reuse the version/configuration/code/dependency guards used by the CLI.
    return workspace.equivalent_action_script('PyFLASH.ui.jobs.replay_request', {
        'request':request, 'input_records':records, 'output_dir':'replayed-output'},
        input_records=records)


def complete(request, result, path, records):
    """Write evidence after all tables and figures exist; include every output."""
    path = Path(path)
    declared = [Path(table['path']) for table in result.get('tables', [])]
    declared.extend(Path(value) for value in result.get('paths', []))
    for cell in result.get('cells', []):
        declared.extend(Path(table['path']) for table in cell.get('tables', []))
        declared.extend(Path(value) for value in cell.get('paths', []))
        declared.append(Path(cell['receipt']))
    declared.extend(Path(result[key]) for key in ('path','result_path') if result.get(key))
    missing = [str(file) for file in declared if not file.is_file()]
    if missing:
        raise FileNotFoundError('Declared outputs are missing: '+', '.join(missing))
    replay = script(request, records)
    (path / 'equivalent.py').write_text(replay, encoding='utf-8')
    result.update(script=replay, receipt=str(path / 'run.json'))
    workspace.write_operation_state(path / 'result.json', result)
    files = [path / 'request.json', path / 'result.json', path / 'equivalent.py']
    files.extend(Path(table['path']) for table in result.get('tables', []))
    files.extend(Path(value) for value in result.get('paths', []))
    for cell in result.get('cells', []):
        files.extend(Path(table['path']) for table in cell.get('tables', []))
        files.extend(Path(value) for value in cell.get('paths', []))
        files.append(Path(cell['receipt']))
    for key in ('path', 'result_path'):
        if result.get(key):
            files.append(Path(result[key]))
    # Figures also emit scientific data/statistics through ReproFig alongside
    # their media. This directory belongs exclusively to this one job.
    files.extend(child for child in path.rglob('*') if child.is_file()
                 and child.name not in {'run.json', 'state.json', 'launch.json', 'progress.log'})
    files = list(dict.fromkeys(file.resolve() for file in files if file.is_file()))
    source = request.get('source')
    source_record = workspace.portable_source(source) if source else None
    if source_record:
        source_record['sha256'] = next(row['sha256'] for row in records if row['parameter'] == 'source')
    record = workspace.run_record(source, result.get('type', request['kind']),
        request.get('parameters', request.get('project', {})), files,
        result.get('style'), input_records=records, source_record=source_record)
    record.update(status='succeeded',request=request, representative_edits=request.get('representatives'))
    workspace.write_json(path / 'run.json', workspace.portable_run_record(record))
    return result


def failed(request, state, path, records):
    """Keep partial outputs and original input identities without claiming success."""
    path = Path(path)
    records = list({row['path']:row for row in records}.values())
    replay = script(request,records)
    (path/'equivalent.py').write_text(replay,encoding='utf-8')
    result = {'status':'failed','type':request.get('action',request.get('kind','processing')),
              'parameters':request.get('parameters',request.get('project',{})),
              'error':state['error'],'script':replay,'receipt':str(path/'run.json')}
    workspace.write_operation_state(path/'result.json',result)
    files = [file for file in path.rglob('*') if file.is_file()
             and file.name not in {'run.json','state.json','launch.json'}]
    source = request.get('source')
    source_record = workspace.portable_source(source) if source else None
    if source_record:
        captured = next((r for r in records if r['parameter']=='source'),None)
        source_record['sha256'] = captured['sha256'] if captured else None
    record = workspace.run_record(source,result['type'],result['parameters'],files,
        request.get('parameters',{}).get('style'),input_records=records,source_record=source_record)
    record.update(status='failed',error=state['error'],request=request,
                  started_at=state.get('started_at'),finished_at=state.get('finished_at'),
                  representative_edits=request.get('representatives'))
    workspace.write_json(path/'run.json',workspace.portable_run_record(record))
    return result
