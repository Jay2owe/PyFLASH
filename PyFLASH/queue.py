"""Durable per-entry execution and resume for registered plot specifications.

This complements the single-operation browser worker. It resumes between calls;
it cannot resume within an interrupted scientific algorithm. Progress/result
files belong to the caller's chosen directory; original source data are read-only.
"""
from __future__ import annotations
import hashlib
from copy import copy
from dataclasses import dataclass
from importlib.metadata import version
import inspect
import json
import os
from pathlib import Path
import pickle
import tempfile
import time
import itertools
import math
import shutil

from PyFLASH import spec


@dataclass(frozen=True)
class _CachedProject:
    """Versioned project setup in a cache, with marked project-relative paths."""
    schema_version: int
    state: dict


@dataclass(frozen=True)
class _CachedGridValue:
    """Versioned result preserving scientific types and the moved project root."""
    schema_version: int
    value: object
    root_from_result: str


@dataclass(frozen=True)
class _RelativeResultPath:
    """An explicitly declared internal path, with its original scalar type."""
    relative: str
    scalar_type: type


def _cache_grid_value(value, path):
    if type(value).__module__ == 'PyFLASH.ui.project_io' and type(value).__name__ == 'Project':
        return _CachedProject(1, _portable_identity(value.to_dict()))
    from PyFLASH._state_paths import map_container_paths
    from pathlib import PurePath
    root = Path.cwd().resolve()
    def convert(item):
        if (not (type(item) is str or isinstance(item,PurePath))
                or not str(item) or not Path(item).is_absolute()):
            return item
        try:
            relative = Path(item).resolve().relative_to(root).as_posix()
        except ValueError:
            return item
        return _RelativeResultPath(relative,type(item))
    portable = map_container_paths(value,convert)
    return _CachedGridValue(1, portable, os.path.relpath(root, Path(path).resolve().parent))


def _write_grid_value(path, value):
    from PyFLASH._state_paths import SAVE_ROOT
    token = SAVE_ROOT.set(Path.cwd().resolve())
    try:
        _write_pickle(path, _cache_grid_value(value, path))
    finally:
        SAVE_ROOT.reset(token)


def _read_grid_value(path):
    with Path(path).open('rb') as handle:
        value = pickle.load(handle)
    if isinstance(value, _CachedProject):
        if type(value.schema_version) is not int or value.schema_version != 1:
            raise ValueError('Cached project result has an unsupported schema version.')
        from PyFLASH.ui import workspace
        from PyFLASH.ui.project_io import Project
        return Project.from_dict(workspace._restore_project_paths(value.state))
    if isinstance(value, _CachedGridValue):
        if type(value.schema_version) is not int or value.schema_version != 1:
            raise ValueError('Cached grid result has an unsupported schema version.')
        if not isinstance(value.root_from_result, str) or Path(value.root_from_result).is_absolute():
            raise ValueError('Cached grid result has invalid project-root metadata.')
        from PyFLASH._state_paths import restore_paths, map_container_paths
        from pathlib import PurePath
        root = (Path(path).resolve().parent/value.root_from_result).resolve()
        def convert(item):
            if not isinstance(item,_RelativeResultPath):
                return item
            if (not isinstance(item.relative,str) or Path(item.relative).is_absolute()
                    or '..' in Path(item.relative).parts
                    or not isinstance(item.scalar_type,type)
                    or not (item.scalar_type is str or issubclass(item.scalar_type,PurePath))):
                raise ValueError('Cached grid result has invalid relative-path metadata.')
            resolved = root/item.relative
            return str(resolved) if item.scalar_type is str else item.scalar_type(resolved)
        result_value = map_container_paths(value.value,convert,marked_type=_RelativeResultPath)
        seen = set()
        def restore(result):
            if id(result) in seen:
                return
            seen.add(id(result))
            if isinstance(result, dict):
                for item in result.values():
                    restore(item)
            elif isinstance(result, (list, tuple)):
                for item in result:
                    restore(item)
            elif hasattr(result, '_relative_state_paths'):
                # Only the newly unpickled object changes. Scientific state
                # owns its table/path conversion and nested-experiment links.
                result._state_path_manifest = {'schema_version':1, 'root_from_state':value.root_from_result}
                restore_paths(result, path)
        restore(result_value)
        return result_value
    # Historical plain results and other scientific result types retain their
    # existing representation; cached projects are the new bounded format.
    return value


