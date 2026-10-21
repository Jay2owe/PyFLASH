"""Shared declared helper actions and dispatch for browser and CLI adapters."""
import importlib
import inspect

# Stable keys stay distinct from titles. The browser imports this very mapping.
HELPER_ACTIONS = {
    'PyFLASH.dependencies.check': ('Check installed feature dependencies', 'value'),
    'PyFLASH.dependencies.repair': ('Repair a declared dependency', 'value'),
    'PyFLASH.export.format_summary_for_display': ('Format a measurement table', 'table'),
    'PyFLASH.export.convert_name': ('Explain a measurement name', 'value'),
    'PyFLASH.export.convert_raw_name': ('Explain an object measurement name', 'value'),
    'PyFLASH.export.normalize_marker_name': ('Normalize a marker name', 'value'),
    'PyFLASH.export.lookup_description': ('Look up a measurement description', 'value'),
    'PyFLASH.stats.bonferroni_correction': ('Correct one p-value (Bonferroni)', 'value'),
    'PyFLASH.stats.sidak_correction': ('Correct one p-value (Sidak)', 'value'),
    'PyFLASH.stats.cauchy_combination_test': ('Combine p-values', 'value'),
    'PyFLASH.stats.fisher_z_correlation_difference': ('Compare two correlations', 'value'),
    'PyFLASH.stats.fisher_z_se': ('Calculate correlation uncertainty', 'value'),
    'PyFLASH.stats.zou_correlation_difference_ci': ('Compare correlation confidence intervals', 'value'),
    'PyFLASH.stats.get_annotation': ('Describe a p-value', 'value'),
    'PyFLASH.batch.Batch.getImageTable': ('Inspect the imported image table', 'instance'),
    'PyFLASH.dataframe.DataFrameExperiment.getRegionDict': ('Inspect the subject-region mapping', 'instance'),
}

# These are the actual browser backend operations, not parallel implementations.
# Job inspection can persist failed-worker recovery, so it has write access.
SUPPORT_ACTIONS = {
    'PyFLASH.ui.services.open_pickle': ('Open a saved analysis', 'value', 'read-only'),
    'PyFLASH.ui.services.save_pickle': ('Save an analysis', 'data', 'mutating'),
    'PyFLASH.ui.workspace.load_table': ('Open a subject table', 'value', 'read-only'),
    'PyFLASH.ui.services.validate_experiment_folder': ('Check an experiment folder', 'value', 'read-only'),
    'PyFLASH.ui.services.discover_experiments': ('Discover experiment folders', 'value', 'read-only'),
    'PyFLASH.ui.services.build_conditions': ('Build group definitions', 'value', 'read-only'),
    'PyFLASH.ui.services.preview_conditions': ('Preview group definitions', 'value', 'read-only'),
    'PyFLASH.ui.services.summary_table': ('Inspect a measurement table', 'data', 'read-only'),
    'PyFLASH.ui.services.export_summary_csv': ('Export a region measurement table', 'data', 'mutating'),
    'PyFLASH.ui.services.batch_overview': ('Inspect analysis metadata', 'data', 'read-only'),
    'PyFLASH.ui.services.export_excel': ('Export a workbook', 'data', 'mutating'),
    'PyFLASH.ui.services.save_batch': ('Save the current analysis', 'data', 'mutating'),
    'PyFLASH.ui.services.get_representative_selections': ('Inspect representative-image choices', 'data', 'read-only'),
    'PyFLASH.ui.services.set_representative_selections': ('Edit representative-image choices', 'data', 'mutating'),
    'PyFLASH.ui.project_io.load_project': ('Open project setup', 'value', 'read-only'),
    'PyFLASH.ui.project_io.save_project': ('Save project setup', 'project', 'mutating'),
    'PyFLASH.ui.workspace.read_recovery': ('Read saved workspace settings', 'value', 'read-only'),
    'PyFLASH.ui.workspace.checkpoint_session': ('Save workspace settings', 'value', 'mutating'),
    'PyFLASH.ui.workspace.set_preferences': ('Edit display settings and selection', 'value', 'mutating'),
    'PyFLASH.ui.jobs.start_processing': ('Submit microscopy processing', 'value', 'mutating'),
    'PyFLASH.ui.jobs.start_operation': ('Submit an analysis or export', 'value', 'mutating'),
    'PyFLASH.ui.jobs.start_dependency_repair': ('Submit a dependency repair', 'value', 'mutating'),
    'PyFLASH.ui.jobs.read_job': ('Inspect processing progress', 'value', 'mutating'),
    'PyFLASH.ui.jobs.latest_job': ('Inspect the latest processing job', 'value', 'mutating'),
    'PyFLASH.ui.jobs.log_tail': ('Inspect the processing log', 'value', 'read-only'),
    'PyFLASH.ui.jobs.replay_request': ('Replay a recorded operation', 'value', 'mutating'),
    'PyFLASH.ui.jobs.start_sweep': ('Compare analysis choices', 'value', 'mutating'),
    'PyFLASH.ui.jobs.cancel_job': ('Cancel after the current analysis finishes', 'value', 'mutating'),
    'PyFLASH.queue.run_action_grid': ('Run a resumable analysis grid', 'optional-data', 'mutating'),
    'PyFLASH.queue.run_spec_queue': ('Run a resumable saved figure recipe', 'data', 'mutating'),
    'PyFLASH.ui.sweeps.promote_cell': ('Use a completed grid choice', 'value', 'mutating'),
}

