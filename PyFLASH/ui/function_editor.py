"""Task-specific plot/pipeline editor using the existing validated job adapters."""
from __future__ import annotations

import copy
from dataclasses import replace
import json

from PyFLASH.ui import function_contracts as fc, function_workbench as fw, function_workflows as flow
from PyFLASH.ui.controls import fold, widget


def remember_value(values, field, value):
    """Preserve saved null/empty overrides while omitting untouched defaults."""
    name = field.name
    default = fc.default_value(field.parameter)
    blank = value is None or value == '' or value == [] or value == {}
    was_set = name in values
    previous = values.get(name)
    if blank and was_set and (previous is None or previous == '' or previous == [] or previous == {}):
        return  # These distinct values are recovered exactly, without a mode menu.
    same_default = value == default or (isinstance(value, list) and isinstance(default, tuple) and tuple(value) == default)
    if not field.parameter.required and (same_default or (blank and default is None)) and not was_set:
        return
    # A recorded explicit default remains explicit. Only untouched new fields
    # are omitted; removing an advanced field or Reset restores omission.
    values[name] = value


def result_changed(contract, values, style, result, region=None, target_experiment=None):
    """Compare effective source defaults, ignoring worker-managed save options."""
    if not result:
        return False
    recorded = result.get('parameters', {})
    for field in contract.fields:
        if field.role in {'bound', 'managed', 'alias', 'object'}:
            continue
        if field.name in {'roi','roi_base'} and field.name not in values:
            continue
        default = fc.default_value(field.parameter)
        a, b = values.get(field.name, default), recorded.get(field.name, default)
        if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            a, b = list(a), list(b)
        if a != b:
            return True
    if style != result.get('style', {}):
        return True
    # Old results already record the adapter's region in kwargs.
    old_region = recorded.get('roi_base', recorded.get('roi'))
    return old_region != values.get('roi_base',values.get('roi',region)) or result.get('target_experiment') != target_experiment


def _select_group(st, contract, field, value, context):
    table = context['table']
    batch = st.session_state.get('batch')
    column = getattr(batch, 'group_col', None) or 'Condition'
    options = [v.item() if hasattr(v,'item') else v for v in table[column].dropna().unique()] if table is not None and column in table else []
    key = fw._key(contract.entry, field.name)
    if value is not None and value not in options:
        options.append(value)  # Keep a legacy override visible; validation names the problem.
    if key not in st.session_state and value is not None:
        st.session_state[key] = value
    return widget(st, 'selectbox', field.label, [None] + options,
                  index=([None]+options).index(value) if value in options else 0, key=key,
                  format_func=lambda v: 'Every pair of groups (default)' if v is None and field.name == 'control' and contract.entry.action == 'group_comparison_pipeline' else
                  'Package default' if v is None else str(v), help=field.parameter.description or 'Choose a group from the open dataset.')


def _groups(st, contract, values, context):
    table = context['table']
    if table is None or 'filter_by' not in {f.name for f in contract.fields}:
        return
    column = getattr(st.session_state['batch'], 'group_col', None) or 'Condition'
    if column not in table:
        return
    options = [v.item() if hasattr(v,'item') else v for v in table[column].dropna().unique()]
    key = fw._key(contract.entry, 'selected_groups')
    saved = values.get('filter_by', {})
    if key not in st.session_state:
        st.session_state[key] = saved.get(column, []) if isinstance(saved, dict) else []
    st.session_state[key] = [v for v in st.session_state[key] if v in options]
    groups = widget(st, 'multiselect', 'Groups', options, key=key, placeholder='All groups',
                    help='Blank includes all groups. Selection filters subjects, retaining their original group identities.')
    if groups:
        if not isinstance(values.get('filter_by'), dict):
            values['filter_by'] = {}
        values['filter_by'][column] = groups
    elif isinstance(values.get('filter_by'), dict):
        values['filter_by'].pop(column, None)
        if not values['filter_by']:
            values.pop('filter_by')


