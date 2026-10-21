"""One selected function editor and result home; normal inputs need no code."""
from __future__ import annotations
from PyFLASH.ui.controls import fold, widget

import copy
import hashlib
import json
from pathlib import Path

from PyFLASH.ui import function_contracts as fc


def _key(entry, name):
    prefix = "_function_event_" if name in {"reset", "run", "restore", "template", "replay", "apply_representatives"} or name.startswith("table_") else "ui_fn_"
    return prefix + hashlib.sha1(entry.key.encode()).hexdigest()[:10] + "_" + name


def restore_draft_controls(state, entry, draft):
    """Restore disclosure/search choices without overwriting live widget edits."""
    prefix = _key(entry, "")
    for key, value in draft.get("controls", {}).items():
        if key.startswith(prefix) and key.endswith(("_open", "_mode", "_search", "_saved", "_fields")):
            state.setdefault(key, copy.deepcopy(value))


def draft_controls(state, entry):
    """Keep form choices with that function, separate from scientific inputs."""
    prefix = _key(entry, "")
    return {key: copy.deepcopy(state[key]) for key in state
            if key.startswith(prefix) and key.endswith(("_open", "_mode", "_search", "_saved", "_fields"))}


def migrate_legacy_draft(state, contract):
    """Import an older figure recipe once, preserving recoverable invalid text."""
    drafts = state.setdefault("ui_function_drafts", {})
    if contract.entry.key in drafts or not contract.entry.action:
        return None
    raw = state.get("ui_fig_params_" + contract.entry.action)
    if raw is None:
        return None
    try:
        values = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if not isinstance(values, dict):
            raise ValueError("The saved recipe must contain named inputs.")
        names = {f.name for f in contract.fields}
        values = {fc.ALIASES.get(k, k) if fc.ALIASES.get(k, k) in names else k: v for k, v in values.items()}
        fc.prepared_values(contract, values)
    except (ValueError, TypeError) as exc:
        return "The previous recipe is retained, but could not be imported: " + str(exc)
    style = state.get("ui_fig_style", {}) if state.get("ui_fig_type") == contract.entry.action else {}
    drafts[contract.entry.key] = {"schema_version": 1, "values": values, "style": style}
    return None


