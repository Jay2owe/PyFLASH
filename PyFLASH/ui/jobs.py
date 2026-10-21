"""Bounded, durable background processing, independent of Streamlit sessions."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

from PyFLASH.ui import workspace

ACTIVE_STATES = {"queued", "running"}
_manager_lock = threading.Lock()
_children = {}


class JobBusyError(RuntimeError):
    pass


def jobs_root():
    return workspace.recovery_path().parent / "jobs"


def _job_path(root, job_id):
    # IDs are generated here, never paths supplied by a request.
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ValueError("Invalid processing job identity.")
    return Path(root) / job_id


def _alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextlib.contextmanager
def _locked(root):
    """A short cross-process admission lock; never wait behind a running job."""
    root.mkdir(parents=True, exist_ok=True)
    with _manager_lock, (root / "manager.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if not stream.tell():
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise JobBusyError("Another processing request is being admitted. Try again.") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def read_job(job_id, root=None):
    root = jobs_root() if root is None else Path(root)
    path = _job_path(root, job_id)
    state = workspace.read_operation_state(path / "state.json")
    child = _children.get(job_id)
    if child is not None and child.poll() is not None:
        _children.pop(job_id, None)  # Reap finished process handles.
    if state["status"] in ACTIVE_STATES:
        launch_path = path / "launch.json"
        launched = workspace.read_operation_state(launch_path) if launch_path.exists() else {}
        pid = state.get("worker_pid") or launched.get("pid") or state.get("launcher_pid")
        if not _alive(pid) or (state["status"] == "queued" and time.time() - state["submitted_at"] > 120):
            state.update(status="failed", finished_at=time.time(),
                         error="The processing worker stopped before completing. Logs and inputs are preserved.")
            workspace.write_operation_state(path / "state.json", state)
    return state


def latest_job(root=None):
    root = jobs_root() if root is None else Path(root)
    pointer = root / "latest.json"
    if not pointer.exists():
        return None
    return read_job(workspace.read_operation_state(pointer)["id"], root)


def log_tail(job_id, root=None, max_bytes=12000):
    root = jobs_root() if root is None else Path(root)
    path = _job_path(root, job_id) / "progress.log"
    if not path.exists():
        return ""
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - max_bytes))
        return stream.read(max_bytes).decode("utf-8", errors="replace")


def _launch(request_path, log_stream, env):
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=log_stream, stderr=log_stream,
                  env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    args = ["-u", "-m", "PyFLASH.ui.job_worker", str(request_path)]
    actual = Path(sys.prefix) / 'python.exe'
    executable = str(actual) if os.name == 'nt' and actual.is_file() else sys.executable
    # A major/minor launcher can choose a different installation and lose the
    # running app's dependencies. Use this environment's actual executable.
    return subprocess.Popen([executable, *args], **kwargs)


def _submit(payload, name, root):
    root = jobs_root() if root is None else Path(root)
    # JSON roundtrip detaches nested lists/dictionaries from later UI edits.
    snapshot = json.loads(json.dumps(payload))
    with _locked(root):
        previous = latest_job(root)
        if previous and previous["status"] in ACTIVE_STATES:
            raise JobBusyError("Processing is already running. You can continue using the other pages.")
        job_id = uuid.uuid4().hex
        path = _job_path(root, job_id); path.mkdir()
        request = {"schema_version": 1, "id": job_id, **snapshot}
        state = {"schema_version": 1, "id": job_id, "name": name, "kind": snapshot["kind"],
                 "status": "queued", "submitted_at": time.time(), "launcher_pid": os.getpid()}
        workspace.write_operation_state(path / "request.json", request)
        workspace.write_operation_state(path / "state.json", state)
        workspace.write_operation_state(root / "latest.json", {"id": job_id})
        env = os.environ.copy()
        env.update(MPLBACKEND="Agg", PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1", OMP_NUM_THREADS="1",
                   OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1")
        try:
            with (path / "progress.log").open("ab", buffering=0) as stream:
                child = _launch(path / "request.json", stream, env)
            _children[job_id] = child
            # Worker owns state.json once launched; publish its PID separately
            # to avoid overwriting a fast worker's completion with queued state.
            workspace.write_operation_state(path / "launch.json", {"pid": child.pid})
        except Exception as exc:
            state.update(status="failed", finished_at=time.time(), error=str(exc))
            workspace.write_operation_state(path / "state.json", state)
            raise
    return job_id


def start_processing(project, *, rerun=False, reimport_images=False, root=None):
    """Submit immutable settings; one active worker, no waiting queue."""
    return _submit({"kind": "processing", "project": project, "rerun": bool(rerun),
                    "reimport_images": bool(reimport_images)}, project.get("name", "Analysis"), root)


def start_dependency_repair(package, *, dataset_token, root=None):
    from PyFLASH.dependencies import registry
    if package not in registry():
        raise ValueError('Choose a declared dependency.')
    return _submit({'kind': 'dependency', 'action': 'PyFLASH.dependencies.repair',
                    'parameters': {'package': package}, 'dataset_token': dataset_token,
                    'target_key': 'ui_dependency_result'}, f'Install {package}', root)


def start_value_action(action, parameters, *, name, dataset_token, target_key, root=None):
    """Run declared scalar/support helpers without requiring a microscopy source."""
    from PyFLASH.actions import HELPER_ACTIONS, resolve_action
    if action not in HELPER_ACTIONS or HELPER_ACTIONS[action][1] != 'value':
        raise ValueError('Choose a declared source-free helper.')
    resolve_action(action, parameters=parameters)
    return _submit({'kind': 'function_value', 'action': action, 'parameters': parameters,
                    'dataset_token': dataset_token, 'target_key': target_key}, name, root)


def start_operation(kind, source, parameters, *, name, dataset_token, target_key,
                    representatives=None, root=None):
    """Queue a figure/image/export against its saved source and current edits."""
    if kind not in {"figure", "figure_spec", "workbooks", "csv", "save", "function"}:
        raise ValueError("Unknown background operation.")
    if not source or not source.get("path"):
        raise ValueError("Save this analysis first so the background operation has a reproducible input.")
    return _submit({"kind": kind, "source": source, "parameters": parameters,
                    "dataset_token": dataset_token, "target_key": target_key,
                    "representatives": representatives}, name, root)


def start_sweep(action, parameters, choices, *, name, dataset_token, target_key,
                source=None, representatives=None, choice_sets=None, root=None):
    """Submit the same registered analysis over explicitly chosen value lists."""
    from PyFLASH.queue import expand_grid
    expand_grid(parameters.get('kwargs', {}), choices)
    return _submit({'kind':'sweep', 'source':source,
        'parameters':{**parameters, 'action':action, 'choices':choices, 'choice_sets':choice_sets or {}},
        'dataset_token':dataset_token, 'target_key':target_key, 'representatives':representatives}, name, root)


def cancel_job(job_id, root=None):
    """Request cancellation between grid cells, without killing scientific code."""
    root = jobs_root() if root is None else Path(root)
    state = read_job(job_id, root)
    if state['kind'] != 'sweep' or state['status'] not in ACTIVE_STATES:
        raise ValueError('Only a running analysis grid can be cancelled between cells.')
    marker = _job_path(root, job_id) / 'cancel.request'
    marker.touch()
    return str(marker)


def _execute_sweep(batch, request, path):
    from PyFLASH.queue import run_action_grid
    params = request['parameters']
    kwargs = dict(params['kwargs'])
    from PyFLASH.spec import PLOT_REGISTRY
    if params['action'] in PLOT_REGISTRY:
        from PyFLASH.config import Config
        from PyFLASH.aesthetics import set_pyflash_style
        Config.SAVE_MODE = True
        if params.get('style'):
            set_pyflash_style(params['style'])
        fn, kwargs = workspace.plot_contract(params['action'], kwargs)
        import inspect
        signature = inspect.signature(fn)
        for name in ('roi_base','roi'):
            if name in signature.parameters and params.get('region') is not None:
                kwargs.setdefault(name, params['region'])
                break
        if 'save' in signature.parameters:
            kwargs.setdefault('save', True)
        if 'show' in signature.parameters:
            kwargs.setdefault('show', False)
        if params.get('target_experiment'):
            batch = next(item for item in batch.experiment_list if item.name == params['target_experiment'])
    completed = []
    def cell_ready(item, answer):
        if answer is None:
            return
        directory = path / f'cell-{item["index"]:04d}'
        directory.mkdir(exist_ok=True)
        cell = {key:value for key,value in answer.items() if key != 'result'}
        cell.update(_result_tables(answer['result'], directory))
        workspace.write_operation_state(directory / 'result.json', cell)
        completed.append(cell)
    result = run_action_grid(batch, params['action'], kwargs, params['choices'], path / 'grid-progress.json',
        cache_dir=path.parent / 'grid-cell-cache', cancel_path=path / 'cancel.request', on_cell=cell_ready)
    return {'type':'grid:'+params['action'], 'action':params['action'], 'cells':completed,
            'parameters':params['kwargs'], 'style':params.get('style', {}), 'choices':params['choices'],
            'choice_sets':params.get('choice_sets', {}), 'failures':result['failures'],
            'pending':result['pending'], 'cancelled':result['cancelled'],
            'progress_path':result['progress_path'], 'log':log_tail(request['id'], path.parent)}


def completed_result(state, dataset_token, root=None):
    """A result for an old dataset can never overwrite the current views."""
    root = jobs_root() if root is None else Path(root)
    path = _job_path(root, state["id"])
    request = workspace.read_operation_state(path / "request.json")
    if (state["status"] != "succeeded" or request.get("kind", "processing") == "processing"
            or request.get("dataset_token") != dataset_token):
        return None
    return request["target_key"], workspace.read_operation_state(path / "result.json")


def _run_operation(request, path):
    from PyFLASH.ui import services, figures
    source = request["source"]
    expected_version = source.get("version")
    if expected_version is not None and workspace.source_version(source["path"]) != expected_version:
        raise ValueError("The source file changed after submission. Reopen it before retrying.")
    if source["kind"] == "pickle":
        batch = services.open_pickle(source["path"])
    else:
        batch = workspace.load_table(source["path"], demo=source["kind"] == "demo",
            group_col=source.get("group_col", "Condition"), subject_col=source.get("subject_col", "AnimalName"))
    if expected_version is not None and workspace.source_version(source["path"]) != expected_version:
        raise ValueError("The source file changed while it was being opened. Reopen it before retrying.")
    if request.get("representatives") is not None:
        services.set_representative_selections(batch, workspace.restore_selection_snapshot(request["representatives"]))
    kind, params = request["kind"], request["parameters"]
    if kind == 'sweep':
        return _execute_sweep(batch, request, path)
    if kind == "csv":
        output = path / "summary.csv"
        from PyFLASH.actions import call_action
        call_action('PyFLASH.ui.services.export_summary_csv', batch,
                    {'filename':str(output), **params})
        return {"path": str(output), "region": params.get("region"), 'parameters':params}
    if kind == "workbooks":
        output_paths = services.export_excel(batch, **{**params, "capture": False, 'return_paths':True})
        return {'paths':output_paths, "log": log_tail(request["id"], path.parent)}
    if kind == "save":
        services.save_batch(batch, params["filename"])
        return {"path": str(Path(params["filename"]).resolve())}
    if kind == "function":
        from PyFLASH.ui import function_contracts
        contract = function_contracts.find(params["function_key"])
        if contract is None:
            raise ValueError("Unknown function.")
        context = function_contracts.input_context(batch, params.get("region"))
        issues = function_contracts.validate(contract, params["kwargs"], context)
        if issues:
            raise ValueError("; ".join(issues.values()))
        func, kwargs = function_contracts.public_call(contract, batch, params["kwargs"], params.get("region"))
        output = func(**kwargs)
        values = _result_tables(output, path)
        return {"type": params["function_key"], "parameters": params["kwargs"], **values,
                "script": _public_script(source, contract, params), "log": log_tail(request["id"], path.parent)}
    target = batch
    experiment_name = params.get("target_experiment")
    if experiment_name is not None:
        target = next(e for e in batch.experiment_list if e.name == experiment_name)
    # Each UI run owns its figures; an edited recipe never overwrites an earlier
    # result still displayed in another function. Source identities are intact.
    target.fig_path = str(path / "figures")
    target.image_fig_path = str(path / "figures" / "Images")
    Path(target.fig_path).mkdir(exist_ok=True)
    from PyFLASH.config import Config
    from PyFLASH.aesthetics import set_pyflash_style
    Config.SAVE_MODE = True
    style = params.get("style") or {}
    if style:
        set_pyflash_style(style)
    started = time.time()
    script = None
    if kind == "figure_spec":
        from PyFLASH.queue import run_spec_queue
        outcome = run_spec_queue(target, params['spec_path'], path / 'spec-progress.json',
                                 output_root=target.fig_path)
        if outcome['failures'] or outcome['pending']:
            raise ValueError("Figure specification failed: " + str(outcome))
        plot_type, kwargs = "saved_figure_specification", {"specification": params["spec_path"], "outcome": outcome}
    else:
        plot_type = params["plot_type"]
        func, kwargs = workspace.plot_contract(plot_type, params["kwargs"])
        if params.get("region") is not None:
            import inspect
            signature = inspect.signature(func)
            for region_name in ("roi_base", "roi"):
                if region_name in signature.parameters:
                    kwargs.setdefault(region_name, params["region"])
                    break
        # run_quick_plot delegates to the same registry and package function.
        import inspect
        signature = inspect.signature(func)
        # Output saving and desktop-window suppression belong to the web adapter.
        if "save" in signature.parameters or plot_type == "representative_images":
            kwargs.setdefault("save", True)
        if "show" in signature.parameters or plot_type == "representative_images":
            kwargs.setdefault("show", False)
        output = services.run_quick_plot(target, plot_type, kwargs)
        script = workspace.equivalent_script(source["path"], plot_type, kwargs,
            source_kind=source["kind"], group_col=source.get("group_col", "Condition"),
            subject_col=source.get("subject_col", "AnimalName"), style=style,
            target_experiment=experiment_name)
        if request.get("representatives") is not None:
            edit_lines = ["from PyFLASH.ui.workspace import restore_selection_snapshot",
                "from PyFLASH.ui.services import set_representative_selections",
                f"set_representative_selections(batch, restore_selection_snapshot({request['representatives']!r}))"]
            script = script.replace("PARAMETERS =", "\n".join(edit_lines) + "\nPARAMETERS =", 1)
    root = getattr(target, "fig_path", None)
    paths = figures.locate_saved_figures(root, since=started)
    if paths and kind == "figure":
        record = workspace.run_record(source, plot_type, kwargs, paths, style)
        record["representative_edits"] = request.get("representatives")
        workspace.write_json(Path(paths[0]).parent / "ui-recipe.json", record)
        if script:
            (Path(paths[0]).parent / "ui-replay.py").write_text(script, encoding="utf-8")
    data = _result_tables(output, path) if kind == "figure" else {}
    return {"type": plot_type, "root": root, "paths": paths, "since": started,
            "script": script, "parameters": kwargs, "style": style, **data,
            "target_experiment": experiment_name,
            "log": log_tail(request["id"], path.parent)}


def _result_tables(output, path):
    """Keep complete returned tables; the browser may display only their first rows."""
    import pandas as pd
    tables, seen = [], set()
    def collect(value, name="Result"):
        if id(value) in seen:
            return None
        if isinstance(value, (dict, tuple, list, pd.DataFrame, pd.Series)):
            seen.add(id(value))
        if isinstance(value, (pd.DataFrame, pd.Series)):
            output_path = path / f"result-table-{len(tables) + 1}.csv"
            value.to_csv(output_path, index=True)
            tables.append({"name": name, "path": str(output_path)})
            return f"Table: {name}"
        if isinstance(value, dict):
            return {str(k): collect(v, f"{name} / {k}") for k,v in value.items()}
        if isinstance(value, (tuple, list)):
            return [collect(v, f"{name} / {i + 1}") for i,v in enumerate(value)]
        if hasattr(value, "item") and getattr(value, "size", 1) == 1:
            return collect(value.item(), name)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)
    value = collect(output)
    return {"tables": tables, "value": value}


def _public_script(source, contract, params):
    """Replay declared helpers with the same content-verified source binding."""
    return workspace.equivalent_action_script(contract.entry.key, params['kwargs'], source,
                                             region=params.get('region'))


def run_request(request_path, *, create=None, save=None):
    """Worker entry; injectable owning-package calls support deterministic tests."""
    path = Path(request_path).parent
    request = workspace.read_operation_state(request_path)
    state = workspace.read_operation_state(path / "state.json")
    state.update(status="running", started_at=time.time(), worker_pid=os.getpid())
    workspace.write_operation_state(path / "state.json", state)
    previous_output = previous_verbosity = None
    image_observer = None
    appearance_context = None
    input_records = []
    observed = {}
    try:
        if request.get('kind') in {'figure','figure_spec','sweep'}:
            from PyFLASH.aesthetics import pyflash_style_context
            appearance_context = pyflash_style_context()
            appearance_context.__enter__()
        from PyFLASH.ui import operation_receipts
        from PyFLASH.ui import services
        from PyFLASH._logging import logger, Verbosity
        previous_output, previous_verbosity = logger._output, logger.verbosity
        logger.set_output(sys.stdout)
        logger.verbosity = Verbosity.info
        # Saving over the opened pickle must retain the original replay input.
        if request.get('kind') == 'save' and Path(request['parameters']['filename']).resolve() == Path(request['source']['path']).resolve():
            original = path / 'opened-analysis.pkl'
            shutil.copy2(request['source']['path'], original)
            request['source'] = {**request['source'], 'path':str(original),
                                 'version':workspace.source_version(original)}
            workspace.write_operation_state(path / 'request.json', request)
        input_records = operation_receipts.inputs(request,records=input_records)
        from PyFLASH.image_io import observe_image_reads
        observed_lock = threading.Lock()
        def image_read(filename):
            with observed_lock:
                filename = str(Path(filename).resolve())
                if filename not in observed:
                    existing = next(parent for parent in Path(filename).parents if parent.exists())
                    size = Path(filename).stat().st_size
                    if size > shutil.disk_usage(existing).free:
                        raise RuntimeError(f'Image read needs {size} bytes locally; free space is insufficient.')
                    observed[filename] = {'parameter':'image_pixels', 'path':filename,
                                          'sha256':workspace.content_hash(filename)}
        image_observer = observe_image_reads(image_read)
        image_observer.__enter__()
        if request.get("kind", "processing") == "processing":
            from PyFLASH.ui.project_io import Project
            project = Project.from_dict(request["project"])
            create = services.create_batch if create is None else create
            batch = create(project.name, services.build_conditions(project.conditions), project.batch_path,
                           experiments=project.experiments or None, pickle_path=project.pickle_path or None,
                           threshold=project.threshold, rerun=request["rerun"], import_images=project.import_images,
                           reimport_images=request["reimport_images"], progress=True)
            result = getattr(batch, "_state_path", None)
            if not result or not Path(result).is_file():
                result = str(path / "analysis.pkl")
                (services.save_batch if save is None else save)(batch, result)
            state["result_path"] = str(Path(result).resolve())
            result_data = {'type':'microscopy_processing', 'result_path':state['result_path']}
        elif request['kind'] == 'sweep' and not request.get('source'):
            result_data = _execute_sweep(None, request, path)
        elif request['kind'] in {'dependency', 'function_value'}:
            from PyFLASH.actions import call_action
            output = call_action(request['action'], parameters=request['parameters'])
            result_data = {'type': request['action'], 'parameters': request['parameters'],
                          **_result_tables(output, path), 'log': log_tail(request['id'], path.parent)}
        else:
            result_data = _run_operation(request, path)
        input_records.extend(observed.values())
        input_records.extend(row for cell in result_data.get('cells', []) for row in cell.get('input_files', []))
        input_records = list({row['path']:row for row in input_records}.values())
        operation_receipts.verify(input_records)
        operation_receipts.complete(request, result_data, path, input_records)
        state.update(status="succeeded", finished_at=time.time())
    except BaseException as exc:
        import traceback
        traceback.print_exc()
        state.update(status="failed", error=str(exc), finished_at=time.time())
        try:
            from PyFLASH.ui import operation_receipts
            operation_receipts.failed(request,state,path,input_records+list(observed.values()))
        except Exception as receipt_error:
            # Preserve the analysis error when evidence storage itself fails.
            state['receipt_error'] = f'{type(receipt_error).__name__}: {receipt_error}'
            traceback.print_exc()
    finally:
        if appearance_context is not None:
            appearance_context.__exit__(None,None,None)
        if image_observer is not None:
            image_observer.__exit__(None, None, None)
        if previous_output is not None:
            logger._output, logger.verbosity = previous_output, previous_verbosity
    workspace.write_operation_state(path / "state.json", state)
    return state


def replay_request(request, output_dir, *, input_records):
    """Execute the same owning operation synchronously in a new output folder."""
    from PyFLASH.ui import operation_receipts
    operation_receipts.verify(input_records)
    request = json.loads(json.dumps(request))
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    request['id'] = uuid.uuid4().hex
    kind = request.get('kind', 'processing')
    if kind == 'save':
        request['parameters']['filename'] = str(output / Path(request['parameters']['filename']).name)
    elif kind == 'workbooks':
        request['parameters']['save_path'] = str(output / 'workbooks')
    elif kind == 'processing':
        project = request['project']
        if not project.get('experiments'):
            from PyFLASH.ui.services import resolve_experiment_paths, discover_experiments
            root = project['batch_path']
            layout = resolve_experiment_paths(root)
            project['experiments'] = {Path(root).name:root} if layout else {
                row['name']:row['path'] for row in discover_experiments(root) if row['valid']}
        project['batch_path'] = str(output / 'processed')
        project['pickle_path'] = str(output / 'states')
        request['rerun'] = True
    workspace.write_operation_state(output / 'request.json', request)
    workspace.write_operation_state(output / 'state.json', {'id':request['id'], 'status':'queued', 'kind':kind})
    state = run_request(output / 'request.json')
    if state['status'] != 'succeeded':
        raise RuntimeError(state['error'])
    return workspace.read_operation_state(output / 'result.json')