def _digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dependency_versions():
    """Include declared optional engines so installing one invalidates reuse."""
    from PyFLASH.dependencies import check
    return {entry['package']:entry['version'] for entry in check()}


def _write_pickle(path,value):
    fd,temporary = tempfile.mkstemp(dir=path.parent,prefix=".queue-",suffix=".tmp")
    try:
        with os.fdopen(fd,"wb") as stream:
            pickle.dump(value,stream,protocol=pickle.HIGHEST_PROTOCOL)
            stream.flush()
            os.fsync(stream.fileno())
        from PyFLASH._persistence import atomic_replace
        atomic_replace(temporary,path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _prepare(experiments,request):
    sources = experiments if isinstance(experiments,dict) else {"default":experiments}
    errors,_ = spec.validate_spec(request,sources)
    prepared = []
    destinations = set()
    for i,entry in enumerate(request.get("plots",[])):
        if not isinstance(entry,dict) or entry.get("type") not in spec.PLOT_REGISTRY:
            continue
        try:
            fn,kwargs = spec.resolve_plot_call(entry['type'],
                {key:value for key,value in entry.items() if key not in spec._SPEC_KEYS})
        except (ValueError, TypeError) as exc:
            errors.append(f"plots[{i}]: {exc}")
            continue
        name = entry.get("batch")
        if not name and len(sources) != 1:
            errors.append(f"plots[{i}]: choose a batch explicitly when multiple sources are supplied")
        source = sources.get(name) if name else next(iter(sources.values()),None)
        try:
            inspect.signature(fn).bind(source,**kwargs)
        except TypeError as exc:
            errors.append(f"plots[{i}]: {exc}")
        from PyFLASH.ui.workspace import parameter_inputs
        try:
            parameter_inputs(kwargs,action=entry['type'],require_existing=True)
        except (OSError,ValueError) as exc:
            errors.append(f'plots[{i}]: {exc}')
        # Explicitly requested same output names are collisions. Ordinary
        # package-specific filenames are captured by the save observer below.
        directory = kwargs.get("output_dir") or kwargs.get("save_path")
        filename = kwargs.get("save_name") or kwargs.get("filename")
        if not filename:
            for parameter_name in ('save_name','filename'):
                parameter = inspect.signature(fn).parameters.get(parameter_name)
                if parameter is not None and isinstance(parameter.default,str):
                    filename = parameter.default
                    break
        if directory and filename:
            destination = str(Path(directory).resolve()/str(filename))
            if destination in destinations:
                errors.append(f"plots[{i}]: output collision: {destination}")
            destinations.add(destination)
        prepared.append((fn,source,kwargs))
    if errors:
        raise ValueError("Queue validation failed before execution:\n"+"\n".join(errors))
    return prepared,sources


def _read_queue_record(path):
    """Read explicit versions; migrate old records in memory without overwriting."""
    from PyFLASH.ui.workspace import read_operation_state
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(raw, dict) or type(raw.get('schema_version')) is not int
            or raw['schema_version'] not in {1, 2}):
        raise ValueError('Queue/grid record has an unsupported schema version.')
    return raw['schema_version'], read_operation_state(path)


def _portable_identity(payload):
    from PyFLASH.ui.workspace import portable_run_record
    return portable_run_record(payload)


