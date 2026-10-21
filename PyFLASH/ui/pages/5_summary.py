"""Live linked exploration. These charts are interface views, never files."""
import streamlit as st
from PyFLASH.ui.performance_trace import record, start
from PyFLASH.ui.controls import fold, widget
from PyFLASH.ui import services, workspace
from PyFLASH.ui.theme import PALETTE
from PyFLASH.ui.workflow import HELP

batch = st.session_state.get("batch")
if batch is None:
    st.info("Open data in Workspace, or build an analysis in Process.")
    st.stop()
stage = start()
raw_table = services.summary_table(batch, roi_base=st.session_state.get("ui_region"), display=False)
record("summary_table", stage, rows=len(raw_table), columns=len(raw_table.columns))
stage = start()
table, metrics, labels = workspace.measurement_catalogue(batch, roi_base=st.session_state.get("ui_region"),
                                    cache=st.session_state.setdefault("_ui_measurement_cache", {}))
record("measurement_catalogue_page", stage, metrics=len(metrics))
if table is None or table.empty:
    st.info("This region has no summary measurements.")
    st.stop()
if not metrics:
    st.info("This region has no finite numeric measurements.")
    st.dataframe(workspace.display_table(table), use_container_width=True)
    st.stop()

import numpy as np
import hashlib
import json
import pandas as pd

group_options = table["Condition"].dropna().astype(str).unique().tolist() if "Condition" in table else []
subject_options = ["All subjects"] + table["AnimalName"].dropna().astype(str).unique().tolist() if "AnimalName" in table else ["All subjects"]
with st.sidebar:
    st.subheader("Explore controls")
    if group_options:
        if "ui_explore_groups" not in st.session_state:
            st.session_state["ui_explore_groups"] = group_options
        else:
            st.session_state["ui_explore_groups"] = [g for g in st.session_state["ui_explore_groups"] if g in group_options]
        groups = widget(st, 'multiselect', "Groups", group_options, key="ui_explore_groups", help="Filter both views and the displayed table.")
        table = table[table["Condition"].astype(str).isin(groups)].copy()
    if st.session_state.get("ui_explore_subject") not in subject_options:
        st.session_state["ui_explore_subject"] = "All subjects"
    for key, default in (("distribution", metrics[-1]), ("x", metrics[0]), ("y", metrics[-1])):
        name = f"ui_explore_{key}"
        if st.session_state.get(name) not in metrics:
            st.session_state[name] = default
    choices = metrics
    if len(metrics) > 200:
        query = widget(st, 'text_input', "Find a measurement", key="ui_explore_search", help="Search measurement names. All columns remain available; selected measurements stay in the menus.")
        choices, matching = workspace.measurement_choices(metrics, labels, query,
            [st.session_state[f"ui_explore_{key}"] for key in ("distribution", "x", "y")])
        st.caption(f"{matching} matching measurements. Menus show up to 200 matches plus your selections; refine the search to see more.")
    metric = widget(st, 'selectbox', "Distribution measurement", choices, key="ui_explore_distribution", format_func=lambda c: labels[c], help=HELP["metric"])
    x = widget(st, 'selectbox', "Relationship horizontal axis", choices, key="ui_explore_x", format_func=lambda c: labels[c], help=HELP["metric"])
    y = widget(st, 'selectbox', "Relationship vertical axis", choices, key="ui_explore_y", format_func=lambda c: labels[c], help=HELP["metric"])
    appearance = fold('explore.appearance')
    height = st.session_state.get('ui_explore_height', 800)
    points = st.session_state.get('ui_explore_point_size', 70)
    font = st.session_state.get('ui_explore_font', 13)
    legend = st.session_state.get('ui_explore_legend', True)
    zero = st.session_state.get('ui_explore_zero', False)
    if appearance.open:
        with appearance:
            height = widget(st, 'slider', "Plot height", 300, 900, value=st.session_state.get("ui_explore_height", 800), step=25, key="ui_explore_height", help=HELP["appearance"])
            points = widget(st, 'slider', "Point size", 20, 200, 70, 10, key="ui_explore_point_size", help=HELP["appearance"])
            font = widget(st, 'slider', "Label size", 10, 22, 13, key="ui_explore_font", help=HELP["appearance"])
            legend = widget(st, 'toggle', "Show legend", True, key="ui_explore_legend", help=HELP["appearance"])
            zero = widget(st, 'toggle', "Start numeric axes at zero", False, key="ui_explore_zero", help=HELP["appearance"])
            if widget(st,'checkbox','Edit one view',key='ui_explore_local_appearance_open',
                      help='Keep separate appearance edits for each linked view.'):
                views = {'distribution_view':'Group distribution','relationship_view':'Measurement relationship'}
                selected_view = widget(st,'selectbox','View appearance',list(views),format_func=views.get,
                                       key='ui_explore_appearance_view',help='Choose the view whose presentation should change.')
                from PyFLASH.ui.appearance import presentation_editor
                styles = st.session_state.setdefault('ui_explore_view_styles',{})
                fields = {'ylim','legend','series_color','series_colors','line_width','font_size','font_family'}
                if selected_view == 'relationship_view':
                    fields.add('xlim')
                styles[selected_view] = presentation_editor(st,styles.get(selected_view,{}),
                    key='ui_explore_appearance_'+selected_view,fields=fields)

