"""Full coupled literal workbook inputs, metadata, measurements and reports.

The independent client declaration precedes candidate execution. Native
openpyxl writes explicit-string reference books and reads actual XlsxWriter
exports. No microscopy processing, fitting or extra estimator vote is claimed.
"""
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path

from reproducibility import excel_workbook_schema_contract as schema
from reproducibility import excel_literal_cell_contract as literal
from reproducibility import dataframe_table_protocol as table_protocol

ARCHIVE=Path(__file__).with_name('reference-sources')/'excel-coupled-client/v2'
MANIFEST_SHA256='81c9c3f31a392b72475062b1342d9e774c24587f89b02e7c2bab9acb1e07771e'
COMPLETE_CAPABILITIES=frozenset()
CAPABILITY_PREFIXES={capability:('excel-coupled.'+capability.rsplit('.',1)[-1]+'.',)
                     for capability in literal.CAPABILITY_PREFIXES}


def check_identity():
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(ARCHIVE/'source-manifest.json')!=MANIFEST_SHA256:
        raise ValueError('Original coupled Excel client manifest changed')
    for name,digest in json.loads((ARCHIVE/'source-manifest.json').read_text(encoding='utf-8')).items():
        if sha(ARCHIVE/name)!=digest:
            raise ValueError('Original coupled Excel client evidence changed: '+name)
    return json.loads((ARCHIVE/'client-reference.json').read_text(encoding='utf-8'))


def cases():
    rows=check_identity()['rows']
    for row in rows:
        row['_case_digest']=hashlib.sha256(json.dumps(row,sort_keys=True,allow_nan=False).encode('utf-8')).hexdigest()
    return rows


