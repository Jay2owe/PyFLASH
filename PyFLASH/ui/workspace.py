"""Streamlit-free dataset loading and atomic presentation recovery."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from collections.abc import Mapping
from PyFLASH._persistence import write_json, code_identity, read_json

SCHEMA_VERSION = 2
RUN_RECORD_SCHEMA_VERSION = 2
OPERATION_STATE_SCHEMA_VERSION = 2
DEMO_PATH = Path(__file__).with_name("data") / "summary.csv"


@lru_cache(maxsize=8)
def _source_references(filename, modified_ns):
    """Index declarations; compiling every plotting body costs seconds."""
    import re
    source = Path(filename).read_text(encoding="utf-8")
    offsets = {m.group(1): m.start() for m in re.finditer(r"(?m)^(?:async )?def ([A-Za-z_]\w*)\(", source)}
    return source, offsets


@lru_cache(maxsize=64)
def _source_reference(filename, modified_ns, name):
    """Parse just the selected declaration and docstring, without executing it."""
    import ast
    import io
    import tokenize
    source, offsets = _source_references(filename, modified_ns)
    excerpt = source[offsets[name]:]
    lines = excerpt.splitlines(keepends=True)
    tokens = tokenize.generate_tokens(io.StringIO(excerpt).readline)
    depth = 0
    for token in tokens:
        if token.type == tokenize.OP:
            if token.string in "([{":
                depth += 1
            elif token.string in ")]}":
                depth -= 1
            elif token.string == ":" and depth == 0:
                row, column = token.end
                header = "".join(lines[:row - 1]) + lines[row - 1][:column]
                break
    else:
        raise ValueError(f"No declaration found for {name}.")
    ignored = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT}
    body = next(token for token in tokens if token.type not in ignored)
    # Adjacent literal strings are allowed docstrings; expressions are not.
    statement = "pass"
    if body.type == tokenize.STRING:
        parts = [body.string]
        for token in tokens:
            if token.type == tokenize.STRING:
                parts.append(token.string)
            elif token.type in {tokenize.NEWLINE, tokenize.ENDMARKER}:
                statement = " ".join(parts)
                break
            elif token.type not in {tokenize.COMMENT, tokenize.NL}:
                break
    node = ast.parse(header + "\n    " + statement + "\n").body[0]
    return {"signature": f"{node.name}({ast.unparse(node.args)})",
            "documentation": ast.get_docstring(node) or "No additional documentation."}


def plot_reference(plot_type):
    from importlib.util import find_spec
    from PyFLASH.spec import PLOT_REGISTRY
    reference = PLOT_REGISTRY[plot_type]
    module, name = reference.rsplit(".", 1) if "." in reference else ("PyFLASH.plotting", reference)
    spec = find_spec(module)
    if not spec or not spec.origin:
        return {"signature": reference, "documentation": "Parameter reference is unavailable."}
    path = Path(spec.origin)
    return _source_reference(str(path), content_hash(path), name)


def content_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_version(path):
    return {"sha256": content_hash(path)}


def set_preferences(state, updates):
    """Change serializable display settings, never identities or measurements."""
    if not isinstance(updates, dict):
        raise ValueError('Display edits must be named settings.')
    for key, value in updates.items():
        if not isinstance(key, str) or not key.startswith(('ui_', 'qp_', 'single_', 'cross1_', 'cross2_', 'cross_cmp_')):
            raise ValueError(f'{key!r} is not a display setting.')
        if key in {'ui_source', 'ui_representative_edits', 'ui_representative_previous'}:
            raise ValueError(f'{key!r} belongs to the data-loading or image-edit operation.')
        json.dumps(value, allow_nan=False)
    state.update(updates)
    return {key: state[key] for key in updates}


def checkpoint_session(state, path=None):
    """Save the same workspace after full-page and linked-view-only edits."""
    import time
    project = state.get('project')
    preferences = {}
    for key, value in state.items():
        if key.startswith('ui_fn_') and not key.endswith('_result'):
            continue
        if not key.startswith(('ui_', 'qp_', 'single_', 'cross1_', 'cross2_', 'cross_cmp_')):
            continue
        if key in {'ui_source', 'ui_recovery_error', 'ui_image_representatives', 'ui_folder_entries'} or key.endswith('_entries'):
            continue
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            continue
        preferences[key] = value
    revision = max(time.time_ns(), state.get('_ui_checkpoint_saved_at_ns', -1) + 1)
    payload = {'schema_version': SCHEMA_VERSION, 'layout_version': 3,
               'saved_at_ns': revision, 'preferences': preferences,
               'source': state.get('ui_source'),
               'project': (project if isinstance(project, dict) else project.to_dict()) if project else None}
    payload,relative_paths = _portable_workspace_paths(payload)
    payload['relative_paths'] = relative_paths
    accepted = write_json(recovery_path() if path is None else path, payload, revision_key='saved_at_ns')
    state.pop('ui_recovery_error', None)
    if accepted:
        state['_ui_checkpoint_saved_at_ns'] = payload['saved_at_ns']
    return payload


def save_representative_edit(state, table):
    """Apply and immediately save an image selection against its loaded source."""
    from PyFLASH.ui import services
    batch = state['batch']
    source = state.get('ui_source')
    if not source:
        raise ValueError('Save or open the analysis before editing representative images.')
    root = Path(source['path']).resolve().parent
    portable = table.copy(deep=True)
    relative = {}
    for name in ('ImagePath', 'FilePath'):
        if name not in portable.columns:
            continue
        flags = []
        def convert(value):
            if isinstance(value, (str, Path)) and str(value):
                try:
                    path = Path(value).resolve().relative_to(root)
                    flags.append(True)
                    return str(path)
                except ValueError:
                    pass
            flags.append(False)
            return value
        portable[name] = portable[name].map(convert)
        relative[name] = flags
    previous = state.get('ui_representative_edits')
    services.set_representative_selections(batch, table.copy(deep=True))
    state['ui_representative_edits'] = {'schema_version': 1,
        'source_sha256': content_hash(source['path']),
        'table': selection_snapshot(portable), 'relative_paths': relative}
    if previous:
        state['ui_representative_previous'] = previous
    checkpoint_session(state)
    return state['ui_representative_edits']


def restore_representative_edit(state):
    """Rebase saved image paths onto the current source after a folder move."""
    edit = state.get('ui_representative_edits')
    if edit is None:
        return False
    source = state.get('ui_source')
    if not source or edit.get('schema_version') != 1:
        raise ValueError('Unsupported representative-image edit or missing source.')
    if content_hash(source['path']) != edit['source_sha256']:
        raise ValueError('Representative-image edits belong to different source contents.')
    table = restore_selection_snapshot(edit['table'])
    root = Path(source['path']).resolve().parent
    for name, flags in edit['relative_paths'].items():
        if len(table) != len(flags) or name not in table.columns:
            raise ValueError('Representative-image path metadata does not match its table.')
        table[name] = [str((root / value).resolve()) if relative else value
                       for value, relative in zip(table[name], flags)]
    from PyFLASH.ui.services import set_representative_selections
    set_representative_selections(state['batch'], table)
    return True


def portable_source(source):
    """Use project-relative paths; leave sources outside the project absolute."""
    if not source:
        return None
    result = dict(source)
    path = Path(result["path"]).resolve()
    try:
        result["path"] = str(path.relative_to(Path.cwd().resolve()))
    except ValueError:
        result["path"] = str(path)
    return result


def recovery_path():
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    project_root = Path.cwd().resolve()
    marker = project_root/'.pyflash-workspace-id.json'
    backup = project_root/'.pyflash-workspace-id.backup.json'
    identity = hashlib.sha256(str(project_root).encode()).hexdigest()[:12]
    def valid_identity(record):
        if (not isinstance(record, dict) or record.get('schema_version') != 1
                or not isinstance(record.get('identity'), str) or len(record['identity']) != 12
                or any(c not in '0123456789abcdef' for c in record['identity'])):
            raise ValueError('Unsupported project recovery identity.')
        return record['identity']
    if marker.exists():
        try:
            record = json.loads(marker.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            # The redundant identity travels with a moved folder too. Keep the
            # damaged primary bytes; never replace them with a guessed identity.
            if not backup.is_file():
                raise
            identity = valid_identity(json.loads(backup.read_text(encoding='utf-8')))
        else:
            identity = valid_identity(record)
            try:
                try:
                    backed_up = json.loads(backup.read_text(encoding='utf-8'))
                except (FileNotFoundError, json.JSONDecodeError):
                    backed_up = None
                if backed_up != record:
                    write_json(backup, record)
            except PermissionError:
                pass
    else:
        if backup.is_file():
            identity = valid_identity(json.loads(backup.read_text(encoding='utf-8')))
        try:
            write_json(marker,{'schema_version':1,'identity':identity})
            write_json(backup,{'schema_version':1,'identity':identity})
        except PermissionError:
            # A read-only directory retains the previous local-settings route.
            pass
    return root / "PyFLASH" / identity / "workspace.json"


def _portable_workspace_paths(payload):
    """Mark exact internal path locations; labels and outside paths stay intact."""
    root = Path.cwd().resolve()
    from PyFLASH._state_paths import PORTABLE_PATH_FIELDS
    fields = PORTABLE_PATH_FIELDS
    locations = []
    # Completed runs appear in both history and the current result. Resolve
    # each identical path once in this write, retaining every path marker.
    resolved = {}
    def visit(value,location=(),path_field=False):
        if isinstance(value,dict):
            return {key:visit(item,(*location,key),key in fields or location and location[-1]=='experiments')
                    for key,item in value.items()}
        if isinstance(value,(list,tuple)):
            return [visit(item,(*location,index),path_field) for index,item in enumerate(value)]
        if path_field and isinstance(value,str) and Path(value).is_absolute():
            if value not in resolved:
                try:
                    resolved[value] = Path(value).resolve().relative_to(root).as_posix()
                except ValueError:
                    resolved[value] = None
            relative = resolved[value]
            if relative is None:
                return value
            locations.append(list(location))
            return relative
        return value
    return visit(payload),locations


def _migrate_workspace_v1(payload):
    return {**payload,'schema_version':2,'relative_paths':[]}


def read_recovery(path):
    path = Path(path)
    if not path.exists():
        return {}
    payload = read_json(path)
    if payload.get('schema_version') == 1:
        payload = _migrate_workspace_v1(payload)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("This workspace was saved by an unsupported version.")
    return _restore_project_paths(payload)


def _restore_project_paths(payload, root=None):
    root = Path.cwd().resolve() if root is None else Path(root).resolve()
    for location in payload.get('relative_paths',[]):
        target = payload
        try:
            for key in location[:-1]:
                target = target[key]
            stored = target[location[-1]]
            if not isinstance(stored,str) or Path(stored).is_absolute():
                raise ValueError('Expected a project-relative path.')
            resolved = (root/stored).resolve()
            if not resolved.is_relative_to(root):
                raise ValueError('A workspace-relative path leaves the project.')
            target[location[-1]] = str(resolved)
        except (KeyError,IndexError,TypeError) as exc:
            raise ValueError('Workspace path metadata does not match its saved values.') from exc
    return payload


def portable_run_record(record):
    """Preserve existing markers when new request fields join a run record."""
    converted,locations = _portable_workspace_paths(record)
    converted['relative_paths'] = [list(location) for location in dict.fromkeys(
        tuple(location) for location in record.get('relative_paths', []) + locations)]
    return converted


def read_run_record(path):
    """Load old run records by version, rebasing new internal paths to the project."""
    payload = read_json(path)
    # CLI envelopes contain the same versioned record under provenance.
    record = payload.get('provenance',payload)
    if record.get('schema_version')==1:
        record = {**record,'schema_version':2,'relative_paths':[]}
    if record.get('schema_version')!=RUN_RECORD_SCHEMA_VERSION:
        raise ValueError('This run record was saved by an unsupported version.')
    record = _restore_project_paths(record)
    if 'provenance' in payload:
        payload['provenance'] = record
        return payload
    return record


def write_operation_state(path, payload):
    """Atomically persist job requests, progress and results across project moves."""
    snapshot = {**payload, 'schema_version': OPERATION_STATE_SCHEMA_VERSION}
    snapshot.pop('relative_paths', None)
    converted, locations = _portable_workspace_paths(snapshot)
    converted['relative_paths'] = locations
    return write_json(path, converted)


def read_operation_state(path, *, project_root=None):
    """Migrate historical worker files in memory, then restore internal paths."""
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError('A saved operation must contain named fields.')
    version = payload.get('schema_version', 1)
    if version == 1:
        payload = {**payload, 'schema_version': OPERATION_STATE_SCHEMA_VERSION,
                   'relative_paths': []}
    elif version != OPERATION_STATE_SCHEMA_VERSION:
        raise ValueError('This operation was saved by an unsupported version.')
    return _restore_project_paths(payload, root=project_root)


def selection_snapshot(table):
    """Lossless small edit snapshot, never a copy of the loaded analysis."""
    import base64
    import pickle
    if table is None:
        return None
    data = pickle.dumps(table, protocol=5)
    return {"encoding": "pandas-pickle-v1", "sha256": hashlib.sha256(data).hexdigest(),
            "data": base64.b64encode(data).decode("ascii")}


def restore_selection_snapshot(snapshot):
    """Restore trusted local worker edits with their exact labels and dtypes."""
    import base64
    import pickle
    import pandas as pd
    if snapshot.get("encoding") != "pandas-pickle-v1":
        raise ValueError("Unsupported selection snapshot.")
    data = base64.b64decode(snapshot["data"], validate=True)
    if hashlib.sha256(data).hexdigest() != snapshot["sha256"]:
        raise ValueError("Selection snapshot checksum does not match.")
    result = pickle.loads(data)
    if not isinstance(result, pd.DataFrame):
        raise ValueError("Selection snapshot must contain a table.")
    return result


def activate_dataset(state, batch, source):
    """Replace loaded views together, so results never leak between datasets."""
    import uuid
    state["_ui_dataset_token"] = uuid.uuid4().hex
    state.pop("_ui_measurement_cache", None)
    state.pop("ui_function_results", None)
    state.pop('ui_representative_edits', None)
    state.pop('ui_representative_previous', None)
    state["batch"] = batch
    state["ui_source"] = source
    state["pickle_path"] = source["path"] if source["kind"] == "pickle" else None
    for key in list(state):
        if key.startswith(("ui_explore_", "ui_fig_", "ui_last_plot", "ui_image_", "ui_location_", "ui_export_", "ui_fn_")):
            del state[key]
        elif key in {"ui_process_log", "ui_save_analysis", "ui_csv_result", "ui_saved_analysis_result"}:
            del state[key]


def load_table(path, *, group_col="Condition", subject_col="AnimalName", demo=False, source_sha256=None):
    """Open subject identities and measurements from verified captured CSV bytes.

    ``source_sha256`` optionally carries a caller's already captured identity;
    otherwise the input identity is checked before and after its consumed bytes.
    """
    import pandas as pd
    from PyFLASH import from_dataframe

    path = Path(path).resolve()
    from PyFLASH._cache_identity import read_csv_verified
    frame, consumed_sha256 = read_csv_verified(path, expected_sha256=source_sha256)
    for col in (group_col, subject_col):
        if col not in frame:
            raise ValueError(f"Missing column: {col}")
        if frame[col].isna().any():
            raise ValueError(f"{col} contains missing identities.")
    if frame.empty:
        raise ValueError("The subject table is empty.")
    output = recovery_path().parent / "outputs" if demo else path.parent
    result = from_dataframe(frame, name="Simulated example" if demo else path.stem,
                            group_col=group_col, subject_col=subject_col,
                            file_path=str(output), source_paths=[str(path)])
    result._pyflash_resident_input_sha256 = consumed_sha256
    return result


def numeric_columns(table):
    import numpy as np
    numbers = table.select_dtypes(include="number")
    try:
        finite = np.isfinite(numbers.to_numpy(copy=False)).any(axis=0)
    except TypeError:  # Nullable pandas numeric arrays need their own dispatch.
        finite = np.isfinite(numbers).any(axis=0).to_numpy()
    return [c for c in numbers.columns[finite]
            if c not in {"AnimalName", "Condition", "Region", "Hemisphere"}]


def measurement_choices(metrics, labels, query="", selected=(), limit=200):
    """Bound menu size; every measurement remains reachable through search."""
    words = query.strip().casefold().split()
    matches = [c for c in metrics if not words or all(
        word in (str(c) + " " + labels.get(c, str(c))).casefold() for word in words)]
    pinned = [c for c in selected if c in labels]
    return list(dict.fromkeys(pinned + matches[:limit])), len(matches)


def measurement_table(batch, roi_base=None, cache=None):
    """Presentation copy: read numeric measurements around package missing tags."""
    import numpy as np
    import pandas as pd
    from PyFLASH.ui import services
    from PyFLASH.utils import EXCLUDED_SENTINEL_PREFIX, NOT_INCLUDED_SENTINEL

    if cache is not None and cache.get("batch") is batch and cache.get("region") == roi_base:
        return cache["table"]
    raw = services.summary_table(batch, roi_base=roi_base, display=False)
    if raw is None:
        return None
    replacements = {}
    floating_frame = None
    def missing(value):
        if isinstance(value, str):
            return (NOT_INCLUDED_SENTINEL in value or value.startswith(EXCLUDED_SENTINEL_PREFIX)
                    or value.strip().casefold() in {"", "nan", "none", "null", "na", "n/a", "<na>"})
        return bool(pd.isna(value)) if pd.api.types.is_scalar(value) else False

    identifiers = {"AnimalName", "Condition", "Region", "Hemisphere"}
    candidates = [i for i,(column,dtype) in enumerate(zip(raw.columns,raw.dtypes))
                  if column not in identifiers and (pd.api.types.is_object_dtype(dtype)
                  or pd.api.types.is_string_dtype(dtype) or isinstance(dtype,pd.CategoricalDtype))]
    block = raw.iloc[:,candidates].to_numpy(dtype=object)
    # Parse floating measurement columns in one pass. Integer-only columns keep
    # their own parser, so uint64 subject measurements are never rounded through
    # a mixed floating block. Nested metadata remains untouched.
    # A float in the first three rows is sufficient to use the floating parser;
    # other columns retain the exact per-column path. Do not scan every cell's
    # Python type before parsing: failed cells alone distinguish unknown text or
    # nested metadata from recognized missing tags.
    eligible = np.frompyfunc(lambda v:isinstance(v,(float,np.floating)),1,1)(block[:3]).astype(bool).any(axis=0)
    positions = np.flatnonzero(eligible)
    if positions.size:
        floating = block[:,positions]
        numeric = pd.to_numeric(floating.ravel(),errors='coerce').reshape(floating.shape)
        valid = np.isfinite(numeric).any(axis=0)
        failures = pd.isna(numeric)
        allowed = np.ones(floating.shape,dtype=bool)
        allowed[failures] = [missing(v) for v in floating[failures]]
        accepted = np.flatnonzero(valid & allowed.all(axis=0))
        columns = [raw.columns[candidates[positions[j]]] for j in accepted]
        if columns:
            floating_frame = pd.DataFrame(numeric[:,accepted],index=raw.index,columns=columns)
    for local in np.flatnonzero(~eligible):
        column = raw.columns[candidates[local]]
        # Coordinates and other nested metadata are not scalar measurements.
        array = block[:,local]
        if not all(map(pd.api.types.is_scalar, array)):
            continue
        # to_numeric already makes text tags missing. Check only failed cells
        # to distinguish those tags from unknown mixed text, without stringifying
        # every numeric value several times or fragmenting the frame per column.
        numeric = pd.to_numeric(array, errors="coerce")
        if np.isfinite(numeric).any() and all(missing(value) for value in array[pd.isna(numeric)]):
            replacements[column] = numeric
    if replacements or floating_frame is not None:
        replaced = set(replacements) | (set(floating_frame.columns) if floating_frame is not None else set())
        parts = [raw.loc[:,[c for c in raw.columns if c not in replaced]]]
        if floating_frame is not None:
            parts.append(floating_frame)
        if replacements:
            parts.append(pd.DataFrame(replacements,index=raw.index))
        table = pd.concat(parts,axis=1).reindex(columns=raw.columns)
    else:
        table = raw.copy()
    table.columns.name = raw.columns.name
    table.attrs = raw.attrs.copy()
    if cache is not None:
        cache.clear()
        cache.update(batch=batch, region=roi_base, table=table)
    return table


class _MeasurementLabels(Mapping):
    """All original field keys, with display names resolved only when requested."""
    def __init__(self, columns):
        self._keys = dict.fromkeys(columns)
        self._resolved = {}

    def __getitem__(self, key):
        if key not in self._keys:
            raise KeyError(key)
        if key not in self._resolved:
            from PyFLASH.export import _display_label_for_summary_column
            self._resolved[key] = _display_label_for_summary_column(str(key))
        return self._resolved[key]

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)


def measurement_catalogue(batch, roi_base=None, cache=None):
    """Prepare numeric choices and labels once per loaded batch and region."""
    cache = {} if cache is None else cache
    initial = getattr(batch, "_ui_initial_catalogue", None)
    if not cache and initial is not None and roi_base == initial[0]:
        table, metrics, labels = initial[1]
        cache.update(batch=batch, region=roi_base, table=table, metrics=metrics, labels=labels)
        return table, metrics, labels
    table = measurement_table(batch, roi_base, cache)
    if table is None:
        return None, [], {}
    if "metrics" not in cache:
        cache["metrics"] = numeric_columns(table)
        cache["labels"] = _MeasurementLabels(table.columns)
    return table, cache["metrics"], cache["labels"]


def exploration_data(table, fields):
    """Send only plotted scalars, using names that cannot mean nested fields."""
    fields = list(dict.fromkeys(fields))
    aliases = {field: f"_measurement_{i}" for i, field in enumerate(fields)}
    identifiers = [c for c in ("AnimalName", "Condition") if c in table]
    return table[identifiers + fields].rename(columns=aliases).copy(), aliases


def display_table(table):
    """Represent mixed/nested metadata as text without modifying the source."""
    result = table.copy()
    for column in result.select_dtypes(include="object"):
        result[column] = result[column].astype("string")
    return result


def selected_subject(event):
    """Read point selections from Streamlit's row or column event format."""
    selection = event.get("selection", {}).get("picked_subject", [])
    if isinstance(selection, list):
        return selection[0].get("_subject", "All subjects") if selection else "All subjects"
    subjects = selection.get("_subject", [])
    return subjects[0] if subjects else "All subjects"


