"""Authenticated whole functional dataframe constructor declarations.

Replay literal client inputs through the real constructors, comparing every
returned field and complete native-pandas tables. No fitted estimator is involved
and this family provides no additional independent statistical vote. Complete
coverage also requires the original identifier, recoding, requested-metadata,
comparison and lifecycle controls; it cannot certify fitted parents or plots.
"""
from copy import deepcopy
import hashlib
import inspect
import json
import os
from pathlib import Path

ARCHIVE=Path(__file__).with_name('reference-sources')/'dataframe-whole-client'/'v6'
MANIFEST_SHA256='9d8951be7d7303c294b079df6c9415f1f934d371803c4d990de7a619693e803a'
ORIGINAL_PROBES=ARCHIVE.parent/'original-probes'/'v1'
ORIGINAL_MANIFEST_SHA256='9296949fe89f0d2e3f90439089a67a2082e73fc5a2518d03b954810364d82335'
TYPED_ORIGINAL_PROBES=ARCHIVE.parent/'typed-original-probes'/'v1'
TYPED_ORIGINAL_MANIFEST_SHA256='392c916a17021daff896871fed59ad039b7699402f903e1c176d6a266eef1a9b'
OPTIONS_ORIGINAL_PROBES=ARCHIVE.parent/'typed-original-probes'/'v2'
OPTIONS_ORIGINAL_MANIFEST_SHA256='58029403c9c300bbb71d3d2165deb9045cb1832cd9e420cce219a912518b1126'
GROUP_ORIGINAL_PROBES=ARCHIVE.parent/'typed-original-probes'/'v3'
GROUP_ORIGINAL_MANIFEST_SHA256='e49d6fc734848cf7a06eee97a3daac410f9ee16d424ed4dc9b47f3a4c1eabe04'
FINAL_ORIGINAL_PROBES=ARCHIVE.parent/'typed-original-probes'/'v4'
FINAL_ORIGINAL_MANIFEST_SHA256='a9ae57e9a3fb639c498240323238efc34f2d2a9ade004a0f4274ec4342dcd7eb'
CAPABILITY_PREFIXES={'PyFLASH.dataframe.'+api:('dataframe-whole.'+api+'.',)
                     for api in ('from_dataframe','coerce_dataframe_input')}
COMPLETE_CAPABILITIES=frozenset(CAPABILITY_PREFIXES)


