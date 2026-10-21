"""Unchanged scripts replay actual UI result families in fresh processes."""
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
import pandas as pd
import pytest
from PyFLASH.ui import jobs, workspace, services
from reproducibility.run import python_command


def drawing_geometry(path):
    """Compare coordinates, transforms and clipping with deterministic SVG IDs."""
    import re
    import xml.etree.ElementTree as ET
    root = ET.parse(path).getroot()
    identities = {element.attrib['id']:f'element-{index}'
                  for index,element in enumerate(root.iter()) if 'id' in element.attrib}
    def normalize(value):
        value = re.sub(r'url\(#([^)]*)\)', lambda match:'url(#'+identities[match[1]]+')', value)
        if value.startswith('#') and value[1:] in identities:
            value = '#'+identities[value[1:]]
        return value
    tags = {'g','defs','clipPath','path','text','tspan','use','line','rect','circle','polygon','ellipse'}
    return [(element.tag, {key:identities[value] if key == 'id' else normalize(value)
                          for key,value in element.attrib.items()}, element.text)
            for element in root.iter() if element.tag.rsplit('}',1)[-1] in tags]


def test_geometry_comparison_preserves_clip_extent_and_transforms(tmp_path):
    first, second = tmp_path/'first.svg', tmp_path/'second.svg'
    svg = '<svg><defs><clipPath id="{id}"><rect x="0" y="0" width="{width}" height="20"/></clipPath></defs><g transform="translate(1,2)"><path d="M 1 2 L 3 4" clip-path="url(#{id})"/></g></svg>'
    first.write_text(svg.format(id='random-one',width=10))
    second.write_text(svg.format(id='random-two',width=10))
    assert drawing_geometry(first) == drawing_geometry(second)
    second.write_text(svg.format(id='random-two',width=11))
    assert drawing_geometry(first) != drawing_geometry(second)


def run_job(tmp_path, monkeypatch, kind, parameters, *, source=None, edits=None):
    monkeypatch.setattr(jobs, '_launch', lambda *args: SimpleNamespace(pid=1, poll=lambda:None))
    source = source or {'kind':'csv', 'path':str(tmp_path / 'subjects.csv')}
    if kind == 'function_value':
        identity = jobs.start_value_action('PyFLASH.stats.bonferroni_correction', parameters,
            name='Correction', dataset_token='one', target_key='result', root=tmp_path / 'jobs')
    elif kind == 'sweep':
        identity = jobs.start_sweep(parameters['action'], {'kwargs':parameters['kwargs']}, parameters['choices'],
            source=source, name='Choices', dataset_token='one', target_key='result', root=tmp_path / 'jobs')
    else:
        identity = jobs.start_operation(kind, source, parameters, name=kind,
            dataset_token='one', target_key='result', representatives=edits, root=tmp_path / 'jobs')
    directory = tmp_path / 'jobs' / identity
    state = jobs.run_request(directory / 'request.json')
    assert state['status'] == 'succeeded', state.get('error')
    receipt = json.loads((directory / 'run.json').read_text())
    assert receipt['code_sha256'] and receipt['dependencies'] and receipt['configuration']
    assert all(workspace.content_hash(row['path']) == row['sha256'] for row in receipt['outputs'])
    cwd = tmp_path / 'fresh'
    cwd.mkdir()
    child = subprocess.run(python_command()+[str(directory / 'equivalent.py')], cwd=cwd,
        capture_output=True, text=True, encoding='utf-8', timeout=90)
    (directory / 'fresh-process.log').write_text(child.stdout+child.stderr, encoding='utf-8')
    assert child.returncode == 0, child.stderr
    return workspace.read_operation_state(directory / 'result.json'), workspace.read_operation_state(
        cwd / 'replayed-output' / 'result.json', project_root=cwd), receipt