def plot_contract(plot_type, params):
    """Resolve aliases once and reject typos before any expensive work."""
    from PyFLASH.spec import resolve_plot_call
    return resolve_plot_call(plot_type, params)


def equivalent_script(source, plot_type, params, *, source_kind="pickle", group_col="Condition", subject_col="AnimalName", style=None, target_experiment=None, source_sha256=None, input_records=None):
    """Replay the same validated package call with content verification."""
    func, kwargs = plot_contract(plot_type, params)
    records = parameter_inputs(params,action=plot_type) if input_records is None else input_records
    records,_ = _portable_workspace_paths(records)
    kwargs,_ = _portable_workspace_paths(kwargs)
    source = Path(source).resolve()
    digest = content_hash(source) if source_sha256 is None else source_sha256
    relative = portable_source({"path": str(source)})["path"]
    from PyFLASH._replay import guard_lines
    lines = guard_lines(source=relative, source_sha256=digest, input_records=records, save_mode=True)
    from PyFLASH._replay import source_load_lines
    constructor = ("batch = PyFLASH.from_dataframe(_source_frame, "
        f"group_col={group_col!r}, subject_col={subject_col!r}, "
        "file_path=str(Path('replayed-output').resolve()), source_paths=[str(SOURCE)])")
    lines += source_load_lines(target="batch", source_expression="str(SOURCE)",
        source_sha256=digest, source_kind=source_kind, csv_constructor=constructor)
    if target_experiment is not None:
        lines += [f"batch = next(e for e in batch.experiment_list if e.name == {target_experiment!r})"]
    lines += ["OUTPUT = Path('replayed-output').resolve()", "OUTPUT.mkdir(parents=True, exist_ok=True)",
              "batch.fig_path = str(OUTPUT)", "batch.image_fig_path = str(OUTPUT / 'Images')"]
    if style:
        lines += [f"PyFLASH.set_pyflash_style({style!r})"]
    lines += [f"from {func.__module__} import {func.__name__}", f"PARAMETERS = {kwargs!r}"]
    from PyFLASH.actions import output_parameters
    for name in output_parameters(plot_type):
        lines += [f"PARAMETERS[{name!r}] = str(OUTPUT)"]
    lines += [f"result = {func.__name__}(batch, **PARAMETERS)", "print(result)"]
    return "\n".join(lines) + "\n"


