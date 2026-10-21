"""Frozen condition-key semantics, geometry, ownership and saved-file controls.

Expected labels and encodings come from the literal declaration, not renderer
output. This family makes no scientific estimator claim. Whole qualification is
withheld until its full interface, native files and reproduction checks pass.
"""
from copy import deepcopy
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

ARCHIVE = Path(__file__).with_name('reference-sources') / 'condition-key/v1'
MANIFEST_SHA256 = '0aa9cd2d2c8665dfa73e2a1f79ed2a33e152427b7b628bb441aef9432d96b23a'
COMPLETE_CAPABILITIES = frozenset({'condition_key'})
CAPABILITY_PREFIXES = {'condition_key': ('condition-key.',)}


def declaration():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256)
    return json.loads((ARCHIVE / 'declaration.json').read_text(encoding='utf-8'))


def cases():
    import hashlib
    supplement = ARCHIVE / 'dataframe-owner.json'
    assert hashlib.sha256(supplement.read_bytes()).hexdigest() == '90a70ad0cd795dca0492eb50d2b5b9a342ef6ffcb077c9270dc4e7bcdd02ed45'
    return [*declaration()['rows'], *json.loads(supplement.read_text())['rows']]


def required_keys(capability):
    return {row['key'] for row in cases()} if capability == 'condition_key' else set()


def check_parameters():
    from PyFLASH.plotting import plot_condition_key
    actual = {name: 'required' if value.default is inspect.Parameter.empty else value.default
              for name, value in inspect.signature(plot_condition_key).parameters.items()}
    assert actual == declaration()['parameters'], 'Public condition-key arguments/defaults changed'


def owner(groups, folder, kind='namespace'):
    from PyFLASH.conditions import condition, conditionList
    members = [condition(row['label'], row['name'], row['color'], 'Treatment', style=row['style'])
               for row in groups]
    if kind == 'dataframe':
        import pandas as pd
        from PyFLASH.dataframe import DataFrameExperiment
        return DataFrameExperiment(pd.DataFrame({
            'Condition': [row['name'] for row in groups],
            'AnimalName': [f'subject-{index}' for index in range(len(groups))],
            'value': [1.] * len(groups)}),
            conditions=conditionList(members), fig_path=str(folder))
    if kind == 'namespace':
        result = SimpleNamespace()
    else:
        if kind == 'experiment':
            from PyFLASH.experiment import Experiment as cls
        elif kind == 'mini-experiment':
            from PyFLASH.experiment import MiniExperiment as cls
        elif kind == 'batch':
            from PyFLASH.batch import Batch as cls
        else:
            raise ValueError('Unknown condition owner')
        result = object.__new__(cls)
    result.condition_list = conditionList(members) if members else []
    result.fig_path = str(folder)
    return result


def _rgba(hex_color):
    text = hex_color.lstrip('#')
    return [int(text[index:index+2], 16) / 255 for index in (0, 2, 4)] + [1.]