def _rows(st, field, value, key, context):
    import pandas as pd
    role = field.role
    options = context["metrics"]
    if role == "associations":
        rows = [{"Name": name, "Horizontal measurement": spec.get("x"), "Vertical measurement": spec.get("y"),
                 "Covariates (one per line)": "\n".join(spec.get("covariates") or [])}
                for name, spec in (value or {}).items()] if isinstance(value, dict) else [
                    {"Name": spec.get("name", ""), "Horizontal measurement": spec.get("x"), "Vertical measurement": spec.get("y"),
                     "Covariates (one per line)": "\n".join(spec.get("covariates") or [])} for spec in value or []]
        columns = ["Name", "Horizontal measurement", "Vertical measurement", "Covariates (one per line)"]
        config = {n: st.column_config.SelectboxColumn(n, options=options, required=True) for n in columns[1:3]}
    elif role == "pairs":
        rows = [{"First": row[0], "Second": row[1], "Within factor (optional)": row[2] if len(row) > 2 else ""} for row in value or []]
        columns, config = ["First", "Second", "Within factor (optional)"], {}
    elif role == "mapping":
        def row(name, v, section=""):
            type_ = "Boolean" if isinstance(v, bool) else "Number" if isinstance(v, (int, float)) else "List" if isinstance(v, (tuple, list)) else "Text"
            if type_ == "List" and v and all(isinstance(x, bool) for x in v):
                type_ = "Boolean list"
            elif type_ == "List" and v and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
                type_ = "Number list"
            return {"Section (optional)": section, "Name": str(name), "Value": "\n".join(map(str, v)) if type_.endswith("list") or type_ == "List" else str(v), "Type": type_}
        rows = []
        for name, v in (value or {}).items():
            rows.extend([row(k, w, str(name)) for k, w in v.items()] if isinstance(v, dict) else [row(name, v)])
        columns = ["Section (optional)", "Name", "Value", "Type"]
        config = {"Type": st.column_config.SelectboxColumn(options=["Text", "Number", "Boolean", "List", "Number list", "Boolean list"], default="Text")}
    elif role == "filters":
        rows = [{"Column": k, "Include value": str(v)} for k, vs in (value or {}).items() for v in (vs if isinstance(vs, list) else [vs])]
        columns = ["Column", "Include value"]
        config = {"Column": st.column_config.SelectboxColumn(options=context["columns"], required=True)}
    else:
        rows = [{"Value": v} for v in ([value] if isinstance(value, str) else value or [])]
        columns = ["Value"]
        config = {"Value": st.column_config.NumberColumn(required=True)} if role == "numbers" else {}
    # Streamlit stores row edits against the original table. Feeding the already
    # edited draft back in would apply insert/delete offsets a second time.
    base_rows = st.session_state.setdefault(key + "_rows", rows)
    editor = widget(st, 'data_editor', pd.DataFrame(base_rows, columns=columns), num_rows="dynamic", hide_index=True,
                            column_config=config, key=key, width="stretch")
    records = editor.where(editor.notna(), None).to_dict("records")
    if role == "associations":
        result = {}
        for index, row in enumerate(records):
            if not any(row.values()):
                continue
            if not row[columns[1]] or not row[columns[2]]:
                raise ValueError("Complete both measurements in each relationship row.")
            name = row["Name"] or f"Relationship {index + 1}"
            if name in result:
                raise ValueError("Give each relationship a different name.")
            result[name] = {"x": row[columns[1]], "y": row[columns[2]], "covariates": (row[columns[3]] or "").splitlines()}
        return result
    if role == "pairs":
        result = []
        for row in records:
            if not any(row.values()):
                continue
            if not row["First"] or not row["Second"]:
                raise ValueError("Complete both members of each pair.")
            result.append([row["First"], row["Second"]] + ([row[columns[2]]] if row[columns[2]] else []))
        return result
    if role == "mapping":
        result = {}
        for row in records:
            if not any(row.values()) or (not row["Name"] and row["Value"] is None):
                continue
            if not row["Name"]:
                raise ValueError("Give each value a name.")
            v = row["Value"] if row["Value"] is not None else ""
            if row["Type"] == "Number":
                v = float(v)
            elif row["Type"] == "Boolean":
                if v.casefold() not in {"true", "false"}:
                    raise ValueError("Boolean values must be True or False.")
                v = v.casefold() == "true"
            elif row["Type"] == "List":
                v = v.splitlines()
            elif row["Type"] == "Number list":
                v = [float(x) for x in v.splitlines()]
            elif row["Type"] == "Boolean list":
                if any(x.casefold() not in {"true", "false"} for x in v.splitlines()):
                    raise ValueError("Boolean list values must be True or False, one per line.")
                v = [x.casefold() == "true" for x in v.splitlines()]
            target = result.setdefault(row[columns[0]], {}) if row[columns[0]] else result
            if row["Name"] in target:
                raise ValueError("Use each name only once within a section.")
            target[row["Name"]] = v
        return result
    if role == "filters":
        result = {}
        table = context["table"]
        for row in records:
            if not any(row.values()):
                continue
            if not row["Column"] or row["Include value"] is None:
                raise ValueError("Choose a column and include value for every filter row.")
            choices = list(table[row["Column"]].dropna().unique())
            original = next((v for v in choices if str(v) == str(row["Include value"])), None)
            if original is None:
                raise ValueError(f"{row['Include value']} is not present in {row['Column']}.")
            original = original.item() if hasattr(original, "item") else original
            result.setdefault(row["Column"], []).append(original)
        return result
    return [r["Value"] for r in records if r["Value"] is not None]