def _draw(st, contract, original, values, context, errors):
    field = flow.field(contract, original)
    existing = values.get(field.name, fc.default_value(field.parameter))
    if contract.entry.action=='regressions' and field.name in {'x','y'} and isinstance(existing,(list,tuple)):
        field=replace(field,role='measurements',label=field.label+' (saved queue)')
    # Optional tri-state booleans must not become False merely by opening a form.
    if field.role == 'boolean' and existing is None:
        field = replace(field, role='choice', choices=(None, True, False))
    try:
        if field.role in {'range','size'} and existing in (None,[], ''):
            st.caption(field.label)
            key=fw._key(contract.entry,field.name)
            first,second=st.columns(2)
            a=widget(first,'number_input','First value',value=None,key=key+'_first',help=field.parameter.description or field.label)
            b=widget(second,'number_input','Second value',value=None,key=key+'_second',help=field.parameter.description or field.label)
            if (a is None)!=(b is None):
                raise ValueError('Complete both values, or leave both blank.')
            value=None if a is None else [a,b]
        elif field.role == 'group':
            value = _select_group(st, contract, field, existing, context)
        else:
            value = fw._widget(st, contract, field, existing, context,
                               format_choice=lambda value: flow.value_label(field, value))
        remember_value(values, original, value)
    except (ValueError, TypeError) as exc:
        errors[field.name] = str(exc)


def _advanced(st, contract, values, context, errors, *, appearance=False):
    primary = flow.primary_names(contract.entry.action)
    available = [f for f in contract.fields if f.name not in primary and f.role not in {'bound','managed','alias','object'}
                 and flow.is_appearance(contract,f) == appearance]
    fields = {f.name:f for f in available}
    if not fields:
        return
    key = fw._key(contract.entry, 'appearance_fields' if appearance else 'advanced_fields')
    # Saved overrides are always discoverable, including explicit None/empty values.
    if key not in st.session_state:
        st.session_state[key] = [name for name in fields if name in values]
    previous=list(st.session_state.get('ui_function_drafts',{}).get(contract.entry.key,{}).get('controls',{}).get(key,[]))
    chosen = widget(st, 'multiselect', 'Additional appearance options' if appearance else 'Additional settings',
                    list(fields), key=key, format_func=lambda name: flow.field(contract, fields[name]).label,
                    help='Choose only the settings you need. Removing a setting restores its package default.')
    for name in previous:
        if name not in chosen and name in fields:
            values.pop(name, None)
    for name in chosen:
        _draw(st, contract, fields[name], values, context, errors)
    # Exact empty/None values belong in this secondary disclosure, not every form field.
    with fold('function.empty_values', namespace=contract.entry.key+('appearance:' if appearance else ':')):
        empty_key=fw._key(contract.entry, 'appearance_empty_fields' if appearance else 'empty_fields')
        options=list(fields) + ([] if appearance else [n for n in primary if n in {f.name for f in contract.fields}])
        selected=widget(st, 'selectbox', 'Input to clear', [None]+options, key=empty_key,
                        format_func=lambda name: 'Choose an input' if name is None else flow.field(contract,next(f for f in contract.fields if f.name==name)).label,
                        help='Optional exact values for saved recipes; ordinary forms do not require this.')
        if selected:
            field=next(f for f in contract.fields if f.name==selected)
            choices=['Package default','No value']
            if field.role in {'measurements','metadata_list','marker_list','image_markers','list','numbers','pairs'}:
                choices.append('Empty list')
            mode=widget(st,'selectbox','Use',choices,key=fw._key(contract.entry, 'appearance_empty_value_mode' if appearance else 'empty_value_mode'),
                        help='Package default omits the argument. No value records None. Empty list records an explicit empty sequence.')
            if widget(st,'button','Apply empty value',key=fw._key(contract.entry,'apply_empty_'+('appearance' if appearance else 'analysis')),
                      help='Changes only this draft; it does not run analysis.'):
                if mode=='Package default': values.pop(selected,None)
                else: values[selected]=None if mode=='No value' else []
                st.session_state.setdefault('ui_function_drafts',{})[contract.entry.key]['values']=dict(values)
                prefix=fw._key(contract.entry,selected)
                for state_key in list(st.session_state):
                    if state_key==prefix or state_key.startswith(prefix+'_'):
                        del st.session_state[state_key]
                st.rerun()


def _count(st, contract, values, context):
    table=context['table']
    if table is None:
        return
    selected=table
    for column, levels in (values.get('filter_by') or {}).items():
        if column in selected:
            selected=selected[selected[column].isin(levels if isinstance(levels,list) else [levels])]
    metrics=[]
    for name in ('data_cols','columns','dependent_variables','x','y','z','column'):
        value=values.get(name)
        metrics.extend(value if isinstance(value,list) else [value] if value else [])
    metrics=list(dict.fromkeys(m for m in metrics if m in selected))
    if metrics:
        selected=selected.dropna(subset=metrics)
    subject=values.get('subject_col') or getattr(st.session_state['batch'],'subject_col',None) or 'AnimalName'
    unit='subjects with selected measurements' if metrics else 'source subjects'
    st.caption(f"{selected[subject].nunique() if subject in selected else len(selected)} {unit} · {len(selected)} rows")