@pytest.mark.parametrize('kind', ['csv', 'function_value', 'function', 'save', 'save_over_opened', 'workbooks', 'figure', 'styled_figure', 'figure_spec', 'sweep'])
def test_actual_result_family_replays_every_table_and_value(tmp_path, monkeypatch, kind):
    shutil.copyfile(workspace.DEMO_PATH, tmp_path / 'subjects.csv')
    parameters, source, edits = {}, None, None
    if kind == 'csv':
        parameters = {'region':'SCN'}
    elif kind == 'function_value':
        parameters = {'p_value':.01, 'n_tests':3}
    elif kind == 'function':
        parameters = {'function_key':'PyFLASH.export.format_summary_for_display', 'kwargs':{}, 'region':'SCN'}
    elif kind in {'save', 'save_over_opened'}:
        filename = tmp_path / 'accepted-analysis.pkl'
        parameters = {'filename':str(filename)}
        selections = pd.DataFrame({'AnimalName':['A01'], 'Representative':[True], 'Score':[1.2345678901234567]})
        edits = workspace.selection_snapshot(selections)
        if kind == 'save_over_opened':
            services.save_batch(workspace.load_table(tmp_path / 'subjects.csv'), str(filename))
            source = {'kind':'pickle', 'path':str(filename), 'version':workspace.source_version(filename)}
            kind = 'save'
    elif kind in {'figure','styled_figure','figure_spec'}:
        recipe = {'data_cols':['Signal_MeanIntensity'], 'stats_test':'welch', 'save_normality':False}
        if kind in {'figure','styled_figure'}:
            parameters = {'plot_type':'mean_bars', 'kwargs':recipe}
            if kind == 'styled_figure':
                kind = 'figure'
                parameters['style'] = {'presentation':{'ylim':[-1,12],'legend':'hide',
                    'font_family':'DejaVu Sans','font_size':18,'series_color':'navy','line_width':3}}
        else:
            specification = tmp_path / 'recipe.json'
            specification.write_text(json.dumps({'plots':[{'type':'mean_bars', **recipe}]}))
            parameters = {'spec_path':str(specification)}
    elif kind == 'sweep':
        parameters = {'action':'mean_bars', 'kwargs':{'data_cols':['Signal_MeanIntensity'], 'save_normality':False},
                      'choices':{'stats_test':['welch','student_t']}}
        # Admission is injected in run_job; execution is the real queue/plot.
    else:
        from test_unregistered_summary_export import _minimal_batch
        batch = _minimal_batch(tmp_path)
        filename = tmp_path / 'workbook-input.pkl'
        services.save_batch(batch, str(filename))
        source = {'kind':'pickle', 'path':str(filename)}
        parameters = {'save_path':str(tmp_path / 'accepted-workbooks'),
                      'if_summary':True, 'if_extended':False, 'behaviour':False}
    original, fresh, receipt = run_job(tmp_path, monkeypatch, kind, parameters, source=source, edits=edits)
    if kind == 'csv':
        assert Path(original['path']).read_bytes() == Path(fresh['path']).read_bytes()
    elif kind in {'function', 'function_value'}:
        assert original['value'] == fresh['value']
        for first, second in zip(original['tables'],fresh['tables'],strict=True):
            assert Path(first['path']).read_bytes() == Path(second['path']).read_bytes()
            assert str(Path(first['path']).resolve()) in {row['path'] for row in receipt['outputs']}
    elif kind == 'save':
        first, second = services.open_pickle(original['path']), services.open_pickle(fresh['path'])
        pd.testing.assert_frame_equal(first.summary, second.summary, check_exact=True)
        pd.testing.assert_frame_equal(first.representative_images, second.representative_images, check_exact=True)
        assert Path(fresh['path']).parent.name == 'replayed-output'
        if source and source['kind'] == 'pickle':
            assert Path(receipt['request']['source']['path']).name == 'opened-analysis.pkl'
            assert receipt['source']['sha256'] != workspace.content_hash(original['path'])
    elif kind == 'workbooks':
        assert original['paths'] and fresh['paths']
        for first, second in zip(original['paths'], fresh['paths'], strict=True):
            if first.endswith('.xlsx'):
                before, after = pd.read_excel(first, sheet_name=None), pd.read_excel(second, sheet_name=None)
                assert before.keys() == after.keys()
                for name in before:
                    pd.testing.assert_frame_equal(before[name], after[name], check_exact=True)
            else:
                assert Path(first).read_bytes() == Path(second).read_bytes()
    else:
        first_cells = original.get('cells', [original])
        second_cells = fresh.get('cells', [fresh])
        for before, after in zip(first_cells,second_cells,strict=True):
            assert before['paths'] and after['paths']
            for first, second in zip(before['paths'],after['paths'],strict=True):
                assert drawing_geometry(first) == drawing_geometry(second)
            for first,second in zip(before.get('tables',[]),after.get('tables',[]),strict=True):
                pd.testing.assert_frame_equal(pd.read_csv(first['path']),pd.read_csv(second['path']),check_exact=True)