ACTION_REGISTRY = {**HELPER_ACTIONS, **{key: value[:2] for key, value in SUPPORT_ACTIONS.items()}}

# An existing destination is never an input. UI and CLI read the same roles.
ACTION_OUTPUT_PARAMETERS = {
    'PyFLASH.ui.services.save_pickle': ('path',),
    'PyFLASH.ui.services.save_batch': ('filename',),
    'PyFLASH.ui.services.export_summary_csv': ('filename',),
    'PyFLASH.ui.services.export_excel': ('save_path',),
    'PyFLASH.ui.project_io.save_project': ('path',),
    'PyFLASH.ui.workspace.checkpoint_session': ('path',),
    'PyFLASH.ui.jobs.replay_request': ('output_dir',),
    'PyFLASH.queue.run_action_grid': ('progress_path', 'cache_dir'),
    'PyFLASH.queue.run_spec_queue': ('progress_path', 'output_root'),
}


def output_parameters(action):
    """Read output roles from the owning plot signature or helper declaration."""
    from PyFLASH.spec import PLOT_REGISTRY, _resolve_func
    if action in PLOT_REGISTRY:
        parameters = inspect.signature(_resolve_func(PLOT_REGISTRY[action])).parameters
        return tuple(name for name in ('save_path', 'output_dir', 'output_root') if name in parameters)
    return ACTION_OUTPUT_PARAMETERS.get(action, ())


def helper_function(action):
    title, binding = ACTION_REGISTRY[action]
    if binding == 'instance':
        module, owner, name = action.rsplit('.', 2)
        cls = getattr(importlib.import_module(module), owner)
        return getattr(cls, name), binding, cls
    module, name = action.rsplit('.', 1)
    return getattr(importlib.import_module(module), name), binding, None


def action_access(action):
    """Describe whether this operation changes files or the environment."""
    if action == 'PyFLASH.dependencies.repair':
        return 'mutating'
    if action in SUPPORT_ACTIONS:
        return SUPPORT_ACTIONS[action][2]
    return 'read-only' if action in HELPER_ACTIONS else 'mutating'


