"""Failed jobs and failed cells keep immutable, reproducible diagnostic evidence."""
import json
from pathlib import Path
import uuid
import numpy as np
from PIL import Image
from PyFLASH import actions,image_io,queue
from PyFLASH.ui import jobs,workspace

ACTION = 'PyFLASH.stats.bonferroni_correction'


def test_failed_worker_keeps_inputs_configuration_versions_and_script(tmp_path,monkeypatch):
    image = tmp_path/'pixels.png'
    Image.fromarray(np.full((8,8),7,dtype=np.uint8)).save(image)
    def failed(*args,**kwargs):
        image_io.read_image_array(image,backend='pil')
        raise ValueError('controlled analysis failure')
    monkeypatch.setattr(actions,'call_action',failed)
    directory = tmp_path/'worker'
    directory.mkdir()
    identity = uuid.uuid4().hex
    request = {'schema_version':1,'id':identity,'name':'Fixture','kind':'function_value',
               'action':ACTION,'parameters':{'p_value':.01,'n_tests':3}}
    workspace.write_json(directory/'request.json',request)
    workspace.write_json(directory/'state.json',{'schema_version':1,'id':identity,
        'kind':'function_value','name':'Fixture','status':'queued'})
    state = jobs.run_request(directory/'request.json')
    assert state['status']=='failed' and state['error']=='controlled analysis failure'
    receipt = json.loads((directory/'run.json').read_text(encoding='utf-8'))
    assert receipt['status']=='failed' and receipt['error']==state['error']
    assert receipt['parameters']==request['parameters']
    assert receipt['configuration'] and receipt['code_sha256'] and receipt['dependencies'] and receipt['python']
    assert 'commit' in receipt
    assert receipt['parameter_inputs']==[{'parameter':'image_pixels','path':str(image.resolve()),'sha256':workspace.content_hash(image)}]
    assert 'replay_request' in (directory/'equivalent.py').read_text(encoding='utf-8')
    assert all(workspace.content_hash(row['path'])==row['sha256'] for row in receipt['outputs'])


def test_retry_keeps_failed_cell_pixels_error_and_partial_outputs(tmp_path,monkeypatch):
    image = tmp_path/'pixels.png'
    Image.fromarray(np.full((8,8),7,dtype=np.uint8)).save(image)
    def failed(*args,**kwargs):
        image_io.read_image_array(image,backend='pil')
        raise ValueError('controlled cell failure')
    original = actions.call_action
    monkeypatch.setattr(actions,'call_action',failed)
    first = queue.run_action_grid(None,ACTION,{'p_value':.01},{'n_tests':[3]},tmp_path/'progress.json')
    failure = first['failures'][0]
    mutable = Path(failure['receipt'])
    record = json.loads(mutable.read_text(encoding='utf-8'))
    attempt = mutable.parent/record['attempts'][0]['receipt']
    digest = workspace.content_hash(attempt)
    evidence = json.loads(attempt.read_text(encoding='utf-8'))
    assert evidence['status']=='failed' and 'controlled cell failure' in evidence['error']
    assert evidence['input_files'][0]['sha256']==workspace.content_hash(image)
    assert evidence['identity']['configuration'] and evidence['identity']['code']
    monkeypatch.setattr(actions,'call_action',original)
    resumed = queue.run_action_grid(None,ACTION,{'p_value':.01},{'n_tests':[3]},tmp_path/'progress.json')
    assert not resumed['failures'] and resumed['results'][0]['result']==.03
    assert workspace.content_hash(attempt)==digest
    final = json.loads(Path(resumed['results'][0]['receipt']).read_text(encoding='utf-8'))
    assert [row['status'] for row in final['attempts']]==['failed','done']
    assert final['attempts'][0]['error']==evidence['error']
