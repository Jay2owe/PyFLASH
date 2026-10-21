"""Registered option sets, streamed comparisons and explicit cell promotion."""
from __future__ import annotations
import json
import math
from pathlib import Path
from PyFLASH.ui.controls import fold, widget

UNITS = {'alpha':'probability', 'confidence':'probability', 'p_value':'probability',
         'r':'correlation', 'r1':'correlation', 'r2':'correlation',
         'n':'observations', 'n1':'observations', 'n2':'observations', 'n_tests':'tests',
         'bins':'bins', 'binwidth':'selected measurement units'}


def option_sets(contract, context):
    from PyFLASH.ui.function_contracts import APPEARANCE
    from PyFLASH.actions import action_access
    if not contract.entry.action and action_access(contract.entry.key) != 'read-only':
        return {}
    result = {}
    for field in contract.fields:
        if field.name in APPEARANCE or field.role not in {
            'choice','boolean','number','integer','text','measurement','measurements','metadata','marker'}:
            continue
        if field.name in {'save_name','filename','output_dir','save_path','title'}:
            continue
        values = list(field.choices)
        if field.role == 'boolean':
            values = [False, True]
        elif field.role in {'measurement','measurements'}:
            values = [[name] for name in context['metrics']] if field.role == 'measurements' else context['metrics']
        elif field.role == 'metadata':
            values = context['columns']
        elif field.role == 'marker':
            values = context['markers']
        result[field.name] = {'key':field.name, 'label':field.label, 'values':values,
            'unit':UNITS.get(field.name, 'category' if field.role not in {'number','integer'} else 'dimensionless'),
            'help':field.parameter.description or field.label+'.', 'role':field.role}
    return result


def parse_values(text, entry):
    values = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if entry['role'] == 'boolean':
            if line.casefold() not in {'true','false'}:
                raise ValueError('Use True or False, one per line.')
            value = line.casefold() == 'true'
        elif entry['role'] in {'number','integer'}:
            value = float(line)
            if not math.isfinite(value) or entry['role'] == 'integer' and not value.is_integer():
                raise ValueError('Enter finite '+('whole numbers.' if entry['role'] == 'integer' else 'numbers.'))
            if entry['role'] == 'integer':
                value = int(value)
        elif entry['role'] == 'measurements':
            value = [part.strip() for part in line.split(',') if part.strip()]
        else:
            value = line
            # Preserve typed enum values, including Boolean scientific options.
            for candidate in entry['values']:
                if str(candidate).casefold() == line.casefold():
                    value = candidate
                    break
        if value not in values:
            values.append(value)
    if not values:
        raise ValueError('Enter at least one value.')
    return values


def _numbers(value, prefix=''):
    if isinstance(value, bool):
        return {}
    if isinstance(value, (int,float)):
        return {prefix or 'Result':float(value)} if math.isfinite(value) else {}
    if isinstance(value, dict):
        return {key:number for name,item in value.items()
                for key,number in _numbers(item, prefix+'/'+str(name)).items()}
    if isinstance(value, list):
        return {key:number for index,item in enumerate(value)
                for key,number in _numbers(item, prefix+'/'+str(index)).items()}
    return {}