def _widget(st, contract, field, value, context, *, key=None, format_choice=None):
    entry, role, label = contract.entry, field.role, field.label
    key = key or _key(entry, field.name)
    help_ = field.parameter.description or f"{label}. Package default: {field.parameter.default or 'required input'}."
    if role == "file" and field.name in {"path", "comparisons_path", "raw_path"}:
        tables = [t for r in st.session_state.get("ui_function_results", {}).values() for t in r.get("tables", []) if Path(t["path"]).is_file()]
        paths = list(dict.fromkeys(t["path"] for t in tables))
        if paths:
            path = widget(st, 'selectbox', "Saved table for " + label.lower(), [None] + paths, index=0,
                                key=key + "_saved", format_func=lambda p: "Choose a table, or enter its path below" if p is None else Path(p).name,
                                help="Tables returned by completed analyses; choose the table with the columns this function expects.")
            if path:
                st.session_state[key] = path
    if role in {"number", "integer"} and value is not None:
        value = int(value) if role == "integer" else float(value)
    if key not in st.session_state and value is not None and role in {"measurement", "measurements", "metadata", "metadata_list", "marker", "marker_list", "image_markers", "object_measurement", "choice"}:
        st.session_state[key] = value
    if role in {"measurement", "measurements", "metadata", "metadata_list", "marker", "marker_list", "image_markers", "object_measurement"}:
        multiple = role in {"measurements", "metadata_list", "marker_list", "image_markers"}
        if role.startswith("measurement"):
            options = context["metrics"]
        elif role.startswith("metadata"):
            options = context["columns"]
        elif role.startswith("marker"):
            options = list(context["markers"])
        elif role == "image_markers":
            options = context["image_markers"]
        else:
            marker = st.session_state.get(_key(entry, "marker"))
            options = context["markers"].get(marker, [])
        compatible = options
        if len(options) > 200:
            from PyFLASH.ui.workspace import measurement_choices
            query = widget(st, 'text_input', f"Find {label.lower()}", key=key + "_search", help="Search every available input; existing selections stay available.")
            selected = st.session_state.get(key, [] if multiple else None)
            selected = selected if isinstance(selected, list) else [selected] if selected is not None else []
            options, count = measurement_choices(options, context["labels"] if role.startswith("measurement") else {o:str(o) for o in options}, query, selected)
            st.caption(f"{count} matches; up to 200 plus selected inputs are shown.")
        if key in st.session_state:
            old = st.session_state[key]
            saved = old if multiple and isinstance(old,list) else [old]
            options = [*options, *(v for v in saved if v is not None and v not in options)]
        format_ = lambda v: context["labels"].get(v, str(v)) if v in compatible else 'Unavailable: '+str(v)
        if multiple:
            return widget(st, 'multiselect', label, options, key=key, format_func=format_, help=help_)
        # Keep an explicit empty option when a search yields a single match.
        # Users can clear a previous choice without silently choosing another.
        selection = widget(st, 'selectbox', label, [None] + options, index=None, key=key,
                            format_func=lambda v: "Choose an input" if v is None else format_(v),
                            placeholder="Choose an input", help=help_)
        return selection
    if role == 'list' and field.choices:
        options = list(field.choices)
        selected = options if value is None else [value] if isinstance(value,str) else list(value)
        options += [name for name in selected if name not in options]
        if key not in st.session_state:
            st.session_state[key] = selected
        from PyFLASH._classifier_registry import CLASSIFIER_FAMILIES
        return widget(st, 'multiselect', label, options, key=key, help=help_,
            format_func=lambda name: CLASSIFIER_FAMILIES[name]['label'] if name in CLASSIFIER_FAMILIES else 'Unavailable: '+str(name))
    if role == "boolean":
        return widget(st, 'checkbox', label, value=bool(value), key=key, help=help_)
    if role in {"number", "integer"}:
        convert = int if role == "integer" else float
        return widget(st, 'number_input', label, value=convert(value) if value is not None else None, step=1 if role == "integer" else 0.01, key=key, help=help_)
    if role == "choice":
        options = list(field.choices)
        if value is not None and value not in options:
            options.append(value)
        return widget(st, 'selectbox', label, options, index=options.index(value) if value in options else None, key=key, help=help_,
                      format_func=format_choice or str)
    if role in {"range", "size"}:
        st.caption(label)
        a, b = st.columns(2)
        values = value or [0.0, 1.0]
        return [widget(a, 'number_input', "First value", value=float(values[0]), key=key + "_first", help=help_),
                widget(b, 'number_input', "Second value", value=float(values[1]), key=key + "_second", help=help_)]
    if role in {"mapping", "pairs", "associations", "filters", "list", "numbers"}:
        st.markdown(f"**{label}**", help=help_)
        return _rows(st, field, value, key, context)
    return widget(st, 'text_input', label, value=str(value) if value is not None else "", key=key, help=help_)


