"""Project-relative scientific state paths without editing a live analysis."""
from contextvars import ContextVar
from pathlib import Path
import os

SAVE_ROOT = ContextVar('pyflash_state_save_root', default=None)
PATH_FIELDS = frozenset({
    'filePath', 'source_root', 'image_root', '_save_root', '_state_path',
    'export_path', 'fig_path', 'image_fig_path', 'representative_path',
    'legend_path', 'data_path', 'csv_path', 'column_path', 'attribute_path',
})
PORTABLE_PATH_FIELDS = PATH_FIELDS | frozenset({
    'path', 'paths', 'root', 'filename', 'source_path', 'source_paths',
    'result_path', 'progress_path', 'spec_path', 'save_path', 'output_dir',
    'output_root', 'batch_path', 'pickle_path', 'experiments', 'experiment_paths',
    'receipt', 'grid_receipt', 'cancel_path', 'cache_dir',
})


def map_container_paths(value, convert, *, marked_type=()):
    """Copy container links only, preserving aliases and leaving arrays shared.

    Scientific objects own their state conversion. Display labels are not paths;
    only declared fields and explicit pathlib values are passed to ``convert``.
    """
    from copy import copy
    from pathlib import PurePath
    memo = {}
    def visit(item, path_field=False, experiments=False):
        if isinstance(item, (PurePath,marked_type) if marked_type else PurePath) or path_field:
            converted = convert(item)
            if converted is not item:
                return converted
        if id(item) in memo:
            return memo[id(item)]
        if isinstance(item, dict):
            result = copy(item)
            result.clear()
            memo[id(item)] = result
            for key, child in item.items():
                result[key] = visit(child, key in PORTABLE_PATH_FIELDS or experiments,
                                    key == 'experiments')
            return result
        if isinstance(item, list):
            result = copy(item)
            result.clear()
            memo[id(item)] = result
            result.extend(visit(child,path_field) for child in item)
            return result
        if isinstance(item, tuple):
            children = [visit(child,path_field) for child in item]
            # A recursive tuple/list graph may already have completed this
            # tuple while visiting its mutable child, as in deepcopy's codec.
            if id(item) in memo:
                return memo[id(item)]
            result = type(item)(*children) if hasattr(item,'_fields') else type(item)(children)
            memo[id(item)] = result
            return result
        return item
    return visit(value)


def portable_state(state):
    """Copy only path-bearing fields; large measurement arrays remain shared."""
    root = SAVE_ROOT.get()
    if root is None:
        return state
    relative = {'fields': [], 'tables': [], 'sources': [], 'inputs': []}

    def convert(value):
        if not isinstance(value, (str, os.PathLike)) or not os.fspath(value):
            return value, False
        path = Path(value)
        if not path.is_absolute():
            path = path.resolve()
        try:
            return path.relative_to(root).as_posix(), True
        except ValueError:
            return os.fspath(value), False

    for key in PATH_FIELDS.intersection(state):
        state[key], changed = convert(state[key])
        if changed:
            relative['fields'].append(key)
    if 'source_paths' in state:
        items, flags = [], []
        for value in state['source_paths']:
            value, changed = convert(value)
            flags.append(changed)
            items.append(value)
        state['source_paths'] = items
        relative['source_paths'] = flags
    sources = []
    for index, source in enumerate(state.get('_provenance_sources', []) or []):
        source = dict(source)
        for key in ('path', 'project_root'):
            if key in source:
                source[key], changed = convert(source[key])
                if changed:
                    relative['sources'].append((index, key))
        sources.append(source)
    if '_provenance_sources' in state:
        state['_provenance_sources'] = sources
    if '_state_inputs' in state:
        inputs = []
        for index, entry in enumerate(state['_state_inputs']):
            entry = dict(entry)
            entry['path'], changed = convert(entry['path'])
            if changed:
                relative['inputs'].append(index)
            inputs.append(entry)
        state['_state_inputs'] = inputs
    for name in ('images', 'representative_images'):
        table = state.get(name)
        if table is None or not hasattr(table, 'columns'):
            continue
        columns = [column for column in ('ImagePath', 'FilePath') if column in table]
        if not columns:
            continue
        copied = table.copy(deep=False)
        for column in columns:
            values, flags = [], []
            for value in table[column]:
                value, changed = convert(value)
                values.append(value)
                flags.append(changed)
            copied[column] = values
            relative['tables'].append((name, column, flags))
        state[name] = copied
    state['_relative_state_paths'] = relative
    return state


def restore_paths(obj, filename):
    """Resolve recorded relative paths against the saved project's new location."""
    manifest = getattr(obj, '_state_path_manifest', None)
    if not manifest:
        return False
    if manifest.get('schema_version') != 1:
        raise ValueError('Unsupported saved path manifest version.')
    root = (Path(filename).resolve().parent / manifest['root_from_state']).resolve()
    changed = False
    targets = [obj, *list(getattr(obj, 'experiment_list', []) or [])]
    for target in targets:
        relative = getattr(target, '_relative_state_paths', {})
        def resolve(value):
            return str((root / value).resolve())
        for key in relative.get('fields', []):
            setattr(target, key, resolve(getattr(target, key)))
            changed = True
        if 'source_paths' in relative:
            target.source_paths = [resolve(value) if flag else value for value, flag in
                                   zip(target.source_paths, relative['source_paths'])]
        for index, key in relative.get('sources', []):
            target._provenance_sources[index][key] = resolve(target._provenance_sources[index][key])
        for index in relative.get('inputs', []):
            target._state_inputs[index]['path'] = resolve(target._state_inputs[index]['path'])
        for name, column, flags in relative.get('tables', []):
            table = getattr(target, name)
            table[column] = [resolve(value) if flag else value for value, flag in zip(table[column], flags)]
        target.__dict__.pop('_relative_state_paths', None)
    # A batch's image table can be derived from its children. Re-link children
    # before rebuilding the parent's aggregate cache.
    for target in reversed(targets):
        if hasattr(target, 'imagesDict') and getattr(target, 'images', None) is not None:
            from PyFLASH.experiment import _build_images_dict
            target.imagesDict = _build_images_dict(getattr(target, 'images', None))
    return changed
