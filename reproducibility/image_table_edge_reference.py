"""Retain extra image-identity predictions before changing production code."""
from pathlib import Path
import hashlib, importlib.util, json, shutil

BASE = Path.home()/'AppData/Local/PyFLASH'
OWNER = BASE / 'image-table-identity-edges-original-20261008-v3'
from reproducibility import image_table_reference as retained_reference
SOURCE = Path(retained_reference.__file__)

def load():
    spec = importlib.util.spec_from_file_location('image_table_original', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_images, original_summary = module.images, module.summary
    def images(case):
        frame = original_images(case)
        if frame is not None and case.get('image_schema') == 'no-experiment':
            frame = frame.drop(columns='Experiment')
        return frame
    def summary(case):
        frame = original_summary(case)
        if case.get('metadata') == 'identity-only':
            frame = frame.drop(columns=['Condition', 'Treatment'])
        return frame
    original_expected = module.expected
    def expected(case):
        frame = images(case)
        if case.get('image_schema') == 'no-experiment' and case['option'] is False:
            return frame[[name for name in module.BASE_COLUMNS if name in frame.columns]].copy()
        return original_expected(case)
    module.images, module.summary, module.expected = images, summary, expected
    return module

def cases(module):
    for case in module.cases():
        if case['image_state'] not in ('cached', 'empty'):
            continue
        yield dict(case, key=case['key'] + '.no-experiment', image_schema='no-experiment')
        if case['profile'] in ('object', 'experiment-key'):
            yield dict(case, key=case['key'] + '.identity-only', metadata='identity-only')

def capture():
    assert not OWNER.exists()
    OWNER.mkdir()
    module = load()
    paths = [Path('PyFLASH/experiment.py'), Path('PyFLASH/batch.py'), SOURCE, Path(__file__)]
    sources = {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    for index,path in enumerate(paths):
        shutil.copyfile(path, OWNER / ('original-' + str(index) + '-' + path.name))
    items = list(cases(module))
    (OWNER / 'inputs.json').write_text(json.dumps(items, indent=2)+'\n')
    (OWNER / 'preflight-amendments.json').write_text(json.dumps(dict(
        initial_launch='v1 failed before module import: root was not on sys.path; use existing check_bootstrap.py',
        preflight='v2 stopped before all production calls: base-only original prediction indexed absent Experiment column',
        amendment='Additional no-experiment base-only prediction selects the declared base-column intersection in canonical order; SQLite metadata lookup and all original 360 predictions unchanged',
        production_changes=False), indent=2)+'\n')
    for case in items:
        json.dumps(module.table(module.expected(case)), allow_nan=False)
    rows = [dict(case=case, **module.production(case, OWNER / 'cases' / case['key'])) for case in items]
    changes = [name for name, sha in sources.items() if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha]
    data = dict(status='finished', actual_calls=len(rows), failed=sum(not r['passed'] for r in rows),
                rows=rows, sources=sources, source_changes=changes,
                scope='Additional whole getter profiles: image identity without experiment column and summaries with identity only. Expected lookup is the retained original SQLite implementation; no source repair applied.')
    (OWNER / 'before.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({key:data[key] for key in ('actual_calls','failed','source_changes')}),flush=True)

if __name__=='__main__': capture()