def _reference(st, contract):
    item = contract.entry
    with fold('function.reference', namespace=contract.entry.key+":"):
        st.code(item.signature, language="python")
        st.dataframe([{"Input": f.label, "Python name": f.name, "Default": f.parameter.default or "Required",
                       "Use": f.parameter.description or f.reason, "Control": f.role} for f in contract.fields], hide_index=True, width="stretch")
        st.text(item.documentation)
        st.caption(f"Defined in {item.source}:{item.line}")
        template = fc.catalogue.call_template(item)
        st.code(template, language="python")
        widget(st, 'download_button', "Download call template (inputs required)", template, "function_template.py", "text/x-python", key=_key(item, "template"))


def _style(st, contract, draft):
    if not contract.entry.action:
        return {}
    style = dict(draft.get("style", {}))
    if widget(st, 'checkbox', "Edit appearance", key=_key(contract.entry, "appearance_open"), help="Presentation settings are separate from the scientific inputs."):
        from PyFLASH.aesthetics import get_pyflash_style
        from PyFLASH.ui.appearance import effective_style
        defaults = get_pyflash_style()
        defaults.update(effective_style(st.session_state, {}))
        previous = st.session_state.get(_key(contract.entry, "style_defaults"), {})
        selected_defaults = {}
        with st.container(border=True):
            for name in ("figure_size", "save_dpi", "point_size", "line_width", "labelsize", "tick_label_size", "legend_fontsize", "font_family", "matrix_cmap"):
                widget_key = _key(contract.entry, "style_" + name)
                if name not in style and name in previous and previous[name] != defaults[name]:
                    for suffix in ("", "_first", "_second"):
                        st.session_state.pop(widget_key + suffix, None)
                selected_defaults[name] = defaults[name]
                p = fc.catalogue.Parameter(name, "keyword", False, repr(defaults[name]), "", "Presentation only; original measurements and statistical settings are unchanged.")
                f = fc.Field(p, "range" if name == "figure_size" else "number" if isinstance(defaults[name], (int, float)) else "text", name.replace("_", " ").capitalize())
                v = _widget(st, contract, f, style.get(name, defaults[name]), {}, key=widget_key)
                if name == "save_dpi" and v is not None:
                    v = int(v)
                if v != defaults[name] and not (name == "figure_size" and tuple(v) == tuple(defaults[name])):
                    style[name] = v
                else:
                    style.pop(name, None)
        st.session_state[_key(contract.entry, "style_defaults")] = selected_defaults
        from PyFLASH.ui.appearance import presentation_editor
        presentation = presentation_editor(st, style.get('presentation',{}), key=_key(contract.entry,'presentation'))
        if presentation:
            style['presentation'] = presentation
        else:
            style.pop('presentation',None)
    return style


def show_result(st, contract, *, compact=False):
    from PyFLASH.ui import figures
    result = st.session_state.get(_key(contract.entry, "result"))
    if not result:
        return
    st.subheader("Result")
    if widget(st, 'button', "Restore this run's inputs", key=_key(contract.entry, "restore"), icon=":material/edit:", help="Restore exactly the inputs and appearance recorded for this result."):
        values = {k:v for k,v in result.get("parameters", {}).items() if k in {f.name for f in contract.fields if f.role not in {"bound", "managed", "alias"}}}
        st.session_state.setdefault("ui_function_drafts", {})[contract.entry.key] = {"schema_version": 1, "values": values, "style": result.get("style", {}), "target_experiment": result.get("target_experiment")}
        for key in list(st.session_state):
            if key.startswith(_key(contract.entry, "")) and not key.endswith("_result"):
                del st.session_state[key]
        st.rerun()
    if result.get("paths"):
        figures.embed_figure(None, result.get("root"), paths=result["paths"], since=result.get("since"), default_columns=1 if compact else 2)
    for table in result.get("tables", []):
        import pandas as pd
        if not Path(table["path"]).is_file():
            st.warning("This run's saved table has moved or been removed. Rerun its recorded inputs to recreate it.")
            continue
        st.markdown(f"**{table['name']}**")
        st.dataframe(pd.read_csv(table["path"], nrows=100), hide_index=True, width="stretch")
        with open(table["path"], "rb") as stream:
            widget(st, 'download_button', "Download complete result table", stream, Path(table["path"]).name, "text/csv", key=_key(contract.entry, "table_" + table["name"]))
    if result.get("value") is not None and not compact:
        st.write(result["value"])
    if result.get("script"):
        widget(st, 'download_button', "Download equivalent Python script", result["script"], "replay_function.py", "text/x-python", key=_key(contract.entry, "replay"), icon=":material/code:")
    with fold('function.record', namespace=contract.entry.key+":"):
        st.json(result.get("parameters", {}))
        if compact and result.get('value') is not None:
            st.write(result['value'])
        st.code(result.get("log", ""), language="text")