def parameter_inputs(parameters, *, action=None, require_existing=False,
                     hash_contents=True, hash_cache=None):
    """Inspect declared files, optionally hashing once per bounded preflight.

    Metadata-only inspection lets resource admission precede file hydration.
    A supplied cache belongs to this invocation's enclosing preflight only;
    callers still verify captured content before reuse and after computation.
    """
    inputs = []
    from PyFLASH.actions import output_parameters
    output_names = output_parameters(action)
    from PyFLASH.spec import PLOT_REGISTRY
    if action in PLOT_REGISTRY:
        output_names = (*output_names,'filename')
    def visit(value, name=''):
        if isinstance(value, dict):
            for key, item in value.items():
                if key not in output_names:
                    visit(item, str(key))
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item, name)
        elif isinstance(value, (str, Path)) and name in {
            'path', 'source', 'source_path', 'source_paths', 'spec_path',
            'comparisons_path', 'raw_path', 'filename'}:
            path = Path(value)
            if require_existing and not path.exists():
                raise FileNotFoundError(f'Missing input {name}: {path}')
            if path.is_file():
                absolute = str(path.resolve())
                row = {'parameter': name, 'path': absolute}
                if hash_contents:
                    if hash_cache is None:
                        row['sha256'] = content_hash(path)
                    else:
                        if absolute not in hash_cache:
                            hash_cache[absolute] = content_hash(path)
                        row['sha256'] = hash_cache[absolute]
                else:
                    row['size'] = path.stat().st_size
                inputs.append(row)
    visit(parameters)
    return list({(row['parameter'],row['path']):row for row in inputs}.values())


