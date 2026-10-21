"""Shared registered disclosures with native state and durable preference keys."""

CONTROL_CATALOGUE = {}
CONTROL_ICONS = {
    'text_input': 'edit', 'text_area': 'edit_note', 'number_input': 'numbers',
    'button': 'touch_app', 'download_button': 'download', 'form_submit_button': 'done',
    'selectbox': 'arrow_drop_down', 'multiselect': 'checklist', 'radio': 'radio_button_checked',
    'checkbox': 'check_box', 'toggle': 'toggle_on', 'slider': 'tune',
    'color_picker': 'palette', 'file_uploader': 'upload_file', 'data_editor': 'table_view',
}


NATIVE_CONTROL_HELP = """<script>
(() => {
  const labelNativeControls = () => {
    document.querySelectorAll('[data-testid="stNumberInput"]').forEach(control => {
      const field = control.querySelector('input');
      const label = control.querySelector('label');
      const name = field?.getAttribute('aria-label') || label?.innerText || 'value';
      for (const [testid,verb] of [['stNumberInputStepDown','Decrease'],['stNumberInputStepUp','Increase']]) {
        const button = control.querySelector(`[data-testid="${testid}"]`);
        if (button) {
          const help = `${verb} ${name}`;
          if (button.getAttribute('aria-label') !== help) button.setAttribute('aria-label',help);
          if (button.title !== help) button.title = help;
        }
      }
    });
    document.querySelectorAll('[data-testid="stButton"] button,[data-testid="stFormSubmitButton"] button,[data-testid="stDownloadButton"] button').forEach(button => {
      // Decorative material icons must not become part of a button's spoken
      // name. Expose its visible text to keyboard and assistive technology.
      const text = button.querySelector('[data-testid="stMarkdownContainer"]')?.innerText || button.innerText;
      const name = text?.trim();
      if (name && !button.getAttribute('aria-label')) button.setAttribute('aria-label', name);
    });
  };
  if (!window.pyflashNativeControlHelp) {
    window.pyflashNativeControlHelp = new MutationObserver(labelNativeControls);
    window.pyflashNativeControlHelp.observe(document.body,{childList:true,subtree:true});
  }
  labelNativeControls();
})();
</script>"""


def install_native_control_help(st):
    """Expose native stepper and download button names on their actual controls."""
    st.html(NATIVE_CONTROL_HELP,unsafe_allow_javascript=True)


def widget(target, kind, *args, **kwargs):
    """Create each native control through one stable-key/help/icon catalogue."""
    import sys
    from pathlib import Path
    frame = sys._getframe(1)
    home = Path(frame.f_code.co_filename).stem
    label = str(args[0]) if args and kind != 'data_editor' else kwargs.get('label', 'Edit table')
    key = kwargs.get('key')
    if key is None:
        raise ValueError('Declare a control key separately from its display label.')
    help_ = kwargs.get('help') or label.rstrip('.') + '.'
    CONTROL_CATALOGUE[str(key)] = {'home': home, 'label': label, 'help': help_,
                                  'icon': CONTROL_ICONS[kind], 'kind': kind}
    if kind == 'data_editor':
        # The native editor provides help on each column rather than a widget tooltip.
        import streamlit as st
        if hasattr(st, 'column_config') and args and hasattr(args[0], 'columns'):
            config = dict(kwargs.get('column_config') or {})
            for name in args[0].columns:
                existing = config.get(name)
                if isinstance(existing, dict):
                    config[name] = {**existing, 'help': existing.get('help') or str(name) + '.'}
                elif name not in config:
                    config[name] = st.column_config.Column(str(name), help=str(name) + '.')
            kwargs['column_config'] = config
    else:
        kwargs['help'] = help_
    if kind == 'text_area':
        # Streamlit supplies no icon argument for a multiline editor. Its
        # Markdown label supports the same Material icon as the other controls.
        if args:
            args = (':material/'+CONTROL_ICONS[kind]+': '+str(args[0]), *args[1:])
        elif 'label' in kwargs:
            kwargs['label'] = ':material/'+CONTROL_ICONS[kind]+': '+str(kwargs['label'])
    if kind in {'number_input', 'text_input', 'button', 'download_button', 'form_submit_button'}:
        kwargs.setdefault('icon', ':material/' + CONTROL_ICONS[kind] + ':')
    return getattr(target, kind)(*args, **kwargs)

FOLDS = {
    'app.help': {'label': 'Workspace help', 'icon': 'help'},
    'workspace.provenance': {'label': 'Loaded data and provenance', 'icon': 'description'},
    'workspace.dependencies': {'label': 'Installation and optional features', 'icon': 'build'},
    'appearance.house': {'label': 'House aesthetic', 'icon': 'palette'},
    'folders.layout': {'label': 'Folder layout details', 'icon': 'folder'},
    'folders.processing': {'label': 'Processing options', 'icon': 'settings'},
    'process.inputs': {'label': 'Processing inputs', 'icon': 'input', 'expanded': True},
    'process.advanced': {'label': 'Advanced', 'icon': 'settings'},
    'explore.appearance': {'label': 'Appearance', 'icon': 'palette'},
    'explore.measurements': {'label': 'Measurements and missing values', 'icon': 'table_view'},
    'function.reference': {'label': 'Function reference', 'icon': 'help'},
    'function.advanced': {'label': 'Advanced', 'icon': 'settings'},
    'function.empty_values': {'label': 'Exact empty values', 'icon': 'tune'},
    'function.history': {'label': 'Saved runs', 'icon': 'history'},
    'function.inputs': {'label': 'Inputs and transformations for this run', 'icon': 'input'},
    'function.sweep': {'label': 'Compare analysis choices', 'icon': 'view_module'},
    'function.record': {'label': 'Recorded settings and run log', 'icon': 'description'},
    'function.images': {'label': 'Imported images and representative selections', 'icon': 'image'},
    'function.specification': {'label': 'Run a saved figure specification', 'icon': 'code'},
    'jobs.log': {'label': 'Live processing log', 'icon': 'terminal'},
    'groups.explanation': {'label': 'Explanation expansion', 'icon': 'help'},
    'export.filters': {'label': 'Workbook filters and names', 'icon': 'filter_alt'},
    'export.log': {'label': 'Workbook export log', 'icon': 'description'},
    'functions.catalogue': {'label': 'Catalogue coverage', 'icon': 'help'},
    'tools.workspace': {'label': 'Other package functions', 'icon': 'code'},
    'tools.appearance': {'label': 'Appearance package reference', 'icon': 'palette'},
    'tools.export': {'label': 'Export package reference', 'icon': 'code'},
}


def fold(key, *, namespace=''):
    """Use the registry label; only the explicit key identifies a saved fold."""
    import streamlit as st
    entry = FOLDS[key]
    def changed():
        from PyFLASH.ui.workspace import checkpoint_session
        try:
            checkpoint_session(st.session_state)
        except OSError as exc:
            st.session_state['ui_recovery_error'] = str(exc)
    return st.expander(entry['label'], expanded=entry.get('expanded', False),
        key='ui_fold_'+namespace+key, icon=f":material/{entry['icon']}:", on_change=changed)