def check_identity():
    path=ARCHIVE/'source-manifest.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=MANIFEST_SHA256:
        raise ValueError('Constructor client manifest changed')
    for name,digest in json.loads(path.read_text(encoding='utf-8')).items():
        if hashlib.sha256((ARCHIVE/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Constructor client declaration changed: '+name)
    transport=Path(__file__).with_name('dataframe_table_protocol.py')
    if hashlib.sha256(transport.read_bytes()).digest()!=hashlib.sha256((ARCHIVE/'table-transport.py').read_bytes()).digest():
        raise ValueError('Constructor client table transport changed')
    return json.loads((ARCHIVE/'client-reference.json').read_text(encoding='utf-8'))


def cases():
    return check_identity()['rows']


def required_keys(capability):
    """No constructor is complete when any declared functional family is absent."""
    if capability not in COMPLETE_CAPABILITIES:raise KeyError(capability)
    assert_parameter_inventory();check_original_failures()
    api=capability.rsplit('.',1)[-1]
    keys={row['key'] for row in cases() if row['api']==api}
    from reproducibility import dataframe_identifier_contract, dataframe_recoding_contract
    from reproducibility import dataframe_metadata_contract, dataframe_comparison_contract, dataframe_lifecycle_contract
    for owner in (dataframe_identifier_contract,dataframe_recoding_contract,
                  dataframe_metadata_contract,dataframe_comparison_contract):
        keys.update(row['key'] for row in owner.cases() if row['api']==api)
    keys.update(row['key'] for row in dataframe_lifecycle_contract.cases())
    return keys


def check_original_failures():
    path=ORIGINAL_PROBES/'source-manifest.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=ORIGINAL_MANIFEST_SHA256:
        raise ValueError('Original constructor probe manifest changed')
    for name,digest in json.loads(path.read_text(encoding='utf-8')).items():
        if hashlib.sha256((ORIGINAL_PROBES/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Original constructor probe changed: '+name)
    path=TYPED_ORIGINAL_PROBES/'source-manifest.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=TYPED_ORIGINAL_MANIFEST_SHA256:
        raise ValueError('Original typed constructor probe manifest changed')
    for name,digest in json.loads(path.read_text(encoding='utf-8')).items():
        if hashlib.sha256((TYPED_ORIGINAL_PROBES/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Original typed constructor probe changed: '+name)
    path=OPTIONS_ORIGINAL_PROBES/'source-manifest.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=OPTIONS_ORIGINAL_MANIFEST_SHA256:
        raise ValueError('Original constructor option probe manifest changed')
    for name,digest in json.loads(path.read_text(encoding='utf-8')).items():
        if hashlib.sha256((OPTIONS_ORIGINAL_PROBES/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Original constructor option probe changed: '+name)
    path=GROUP_ORIGINAL_PROBES/'source-manifest.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=GROUP_ORIGINAL_MANIFEST_SHA256:
        raise ValueError('Original constructor group probe manifest changed')
    for name,digest in json.loads(path.read_text(encoding='utf-8')).items():
        if hashlib.sha256((GROUP_ORIGINAL_PROBES/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Original constructor group probe changed: '+name)
    path=FINAL_ORIGINAL_PROBES/'source-manifest.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=FINAL_ORIGINAL_MANIFEST_SHA256:
        raise ValueError('Original final constructor probe manifest changed')
    for name,digest in json.loads(path.read_text(encoding='utf-8')).items():
        if hashlib.sha256((FINAL_ORIGINAL_PROBES/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Original final constructor probe changed: '+name)


def assert_parameter_inventory():
    from PyFLASH.dataframe import DataFrameExperiment,coerce_dataframe_input
    fixture=check_identity()
    actual=set(inspect.signature(DataFrameExperiment).parameters)
    if actual!=set(fixture['constructor_parameters']):
        raise ValueError('Unclassified constructor parameters: '+str(actual ^ set(fixture['constructor_parameters'])))
    actual=set(inspect.signature(coerce_dataframe_input).parameters)
    if actual!=set(fixture['coerce_parameters']):
        raise ValueError('Unclassified dataframe adapter parameters: '+str(actual ^ set(fixture['coerce_parameters'])))
    public_fields={name for name,value in vars(DataFrameExperiment).items()
                   if not name.startswith('_') and not callable(value)}
    if public_fields!=set(fixture['public_class_fields']):
        raise ValueError('Unclassified constructor class fields: '+str(public_fields ^ set(fixture['public_class_fields'])))


def expand(value,work):
    if isinstance(value,str):return value.replace('<CASE>',str(work))
    if isinstance(value,list):return [expand(v,work) for v in value]
    if isinstance(value,dict):return {k:expand(v,work) for k,v in value.items()}
    return value


def load_frame(record,work):
    from reproducibility.dataframe_table_protocol import restore
    return restore(expand(deepcopy(record),work))


def pack(value,work):
    import math
    import pandas as pd
    if isinstance(value,pd.DataFrame):
        from reproducibility.dataframe_table_protocol import table
        return pack(table(value),work)
    if isinstance(value,bytes):return {'filesystem_bytes':value.hex()}
    if isinstance(value,Path):return {'path_object':pack(str(value),work)}
    if isinstance(value,str):
        result=value.replace(str(work),'<CASE>')
        return result.replace('\\','/') if result.startswith('<CASE>') else result
    if isinstance(value,float) and math.isnan(value):return {'nonfinite':'nan'}
    if isinstance(value,(list,tuple)):return [pack(v,work) for v in value]
    if isinstance(value,dict):return {str(k):pack(v,work) for k,v in value.items()}
    if isinstance(value,set):return sorted(pack(v,work) for v in value)
    return value


def group_record(value):
    return {key:getattr(value,key) for key in ('name','label','color','factor','style','factor_explanation')}


def snapshot(experiment,work):
    state={key:pack(value,work) for key,value in experiment.__dict__.items()
           if key not in ('condition_list','factorDict','data')}
    state['condition_list']=dict(groups=[group_record(c) for c in experiment.condition_list],
                                 comparisons=experiment.condition_list.comparisons)
    state['factorDict']={key:[group_record(c) for c in values] for key,values in experiment.factorDict.items()}
    state['data']={key:dict(name=value.name,df=pack(value.df,work)) for key,value in experiment.data.items()}
    state['data_layout']=experiment.data_layout
    for key in ('filePath','fig_path','data_path','export_path','image_fig_path','representative_path','legend_path'):
        if isinstance(state[key],str):state[key]=state[key].replace('\\','/')
    return state


def production(row,output):
    import pandas as pd
    from types import SimpleNamespace
    from PyFLASH import dataframe
    from PyFLASH.conditions import condition,conditionList,groupList
    from reproducibility.dataframe_table_protocol import table
    if row.get('passthrough'):
        supplied={'none':None,'integer':17,'mapping':{'client':'recorded'},'list':[1,2],
                  'object':object()}[row['passthrough']]
        return dict(returned_original=dataframe.coerce_dataframe_input(supplied) is supplied,inputs_unchanged=True),None
    token=hashlib.sha256(row['key'].encode()).hexdigest()[:20]
    work=Path(output).resolve()/'constructor-client'/token
    work.mkdir(parents=True,exist_ok=False)
    summary=load_frame(row['summary'],work)
    tracked=[(summary,table(summary))]
    parameters=expand(deepcopy(row['parameters']),work)
    for name,kind in row.get('filesystem_parameters',{}).items():
        parameters[name]=Path(parameters[name]) if kind=='path' else os.fsencode(parameters[name])
    source_values=expand(row.get('source_values',[]),work)
    if 'source_paths' in parameters:
        kind=row.get('source_kind','none')
        parameters['source_paths']=(source_values[0] if kind=='string' else Path(source_values[0]) if kind=='path'
            else os.fsencode(source_values[0]) if kind=='bytes' else tuple(source_values) if kind=='tuple'
            else iter(source_values) if kind=='iterator' else None if kind=='none' else source_values)
    for path in source_values:
        target=Path(path) if os.path.isabs(path) else work/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(b'literal-source-v1\n')
    if row.get('consumed_bytes'):(work/'consumed.csv').write_bytes(row['consumed_bytes'].encode())
    groups=None;supplied_group=None;members=[]
    mode=row.get('condition_input')
    if mode is not None:
        members=[condition(c['label'],c['name'],c['color'],c['factor'],style=c['style']) for c in row['groups']]
        if mode=='existing':groups=conditionList(members,comparisons=row['comparisons'])
        elif mode=='group-list':groups=groupList(members,comparisons=row['comparisons'])
        elif mode=='list':groups=members
        elif mode=='tuple':groups=tuple(members)
        elif mode=='iterator':groups=iter(members)
        elif mode=='invalid-empty-list':groups=[]
        elif mode=='invalid-integer':groups=17
        elif mode in ('invalid-members-text','invalid-members-integer'):
            members=['B','A'] if mode.endswith('text') else [17,29]
            groups=members
        else:raise ValueError('Undeclared group input mode: '+mode)
        supplied_group=groups
        parameters[row.get('condition_argument','conditions')]=groups
        for name in row.get('condition_arguments',[]):parameters[name]=groups
    if 'summaries' in parameters:
        supplied={key:load_frame(value,work) for key,value in row['summaries'].items()}
        parameters['summaries']=supplied
        tracked.extend((value,table(value)) for value in supplied.values())
    if 'data' in parameters:
        supplied={key:load_frame(value,work) for key,value in row['data'].items()}
        tracked.extend((value,table(value)) for value in supplied.values())
        parameters['data']={key:SimpleNamespace(df=value) if row.get('marker_wrapped') else value for key,value in supplied.items()}
    image_inputs={}
    for name in ('images','representative_images'):
        if name in parameters:
            supplied=row[name]
            value=load_frame(supplied,work) if isinstance(supplied,dict) and supplied.get('protocol')==1 else deepcopy(supplied)
            parameters[name]=value;image_inputs[name]=value
            if isinstance(value,pd.DataFrame):tracked.append((value,table(value)))
    if row.get('invalid_summary'):
        summary={'none':None,'integer':17,'mapping':{'Measurement':[1.25]},'list':[[1.25]]}[row['invalid_summary']]
    before={path.relative_to(work).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
            for path in work.rglob('*') if path.is_file()}
    before_directories={path.relative_to(work).as_posix() for path in work.rglob('*') if path.is_dir()}
    cwd=os.getcwd()
    actual,error=None,None
    try:
        os.chdir(work)
        if row['api']=='coerce_dataframe_input':
            names=set(inspect.signature(dataframe.coerce_dataframe_input).parameters)
            converted={'comparisons':'condition_comparisons','comparison_mode':'condition_comparison_mode','control':'condition_control'}
            parameters={converted.get(key,key):value for key,value in parameters.items()}
            explicit={key:value for key,value in parameters.items() if key in names}
            extra={key:value for key,value in parameters.items() if key not in names}
            extra.update(expand(deepcopy(row.get('extra_parameters',{})),work))
            explicit.update(expand(deepcopy(row.get('explicit_overrides',{})),work))
            parameters=dict(explicit,dataframe_kwargs=extra)
            if row.get('invalid_dataframe_kwargs')=='integer':parameters['dataframe_kwargs']=17
        experiment=getattr(dataframe,row['api'])(summary,**parameters)
        actual=dict(state=snapshot(experiment,work),inputs_unchanged=True,paths_unchanged=True,
            supplied_group_identity=mode in ('existing','group-list') and experiment.condition_list is supplied_group,
            supplied_group_members_preserved=mode is not None and all(a is b for a,b in zip(experiment.condition_list,members)),
            images_copied=isinstance(image_inputs.get('images'),pd.DataFrame) and experiment.images is not image_inputs['images'],
            representatives_copied=isinstance(image_inputs.get('representative_images'),pd.DataFrame) and experiment.representative_images is not image_inputs['representative_images'])
    except Exception as exc:
        error=type(exc).__name__+': '+str(exc)
        actual=dict(error_type=type(exc).__name__,inputs_unchanged=True,paths_unchanged=True)
    finally:
        os.chdir(cwd)
    for value,original in tracked:
        assert table(value)==original, 'Supplied table values or metadata changed'
    after={path.relative_to(work).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
           for path in work.rglob('*') if path.is_file()}
    after_directories={path.relative_to(work).as_posix() for path in work.rglob('*') if path.is_dir()}
    actual['paths_unchanged']=before==after and before_directories==after_directories
    return actual,error


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    assert_parameter_inventory()
    check_original_failures()
    records,paired=[],[]
    for row in cases():
        actual,error=None,None
        try:actual,error=production(row,output)
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        answer=row['expected'];agrees=actual==answer
        records.append(comparison(row['key'],'literal-whole-state-client/native-pandas-copied-tables',
            'functional-input-adaptation/no-extra-estimator-vote',actual,answer,agrees,True,
            'every-returned-field/full-table-dtypes-index-attrs/group-path-source-image-metadata/typed-refusals/ownership',0.,0.))
        paired.append(dict(case=row,actual=actual,expected=answer,error=error,agrees=agrees))
    write_json(Path(output)/'dataframe-whole-client-paired.json',dict(rows=paired,
        complete_contract='Whole functional construction additionally requires every key returned by required_keys for the selected API.',
        independent_estimator_votes=0,scope=__doc__))
    return records