def check_parameter_inventory(fixture=None):
    from PyFLASH.batch import Batch
    fixture=check_identity() if fixture is None else fixture
    actual={}
    required={'required':True}
    for name in fixture['parameter_inventory']:
        signature=inspect.signature(getattr(Batch,name))
        values=[parameter for parameter in signature.parameters.values() if parameter.name!='self']
        positional=[parameter for parameter in values if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY,inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        keyword=[parameter for parameter in values if parameter.kind is inspect.Parameter.KEYWORD_ONLY]
        actual[name]=dict(positional=[parameter.name for parameter in positional],
            keyword_only=[parameter.name for parameter in keyword],
            vararg=next((parameter.name for parameter in values if parameter.kind is inspect.Parameter.VAR_POSITIONAL),None),
            kwarg=next((parameter.name for parameter in values if parameter.kind is inspect.Parameter.VAR_KEYWORD),None),
            positional_defaults=[parameter.default for parameter in positional if parameter.default is not inspect.Parameter.empty],
            keyword_defaults=[required if parameter.default is inspect.Parameter.empty else parameter.default for parameter in keyword])
    if actual!=fixture['parameter_inventory']:
        raise ValueError('Public Excel parameter/default inventory needs a new declared client contract')
    return actual


def frame(packet):
    import pandas as pd
    result=pd.DataFrame(packet['rows'],columns=packet['columns'],index=packet['index'])
    result.attrs=deepcopy(packet['attrs'])
    result.index.name='source row'
    return result


def group_state(value):
    if isinstance(value,(list,tuple)):return [group_state(item) for item in value]
    if isinstance(value,dict):return {key:group_state(item) for key,item in value.items()}
    if hasattr(value,'__dict__'):return dict(type=type(value).__name__,fields=group_state(vars(value)))
    return value


def literal_batch(folder,row):
    from types import SimpleNamespace
    from PyFLASH.batch import Batch
    from PyFLASH.conditions import condition,multiCondition,conditionList
    from PyFLASH.markers import Antibody
    design=row['design'];pool={};groups=[]
    for specification in design['groups']:
        components=[]
        for part in specification['components']:
            identity=(part['factor'],part['name'])
            if identity not in pool:
                pool[identity]=condition(part['label'],part['name'],part['color'],part['factor'],
                    explanation=part['explanation'],style=part['style'])
            components.append(pool[identity])
        groups.append(components[0] if len(components)==1 else multiCondition(components))
    owner=conditionList(groups)
    assert [group.name for group in owner]==design['group_names']
    experiments=[]
    for exp_idx,specification in enumerate(design['experiments'],1):
        source=folder/f'source-{exp_idx}';source.mkdir()
        tables={}
        for marker,packet in specification['raw_tables'].items():
            obj=object.__new__(Antibody);obj.name=marker;obj.df=frame(packet);tables[marker]=obj
        for analysis,macros in specification['macros'].items():
            directory=source/('Objects' if analysis=='Object' else 'ROI Intensities')/'Analysis Details'
            directory.mkdir(parents=True)
            (directory/'IBA1.txt').write_text('<Filter Macro>\n'+macros['filter']+'\n</Filter Macro>\n'
                '<Analysis Macro>\n'+macros['analysis']+'\n</Analysis Macro>\n',encoding='utf-8')
        experiments.append(SimpleNamespace(data=tables,summary=frame(specification['summary']),filePath=str(source)))
    batch=object.__new__(Batch)
    batch.name='literal coupled export';batch.condition_list=owner;batch.conditions=owner.conditions
    batch.factor=owner.factor;batch.factorDict=owner.factorDict
    batch.summaries={roi:frame(packet) for roi,packet in design['summaries'].items()}
    batch.summary=batch.summaries['SCN'];batch.experiment_list=experiments
    batch.data={**experiments[0].data,'Behaviour':SimpleNamespace(df=frame(design['behavior']))}
    batch.export_path=str(folder/'default');batch.filePath=str(folder/'batch-source')
    return batch


def observe(row,output,*,native_reference_root=None,call_options=None,owner_setup=None):
    digest=hashlib.sha256(json.dumps({key:value for key,value in row.items() if key!='_case_digest'},sort_keys=True,allow_nan=False).encode('utf-8')).hexdigest()
    assert digest==row['_case_digest'],'Declared coupled input/request/answer was changed'
    folder=(Path(output)/('coupled-'+hashlib.sha256(row['key'].encode('utf-8')).hexdigest()[:20])).resolve()
    folder.mkdir(parents=True,exist_ok=False)
    if native_reference_root is None:
        natives=literal.native_literal_reference(row,folder)
    else:
        native_folder=Path(native_reference_root)/folder.name
        natives=[]
        for i,expected in enumerate(row['expected_workbooks']):
            path=native_folder/f'native-literal-reference-{i}.xlsx'
            before_hash=hashlib.sha256(path.read_bytes()).hexdigest()
            actual=schema.read_workbook(path)
            assert [dict(name=sheet['name'],cells=sheet['cells'],merged_ranges=sheet['merged_ranges']) for sheet in actual]==expected['worksheets']
            assert not any(sheet['formula_cells'] for sheet in actual)
            assert hashlib.sha256(path.read_bytes()).hexdigest()==before_hash
            natives.append(dict(path=str(path),sha256=before_hash,reused=True))
    batch=literal_batch(folder,row)
    if owner_setup is not None:
        owner_setup(batch, row)
    supplied_summaries = getattr(batch, 'summaries', None) or {}
    frames=[batch.summary,*supplied_summaries.values(),batch.data['Behaviour'].df,
            *[experiment.summary for experiment in batch.experiment_list],
            *[obj.df for experiment in batch.experiment_list for obj in experiment.data.values()]]
    before=[table_protocol.table(value) for value in frames]
    groups=group_state(batch.condition_list.condition_list)
    identities=[id(group) for group in batch.condition_list]
    sources={path.relative_to(folder).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
             for path in folder.glob('source-*/**/*.txt')}
    outputs=[];error=None
    try:
        outputs=getattr(batch,row['method'])(save_path=folder/'absolute',
            **(row['options'] if call_options is None else call_options))
    except Exception as exc:error=type(exc).__name__+': '+str(exc)
    assert before==[table_protocol.table(value) for value in frames],'Caller table or complete metadata changed'
    assert groups==group_state(batch.condition_list.condition_list)
    assert identities==[id(group) for group in batch.condition_list]
    assert sources=={path.relative_to(folder).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in folder.glob('source-*/**/*.txt')}
    workbooks=[]
    for expected in row['expected_workbooks']:
        item=expected['request'];path=folder/item['directory']/(item['name']+'.xlsx')
        if path.is_file():
            sidecar=path.with_name(item['name']+'_RegexFilters.txt')
            workbooks.append(dict(request=item,worksheets=schema.read_workbook(path),
                regex_report=sidecar.read_text(encoding='utf-8') if sidecar.exists() else None))
    actual_paths=[str(Path(path).resolve()) for path in outputs or []]
    expected_paths=[str(folder/item['request']['directory']/(item['request']['name']+ending))
                    for item in row['expected_workbooks'] for ending in ('.xlsx','_RegexFilters.txt')]
    observed=dict(error=error,outputs=actual_paths,workbooks=workbooks,inputs_unchanged=True,
        source_macros_unchanged=True,native_literal_references=natives,input_tables=before,groups=groups)
    observed['disagreements']=schema.evaluate(row,observed)
    if error!=row['expected_error']:observed['disagreements'].append('unexpected execution error')
    if actual_paths!=expected_paths:observed['disagreements'].append('output paths/order')
    return observed


def required_keys(capability):
    method=capability.rsplit('.',1)[-1]
    return {row['key'] for row in cases() if row['method']==method}


def validate(output,*,native_reference_root=None):
    import traceback
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    # Authenticate once within this audit; source identity is re-read at the
    # end by the owning workflow. Never retain a cross-audit fixture cache.
    fixture=check_identity();check_parameter_inventory(fixture)
    declared=cases();paired=[];comparisons=[]
    for row in declared:
        observed,error=None,None
        try:observed=observe(row,output,native_reference_root=native_reference_root)
        except Exception:error=traceback.format_exc()
        agrees=error is None and not observed['disagreements']
        comparisons.append(comparison(row['key'],'predeclared-coupled-client/native-openpyxl-literal-writer-and-reader',
            'functional-coupled-workbook-report-and-provenance-transport/no-extra-estimator-vote',
            {'all_coupled_outputs_match':agrees},{'all_coupled_outputs_match':True},agrees,True,
            'exact-all-sheets-cells-missingness-merged-ranges-reports-source-macros-and-unchanged-inputs',0.,0.))
        paired.append(dict(case=row,observed=observed,error=error,agrees=agrees))
    write_json(Path(output)/'excel-coupled-paired.json',dict(schema_version=1,complete_contract=False,scope=__doc__,rows=paired))
    return comparisons