def render(contract):
    import streamlit as st
    st.subheader(contract.title)
    show_result(st, contract)
    if contract.access != "form":
        st.info(contract.reason)
        _reference(st, contract)
        return
    batch = st.session_state.get("batch")
    from PyFLASH.actions import HELPER_ACTIONS
    needs_source = bool(contract.entry.action) or HELPER_ACTIONS.get(contract.entry.key, ('', 'instance'))[1] != 'value'
    if batch is None and needs_source:
        st.info("Open a dataset in Workspace to choose its measurements and run this function.")
        _reference(st, contract)
        return
    migration_issue = migrate_legacy_draft(st.session_state, contract)
    from PyFLASH.ui import dependency_controls
    if not dependency_controls.render('core'):
        _reference(st, contract)
        return
    if migration_issue:
        st.warning(migration_issue)
        previous = st.session_state.get("ui_fig_params_" + contract.entry.action)
        widget(st, 'download_button', "Download the previous recipe for recovery", previous if isinstance(previous, str) else json.dumps(previous),
                           "previous_recipe.json", "application/json", key=_key(contract.entry, "replay"))
    drafts = st.session_state.setdefault("ui_function_drafts", {})
    draft = copy.deepcopy(drafts.get(contract.entry.key, {"schema_version": 1, "values": {}, "style": {}}))
    restore_draft_controls(st.session_state, contract.entry, draft)
    target = batch
    experiments = list(getattr(batch, "experiment_list", []) or [])
    if contract.entry.action == "locations" and experiments:
        names = [e.name for e in experiments]
        experiment_key = _key(contract.entry, "target_experiment")
        if experiment_key not in st.session_state and draft.get("target_experiment") in names:
            st.session_state[experiment_key] = draft["target_experiment"]
        chosen = widget(st, 'selectbox', "Experiment", names, key=experiment_key,
                              help="Select the experiment with the object coordinates to plot.")
        draft["target_experiment"] = chosen
        target = next(e for e in experiments if e.name == chosen)
    context = fc.input_context(target, st.session_state.get("ui_region"), st.session_state.setdefault("_ui_measurement_cache", {}))
    if target is not batch:
        context = {**context, "experiments": experiments}
    values = dict(draft.get("values", {}))
    if contract.entry.action in {"histograms", "ridgeline", "ecdf", "pie_charts", "combo_pies", "coloc_upset", "coloc_sankey"} and not context["markers"]:
        st.info("This dataset has summary measurements but no imported per-object marker tables. Open a processed FLASH dataset with object measurements to use this function.")
    if contract.entry.action in {"images", "representative_images"} and not context["image_markers"]:
        st.info("This dataset has no imported microscopy images. Import images in the experiment setup before using this function.")
    if widget(st, 'button', "Reset to package defaults", key=_key(contract.entry, "reset"), help="Clears this function's draft only; previous results remain available."):
        drafts.pop(contract.entry.key, None)
        for key in list(st.session_state):
            if key.startswith(_key(contract.entry, "")) and not key.endswith("_result"):
                del st.session_state[key]
        st.rerun()
    primary = [f for f in contract.fields if f.name in fc.COMMON or (f.parameter.required and f.role not in {"bound", "managed", "alias", "object"})]
    remaining = [f for f in contract.fields if f not in primary and f.role not in {"bound", "managed", "alias", "object"}]
    field_errors = {}
    def draw(field, advanced=False):
        default = fc.default_value(field.parameter)
        existing = values.get(field.name, default)
        mode = "Set value"
        if advanced:
            mode = widget(st, 'selectbox', field.label + " setting", ["Package default", "Set value", "None"],
                                index=1 if field.name in values and values[field.name] is not None else 2 if field.name in values else 0,
                                key=_key(contract.entry, field.name + "_mode"), help="Package default omits the argument. None explicitly supplies an empty optional value.")
            if mode == "Package default":
                values.pop(field.name, None)
                return
            if mode == "None":
                values[field.name] = None
                return
        try:
            value = _widget(st, contract, field, existing, context)
            if advanced or field.parameter.required or value not in (None, "", []) and value != default:
                values[field.name] = value
            elif field.name not in values or values[field.name] not in (None, [], ""):
                values.pop(field.name, None)
        except (ValueError, TypeError) as exc:
            field_errors[field.name] = str(exc)
        old_issue = st.session_state.get(_key(contract.entry, "errors"), {}).get(field.name)
        if old_issue:
            st.error(old_issue)
    for field in primary:
        draw(field)
    # Groups use their original values, including numeric levels; empty means all.
    table = context["table"]
    if table is not None and "filter_by" in {f.name for f in contract.fields}:
        group_col = getattr(batch, "group_col", None) or "Condition"
        if group_col in table:
            group_options = list(table[group_col].dropna().unique())
            groups_key = _key(contract.entry, "selected_groups")
            if groups_key not in st.session_state:
                st.session_state[groups_key] = values.get("filter_by", {}).get(group_col, []) if isinstance(values.get("filter_by"), dict) else []
            st.session_state[groups_key] = [v for v in st.session_state[groups_key] if v in group_options]
            groups = widget(st, 'multiselect', "Groups", group_options, key=groups_key, help="Blank uses all groups. Selected levels are pooled into this analysis, preserving their identities.")
            if groups:
                values.setdefault("filter_by", {})[group_col] = groups
            elif isinstance(values.get("filter_by"), dict):
                values["filter_by"].pop(group_col, None)
                if not values["filter_by"]:
                    values.pop("filter_by")
    if contract.entry.action in {"images", "representative_images"}:
        from PyFLASH.ui import services
        with fold('function.images', namespace=contract.entry.key+":"):
            images = services.image_table(batch)
            if images is not None:
                st.dataframe(images, hide_index=True, width="stretch")
            selections = services.get_representative_selections(batch)
            if selections is not None and not selections.empty:
                edited = widget(st, 'data_editor', selections, num_rows="dynamic", key=_key(contract.entry, "representatives"), width="stretch")
                if widget(st, 'button', "Apply representative selections", key=_key(contract.entry, "apply_representatives"), help="Updates the current workspace selection; background runs record these exact edits."):
                    from PyFLASH.ui.workspace import save_representative_edit
                    save_representative_edit(st.session_state, edited)
                    st.success("Representative selections updated.")
    if widget(st, 'checkbox', "Show advanced analysis settings", key=_key(contract.entry, "advanced_open"), help="Fields stay at their package defaults until explicitly changed."):
        for field in primary:
            if field.parameter.required:
                continue
            choices = ["Use form value", "Package default", "None"]
            if field.role in {"measurements", "metadata_list", "marker_list", "image_markers", "list", "numbers"}:
                choices.append("Empty list")
            mode = widget(st, 'selectbox', field.label + " setting", choices,
                                index=2 if field.name in values and values[field.name] is None else 3 if len(choices) == 4 and values.get(field.name) == [] else 0,
                                key=_key(contract.entry, field.name + "_mode"), help="Use the visible form value, omit the input, or explicitly supply None or an empty list.")
            if mode == "Package default":
                values.pop(field.name, None)
            elif mode == "None":
                values[field.name] = None
            elif mode == "Empty list":
                values[field.name] = []
        for field in remaining:
            if field.name not in fc.APPEARANCE:
                draw(field, advanced=True)
    style = _style(st, contract, draft)
    if widget(st, 'checkbox', "Show function-specific appearance settings", key=_key(contract.entry, "specific_appearance_open"), help="Figure-specific labels, axis ranges and colors."):
        for field in remaining:
            if field.name in fc.APPEARANCE:
                draw(field, advanced=True)
    drafts[contract.entry.key] = {"schema_version": 1, "values": values, "style": style,
                                "controls": draft_controls(st.session_state, contract.entry),
                                "sweep": draft.get("sweep", {"parameters":[], "text":{}}),
                                "target_experiment": draft.get("target_experiment")}
    if table is not None:
        selected = table
        for col, vs in (values.get("filter_by") or {}).items():
            if col in selected:
                selected = selected[selected[col].isin(vs if isinstance(vs, list) else [vs])]
        subject = values.get("subject_col") or getattr(batch, "subject_col", None) or "AnimalName"
        st.caption(f"{len(selected)} rows · {selected[subject].nunique() if subject in selected else 'unknown'} subjects · region {st.session_state.get('ui_region', 'all')}")
    from PyFLASH.ui.appearance import effective_style, errors as appearance_errors
    run_style = effective_style(st.session_state, style) if contract.entry.action else style
    issues = {**fc.validate(contract, values, context), **field_errors, **appearance_errors(run_style)}
    from PyFLASH.actions import required_dependency_groups
    try:
        for dependency_group in required_dependency_groups(contract.entry.action or contract.entry.key, values):
            if not dependency_controls.render(dependency_group):
                issues['dependencies'] = 'Install the selected feature dependency before running.'
    except ValueError as exc:
        issues['model_families'] = str(exc)
    with fold('function.inputs', namespace=contract.entry.key+":"):
        st.write(values)
        st.caption("Unchanged options use the documented package defaults shown in Function reference.")
    from PyFLASH.ui import jobs
    job = jobs.latest_job()
    busy = job and job["status"] in jobs.ACTIVE_STATES
    if busy:
        st.info("A job is running. You can keep editing these inputs; run them when it finishes.")
    from PyFLASH.ui.sweeps import render_options
    render_options(st, contract, values, run_style, context, busy=busy, issues=issues)
    if widget(st, 'button', "Run " + contract.title.lower(), type="primary", icon=":material/play_arrow:",
                 key=_key(contract.entry, "run"), disabled=bool(busy), help="Starts the owning package function in a background worker; inputs alone never start processing."):
        st.session_state[_key(contract.entry, "errors")] = issues
        if issues:
            for error in issues.values():
                st.error(error)
        else:
            try:
                from PyFLASH.ui.job_status import submit
                params = {"kwargs": fc.prepared_values(contract, values), "style": run_style, "region": st.session_state.get("ui_region")}
                if contract.entry.action:
                    params["plot_type"] = contract.entry.action
                    if contract.entry.action == "locations":
                        params["target_experiment"] = draft.get("target_experiment") or context["experiments"][0].name
                    submit("figure", params, contract.title, _key(contract.entry, "result"))
                else:
                    if HELPER_ACTIONS[contract.entry.key][1] == 'value':
                        jobs.start_value_action(contract.entry.key, params['kwargs'], name=contract.title,
                            dataset_token=st.session_state['_ui_dataset_token'], target_key=_key(contract.entry, 'result'))
                        st.rerun()
                    else:
                        params["function_key"] = contract.entry.key
                        submit("function", params, contract.title, _key(contract.entry, "result"))
            except Exception as exc:
                st.error(f"Could not start this function: {exc}")
    _reference(st, contract)