def _validate_queue_state(state, identity, payload, request, root):
    """Validate the whole resume plan before writing progress or starting a call."""
    if (not isinstance(state, dict) or type(state.get('schema_version')) is not int
            or state['schema_version'] != 2 or state.get('identity') != identity):
        raise ValueError('Queue inputs, parameters, schema or scientific code changed; choose a new progress path.')
    canonical = json.loads(json.dumps(payload, sort_keys=True, default=str))
    if state.get('record') != canonical:
        raise ValueError('Queue saved record does not match its input identity.')
    items = state.get('items')
    if not isinstance(items, list) or len(items) != len(request['plots']):
        raise ValueError('Queue saved items do not match the requested calls.')
    statuses = {'pending', 'running', 'done', 'failed', 'interrupted'}
    def checked_file(row, item_index, *, verify):
        if (not isinstance(row, dict) or not isinstance(row.get('path'), str) or not row['path']
                or not isinstance(row.get('sha256'), str) or len(row['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in row['sha256'])):
            raise ValueError(f'Queue item {item_index} has invalid output/input metadata.')
        filename = Path(row['path'])
        if not filename.is_absolute():
            filename = root / filename
        if verify and (not filename.is_file() or _digest_file(filename) != row['sha256']):
            raise ValueError(f'Completed queue item {item_index} changed or lost an output or input; refusing to skip it.')
    for index, (item, entry) in enumerate(zip(items, request['plots'], strict=True)):
        if (not isinstance(item, dict) or type(item.get('index')) is not int
                or item['index'] != index or item.get('type') != entry['type']):
            raise ValueError('Queue saved item order or action identity is invalid.')
        if item.get('status') not in statuses:
            raise ValueError(f'Queue item {index} has an invalid status.')
        attempts = item.get('attempts')
        if not isinstance(attempts, list) or any(
                not isinstance(attempt, dict) or attempt.get('status') not in statuses-{'pending'}
                for attempt in attempts):
            raise ValueError(f'Queue item {index} has invalid attempts.')
        completed = item['status'] == 'done'
        for field in ('outputs', 'input_files'):
            rows = item.get(field, [] if not completed else None)
            if not isinstance(rows, list):
                raise ValueError(f'Queue item {index} has invalid {field} records.')
            for row in rows:
                checked_file(row, index, verify=completed)
        if completed:
            checked_file(item.get('result'), index, verify=True)


def run_spec_queue(experiments,path,progress_path,*,resume=True,retry_failed=True,output_root=None):
    """Validate every entry, isolate failures, and resume only matching inputs/code.

    Returns a summary dictionary. A completed call is skipped only after its
    recorded result and figure hashes have been verified. Interrupted and failed
    entries can be retried; previous attempt errors stay in progress history.
    Unknown parameters and missing required arguments stop the whole queue before
    any call runs. Load only progress/result directories produced by trusted code.
    """
    from PyFLASH.ui.workspace import write_operation_state as write_json
    from PyFLASH.config import config_snapshot
    from PyFLASH import utils
    from PyFLASH.aesthetics import get_pyflash_style
    request = spec.load_spec(path)
    prepared,sources = _prepare(experiments,request)
    from PyFLASH.ui.workspace import parameter_inputs
    from PyFLASH.actions import output_parameters
    declared_inputs = [parameter_inputs(kwargs,action=entry['type'],require_existing=True)
                       for entry,(_,_,kwargs) in zip(request['plots'],prepared,strict=True)]
    progress_path = Path(progress_path).resolve()
    payload = {"spec":request,"version":version("PyFLASH-analysis"),
               'output_root':str(Path(output_root).resolve()) if output_root else None,
               "configuration": config_snapshot(),
               "dependencies": _dependency_versions(),
               "style":get_pyflash_style(),
               'parameter_inputs':declared_inputs,
               "code":{str(p.relative_to(Path(__file__).parent)):_digest_file(p)
                       for p in Path(__file__).parent.rglob("*.py")},
               "inputs":{name:hashlib.sha256(pickle.dumps(obj,protocol=5)).hexdigest() for name,obj in sources.items()}}
    identity = hashlib.sha256(json.dumps(_portable_identity(payload),sort_keys=True,default=str).encode("utf-8")).hexdigest()
    if progress_path.exists():
        if not resume:
            raise FileExistsError(f"Preserve the existing queue; choose a new progress path: {progress_path}")
        try:
            stored_version, state = _read_queue_record(progress_path)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError('Queue saved record is unreadable; preserve it before retrying.') from exc
        if stored_version == 1:
            legacy_identity = hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode('utf-8')).hexdigest()
            if state.get('identity') == legacy_identity:
                # Only the format changes; scientific code and input hashes
                # must still match the historical identity before migration.
                state['identity'] = identity
        _validate_queue_state(state, identity, payload, request, progress_path.parent)
    else:
        state = {"schema_version":2,"identity":identity,"record":payload,"items":[
            {"index":i,"type":entry["type"],"status":"pending","attempts":[]} for i,entry in enumerate(request["plots"])]}
    progress_path.parent.mkdir(parents=True,exist_ok=True)
    result_dir = progress_path.parent/(progress_path.stem+"-results")
    result_dir.mkdir(exist_ok=True)
    started = time.perf_counter()
    def portable(path):
        path = Path(path).resolve()
        try:
            return str(path.relative_to(progress_path.parent))
        except ValueError:
            return str(path)
    def resolved(path):
        path = Path(path)
        return path if path.is_absolute() else progress_path.parent/path
    def summary_record():
        summary = {"schema_version":2,"identity":identity,"elapsed_seconds":time.perf_counter()-started,
                   "successes":[i["index"] for i in state["items"] if i["status"] == "done"],
                   "failures":[{"index":i["index"],"type":i["type"],"error":i.get("error")} for i in state["items"] if i["status"] == "failed"],
                   "pending":[i["index"] for i in state["items"] if i["status"] not in {"done","failed"}]}
        write_json(progress_path.with_name(progress_path.stem+"-summary.json"),summary)
        return summary
    write_json(progress_path,state)
    summary_record()
    for i,(fn,source,kwargs) in enumerate(prepared):
        item = state["items"][i]
        if item["status"] == "done":
            paths = [item["result"]]+item.get("outputs",[])
            if not all(resolved(p["path"]).is_file() and _digest_file(resolved(p["path"])) == p["sha256"] for p in paths):
                raise ValueError(f"Completed queue item {i} changed or lost an output; refusing to skip it.")
            if any(not Path(row['path']).is_file() or _digest_file(row['path']) != row['sha256']
                   for row in item.get('input_files',[])):
                raise ValueError(f'Completed queue item {i} has changed image inputs; choose a new progress path.')
            continue
        if item["status"] == "failed" and not retry_failed:
            continue
        item["status"] = "running"
        write_json(progress_path,state)
        saved = []
        def observer(full_path,*args):
            saved.append({"path":portable(full_path),"sha256":_digest_file(full_path)})
        utils.register_fig_saved_observer(observer)
        attempt = {"started_at":time.time()}
        attempt_dir = result_dir/f'item-{i:04d}'/f'attempt-{len(item["attempts"])+1:04d}'
        attempt_dir.mkdir(parents=True,exist_ok=False)
        figure_dir = ((Path(output_root)/f'item-{i:04d}'/attempt_dir.name)
                      if output_root else attempt_dir)/'figures'
        from PyFLASH.image_io import observe_image_reads
        import threading
        external_inputs = {row['path']:row for row in declared_inputs[i]}
        input_lock = threading.Lock()
        def image_read(filename):
            filename = str(Path(filename).resolve())
            with input_lock:
                if filename not in external_inputs:
                    external_inputs[filename] = {'parameter':'image_pixels','path':filename,
                                                 'sha256':_digest_file(filename)}
        try:
            # Repeated parameter choices own separate figure directories. Shared
            # input measurements remain untouched; explicit destinations retain
            # the caller's ownership and are checked for collisions above.
            target = source
            figure_dir.mkdir(parents=True,exist_ok=True)
            if hasattr(source,'fig_path'):
                target = copy(source)
                target.fig_path = str(figure_dir)
                target.image_fig_path = str(figure_dir/'Images')
            kwargs = dict(kwargs)
            for name in output_parameters(request['plots'][i]['type']):
                if output_root or not kwargs.get(name):
                    kwargs[name] = str(figure_dir)
            with observe_image_reads(image_read):
                result = fn(target,**kwargs)
            if any(_digest_file(row['path']) != row['sha256'] for row in external_inputs.values()):
                raise ValueError('Analysis input content changed while running this queue item.')
            result_path = attempt_dir/'result.pkl'
            _write_pickle(result_path,result)
            item.update(status="done",result={"path":portable(result_path),"sha256":_digest_file(result_path)},outputs=saved)
            item.pop("error",None)
            attempt["status"] = "done"
        except Exception as exc:
            item.update(status="failed",error=f"{type(exc).__name__}: {exc}",outputs=saved)
            attempt.update(status="failed",error=item["error"])
        except BaseException as exc:
            item.update(status='interrupted',error=f'{type(exc).__name__}: {exc}',outputs=saved)
            attempt.update(status='interrupted',error=item['error'])
            raise
        finally:
            utils.unregister_fig_saved_observer(observer)
            # Capture tables and other owned files as well as observed figures,
            # including partial outputs of an unsuccessful attempt.
            emitted = {str(resolved(row['path']).resolve()):row for row in saved}
            for directory in (attempt_dir,figure_dir):
                if directory.is_dir():
                    for file in directory.rglob('*'):
                        if file.is_file() and file.name != 'result.pkl':
                            emitted[str(file.resolve())] = {'path':portable(file),'sha256':_digest_file(file)}
            item['outputs'] = list(emitted.values())
            item["attempts"].append(attempt)
            attempt['ended_at'] = time.time()
            item['input_files'] = list(external_inputs.values())
            attempt_receipt = attempt_dir/'attempt.json'
            write_json(attempt_receipt,{'schema_version':2,'identity':identity,'record':payload,
                'index':i,'parameters':request['plots'][i],**attempt,'outputs':item.get('outputs',[]),
                'result':item.get('result'),'input_files':item['input_files']})
            attempt['receipt'] = portable(attempt_receipt)
            item.setdefault('outputs',[]).append({'path':portable(attempt_receipt),'sha256':_digest_file(attempt_receipt)})
            write_json(progress_path,state)
            summary_record()
    return summary_record()


def expand_grid(parameters, choices, *, max_cells=64):
    """Build the Cartesian product without allocating an oversized grid."""
    if not choices or any(not isinstance(values, (list, tuple)) or not values for values in choices.values()):
        raise ValueError('Choose at least one parameter, with a non-empty value list.')
    count = math.prod(len(values) for values in choices.values())
    if count > max_cells:
        raise ValueError(f'This grid requests {count} cells; the limit is {max_cells}. Reduce the value lists.')
    names = sorted(choices)
    return [{**parameters, **dict(zip(names, values))} for values in itertools.product(*(choices[name] for name in names))]


def _validate_grid_record(record, key, parameters, identity, directory):
    """Reject malformed or future cache records before changing progress."""
    if not isinstance(record, dict) or type(record.get('schema_version')) is not int or record['schema_version'] != 2:
        raise ValueError('Cached grid cell has an unsupported schema version.')
    canonical = lambda value: json.loads(json.dumps(value, sort_keys=True, default=str))
    if (record.get('key') != key or record.get('parameters') != canonical(parameters)
            or record.get('identity') != canonical(identity)):
        raise ValueError('Cached grid cell identity does not match its declared inputs.')
    if record.get('status') not in {'running', 'done', 'failed', 'interrupted'}:
        raise ValueError('Cached grid cell has an invalid status.')
    if not isinstance(record.get('attempts'), list):
        raise ValueError('Cached grid cell has an invalid attempts record.')
    if record['status'] != 'done':
        return
    outputs = record.get('outputs')
    if not isinstance(outputs, list) or not outputs or not isinstance(record.get('input_files'), list):
        raise ValueError('Completed cached grid cell must declare its outputs and input records.')
    def internal(value):
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ValueError('Cached grid cell has an invalid internal output path.')
        path = (directory / value).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError('Cached grid cell output leaves its owned directory.')
        return path
    result = record.get('result')
    internal(result)
    internal(record.get('accepted_receipt'))
    recorded_paths = set()
    for row in outputs:
        if not isinstance(row, dict) or not isinstance(row.get('sha256'), str) or len(row['sha256']) != 64:
            raise ValueError('Cached grid cell has invalid output hash metadata.')
        output = internal(row.get('path'))
        if output in recorded_paths:
            raise ValueError('Cached grid cell declares duplicate outputs.')
        recorded_paths.add(output)
        if not output.is_file() or _digest_file(output) != row['sha256']:
            raise ValueError('Cached grid cell lost or changed an output; preserve it and choose a new cache.')
    if internal(result) not in recorded_paths:
        raise ValueError('Cached grid cell result is missing from its declared outputs.')


def run_action_grid(data, action, parameters, choices, progress_path, *, cache_dir=None,
                    max_cells=64, memory_budget_bytes=None, disk_budget_bytes=None,
                    cancel_path=None, on_cell=None):
    """Stream resumable, content-keyed registered calls with bounded resources.

    Changing the enclosing grid never invalidates unchanged cells. Each cell
    owns its outputs; reuse requires every recorded output and result hash.
    Cancellation occurs between scientific calls, preserving finished cells.
    """
    from PyFLASH.actions import call_action, resolve_action, action_access, ACTION_REGISTRY, output_parameters
    from PyFLASH._persistence import code_identity
    from PyFLASH.ui.workspace import write_operation_state as write_json
    from PyFLASH.config import config_snapshot
    import psutil
    if action not in spec.PLOT_REGISTRY and (action not in ACTION_REGISTRY or action_access(action) != 'read-only'):
        raise ValueError('Sweeps require a declared analysis or read-only helper.')
    cells = expand_grid(parameters, choices, max_cells=max_cells)
    from PyFLASH.ui.workspace import parameter_inputs
    cell_inputs = []
    for cell in cells:
        resolve_action(action, data, cell)
        cell_inputs.append(parameter_inputs(cell, action=action, require_existing=True,
                                           hash_contents=False))
    # Stream the source fingerprint rather than holding a second pickle in RAM.
    digest = hashlib.sha256()
    class Fingerprint:
        size = 0
        def write(self, value):
            digest.update(value)
            self.size += len(value)
            return len(value)
    stream = Fingerprint()
    pickle.dump(data, stream, protocol=5)
    configuration = config_snapshot()
    from PyFLASH.aesthetics import get_pyflash_style
    style = get_pyflash_style()
    dimensions = [cell.get('figsize') or style['figure_size'] for cell in cells]
    width, height = max(dimensions, key=lambda size:size[0]*size[1])
    dpi = configuration.get('FIGURE_DPI') or style['save_dpi']
    image_bytes = max(1, int(width * height * dpi * dpi * 4)) if action in spec.PLOT_REGISTRY else 0
    input_sizes = {row['path']: row['size'] for records in cell_inputs for row in records}
    peak_inputs = max((sum({row['path']: row['size'] for row in records}.values())
                       for records in cell_inputs), default=0)
    memory = (stream.size + peak_inputs) * 6 + image_bytes * 4 + 16 * 1024**2
    disk = len(cells) * (stream.size + image_bytes * 2 + 1024**2) + sum(input_sizes.values())
    progress_path = Path(progress_path).resolve()
    ancestor = progress_path.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    free_memory = psutil.virtual_memory().available if memory_budget_bytes is None else memory_budget_bytes
    free_disk = shutil.disk_usage(ancestor).free if disk_budget_bytes is None else disk_budget_bytes
    if memory > free_memory or disk > free_disk:
        raise ValueError(f'This grid needs about {memory / 1024**2:.1f} MiB memory and {disk / 1024**2:.1f} MiB disk; '
                         f'available: {free_memory / 1024**2:.1f} MiB memory, {free_disk / 1024**2:.1f} MiB disk. Reduce the grid.')
    input_hashes = {}
    cell_inputs = [parameter_inputs(cell, action=action, require_existing=True,
                                   hash_cache=input_hashes) for cell in cells]
    identity = {'data_sha256':digest.hexdigest(), 'action':action, 'configuration':configuration,
                'style':style, 'code':code_identity(), 'dependencies':_dependency_versions()}
    cache = Path(cache_dir).resolve() if cache_dir else progress_path.parent / 'cell-cache'
    plans = []
    for index, cell in enumerate(cells):
        key = hashlib.sha256(json.dumps(_portable_identity({**identity, 'parameters': cell,
                                        'input_files': cell_inputs[index]}), sort_keys=True,
                                       allow_nan=False, default=str).encode('utf-8')).hexdigest()
        directory = cache / key
        receipt_path = directory / 'cell.json'
        if receipt_path.exists():
            try:
                _, record = _read_queue_record(receipt_path)
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f'Cached grid cell {index} has an unreadable record; preserve it.') from exc
            _validate_grid_record(record, key, cell, identity, directory)
        else:
            record = None
        plans.append((key, directory, receipt_path, record))
    # Completed results may be larger than their inputs. Bound their retained
    # decoded data plus one temporary decode before reading any cached pickle.
    result_sizes = [((directory / record['result']).stat().st_size)
                    for _,directory,_,record in plans if record and record['status']=='done']
    if result_sizes:
        memory = max(memory, 16*1024**2 + sum(result_sizes)*6 + max(result_sizes)*6)
        if memory > free_memory:
            raise ValueError(f'Cached grid results need about {memory / 1024**2:.1f} MiB memory; '
                             f'available: {free_memory / 1024**2:.1f} MiB memory. Reduce the grid.')
        # Validate every decoded result version before progress or any earlier
        # pending cell can execute. Only one decoded result is held at a time.
        for _,directory,_,record in plans:
            if record and record['status']=='done':
                _read_grid_value(directory / record['result'])
    cache.mkdir(parents=True, exist_ok=True)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    state = {'schema_version':2, 'action':action, 'choices':choices, 'parameters':parameters,
             'identity':identity, 'resources':{'memory_bytes':memory, 'disk_bytes':disk},
             'items':[], 'failures':[], 'pending':list(range(len(cells))), 'cancelled':False}
    write_json(progress_path, state)
    answers = []
    for index, cell in enumerate(cells):
        if cancel_path and Path(cancel_path).exists():
            state['cancelled'] = True
            break
        key, directory, receipt_path, record = plans[index]
        reused = bool(record and record['status'] == 'done')
        if reused:
            reused = all(Path(row['path']).is_file() and _digest_file(row['path']) == row['sha256']
                         for row in record.get('input_files', []))
        if reused:
            for output in record['outputs']:
                if not (directory / output['path']).is_file() or _digest_file(directory / output['path']) != output['sha256']:
                    raise ValueError(f'Cached grid cell {index} lost or changed an output. Preserve it and choose a new cache.')
        else:
            directory.mkdir(exist_ok=True)
            attempt = directory / f'attempt-{len(record.get("attempts", [])) if record else 0:04d}'
            attempt.mkdir(exist_ok=False)
            saved = []
            def observer(path, *unused):
                saved.append(Path(path))
            record = {'schema_version':2, 'key':key, 'parameters':cell, 'identity':identity,
                      'attempts':record.get('attempts', []) if record else [], 'status':'running'}
            write_json(receipt_path, record)
            target = copy(data) if data is not None else None
            kwargs = dict(cell)
            if action in spec.PLOT_REGISTRY:
                figure_root = attempt / 'figures'
                figure_root.mkdir()
                if target is not None:
                    target.fig_path = str(figure_root)
                    target.image_fig_path = str(figure_root / 'Images')
                for name in output_parameters(action):
                    kwargs[name] = str(figure_root)
            from PyFLASH import utils
            utils.register_fig_saved_observer(observer)
            started = time.time()
            from PyFLASH.image_io import observe_image_reads
            import threading
            external_inputs = {row['path']: row for row in cell_inputs[index]}
            inputs_lock = threading.Lock()
            def image_read(filename):
                with inputs_lock:
                    filename = str(Path(filename).resolve())
                    if filename not in external_inputs:
                        external_inputs[filename] = {'parameter':'image_pixels', 'path':filename,
                                                     'sha256':_digest_file(filename)}
            try:
                with observe_image_reads(image_read):
                    answer = call_action(action, target, kwargs)
                if any(_digest_file(row['path']) != row['sha256'] for row in external_inputs.values()):
                    raise RuntimeError('Image input changed while computing this grid cell.')
                result_path = attempt / 'result.pkl'
                _write_grid_value(result_path, answer)
                saved.append(result_path)
                outputs = [file for file in attempt.rglob('*') if file.is_file()]
                record.update(status='done', result=str(result_path.relative_to(directory)),
                    input_files=list(external_inputs.values()),
                    accepted_receipt=str((attempt / 'accepted-cell.json').relative_to(directory)),
                    root_relative='..',
                    outputs=[{'path':str(file.relative_to(directory)), 'sha256':_digest_file(file)} for file in outputs])
                record.pop('error', None)
            except BaseException as exc:
                record.update(status='failed' if isinstance(exc, Exception) else 'interrupted',
                              error=f'{type(exc).__name__}: {exc}', outputs=[],
                              input_files=list(external_inputs.values()))
                if not isinstance(exc, Exception):
                    raise
            finally:
                utils.unregister_fig_saved_observer(observer)
                finished = time.time()
                attempted_outputs = [{'path':str(file.relative_to(directory)),'sha256':_digest_file(file)}
                                     for file in attempt.rglob('*') if file.is_file()]
                attempt_receipt = attempt/'attempt.json'
                attempt_record = {'schema_version':2,'status':record['status'],'parameters':cell,
                    'identity':identity,'input_files':list(external_inputs.values()),
                    'started_at':started,'finished_at':finished,'outputs':attempted_outputs,
                    'error':record.get('error')}
                write_json(attempt_receipt,attempt_record)
                record['attempts'].append({'status':record['status'],'started_at':started,
                    'finished_at':finished,'receipt':str(attempt_receipt.relative_to(directory)),
                    'error':record.get('error')})
                if record['status']=='done':
                    record['outputs'].append({'path':str(attempt_receipt.relative_to(directory)),
                                              'sha256':_digest_file(attempt_receipt)})
                write_json(receipt_path, record)
                if record['status'] == 'done':
                    write_json(directory / record['accepted_receipt'], record)
        effective_key = hashlib.sha256(json.dumps(_portable_identity({'key':key, 'inputs':record.get('input_files', [])}),
                                                   sort_keys=True).encode()).hexdigest()
        item = {'index':index, 'key':effective_key, 'parameters':cell, 'status':record['status'], 'reused':reused,
                'receipt':str(directory / record['accepted_receipt']) if record['status'] == 'done' else str(receipt_path),
                'error':record.get('error')}
        state['items'].append(item)
        state['pending'].remove(index)
        if record['status'] == 'done':
            answer = _read_grid_value(directory / record['result'])
            answers.append({**item, 'result':answer, 'input_files':record.get('input_files', []), 'paths':[str(directory / row['path'])
                           for row in record['outputs'] if Path(row['path']).suffix.lower() in {'.svg','.png'}]})
        else:
            item['input_files'] = record.get('input_files',[])
            state['failures'].append(item)
        write_json(progress_path, state)
        if on_cell:
            on_cell(item, answers[-1] if record['status'] == 'done' else None)
    write_json(progress_path, state)
    return {**state, 'results':answers, 'progress_path':str(progress_path)}