def show_grid(st, result, *, namespace, promote=False):
    """Keep the complete outcome/choice display ahead of a promotion control."""
    import pandas as pd
    cells = result.get('cells', [])
    if not cells:
        return None
    rows = []
    outcomes = {}
    for cell in cells:
        values = _numbers(cell.get('value'))
        for table in cell.get('tables', []):
            frame = pd.read_csv(table['path'])
            for name in frame.select_dtypes(include='number'):
                for index, value in enumerate(frame[name]):
                    if pd.notna(value) and math.isfinite(float(value)):
                        values[f"{table['name']} / {name} / row {index+1}"] = float(value)
        outcomes[cell['index']] = values
        rows.append({'Cell':cell['index'], 'Reused':cell.get('reused', False),
                     **{name:cell['parameters'][name] for name in result['choices']}})
    common = sorted(set.intersection(*(set(values) for values in outcomes.values())))
    table = pd.DataFrame(rows)
    if common:
        selected = widget(st, 'selectbox', 'Outcome to compare', common,
                          key='ui_grid_outcome_'+namespace,
                          help='Compare the same returned statistic and table row across every completed cell.')
        table['Estimate'] = table['Cell'].map(lambda index:outcomes[index][selected])
        ordered = table.sort_values(['Estimate','Cell']).reset_index(drop=True)
        ordered['Order'] = range(len(ordered))
        import altair as alt
        from PyFLASH.ui.theme import PALETTE
        cursor = alt.selection_point(fields=['Cell'], on='pointerover', clear='pointerout', empty=False)
        curve = alt.Chart(ordered).mark_point(filled=True).encode(
            x=alt.X('Order:O', title='Choices sorted by outcome'),
            y=alt.Y('Estimate:Q', title=selected, scale=alt.Scale(zero=False)),
            color=alt.condition(cursor, alt.value(PALETTE[2]), alt.value(PALETTE[-1])),
            tooltip=['Cell','Estimate']+list(result['choices'])).add_params(cursor)
        choice_rows = [{'Order':row['Order'], 'Cell':row['Cell'], 'Choice':name,
                        'Value':str(row[name])} for row in ordered.to_dict('records') for name in result['choices']]
        matrix = alt.Chart(pd.DataFrame(choice_rows)).mark_rect().encode(
            x=alt.X('Order:O', title=None), y=alt.Y('Choice:N', title=None),
            color=alt.Color('Value:N', legend=None),
            opacity=alt.condition(cursor, alt.value(1), alt.value(.6)),
            tooltip=['Cell','Choice','Value'])
        st.altair_chart(alt.vconcat(curve, matrix).resolve_scale(x='shared'), width='stretch')
        table = ordered.drop(columns='Order')
    st.dataframe(table, hide_index=True, width='stretch')
    paths = [path for cell in cells for path in cell.get('paths', [])]
    if paths:
        from PyFLASH.ui.figures import embed_figure
        titles = {path:f"Cell {cell['index']}" for cell in cells for path in cell.get('paths', [])}
        embed_figure(None, None, paths=paths, titles=titles)
    if result.get('failures'):
        st.error(f"{len(result['failures'])} choices failed. Completed cells and failure records are preserved.")
    if result.get('script'):
        widget(st, 'download_button', 'Download complete grid script', result['script'], 'replay_grid.py',
               'text/x-python', key='grid_replay_'+namespace, help='Includes every choice and every input identity.')
    if not promote:
        return None
    chosen = widget(st, 'selectbox', 'Choice to use', [cell['index'] for cell in cells],
                    key='ui_grid_promote_'+namespace, help='Nothing is selected as the main result until you apply it.')
    if widget(st, 'button', 'Use these settings', key='grid_apply_'+namespace,
              help='Records the chosen cell alongside the complete grid and restores its inputs.'):
        return promote_cell(result['receipt'], chosen)
    return None


def promote_cell(receipt_path, index):
    """Record an explicit choice without changing cached scientific results."""
    import time
    from PyFLASH.ui import workspace
    path = Path(receipt_path)
    result = workspace.read_operation_state(path.parent / 'result.json')
    cell = next((row for row in result['cells'] if row['index'] == index), None)
    if cell is None:
        raise ValueError('Choose a completed cell from this grid.')
    cache_receipt = Path(cell['receipt'])
    cached = json.loads(cache_receipt.read_text(encoding='utf-8'))
    cache_root = cache_receipt.parent / cached.get('root_relative', '.')
    for output in cached['outputs']:
        if workspace.content_hash(cache_root / output['path']) != output['sha256']:
            raise ValueError('A grid output changed; it cannot be promoted.')
    event = {'schema_version':1, 'cell_index':index, 'cell_key':cell['key'],
             'parameters':cell['parameters'], 'created_ns':time.time_ns()}
    event_path = path.parent / f'promotion-{event["created_ns"]}.json'
    workspace.write_json(event_path, event)
    record = workspace.read_run_record(path)
    record.setdefault('promotions', []).append(event)
    record['promoted_cell'] = cell['key']
    record['outputs'].append({'path':str(event_path), 'sha256':workspace.content_hash(event_path)})
    workspace.write_json(path, workspace.portable_run_record(record))
    return {**cell, 'type':result['action'], 'style':result.get('style', {}),
            'script':result['script'], 'grid_receipt':str(path), 'promotion':event}