def resolve_action(action, data=None, parameters=None):
    from PyFLASH.spec import PLOT_REGISTRY, resolve_plot_call
    parameters = dict(parameters or {})
    if action in PLOT_REGISTRY:
        fn, kwargs = resolve_plot_call(action, parameters)
        return fn, (data,), kwargs
    if action not in ACTION_REGISTRY:
        raise ValueError(f"Unknown action {action!r}. Valid: {', '.join(sorted(set(PLOT_REGISTRY) | set(ACTION_REGISTRY)))}")
    fn, binding, cls = helper_function(action)
    args = ()
    if binding == 'instance':
        if not isinstance(data, cls):
            raise ValueError(f"Open a {cls.__name__} dataset before using this method.")
        args = (data,)
    elif binding == 'table':
        table = getattr(data, 'summary', data)
        if table is None:
            raise ValueError('This action requires an input measurement table.')
        parameters['summary'] = table.copy()
    elif binding in {'data','optional-data'}:
        if data is None and binding == 'data':
            raise ValueError('This operation requires an open analysis or --input.')
        args = (data,)
        if action.endswith('.set_representative_selections') and not hasattr(parameters.get('df'), 'columns'):
            import pandas as pd
            parameters['df'] = pd.DataFrame(parameters['df'])
    elif binding == 'project' and isinstance(parameters.get('project'), dict):
        from PyFLASH.ui.project_io import Project
        parameters['project'] = Project.from_dict(parameters['project'])
    if action.endswith('.preview_conditions') and isinstance(parameters.get('cl'), dict):
        from PyFLASH.ui.services import build_conditions
        parameters['cl'] = build_conditions(parameters['cl'])
    inspect.signature(fn).bind(*args, **parameters)
    return fn, args, parameters


def call_action(action, data=None, parameters=None):
    """Execute the owning package callable after strict action validation."""
    fn, args, kwargs = resolve_action(action, data, parameters)
    return fn(*args, **kwargs)


# Selected feature dependencies are declared beside the public action registry.
ACTION_DEPENDENCIES = {
    'iterative_model_sweep': ('PyFLASH._classifier_registry', 'dependency_groups', 'model_families'),
}

def required_dependency_groups(action, parameters=None):
    from importlib import import_module
    from PyFLASH.spec import PLOT_REGISTRY
    canonical = action
    if canonical not in ACTION_DEPENDENCIES:
        canonical = next((key for key in ACTION_DEPENDENCIES if PLOT_REGISTRY.get(key) == action), action)
    entry = ACTION_DEPENDENCIES.get(canonical)
    if entry is None:
        return ()
    module, resolver, parameter = entry
    return getattr(import_module(module), resolver)((parameters or {}).get(parameter))


