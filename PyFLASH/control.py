"""Installable JSON CLI over the same plot and helper actions as the browser."""
from __future__ import annotations
import argparse
import importlib.util
from importlib.metadata import version, PackageNotFoundError
import inspect
import json
from pathlib import Path
import sys
import time

from PyFLASH.actions import ACTION_REGISTRY, HELPER_ACTIONS, call_action, helper_function, action_access
from PyFLASH.spec import PLOT_REGISTRY, resolve_plot_call, plot_requires_input


def describe(action=None):
    """Return stable action keys, owners and live declared parameters."""
    if action is None:
        return [{"action":name,"owner":owner,"access":"mutating"}
                for name,owner in PLOT_REGISTRY.items()] + [
                {"action":name,"title":title,"binding":binding,"access":action_access(name)}
                for name,(title,binding) in ACTION_REGISTRY.items()]
    if action in PLOT_REGISTRY:
        from PyFLASH.spec import _resolve_func
        fn = _resolve_func(PLOT_REGISTRY[action])
    elif action in ACTION_REGISTRY:
        fn = helper_function(action)[0]
    else:
        raise ValueError(f"Unknown action {action!r}. Valid: {', '.join(sorted(set(PLOT_REGISTRY)|set(ACTION_REGISTRY)))}")
    parameter_metadata = {}
    if action in PLOT_REGISTRY or action in HELPER_ACTIONS:
        from PyFLASH.ui import function_contracts as fc
        from PyFLASH.ui.sweeps import option_sets, UNITS
        contract = fc.find(action)
        options = option_sets(contract, {'metrics':[], 'columns':[], 'markers':[]})
        parameter_metadata = {field.name:{'key':field.name, 'label':field.label,
            'role':field.role, 'help':field.parameter.description or field.label+'.',
            'unit':options.get(field.name, {}).get('unit', UNITS.get(field.name, 'dimensionless')),
            'choices':options.get(field.name, {}).get('values', list(field.choices))}
            for field in contract.fields}
    if action in ACTION_REGISTRY and action not in HELPER_ACTIONS:
        from PyFLASH.actions import support_parameter_metadata
        parameter_metadata = support_parameter_metadata(action)
    return {"action":action,"owner":fn.__module__+'.'+fn.__qualname__,
            "access":action_access(action),
            "parameters":[{"name":name,"kind":str(p.kind),"required":p.default is inspect.Parameter.empty,
                           "default":None if p.default is inspect.Parameter.empty else repr(p.default),
                           **parameter_metadata.get(name,{})}
                          for name,p in inspect.signature(fn).parameters.items()],
            "appearance": _appearance_description() if action in PLOT_REGISTRY else {},
            "documentation":inspect.getdoc(fn) or ACTION_REGISTRY.get(action, ('Run this registered analysis.',))[0]}


def _appearance_description():
    from PyFLASH.aesthetics import PRESENTATION_FIELDS, get_pyflash_style
    return {'argument':'--style','defaults':get_pyflash_style(),'presentation':PRESENTATION_FIELDS}


def doctor():
    from PyFLASH.dependencies import check
    return check()


