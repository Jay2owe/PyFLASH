"""Saved house defaults for new figure runs, without process-global changes."""
import math
from PyFLASH.ui.controls import fold, widget


def errors(style):
    result = {}
    if 'presentation' in style:
        from PyFLASH.aesthetics import _validate_presentation
        try:
            _validate_presentation(style['presentation'])
        except (TypeError,ValueError) as exc:
            result['presentation'] = str(exc)
    for name, value in style.items():
        if name == "figure_size" and (not isinstance(value, (list, tuple)) or len(value) != 2 or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in value)):
            result[name] = "Enter two positive figure dimensions."
        elif name in {"save_dpi", "point_size", "line_width", "labelsize", "tick_label_size", "legend_fontsize"} and (not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (name not in {"point_size", "line_width"} and value == 0)):
            result[name] = "Enter a valid appearance value before running."
    return result


def presentation_editor(st, settings, *, key, fields=None):
    """Build every plot's display-only controls from the shared vocabulary."""
    from PyFLASH.aesthetics import PRESENTATION_FIELDS
    result = dict(settings)
    for name, field in PRESENTATION_FIELDS.items():
        if fields is not None and name not in fields:
            continue
        item_key = key+'_'+name
        label, help_ = field['label'], field['help']
        if name == 'legend':
            choices = field['choices']
            chosen = widget(st,'selectbox',label,choices,index=choices.index(result.get(name,'keep')),
                            key=item_key,help=help_)
            if chosen == 'keep':
                result.pop(name,None)
            else:
                result[name] = chosen
            continue
        if not widget(st,'checkbox','Set '+label.lower(),value=name in settings,key=item_key+'_enabled',help=help_):
            result.pop(name,None)
            continue
        kind = field['kind']
        if kind == 'range':
            first,second = st.columns(2)
            bounds = result.get(name,[0.,1.])
            result[name] = [widget(first,'number_input',label+' minimum',value=float(bounds[0]),key=item_key+'_first',help=help_),
                            widget(second,'number_input',label+' maximum',value=float(bounds[1]),key=item_key+'_second',help=help_)]
        elif kind == 'color':
            from matplotlib.colors import to_hex
            from PyFLASH.ui.theme import PALETTE
            result[name] = widget(st,'color_picker',label,value=to_hex(result.get(name,PALETTE[0])),key=item_key,help=help_)
        elif kind == 'mapping':
            import pandas as pd
            values = result.get(name,{})
            rows = st.session_state.setdefault(item_key+'_rows',[{'Series label':k,'Colour':v} for k,v in values.items()])
            edited = widget(st,'data_editor',pd.DataFrame(rows,columns=['Series label','Colour']),num_rows='dynamic',hide_index=True,key=item_key)
            result[name] = {str(row['Series label']):str(row['Colour']) for row in edited.to_dict('records')
                            if row.get('Series label') and row.get('Colour')}
        elif kind == 'number':
            result[name] = widget(st,'number_input',label,value=float(result.get(name,2. if name=='line_width' else 16.)),
                                 min_value=0. if name=='line_width' else 1.,key=item_key,help=help_)
        else:
            result[name] = widget(st,'text_input',label,value=result.get(name,'Arial'),key=item_key,help=help_)
    return result