def render_options(st, contract, values, style, context, *, busy, issues):
    from PyFLASH.ui.function_workbench import _key
    from PyFLASH.ui import jobs, workspace, services
    from PyFLASH.ui import function_contracts as fc
    registry = option_sets(contract, context)
    if not registry:
        return
    draft = st.session_state['ui_function_drafts'][contract.entry.key]
    saved = draft.setdefault('sweep', {'parameters':[], 'text':{}})
    with fold('function.sweep', namespace=contract.entry.key+':'):
        names_key = _key(contract.entry, 'sweep_parameters')
        st.session_state.setdefault(names_key, saved['parameters'])
        names = widget(st, 'multiselect', 'Settings to compare', list(registry), key=names_key,
                       format_func=lambda name:registry[name]['label'],
                       help='Runs every combination; unchanged cells are reused by content.')
        saved['parameters'] = names
        choices, invalid = {}, dict(issues)
        for name in names:
            entry = registry[name]
            key = _key(contract.entry, 'sweep_values_'+name)
            default = '\n'.join(','.join(map(str,value)) if isinstance(value,list) else str(value)
                                for value in entry['values'])
            st.session_state.setdefault(key, saved['text'].get(name, default))
            text = widget(st, 'text_area', entry['label']+' values', key=key,
                          help=entry['help']+' One choice per line. Unit: '+entry['unit']+'.')
            saved['text'][name] = text
            try:
                choices[name] = parse_values(text, entry)
            except ValueError as exc:
                invalid[name] = str(exc)
        if widget(st, 'button', 'Compare these choices', key=_key(contract.entry, 'sweep_run'),
                  disabled=bool(busy) or not names, icon=':material/view_module:',
                  help='Shows the whole grid before you choose one result.'):
            try:
                from PyFLASH.queue import expand_grid
                cells = expand_grid(values, choices)
                for cell in cells:
                    invalid.update(fc.validate(contract, cell, context))
                if invalid:
                    raise ValueError('; '.join(invalid.values()))
                source = dict(st.session_state.get('ui_source') or {}) or None
                if source:
                    expected = getattr(st.session_state.get('batch'), '_ui_source_version', None)
                    current = workspace.source_version(source['path'])
                    if expected is not None and current != expected:
                        raise ValueError('The source changed after it was opened. Reopen it before comparing choices.')
                    source['version'] = current
                from PyFLASH.actions import HELPER_ACTIONS
                if not contract.entry.action and HELPER_ACTIONS[contract.entry.key][1] == 'value':
                    source = None
                params = {'kwargs':fc.prepared_values(contract, values), 'style':style,
                          'region':st.session_state.get('ui_region'), 'target_experiment':draft.get('target_experiment')}
                jobs.start_sweep(contract.entry.action or contract.entry.key, params, choices,
                    name=contract.title+' comparison', dataset_token=st.session_state['_ui_dataset_token'],
                    target_key=_key(contract.entry, 'sweep_result'), source=source,
                    representatives=workspace.selection_snapshot(services.get_representative_selections(st.session_state.get('batch'))),
                    choice_sets={name:{**registry[name], 'values':choices[name]} for name in names})
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    result = st.session_state.get(_key(contract.entry, 'sweep_result'))
    if result:
        st.subheader('Comparison of choices')
        promoted = show_grid(st, result, namespace=contract.entry.key, promote=True)
        if promoted:
            allowed = {field.name for field in contract.fields if field.role not in {'bound','managed','alias'}}
            draft['values'] = {name:value for name,value in promoted['parameters'].items() if name in allowed}
            draft['style'] = promoted['style']
            st.session_state[_key(contract.entry, 'result')] = promoted
            for key in list(st.session_state):
                if key.startswith(_key(contract.entry, '')) and not key.endswith('_result'):
                    del st.session_state[key]
            workspace.checkpoint_session(st.session_state)
            st.rerun()