def observe(case, output, *, capture_figure=None):
    import matplotlib.pyplot as plt
    import numpy as np
    from PyFLASH import plotting
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    data = declaration()
    groups = deepcopy(data['designs'][case['design']])
    experiment = owner(groups, output, case.get('owner', 'namespace'))
    untouched = deepcopy([vars(group) for group in experiment.condition_list])
    options = deepcopy(case['options'])
    mode = case['mode']
    destination = case.get('destination', 'explicit')
    expected = output / ('condition-key.' + case.get('extension', 'png'))
    if mode == 'memory':
        options['save'] = False
    elif destination in ('default', 'fallback'):
        expected = output / 'condition_key.png'
        if destination == 'fallback':
            del experiment.fig_path
    elif destination == 'filename':
        options['filename'] = 'selected-key'
        expected = output / 'selected-key.png'
    elif destination == 'extensionless':
        options['save_path'] = str(output / 'extensionless')
        expected = output / 'extensionless.png'
    elif destination == 'relative':
        options['save_path'] = 'relative-key.png'
        expected = output / 'relative-key.png'
    elif destination == 'path-object':
        options['save_path'] = expected
    else:
        options['save_path'] = str(expected)
    before_figures = set(plt.get_fignums())
    original_save = plotting.save_fig
    captured = {}
    declared_error = OSError('declared condition-key save failure')
    def save(fig, *args, **kwargs):
        captured.update(figure=fig, settings=kwargs)
        if case.get('inject_save_error'):
            raise declared_error
        return original_save(fig, *args, **kwargs)
    plotting.save_fig = save
    previous_directory = Path.cwd()
    result, error = None, None
    try:
        os.chdir(output)
        try:
            result = plotting.plot_condition_key(experiment, **options)
        except Exception as exc:
            error = exc
        leaked = set(plt.get_fignums()) - before_figures
        assert [vars(group) for group in experiment.condition_list] == untouched, 'Condition metadata changed'
        if mode == 'error':
            assert error is not None and type(error).__name__ == case['expected_error'], repr(error)
            if case.get('inject_save_error'):
                assert error is declared_error, 'Original save error replaced'
            if case.get('no_figure_leak'):
                assert not leaked, 'Failed save leaked an allocated figure'
            return dict(expected_error=type(error).__name__, inputs_unchanged=True, open_figures=len(leaked))
        if error is not None:
            raise error
        fig = result if mode == 'memory' else captured['figure']
        fig.canvas.draw()
        legend = fig.axes[0].get_legend()
        assert legend is not None
        assert [text.get_text() for text in legend.get_texts()] == [row['label'] for row in groups]
        from matplotlib.font_manager import FontProperties
        expected_font = FontProperties(size=plt.rcParams['legend.fontsize']).get_size_in_points()
        assert all(text.get_fontsize() == expected_font for text in legend.get_texts()), 'Legend overrides shared typography'
        patches = legend.legend_handles
        assert len(patches) == len(groups)
        for patch, group, style in zip(patches, groups, case['expected_styles']):
            color = _rgba(group['color'])
            hollow = style in ('hollow', 'outline', 'open')
            np.testing.assert_allclose(patch.get_facecolor(), [0.,0.,0.,0.] if hollow else color, rtol=0, atol=1e-12)
            np.testing.assert_allclose(patch.get_edgecolor(), color if hollow else [1.,1.,1.,1.] if style != 'fill' else [0.,0.,0.,0.], rtol=0, atol=1e-12)
            assert patch.get_hatch() == (None if style in ('fill','hollow','outline','open') else style)
        assert legend.get_title().get_text() == (options.get('title') or '')
        assert legend._ncols == case.get(
            'expected_columns', max(1, int(options.get('ncol', 1))))
        if case.get('fully_visible'):
            renderer = fig.canvas.get_renderer()
            for text in [*legend.get_texts(), legend.get_title()]:
                if not text.get_text():
                    continue
                box = text.get_window_extent(renderer)
                assert (box.x0 >= fig.bbox.x0 - .25 and box.x1 <= fig.bbox.x1 + .25
                        and box.y0 >= fig.bbox.y0 - .25 and box.y1 <= fig.bbox.y1 + .25), 'Complete legend text extends beyond figure'
        if mode == 'memory':
            assert set(plt.get_fignums()) - before_figures == {fig.number}
            assert not list(output.iterdir()), 'save=False wrote files'
        else:
            returned = Path(result)
            assert returned.resolve() == expected.resolve() and returned.is_file(), 'Returned path is not the actual saved carrier'
            assert not leaked, 'Successful save left an allocated figure'
            from reprofig import validate_artifact
            validation = validate_artifact(expected, expected_profile='master')
            assert validation.valid, str(validation)
            if expected.suffix == '.pdf':
                import fitz
                with fitz.open(expected) as document:
                    assert len(document) == 1
                    text = document[0].get_text()
                    assert all(group['label'] in text for group in groups), 'PDF omitted a condition label'
            elif expected.suffix != '.svg':
                from PIL import Image
                if expected.suffix == '.heif':
                    from pillow_heif import register_heif_opener
                    register_heif_opener()
                with Image.open(expected) as image:
                    image.load()
                    assert image.width > 0 and image.height > 0
            if expected.suffix == '.png' and 'dpi' in options:
                from PIL import Image
                with Image.open(expected) as image:
                    np.testing.assert_allclose(image.info['dpi'], [options['dpi']] * 2, rtol=0, atol=.03)
            if expected.suffix == '.svg':
                import xml.etree.ElementTree as ET
                tree = ET.parse(expected)
                texts = tree.findall('.//{http://www.w3.org/2000/svg}text')
                assert texts, 'SVG labels are outlined instead of editable text'
                labels = [''.join(node.itertext()) for node in texts]
                assert all(group['label'] in labels for group in groups), 'SVG omitted an editable condition label'
        if capture_figure is not None:
            capture_figure(fig)
        return dict(labels=[row['label'] for row in groups], styles=case['expected_styles'],
                    inputs_unchanged=True, complete_text_visible=True,
                    returned_path=str(result) if mode != 'memory' else None)
    finally:
        plotting.save_fig = original_save
        os.chdir(previous_directory)
        for number in set(plt.get_fignums()) - before_figures:
            plt.close(number)


def validate(output):
    import traceback
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    check_parameters()
    rows, paired = [], []
    for index, case in enumerate(cases()):
        actual, error = None, None
        try:
            actual = observe(case, Path(output) / f'case-{index:02d}')
        except Exception:
            error = traceback.format_exc()
        agrees = error is None
        rows.append(comparison(case['key'], 'predeclared-literal-legend/native-renderer-and-carrier-readers',
            'functional-public-condition-key/no-scientific-estimator-vote',
            {'complete_contract_matches': agrees}, {'complete_contract_matches': True}, agrees, True,
            'exact-labels-order-styles-paths-and-ownership/rgba-atol-1e-12/bounds-atol-.25px', 0, 0))
        paired.append(dict(case=case, observed=actual, error=error))
    write_json(Path(output) / 'condition-key-paired.json', dict(
        complete_contract=all(row['error'] is None for row in paired), rows=paired))
    return rows