def run_record(source, plot_type, params, outputs, style=None, *, input_records=None,
               source_record=None):
    """Record content identities alongside each completed UI figure recipe."""
    import platform
    import subprocess
    from datetime import datetime, timezone
    from PyFLASH.config import config_snapshot
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    source = portable_source(source) if source_record is None else dict(source_record)
    if source and source_record is None:
        source["sha256"] = content_hash(source["path"])
    from PyFLASH.dependencies import check
    record = {"schema_version": RUN_RECORD_SCHEMA_VERSION, "created_utc": datetime.now(timezone.utc).isoformat(),
            "type": plot_type, "parameters": params, "style": style or {},
            "parameter_inputs": parameter_inputs(params, action=plot_type) if input_records is None else input_records,
            "configuration": config_snapshot(),
            "code_sha256": code_identity(),
            "source": source, "python": platform.python_version(),
            "pyflash": version("PyFLASH-analysis"), "commit": commit,
            "dependencies": {entry['package']: entry['version'] for entry in check()},
            "outputs": [{"path": str(p), "sha256": content_hash(p)} for p in outputs]}
    return portable_run_record(record)


def equivalent_action_script(action, params, source=None, *, region=None, input_records=None, style=None):
    """Replay a declared helper, including source-free checks, with exact identities."""
    from PyFLASH.actions import ACTION_REGISTRY
    from PyFLASH.config import config_snapshot
    from PyFLASH.dependencies import check
    records = parameter_inputs(params,action=action) if input_records is None else input_records
    params,_ = _portable_workspace_paths(params)
    records,_ = _portable_workspace_paths(records)
    from PyFLASH._replay import guard_lines
    lines = guard_lines()
    if source:
        source_digest = source.get('sha256')
        if source_digest is None:
            source_digest = content_hash(source['path'])
        lines += [f"SOURCE = Path({portable_source(source)['path']!r})", 'digest = hashlib.sha256()',
                  "with SOURCE.open('rb') as stream:",
                  "    for chunk in iter(lambda: stream.read(1024 * 1024), b''):",
                  '        digest.update(chunk)',
                  f"assert digest.hexdigest() == {source_digest!r}, 'Input content changed'"]
        from PyFLASH._replay import source_load_lines
        constructor = ("data = PyFLASH.from_dataframe(_source_frame, "
            f"group_col={source.get('group_col', 'Condition')!r}, "
            f"subject_col={source.get('subject_col', 'AnimalName')!r}, file_path='replayed-output')")
        lines += source_load_lines(target="data", source_expression="str(SOURCE)",
            source_sha256=source_digest, source_kind=source['kind'], csv_constructor=constructor)
        if ACTION_REGISTRY[action][1] == 'table':
            lines += ['from PyFLASH.ui.services import summary_table',
                      f'data = summary_table(data, roi_base={region!r}, display=False)']
    else:
        lines += ['data = None']
    lines += _input_guard_lines(records)
    from PyFLASH.actions import output_parameters
    output_names = output_parameters(action)
    lines += [f'PARAMETERS = {params!r}']
    if output_names:
        lines += ["OUTPUT = Path('replayed-output').resolve()"]
        if action != 'PyFLASH.ui.jobs.replay_request':
            lines += ['OUTPUT.mkdir(parents=True, exist_ok=True)']
        for name in output_names:
            if name in params and params[name] is not None:
                expression = 'str(OUTPUT)' if name in {'save_path', 'output_dir', 'output_root'} else f"str(OUTPUT / Path(PARAMETERS[{name!r}]).name)"
                lines += [f'PARAMETERS[{name!r}] = {expression}']
    if style:
        lines += [f'PyFLASH.set_pyflash_style({style!r})']
    lines += ['from PyFLASH.actions import call_action',
              f'result = call_action({action!r}, data, PARAMETERS)', 'print(result)']
    return '\n'.join(lines) + '\n'


from PyFLASH._replay import input_guard_lines as _input_guard_lines
from PyFLASH._replay import dependency_guard_lines as _dependency_guard_lines