def test_existing_destination_is_not_hashed_as_an_input(tmp_path):
    target = tmp_path / 'already-there.pkl'
    target.write_bytes(b'previous output')
    assert workspace.parameter_inputs({'filename':str(target)}, action='PyFLASH.ui.services.save_batch') == []


def test_changed_input_rejects_replay_before_output_is_created(tmp_path):
    from PyFLASH.ui import operation_receipts
    source = tmp_path / 'data.csv'
    source.write_text('first')
    request = {'kind':'csv', 'source':{'kind':'csv','path':str(source)}, 'parameters':{}}
    records = operation_receipts.inputs(request)
    source.write_text('changed')
    output = tmp_path / 'must-stay-absent'
    with pytest.raises(ValueError, match='Input content changed'):
        jobs.replay_request(request, output, input_records=records)
    assert not output.exists()


def test_raw_microscopy_processing_replays_complete_measurements(tmp_path, monkeypatch):
    from test_experiment_new_imagej_layout import _make_new_export
    from PyFLASH.ui.project_io import Project
    import numpy as np
    from PIL import Image
    root = tmp_path / 'raw-FLASH'
    _make_new_export(str(root))
    # Valid, explicitly synthetic pixels; no biological image is fabricated.
    pixels = root / 'Results/Presentation Images/Images/A1/GFAP_LH_SCN.png'
    Image.fromarray(np.arange(64,dtype=np.uint8).reshape(8,8)).save(pixels)
    project = Project(name='Raw fixture', batch_path=str(tmp_path / 'processed'),
        experiments={'one':str(root)}, import_images=True,
        conditions={'factor':'Group','entries':[{'label':'A','short':'A','color':'blue'}]}).to_dict()
    monkeypatch.setattr(jobs, '_launch', lambda *args:SimpleNamespace(pid=1,poll=lambda:None))
    identity = jobs.start_processing(project, root=tmp_path / 'jobs')
    directory = tmp_path / 'jobs' / identity
    state = jobs.run_request(directory / 'request.json')
    assert state['status'] == 'succeeded', state.get('error')
    before = services.open_pickle(state['result_path'])
    receipt = json.loads((directory / 'run.json').read_text())
    assert len([row for row in receipt['parameter_inputs'] if row['parameter'] == 'raw_table']) == 4
    assert all(workspace.content_hash(row['path']) == row['sha256'] for row in receipt['outputs'])
    fresh = tmp_path / 'fresh'
    fresh.mkdir()
    child = subprocess.run(python_command()+[str(directory / 'equivalent.py')],cwd=fresh,
                           capture_output=True,text=True,encoding='utf-8',timeout=90)
    (directory / 'fresh-process.log').write_text(child.stdout+child.stderr,encoding='utf-8')
    assert child.returncode == 0, child.stderr
    result = workspace.read_operation_state(fresh / 'replayed-output/result.json', project_root=fresh)
    after = services.open_pickle(result['result_path'])
    assert before.summaries.keys() == after.summaries.keys()
    for region in before.summaries:
        pd.testing.assert_frame_equal(before.summaries[region],after.summaries[region],check_exact=True)
    assert before.markers == after.markers
    first_images = before.getImageTable(include_summary=False)
    second_images = after.getImageTable(include_summary=False)
    assert len(first_images) == len(second_images) == 1
    pd.testing.assert_frame_equal(first_images, second_images, check_exact=True)
    assert Path(after.filePath).is_relative_to(fresh)