# Shared support-operation vocabulary. Defaults remain owned by live signatures.
# None means a unit is not applicable; empty choices do not claim an enum.
SUPPORT_PARAMETER_HELP = {
    'path': ('File path', 'file', 'Path read or written by this operation.', None),
    'source_sha256': ('Expected input content hash', 'text', 'SHA-256 of the input bytes already captured by the caller; None captures the current identity.', None),
    'obj': ('Analysis', 'bound', 'Loaded analysis supplied by the dispatcher.', None),
    'batch': ('Analysis', 'bound', 'Loaded analysis supplied by the dispatcher.', None),
    'data': ('Analysis', 'bound', 'Loaded analysis supplied by the dispatcher; optional for actions that need no data.', None),
    'experiments': ('Analysis', 'bound', 'Loaded analysis supplied by the dispatcher.', None),
    'group_col': ('Grouping column', 'text', 'Input table column containing group labels.', None),
    'subject_col': ('Subject identity column', 'text', 'Input table column containing subject identities.', None),
    'demo': ('Use example data', 'boolean', 'Mark this opened table as the bundled example dataset.', None),
    'root': ('Root directory', 'folder', 'Root directory used by this operation; omitted job roots use the configured job store.', None),
    'spec': ('Group definitions', 'mapping', 'JSON-serializable condition builder specification.', None),
    'cl': ('Group definitions', 'object', 'Built condition list, or a condition builder specification accepted by the dispatcher.', None),
    'roi_base': ('Region', 'text', 'Region table key; omitted values use the summary adapter default.', None),
    'region': ('Region', 'text', 'Region table key to export.', None),
    'display': ('Readable column labels', 'boolean', 'Format column labels for display instead of returning raw labels.', None),
    'column_strings': ('Include column substrings', 'list', 'Keep measurements whose names contain any of these substrings.', None),
    'exclude': ('Exclude column substrings', 'list', 'Drop matching measurement column names.', None),
    'filename': ('Output file', 'file', 'Destination file written by this operation.', None),
    'groups': ('Groups', 'list', 'Group labels included in the exported table.', None),
    'columns': ('Measurements', 'list', 'Measurement columns included in the exported table.', None),
    'save_path': ('Output directory', 'folder', 'Workbook destination; None uses the loaded analysis export directory.', None),
    'if_summary': ('Export fluorescence summary', 'boolean', 'Write the fluorescence summary workbook.', None),
    'if_extended': ('Export fluorescence details', 'boolean', 'Write the extended fluorescence workbook.', None),
    'behaviour': ('Export behaviour summary', 'boolean', 'Write the behaviour workbook when a behaviour table is available.', None),
    'capture': ('Capture export log', 'boolean', 'Return the captured progress log instead of writing it to the terminal.', None),
    'return_paths': ('Return written paths', 'boolean', 'Include the paths of the workbooks written by the exporter.', None),
    'df': ('Image selection table', 'object', 'Representative-image selection table; JSON rows are converted to a table by the dispatcher.', None),
    'project': ('Project setup', 'object', 'Project settings; save_project also accepts a JSON object through the dispatcher.', None),
    'state': ('Workspace state', 'mapping', 'Current workspace state used to save or edit display preferences.', None),
    'updates': ('Display preference edits', 'mapping', 'Serializable display settings and selection edits; analysis identities and measurements are refused.', None),
    'rerun': ('Reprocess analysis', 'boolean', 'Request processing again rather than reusing the existing analysis.', None),
    'reimport_images': ('Reimport images', 'boolean', 'Reload image inputs during processing.', None),
    'kind': ('Operation kind', 'text', 'Operation kind supported by the job worker.', None),
    'source': ('Saved input', 'object', 'Recorded saved-input description used to open the analysis.', None),
    'parameters': ('Analysis parameters', 'mapping', 'Parameters passed unchanged to the owning registered operation.', None),
    'name': ('Job name', 'text', 'Display name for this submitted operation.', None),
    'dataset_token': ('Dataset identity', 'text', 'Current dataset identity used to refuse superseded results.', None),
    'target_key': ('Result destination key', 'text', 'Stable workspace key where the completed result belongs.', None),
    'representatives': ('Image choices', 'object', 'Current representative-image selections captured with this request.', None),
    'package': ('Dependency', 'text', 'Declared dependency to repair.', None),
    'job_id': ('Job identity', 'text', 'Identity of a job in the selected job store.', None),
    'max_bytes': ('Maximum log bytes', 'integer', 'Maximum number of trailing log bytes to read.', 'bytes'),
    'request': ('Recorded request', 'mapping', 'Previously recorded operation request to replay.', None),
    'output_dir': ('Replay output directory', 'folder', 'New directory that owns the replay outputs.', None),
    'input_records': ('Input identities', 'list', 'Recorded input paths and content hashes verified for replay.', None),
    'action': ('Registered action', 'text', 'Stable action key from the shared action registry.', None),
    'choices': ('Parameter choices', 'mapping', 'Explicit value lists compared by the analysis grid.', None),
    'choice_sets': ('Choice metadata', 'mapping', 'Option-set metadata recorded with a submitted sweep.', None),
    'progress_path': ('Progress file', 'file', 'Resumable progress ledger; completed entries are reused only after identity checks.', None),
    'cache_dir': ('Cell output directory', 'folder', 'Directory containing content-keyed grid cell outputs.', None),
    'max_cells': ('Maximum grid cells', 'integer', 'Maximum allowed number of requested parameter combinations.', 'cells'),
    'memory_budget_bytes': ('Memory budget', 'integer', 'Memory budget enforced by the grid, in bytes.', 'bytes'),
    'disk_budget_bytes': ('Disk budget', 'integer', 'Disk budget enforced by the grid, in bytes.', 'bytes'),
    'cancel_path': ('Cancellation file', 'file', 'A cancellation request at this path stops between scientific calls.', None),
    'on_cell': ('Cell completion callback', 'object', 'Python callback invoked after a grid cell completes.', None),
    'resume': ('Resume completed entries', 'boolean', 'Reuse previously completed queue entries only after content and output verification.', None),
    'retry_failed': ('Retry failed entries', 'boolean', 'Retry previous failed queue entries while preserving their failure history.', None),
    'output_root': ('Queue output directory', 'folder', 'Root directory owning the saved-recipe queue outputs.', None),
    'receipt_path': ('Grid receipt', 'file', 'Receipt of the completed parameter grid containing the choice.', None),
    'index': ('Grid choice index', 'integer', 'Zero-based index of the completed cell to promote.', 'cells'),
}