def render(contract):
    import streamlit as st
    from PyFLASH.ui import jobs
    from PyFLASH.ui.appearance import effective_style, errors as appearance_errors
    home=flow.home(contract.entry.action)
    st.subheader(flow.title(contract))
    batch=st.session_state.get('batch')
    if batch is None:
        st.info('Open a dataset in Workspace to choose inputs for this picture.')
        return
    from PyFLASH.ui import dependency_controls
    if not dependency_controls.render('core'):
        return
    issue=fw.migrate_legacy_draft(st.session_state,contract)
    if issue:
        st.warning(issue)
        previous=st.session_state.get('ui_fig_params_'+contract.entry.action)
        widget(st,'download_button','Download previous recipe',previous if isinstance(previous,str) else json.dumps(previous),
               'previous_recipe.json','application/json',key=fw._key(contract.entry,'replay'))
    drafts=st.session_state.setdefault('ui_function_drafts',{})
    draft=copy.deepcopy(drafts.get(contract.entry.key,{'schema_version':1,'values':{},'style':{}}))
    drafts.setdefault(contract.entry.key,copy.deepcopy(draft))
    fw.restore_draft_controls(st.session_state,contract.entry,draft)
    values=dict(draft.get('values',{}))
    input_panel,result_panel=st.columns([1,2.8],gap='small')
    target=batch
    field_errors={}
    fields={f.name:f for f in contract.fields}
    with input_panel:
        st.markdown('<span id="function-inputs"></span>',unsafe_allow_html=True)
        st.caption(flow.unit(contract.entry.action,values))
        experiments=list(getattr(batch,'experiment_list',[]) or [])
        if contract.entry.action=='locations' and experiments:
            names=[e.name for e in experiments]
            key=fw._key(contract.entry,'target_experiment')
            if key not in st.session_state and draft.get('target_experiment') in names:
                st.session_state[key]=draft['target_experiment']
            name=widget(st,'selectbox','Experiment',names,key=key,help='The processed experiment whose object coordinates to inspect.')
            draft['target_experiment']=name
            target=next(e for e in experiments if e.name==name)
        context=fc.input_context(target,st.session_state.get('ui_region'),st.session_state.setdefault('_ui_measurement_cache',{}))
        if target is not batch:
            context={**context,'experiments':experiments}
        for index,(section,names) in enumerate(flow.SECTIONS[contract.entry.action]):
            if home.pipeline or len(flow.SECTIONS[contract.entry.action])>1:
                st.markdown('**'+section+'**')
            for name in names:
                _draw(st,contract,fields[name],values,context,field_errors)
            if index==0:
                _groups(st,contract,values,context)
        if contract.entry.action in {'images','representative_images'}:
            from PyFLASH.ui import services
            with fold('function.images',namespace=contract.entry.key+':'):
                images=services.image_table(batch)
                if images is not None:
                    st.dataframe(images,hide_index=True,width='stretch')
                selections=services.get_representative_selections(batch)
                if selections is not None and not selections.empty:
                    edited=widget(st,'data_editor',selections,num_rows='dynamic',key=fw._key(contract.entry,'representatives'),width='stretch')
                    if widget(st,'button','Apply representative selections',key=fw._key(contract.entry,'apply_representatives')):
                        from PyFLASH.ui.workspace import save_representative_edit
                        save_representative_edit(st.session_state,edited)
        advanced_panel=fold('function.advanced',namespace=contract.entry.key+':')
        with advanced_panel:
            _advanced(st,contract,values,context,field_errors)
        # Legacy source-specific appearance remains accessible through one editor.
    with result_panel:
        style=fw._style(st,contract,draft)
        if st.session_state.get(fw._key(contract.entry,'appearance_open')):
            _advanced(st,contract,values,context,field_errors,appearance=True)
            st.caption('Appearance is applied to the next run; the previous result keeps its recorded settings.')
    draft.update({'schema_version':1,'values':values,'style':style,
                  'controls':fw.draft_controls(st.session_state,contract.entry)})
    drafts[contract.entry.key]=draft
    run_style=effective_style(st.session_state,style)
    issues={**fc.validate(contract,values,context),**field_errors,**appearance_errors(run_style)}
    if contract.entry.action in {'correlation_pipeline','adjusted_correlation_pipeline'} and not any(values.get(name) for name in ('data_cols','data_col_contains','data_col_regex')):
        issues['data_cols']='Choose the measurements to compare before running this pipeline.'
    # Statistical safeguards are input validation, never new defaults.
    if contract.entry.action=='histograms' and ('bins' in values and (not isinstance(values['bins'],int) or values['bins']<1)):
        issues['bins']='Use a positive whole number of bins.'
    if contract.entry.action=='group_comparison_pipeline' and values.get('gate')=='fdr' and not values.get('screen',False):
        issues['gate']='Enable exploratory screening to use false-discovery-rate q-values.'
    with input_panel:
        _count(st,contract,values,context)
        for message in issues.values():
            st.error(message)
        job=jobs.latest_job()
        busy=bool(job and job['status'] in jobs.ACTIVE_STATES)
        if busy:
            st.caption('A job is running. You can keep editing; these changes are for the next run.')
        if widget(st,'button','Run pipeline' if home.pipeline else 'Create plot',type='primary',icon=':material/play_arrow:',
                  key=fw._key(contract.entry,'run'),disabled=busy or bool(issues),help='Runs the selected package action in the background with a frozen copy of these inputs.'):
            from PyFLASH.ui.job_status import submit
            params={'kwargs':fc.prepared_values(contract,values),'style':run_style,'region':st.session_state.get('ui_region'),'plot_type':contract.entry.action}
            if contract.entry.action=='locations':
                params['target_experiment']=draft.get('target_experiment')
            try:
                submit('figure',params,flow.title(contract),fw._key(contract.entry,'result'))
            except Exception as exc:
                st.error('Could not start this run: '+str(exc))
        if widget(st,'button','Reset inputs',key=fw._key(contract.entry,'reset'),help='Restores package defaults for this draft; completed results remain available.'):
            drafts.pop(contract.entry.key,None)
            for key in list(st.session_state):
                if key.startswith(fw._key(contract.entry,'')) and not key.endswith('_result'):
                    del st.session_state[key]
            st.rerun()
        with advanced_panel:
            from PyFLASH.ui.sweeps import render_options
            render_options(st,contract,values,run_style,context,busy=busy,issues=issues)
    with result_panel:
        result=st.session_state.get(fw._key(contract.entry,'result'))
        if result_changed(contract,values,run_style,result,st.session_state.get('ui_region'),draft.get('target_experiment')):
            st.caption('Inputs changed · showing the previous completed result.')
        if result:
            fw.show_result(st,contract,compact=True)
        else:
            st.info('Choose inputs and '+('run the pipeline' if home.pipeline else 'create the plot')+' to show real results here.')
        with fold('function.inputs',namespace=contract.entry.key+':'):
            st.write(values)
            st.caption('Unchanged options use the owning package defaults. The result script records the actual run.')
        fw._reference(st,contract)