if table.empty:
    st.info("Select at least one group to inspect measurements.")
    st.stop()
shown_fields = list(dict.fromkeys((metric, x, y)))
stage = start()
data, field_keys = workspace.exploration_data(table, shown_fields)
record("exploration_data", stage, rows=len(data), columns=len(data.columns))
data = data.replace([np.inf, -np.inf], np.nan)
data["_subject"] = data["AnimalName"].astype(str) if "AnimalName" in data else data.index.astype(str)
data["_group"] = data["Condition"].astype(str) if "Condition" in data else "All"
data["_row"] = np.arange(len(data))
colour = {"field": "_group", "type": "nominal", "title": "Group",
          "scale": {"domain": group_options or ["All"], "range": list(PALETTE)},
          "legend": {"orient": "bottom", "title": ""} if legend else None}
data_identity = hashlib.sha256(pd.util.hash_pandas_object(data, index=True).values.tobytes()).hexdigest()
tooltips = [{"field": "_subject", "type": "nominal", "title": "Subject"},
            {"field": "_group", "type": "nominal", "title": "Group"}]


def quantitative(field):
    return {"field": field_keys[field], "type": "quantitative", "title": labels[field], "scale": {"zero": zero}}


def draw(chart, key):
    # Keep the data rectangles equally tall. Fitting the total height shrinks
    # each plot differently when its axis labels or legend need more space.
    chart.update({"height": height, "autosize": {"type": "none", "contains": "padding", "resize": True},
                  "usermeta": {"input_hash": data_identity},
                  "padding": {"left": font * 3 + 40, "right": font * 2, "top": max(16, font), "bottom": 125}, "config": {
        "axis": {"labelFontSize": font, "titleFontSize": font + 1, "tickCount": 6, "labelAngle": 0},
        "axisX": {"minExtent": font + 22, "maxExtent": font + 22, "titlePadding": 10},
        "legend": {"labelFontSize": font, "symbolSize": points},
        "view": {"stroke": None}}})
    from PyFLASH.ui.appearance import style_live_chart
    try:
        chart = style_live_chart(chart,st.session_state.get('ui_explore_view_styles',{}).get(key,{}))
    except (ValueError,TypeError) as exc:
        st.error('Appearance needs valid settings: '+str(exc))
    # A direct Vega-Lite specification avoids rebuilding and validating the
    # same Altair object tree on every subject-highlight change.
    # Attach selection only to points, not to the boxplot's generated layers.
    selection_layer = chart["layer"][-1] if "layer" in chart else chart
    selection_layer["name"] = key + "_points"
    chart["params"] = [{"name": "picked_subject", "select": {"type": "point", "fields": ["_subject"]},
                        "views": [key + "_points"]}]

    def select_subject():
        from PyFLASH.actions import call_action
        call_action('PyFLASH.ui.workspace.set_preferences', parameters={'state': st.session_state,
            'updates': {'ui_explore_subject': workspace.selected_subject(st.session_state.get(key, {}))}})

    selected = st.session_state.get("ui_explore_subject", "All subjects")
    view_data = data.assign(_highlight_opacity=np.where(True if selected == "All subjects" else data["_subject"].eq(selected), .9, .18))
    # Streamlit's Arrow hash uses schema and byte count, rather than cell values.
    # A presentation identity column invalidates its data cache without recompiling
    # the Vega specification or modifying any scientific measurement.
    view_data["_view_revision_" + hashlib.sha256(selected.encode()).hexdigest()[:16]] = False
    stage = start()
    st.vega_lite_chart(view_data, chart, width="stretch", theme="streamlit", key=key,
                       on_select=select_subject)
    record("chart_delta", stage, chart=key, rows=len(view_data))