def json_value(value):
    import math
    if isinstance(value,dict):return {str(k):json_value(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [json_value(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    if hasattr(value,'to_dict'):
        try:return {'type':type(value).__name__,'data':json_value(value.to_dict(orient='split'))}
        except TypeError:return json_value(value.to_dict())
    if hasattr(value,'tolist'):return json_value(value.tolist())
    if isinstance(value,Path):return str(value)
    return {'type':type(value).__name__,'representation':repr(value)}


def _replay_script(args, parameters, source, records, style):
    from PyFLASH.ui.workspace import equivalent_script, equivalent_action_script
    if args.action in PLOT_REGISTRY and source:
        return equivalent_script(source['path'],args.action,parameters,source_kind=source['kind'],
            group_col=args.group_col,subject_col=args.subject_col,style=style,source_sha256=source['sha256'],input_records=records)
    if source:
        source = {**source,'group_col':args.group_col,'subject_col':args.subject_col}
    return equivalent_action_script(args.action,parameters,source,input_records=records,style=style)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('describe','discover','doctor','validate','run','queue'))
    parser.add_argument('action',nargs='?')
    parser.add_argument('--input',type=Path,help='CSV subject table or trusted saved pickle.')
    parser.add_argument('--params',default='{}',help='JSON object, or @path to a JSON file.')
    parser.add_argument('--style',default='{}',help='Display-only PyFLASH style JSON, or @path; separate from analysis parameters.')
    parser.add_argument('--group-col',default='Condition')
    parser.add_argument('--subject-col',default='AnimalName')
    parser.add_argument('--output',type=Path,help='New output directory for a single run.')
    parser.add_argument('--spec',type=Path)
    parser.add_argument('--progress',type=Path)
    parser.add_argument('--json',action='store_true',help='JSON output is always used; accepted for automation.')
    args = parser.parse_args(argv)
    started = time.perf_counter()
    output = None
    output_owned = False
    source_record = None
    input_records, saved = [], []
    image_inputs = {}
    try:
        parameters = json.loads(Path(args.params[1:]).read_text(encoding='utf-8') if args.params.startswith('@') else args.params)
        if not isinstance(parameters,dict):raise ValueError('Parameters must be a JSON object.')
        style = json.loads(Path(args.style[1:]).read_text(encoding='utf-8') if args.style.startswith('@') else args.style)
        if not isinstance(style,dict):raise ValueError('Style must be a JSON object.')
        if style:
            from PyFLASH.aesthetics import pyflash_style_context
            with pyflash_style_context(style):
                pass  # Validate before source reads or output creation.
        queued = args.command == 'queue'
        if queued:
            if not args.input or not args.spec or not args.progress:
                raise ValueError('A queue requires --input, --spec and --progress.')
            args.action = 'PyFLASH.queue.run_spec_queue'
            parameters = {**parameters,'path':str(args.spec.resolve()),
                          'progress_path':str(args.progress.resolve())}
            if not args.output:
                args.output = args.progress.parent/(args.progress.stem+'-runs')/str(time.time_ns())
            args.command = 'run'
        if args.command in {'describe','discover'}:
            answer = {'ok':True,'result':describe(args.action)}
        elif args.command == 'doctor':
            result = doctor()
            answer = {'ok':all(r['compatible'] or r['optional'] for r in result),'result':result}
        else:
            if args.command in {'run','validate'} and not args.action:
                raise ValueError('Choose an action from describe.')
            # Parameter validation happens before input reads and output writes.
            if args.action in PLOT_REGISTRY:
                resolve_plot_call(args.action,parameters)
            elif args.command in {'run','validate'}:
                describe(args.action)
                fn,binding,_ = helper_function(args.action)
                signature = inspect.signature(fn)
                if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
                    unknown = set(parameters) - signature.parameters.keys()
                    if unknown:
                        raise ValueError('Unknown parameters: '+', '.join(sorted(unknown)))
                if binding in {'value', 'project'}:inspect.signature(fn).bind(**parameters)
                elif binding in {'instance', 'data', 'optional-data'}:inspect.signature(fn).bind(object(),**parameters)
                else:inspect.signature(fn).bind(summary=object(),**parameters)
            if args.command == 'validate':
                answer = {'ok':True,'action':args.action,'parameters':parameters}
            else:
                if args.action in PLOT_REGISTRY and not args.input and plot_requires_input(args.action):
                    raise ValueError('This plot or pipeline requires --input.')
                if not args.output:
                    raise ValueError('A run requires a new --output directory for its receipt.')
                output = args.output.resolve()
                output.mkdir(parents=True,exist_ok=False)
                output_owned = True
                from PyFLASH import from_dataframe, load_state
                from PyFLASH.ui.workspace import (run_record, equivalent_script,
                    equivalent_action_script, parameter_inputs, content_hash)
                from PyFLASH.config import config_snapshot
                from PyFLASH._persistence import write_json, code_identity
                from PyFLASH import utils
                source = args.input.resolve() if args.input else None
                source_hash = content_hash(source) if source else None
                source_kind = ('csv' if source.suffix.lower() == '.csv' else 'pickle') if source else None
                source_record = {'kind':source_kind,'path':str(source),'sha256':source_hash} if source else None
                if source_record:
                    input_records.append({'parameter':'source','path':str(source),'sha256':source_hash})
                input_records.extend(parameter_inputs(parameters,action=args.action))
                data = None
                if source:
                    if source.suffix.lower() == '.csv':
                        import pandas as pd
                        from PyFLASH._cache_identity import read_csv_verified
                        frame, consumed_sha256 = read_csv_verified(source, expected_sha256=source_hash)
                        data = from_dataframe(frame,group_col=args.group_col,subject_col=args.subject_col,
                                              source_paths=[str(source)])
                        source_kind = 'csv'
                    else:
                        from PyFLASH.serialization import _load_cached_state
                        data = _load_cached_state(str(source), expected_sha256=source_hash, verify_current=False)
                        source_kind = 'pickle'
                if args.command == 'run':
                    if args.action in PLOT_REGISTRY and data is None and plot_requires_input(args.action):
                        raise ValueError('This plot or pipeline requires --input.')
                    if not args.output:raise ValueError('A run requires a new --output directory for its receipt.')
                    if data is not None and not queued:
                        data.fig_path = str(output)
                        data.image_fig_path = str(output/'Images')
                    from PyFLASH.actions import output_parameters as declared_outputs
                    output_parameters = declared_outputs(args.action)
                    if args.action in PLOT_REGISTRY:
                        for name in output_parameters:
                            if parameters.get(name) is None:
                                parameters[name] = str(output)
                    if args.action == 'PyFLASH.ui.services.export_excel' and parameters.get('save_path') is None:
                        parameters['save_path'] = str(output / 'workbooks')
                    if source and any(Path(parameters[name]).resolve() == source for name in output_parameters
                                      if parameters.get(name)):
                        import shutil
                        original = output / ('opened-input'+source.suffix)
                        shutil.copyfile(source, original)
                        source_record['path'] = str(original)
                        source = original
                        input_records = [({**row,'path':str(original)} if row['parameter']=='source' else row)
                                         for row in input_records]
                    def observer(path,*unused):saved.append(path)
                    utils.register_fig_saved_observer(observer)
                    import threading
                    from PyFLASH.image_io import observe_image_reads
                    image_inputs, inputs_lock = {}, threading.Lock()
                    def image_read(filename):
                        filename = str(Path(filename).resolve())
                        with inputs_lock:
                            if filename not in image_inputs:
                                image_inputs[filename] = {'parameter':'image_pixels', 'path':filename,
                                                         'sha256':content_hash(filename)}
                    try:
                        if source and content_hash(source) != source_hash:
                            raise ValueError('Input content changed while opening the analysis.')
                        from contextlib import nullcontext
                        from PyFLASH.aesthetics import pyflash_style_context
                        with observe_image_reads(image_read), (pyflash_style_context(style) if style else nullcontext()):
                            result = call_action(args.action,data,parameters)
                    finally:
                        utils.unregister_fig_saved_observer(observer)
                    input_records.extend(image_inputs.values())
                    from PyFLASH.ui.operation_receipts import verify
                    verify(input_records)
                    for name in output_parameters:
                        if args.action in PLOT_REGISTRY and parameters.get('save') is False:
                            continue
                        if parameters.get(name):
                            destination = Path(parameters[name])
                            if not destination.exists():
                                raise FileNotFoundError('Declared output is missing: '+str(destination))
                            saved.extend([destination] if destination.is_file() else
                                         [path for path in destination.rglob('*') if path.is_file()])
                    if isinstance(result, dict):
                        for cell in result.get('results', []):
                            input_records.extend(cell.get('input_files', []))
                            cell_receipt = Path(cell['receipt'])
                            saved.append(cell_receipt)
                            record = json.loads(cell_receipt.read_text(encoding='utf-8'))
                            cache_root = cell_receipt.parent / record.get('root_relative', '.')
                            saved.extend(cache_root / row['path'] for row in record['outputs'])
                    if args.action == 'PyFLASH.queue.run_spec_queue':
                        progress = Path(parameters['progress_path']).resolve()
                        state = json.loads(progress.read_text(encoding='utf-8'))
                        for item in state['items']:
                            input_records.extend(item.get('input_files',[]))
                            for row in ([item['result']] if item.get('result') else [])+item.get('outputs',[]):
                                path = Path(row['path'])
                                saved.append(path if path.is_absolute() else progress.parent/path)
                        # Freeze this run's mutable queue checkpoint beside its receipt.
                        for path in (progress,progress.with_name(progress.stem+'-summary.json')):
                            import shutil
                            copied = output/path.name
                            shutil.copyfile(path,copied)
                            saved = [p for p in saved if Path(p).resolve() != path]
                            saved.append(copied)
                    verify(input_records)
                    saved = list(dict.fromkeys(Path(path).resolve() for path in saved))
                    receipt = run_record(source_record,args.action,parameters,saved,style=style,input_records=input_records,
                                         source_record=source_record)
                    receipt['versions'] = {name:version(name) for name in ('numpy','pandas','scipy','statsmodels','reprofig')}
                    receipt['status'] = 'succeeded'
                    script = _replay_script(args,parameters,source_record,input_records,style)
                    (output/'equivalent.py').write_text(script,encoding='utf-8')
                    receipt['outputs'].append({'path':str(output/'equivalent.py'),
                                               'sha256':content_hash(output/'equivalent.py')})
                    from PyFLASH.ui.workspace import portable_run_record
                    receipt = portable_run_record(receipt)
                    answer = {'ok':not result['failures'] and not result['pending'] if queued else True,
                              'result':json_value(result),'provenance':receipt,
                              'equivalent_script':script,'elapsed_seconds':time.perf_counter()-started}
                    write_json(output/'run.json',json_value(answer))
        print(json.dumps(json_value(answer),allow_nan=False))
        return 0 if answer['ok'] else 1
    except Exception as exc:
        answer = {'ok':False,'error':f'{type(exc).__name__}: {exc}'}
        if output_owned:
            try:
                from PyFLASH.ui.workspace import run_record, content_hash
                from PyFLASH._persistence import write_json
                records = list({(row['parameter'],row['path']):row
                                for row in [*input_records,*image_inputs.values()]}.values())
                script = _replay_script(args,parameters,source_record,records,style)
                (output/'equivalent.py').write_text(script,encoding='utf-8')
                # Retain partial owned files and observed figure exports; do not
                # invent outputs for an action that raised before producing them.
                files = list(dict.fromkeys(Path(path).resolve() for path in [
                    *saved,*(p for p in output.rglob('*') if p.is_file() and p.name!='run.json')]
                    if Path(path).is_file()))
                receipt = run_record(source_record,args.action,parameters,files,style=style,
                                     input_records=records,source_record=source_record)
                receipt.update(status='failed',error=answer['error'])
                answer.update(provenance=receipt,equivalent_script=script,
                              elapsed_seconds=time.perf_counter()-started)
                write_json(output/'run.json',json_value(answer))
            except Exception as receipt_exc:
                answer['receipt_error'] = f'{type(receipt_exc).__name__}: {receipt_exc}'
        print(json.dumps(json_value(answer),allow_nan=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
