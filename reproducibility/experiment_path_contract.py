"""Literal supported folder discovery envelopes, not scientific inference."""
from pathlib import Path
import hashlib,json
from PyFLASH import experiment
FIXTURE=Path(__file__).with_name('fixtures')/'experiment_path_reference.json'
BEFORE=Path(__file__).with_name('reference-sources')/'experiment-layout-labels/frozen-before/frozen-before.json'
APIS=('resolve_experiment_paths','resolve_experiment_data_path','is_experiment_folder')

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    if hashlib.sha256(BEFORE.read_bytes()).hexdigest()!=fixture['before_sha256']:
        raise ValueError('Original folder lookup evidence changed.')
    original=json.loads(BEFORE.read_text(encoding='utf-8'))['rows']
    if fixture['rows']!=[row['case'] for row in original]:
        raise ValueError('Frozen folder lookup inputs or literal expected answers changed.')
    if fixture['contract_kind']!='functional-experiment-folder-discovery':
        raise ValueError('Folder discovery does not establish microscopy-processing equivalence.')

def required_keys(api):return {f'experiment-path.{api}.'+case['key'] for case in cases()}

def production(case,output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    for name in case['directories']:(output/name).mkdir(parents=True,exist_ok=True)
    for name,text in case['files'].items():
        path=output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    source=str((output/case['query']).resolve()) if case['query'] is not None else None
    before={str(path.relative_to(output)):hashlib.sha256(path.read_bytes()).hexdigest() for path in output.rglob('*') if path.is_file()}
    lookup=experiment.resolve_experiment_paths(source)
    if lookup is not None:
        lookup={key:str(Path(value).relative_to(output)).replace('\\','/') if key.endswith('_path') else value for key,value in lookup.items()}
    data=experiment.resolve_experiment_data_path(source)
    data=str(Path(data).relative_to(output)).replace('\\','/') if data is not None else None
    valid=experiment.is_experiment_folder(source)
    after={str(path.relative_to(output)):hashlib.sha256(path.read_bytes()).hexdigest() for path in output.rglob('*') if path.is_file()}
    if after!=before:raise ValueError('Folder lookup changed its inputs.')
    return {APIS[0]:lookup,APIS[1]:data,APIS[2]:valid}

def answer(case):
    lookup=case['expected']
    return {APIS[0]:lookup,APIS[1]:lookup['data_path'] if lookup else None,APIS[2]:lookup is not None}

def validate(output):
    from reproducibility.normality_association_validation import comparison
    from PyFLASH._persistence import write_json
    check_identity();output=Path(output);rows=[];paired=[]
    for index,case in enumerate(cases()):
        error=None
        try:
            actual=production(case,output/'folder-lookup-inputs'/str(index))
        except Exception as exception:
            actual={api:None for api in APIS}
            error=type(exception).__name__+': '+str(exception)
        expected=answer(case)
        for api in APIS:
            key=f'experiment-path.{api}.'+case['key']
            rows.append(comparison(key,'original-literal-supported-folder-policy',
                'functional-experiment-folder-discovery',actual[api],expected[api],error is None and actual[api]==expected[api],True,
                'exact-full-envelope-and-paths',0.,0.))
            paired.append({'key':key,'input':case,'production':actual[api],'reference':expected[api],
                           'error':error,'agrees':error is None and actual[api]==expected[api]})
        write_json(output/'experiment-path-paired.json',{'rows':paired})
    return rows