# Workbook families share the same meaning, without copying their defaults.
for _family, _label in (('if_summary', 'Fluorescence summary'), ('if_extended', 'Fluorescence details'), ('behaviour', 'Behaviour summary')):
    for _filter in ('include', 'exclude'):
        SUPPORT_PARAMETER_HELP[_family+'_'+_filter] = (
            _label+' '+_filter+' filter', 'text',
            'Column-name regular expressions passed to the workbook owner for '+_filter+' filtering.', None)
    SUPPORT_PARAMETER_HELP[_family+'_save_name'] = (
        _label+' filename', 'text', 'Workbook filename stem without .xlsx; None uses the exporter default.', None)

SUPPORT_PARAMETER_OVERRIDES = {
    ('PyFLASH.ui.services.open_pickle', 'path'): ('Saved analysis file', 'file', 'Trusted saved analysis pickle to open.', None),
    ('PyFLASH.ui.services.save_pickle', 'path'): ('Saved analysis destination', 'file', 'Destination pickle; None uses the analysis owner default.', None),
    ('PyFLASH.ui.workspace.load_table', 'path'): ('Subject measurement table', 'file', 'CSV file containing subject identities, group labels and measurements.', None),
    ('PyFLASH.ui.services.validate_experiment_folder', 'path'): ('Experiment directory', 'folder', 'Experiment directory checked for a supported import layout.', None),
    ('PyFLASH.ui.services.discover_experiments', 'root'): ('Experiment root directory', 'folder', 'Parent directory whose immediate subfolders are checked as experiments.', None),
    ('PyFLASH.ui.project_io.load_project', 'path'): ('Project setup file', 'file', 'Project JSON file to open.', None),
    ('PyFLASH.ui.project_io.save_project', 'path'): ('Project setup destination', 'file', 'Project JSON destination written atomically with portable paths.', None),
    ('PyFLASH.ui.workspace.read_recovery', 'path'): ('Workspace settings file', 'file', 'Previously saved workspace settings to reopen.', None),
    ('PyFLASH.ui.workspace.checkpoint_session', 'path'): ('Workspace settings destination', 'file', 'Workspace settings destination; omitted paths use the current workspace setting.', None),
    ('PyFLASH.queue.run_spec_queue', 'path'): ('Figure recipe file', 'file', 'Saved figure recipe containing the queue entries to validate and run.', None),
}


def support_parameter_metadata(action):
    """Describe backend parameters from the shared vocabulary and live owner.

    Discovery does not call the operation. Unknown vocabulary is an explicit
    error, so new backend parameters cannot silently lose their help entry.
    """
    if action not in SUPPORT_ACTIONS:
        raise ValueError(f'Not a registered support action: {action!r}')
    fn, binding, _ = helper_function(action)
    from PyFLASH.ui.catalogue import _parameter_help
    owner_help = _parameter_help(inspect.getdoc(fn) or '')
    outputs = set(output_parameters(action))
    result = {}
    for index, (name, parameter) in enumerate(inspect.signature(fn).parameters.items()):
        entry = SUPPORT_PARAMETER_OVERRIDES.get((action, name), SUPPORT_PARAMETER_HELP.get(name))
        if entry is None:
            raise ValueError(f'Missing support parameter help: {action}.{name}')
        label, role, help_text, unit = entry
        if name in outputs:
            role = 'output'
        elif index == 0 and binding in {'data', 'optional-data', 'instance'}:
            role = 'bound'
        result[name] = {'key': name, 'label': label, 'role': role,
                        'help': owner_help.get(name) or help_text,
                        'unit': unit, 'choices': []}
    return result