def saved_specification():
    """Keep existing declarative recipes in the same background result home."""
    import streamlit as st
    from dataclasses import replace
    from PyFLASH.ui import jobs, job_status
    owner = fc.find("action:mean_bars")
    contract = replace(owner, entry=replace(owner.entry, key="saved_figure_specification"))
    with fold('function.specification', namespace=contract.entry.key+":"):
        st.caption("Existing YAML, JSON and TOML figure recipes still run here. The worker validates the recipe before executing it.")
        path = widget(st, 'text_input', "Saved specification file", key="ui_spec_path")
        uploaded = widget(st, 'file_uploader', "Or choose a saved specification", type=["yaml", "yml", "json", "toml"], key="_function_event_spec_upload")
        batch = st.session_state.get("batch")
        job = jobs.latest_job()
        busy = job and job["status"] in jobs.ACTIVE_STATES
        if widget(st, 'button', "Validate and run specification", key="_function_event_spec_run", disabled=batch is None or bool(busy)):
            if uploaded is not None:
                from PyFLASH.ui import workspace
                content = uploaded.getvalue()
                destination = workspace.recovery_path().parent / "specifications" / (hashlib.sha256(content).hexdigest() + Path(uploaded.name).suffix)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.is_file():
                    destination.write_bytes(content)
                path = str(destination)
            if not Path(path).is_file():
                st.error("Choose an existing specification file.")
            else:
                job_status.submit("figure_spec", {"spec_path": str(Path(path).resolve())},
                                  "Saved figure specification", _key(contract.entry, "result"))
        show_result(st, contract)