def style_live_chart(chart, settings):
    """Style a copied Vega view without modifying its source arrays or identities."""
    import copy
    chart = copy.deepcopy(chart)
    if not settings:
        return chart
    from PyFLASH.aesthetics import _validate_presentation
    _validate_presentation(settings)
    from matplotlib.colors import to_hex
    for layer in chart.get('layer',[chart]):
        encoding = layer.get('encoding',{})
        for axis in ('x','y'):
            if axis+'lim' in settings and encoding.get(axis,{}).get('type') == 'quantitative':
                encoding[axis].setdefault('scale',{}).update(domain=list(settings[axis+'lim']),zero=False)
        colour = encoding.get('color')
        if isinstance(colour,dict):
            if settings.get('legend') == 'hide':
                colour['legend'] = None
            elif settings.get('legend') == 'show':
                colour['legend'] = colour.get('legend') or {'orient':'bottom','title':''}
            scale = colour.get('scale',{})
            domain = scale.get('domain',[])
            old = scale.get('range',[])
            if domain and ('series_color' in settings or 'series_colors' in settings):
                from PyFLASH.ui.theme import PALETTE
                old = old or PALETTE
                scale['range'] = [to_hex(settings.get('series_colors',{}).get(str(label),
                    settings.get('series_color',old[index % len(old)]))) for index,label in enumerate(domain)]
        mark = layer.get('mark')
        if isinstance(mark,dict) and 'line_width' in settings:
            mark['strokeWidth'] = settings['line_width']
    config = chart.setdefault('config',{})
    if 'font_size' in settings:
        font = settings['font_size']
        config.setdefault('axis',{}).update(labelFontSize=font,titleFontSize=font)
        config.setdefault('legend',{}).update(labelFontSize=font)
        # A local font edit must also reserve its own axis space; otherwise the
        # original, smaller house-font margin clips the vertical title.
        padding = chart.get('padding')
        if isinstance(padding,dict):
            padding.update(left=max(padding.get('left',0),font*3+40),
                           right=max(padding.get('right',0),font*2),
                           top=max(padding.get('top',0),font))
        config.setdefault('axisX',{}).update(minExtent=font+22,maxExtent=font+22,titlePadding=10)
    if 'font_family' in settings:
        config.setdefault('axis',{}).update(labelFont=settings['font_family'],titleFont=settings['font_family'])
        config.setdefault('legend',{}).update(labelFont=settings['font_family'],titleFont=settings['font_family'])
    return chart


def effective_style(state, overrides):
    return {**state.get("ui_house_style", {}), **overrides}


def render():
    import streamlit as st
    from PyFLASH.aesthetics import get_pyflash_style
    from PyFLASH.ui import function_tools

    with fold('appearance.house'):
        st.caption("Defaults for new figures and pipelines. Each function can override them in Edit appearance; existing results keep their recorded appearance.")
        package = get_pyflash_style()
        current = dict(package)
        current.update(st.session_state.get("ui_house_style", {}))
        with st.form("house_aesthetic"):
            a, b, c = st.columns(3)
            size = current["figure_size"]
            width = widget(a, 'number_input', "Figure width (inches)", min_value=0.1, value=float(size[0]), key="ui_house_width")
            height = widget(b, 'number_input', "Figure height (inches)", min_value=0.1, value=float(size[1]), key="ui_house_height")
            dpi = widget(c, 'number_input', "Save DPI", min_value=1, value=int(current["save_dpi"]), key="ui_house_dpi", help="Pixels per inch for raster exports.")
            values = {"figure_size": (width, height), "save_dpi": dpi}
            labels = {"point_size": "Point size", "line_width": "Line width", "labelsize": "Axis label size", "tick_label_size": "Tick label size", "legend_fontsize": "Legend font size"}
            for i, (name, label) in enumerate(labels.items()):
                values[name] = widget((a, b, c)[i % 3], 'number_input', label, min_value=0.0 if name in {"point_size", "line_width"} else 1.0,
                                                           value=float(current[name]), key="ui_house_" + name)
            values["font_family"] = widget(a, 'text_input', "Font family", value=current["font_family"], key="ui_house_font_family")
            values["matrix_cmap"] = widget(b, 'text_input', "Matrix colour map", value=current["matrix_cmap"], key="ui_house_matrix_cmap")
            save = widget(st, 'form_submit_button', "Save house aesthetic", type="primary", key='_control_event_appearance_001')
        if save:
            issues = errors(values)
            if not values["font_family"].strip():
                issues["font_family"] = "Enter a font family."
            from matplotlib import colormaps
            if values["matrix_cmap"] not in colormaps:
                issues["matrix_cmap"] = "Choose a Matplotlib colour map, for example coolwarm or viridis."
            if issues:
                for issue in issues.values():
                    st.error(issue)
            else:
                st.session_state["ui_house_style"] = {k:v for k,v in values.items() if v != package[k]}
                st.success("House aesthetic saved for new runs.")
        if widget(st, 'button', "Reset house aesthetic", key="_function_event_house_reset"):
            st.session_state.pop("ui_house_style", None)
            for key in list(st.session_state):
                if key.startswith("ui_house_"):
                    del st.session_state[key]
            st.rerun()
        function_tools.render("appearance", "Appearance package reference")