def saved_runs():
    import streamlit as st
    history=st.session_state.get('ui_function_results',{})
    supported={c.entry.action:c for c in fc.catalogue_contracts()}
    choices=[key for key in history if key in supported]
    if not choices:
        return
    with fold('function.history'):
        selected=widget(st,'selectbox','Completed run',[None]+choices,key='ui_saved_workflow_run',
                        format_func=lambda key:'Choose a completed run' if key is None else flow.title(supported[key]),
                        help='Reopen the completed result and restore the exact inputs recorded for it.')
        if selected and widget(st,'button','Reopen this run',key='_function_event_reopen_workflow'):
            contract=supported[selected]
            result=history[selected]
            names={f.name for f in contract.fields if f.role not in {'bound','managed','alias','object'}}
            st.session_state.setdefault('ui_function_drafts',{})[contract.entry.key]={'schema_version':1,'values':{k:v for k,v in result.get('parameters',{}).items() if k in names},
                'style':result.get('style',{}),'target_experiment':result.get('target_experiment')}
            for key in list(st.session_state):
                if key.startswith(fw._key(contract.entry,'')) and not key.endswith('_result'):
                    del st.session_state[key]
            st.session_state[fw._key(contract.entry,'result')]=result
            st.session_state['ui_function_selection']=contract.entry.key
            st.rerun()