@st.fragment
def show_views():
    heading, subject_control = st.columns([1, 1], vertical_alignment="center")
    with heading:
        st.title("Explore")
    with subject_control:
        subject = widget(st, 'selectbox', "Highlight subject", subject_options, key="ui_explore_subject", help=HELP["subject"], label_visibility="collapsed")
    opacity = {"field": "_highlight_opacity", "type": "quantitative", "scale": None, "legend": None}
    left, right = st.columns(2, gap="small")
    with left:
        st.subheader("Group distribution")
        common = {"x": {"field": "_group", "type": "nominal", "title": "Group"},
                  "y": quantitative(metric), "color": colour}
        draw({"transform": [{"filter": {"field": field_keys[metric], "valid": True}}], "layer": [
            {"mark": {"type": "boxplot", "extent": 1.5, "size": 45, "opacity": 0.25}, "encoding": common},
            {"mark": {"type": "circle", "size": points}, "encoding": {
                **common, "opacity": opacity, "tooltip": tooltips + [{"field": field_keys[metric], "type": "quantitative", "title": labels[metric]}]}}]}, "distribution_view")
    with right:
        st.subheader("Measurement relationship")
        chart = {"mark": {"type": "circle", "size": points}, "encoding": {
            "x": quantitative(x), "y": quantitative(y), "color": colour, "opacity": opacity,
            "tooltip": tooltips + [{"field": field_keys[c], "type": "quantitative", "title": labels[c]} for c in dict.fromkeys((x, y))]}}
        draw(chart, "relationship_view")

    try:
        workspace.checkpoint_session(st.session_state)
    except (OSError,ValueError) as exc:
        st.session_state["ui_recovery_error"] = str(exc)
        st.error(f"Could not save workspace preferences: {exc}")

show_views()

measurements = fold('explore.measurements')
if measurements.open:
    with measurements:
        shown = raw_table.loc[table.index, [c for c in ("AnimalName", "Condition") if c in raw_table] + shown_fields]
        st.dataframe(workspace.display_table(shown), width="stretch", hide_index=True)
        st.caption(f"{len(table)} summary rows · {int(table[shown_fields].isna().sum().sum())} missing or excluded values in the selected measurements. Values are not imputed; original tags remain in the table. Export provides the full summary.")
        from PyFLASH.ui.job_status import submit
        parameters = {'region':st.session_state.get('ui_region'), 'columns':list(shown.columns),
                      'groups':groups if group_options else None}
        if widget(st, 'button', 'Prepare shown table', key='_control_event_5_summary_001',
                  help='Prepares the displayed rows and columns with a complete receipt and replay script.'):
            try:
                submit('csv', parameters, 'Shown measurements', 'ui_explore_csv_result')
            except Exception as exc:
                st.error(str(exc))
        exported = st.session_state.get('ui_explore_csv_result')
        if exported and exported.get('parameters') == parameters:
            from pathlib import Path
            widget(st, 'download_button', 'Download shown table', Path(exported['path']).read_bytes(),
                   'measurements.csv', 'text/csv', key='explore_download_table',
                   help='The complete displayed table, preserving original missing-value tags.')
            widget(st, 'download_button', 'Download table script', exported['script'],
                   'replay_table.py', 'text/x-python', key='explore_download_script',
                   help='Recreates these exact rows and columns from content-verified inputs.')
