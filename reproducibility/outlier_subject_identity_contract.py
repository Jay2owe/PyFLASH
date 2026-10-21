"""Subject identity and whole-animal exclusion controls; complete parents remain open."""
import json
import math
from pathlib import Path

ARCHIVE=Path(__file__).with_name('reference-sources')/'outlier-requests/whole-v1'
MANIFEST_SHA256='46652de5ab1734505881120585f12f92bb4ca081db7b88ab923430edb8f11d22'
CAPABILITY_PREFIXES={
    'PyFLASH.exclusions.'+api:('outlier-parent-identity.'+api+'.',)
    for api in ('mark_outliers','exclude_outliers')}
COMPLETE_CAPABILITIES=frozenset()


def cases():
    from reproducibility.compact_evidence import entries
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
    from reproducibility.compact_evidence import digest
    for name,sha in json.loads((ARCHIVE/'declaration.json').read_text())['dependencies'].items():
        if digest(Path(__file__).resolve().parents[1]/name)!=sha:
            raise ValueError('Independent outlier mathematics changed: '+name)
    return list(entries(ARCHIVE/'cases.jsonl.gz'))


def production(row, output):
    from copy import deepcopy
    from types import SimpleNamespace
    import pandas as pd
    from PyFLASH import exclusions
    input_path=(Path(__file__).resolve().parents[1]/row['input_fixture']
                if row.get('input_fixture') else ARCHIVE/'input-definitions.json')
    source=json.loads(input_path.read_text())
    labels=source['indices'][row['index']]
    index=pd.MultiIndex.from_tuples(list(map(tuple,labels))) if row['index']=='multilevel' else labels
    frame=pd.DataFrame(source['rows'],columns=source['columns'],index=index)
    frame.attrs=deepcopy(source['attrs'])
    other=frame.copy(deep=True);other['X']=other['X']+1000
    for source_frame in (frame,other):
        if row.get('form')=='strings':
            for column in ('X','Y','Z'):source_frame[column]=source_frame[column].astype(str)
        elif row.get('form')=='missing':
            source_frame.loc[source_frame['AnimalName']=='S5','X']=float('nan')
    original=frame.copy(deep=True);original_other=other.copy(deep=True)
    raw=object()
    exp=SimpleNamespace(summary=frame,summaries={'SCN':frame,'OC':other},data=raw,
        name='Literal identity controls',condition_list=[],data_path=str(output),fig_path=str(output/'figures'))
    owner=row.get('owner','mapped')
    if row.get('inspect_options'):
        exp.condition_list=[SimpleNamespace(name=name) for name in dict.fromkeys(frame['Condition'])]
    if owner=='legacy':
        del exp.summaries
    elif owner in ('Experiment','MiniExperiment','Batch'):
        from PyFLASH.experiment import Experiment,MiniExperiment
        from PyFLASH.batch import Batch
        kind={'Experiment':Experiment,'MiniExperiment':MiniExperiment,'Batch':Batch}[owner]
        actual=kind.__new__(kind);actual.__dict__.update(exp.__dict__)
        actual.filePath=str(output);actual.images=None
        exp=actual;exp.data={}
    elif owner=='DataFrameExperiment':
        from PyFLASH import from_dataframe
        exp=from_dataframe(frame,summaries={'SCN':frame,'OC':other},data_path=str(output),fig_path=str(output/'figures'))
    def tables(value):
        return value.summaries if isinstance(getattr(value,'summaries',None),dict) else {'SCN':value.summary}
    if owner!='mapped' and owner!='legacy':
        exp.data['probe']=SimpleNamespace(experiment=exp,df=frame.copy(deep=True))
    raw=exp.data
    raw_refs=[(item,getattr(item,'experiment')) for item in raw.values() if hasattr(item,'experiment')] if isinstance(raw,dict) else []
    owner_tables={key:value.copy(deep=True) for key,value in tables(exp).items()}
    paths={key:getattr(exp,key,None) for key in ('filePath','data_path','fig_path')}
    flags=pd.DataFrame([dict(AnimalName='S5',column=name,group='All',value=value,
        iqr_outlier=row['method']=='iqr',mad_outlier=row['method']=='mad',rout_outlier=row['method']=='rout')
        for name,value in [('X',100.),('Y',200.)]])
    roi=row.get('roi','SCN')
    if row.get('flag_values')=='matching':
        target=tables(exp)[roi]
        flags['value']=[float(target.iloc[5][name]) if pd.notna(target.iloc[5][name]) else None
                        for name in flags['column']]
    elif row.get('flag_values')=='stale':flags['value']=1234.
    elif row.get('flag_values')=='omitted':flags=flags.drop(columns=['value'])
    elif row.get('flag_values')=='null':flags['value']=None
    if row.get('duplicate'):flags=pd.concat([flags,flags],ignore_index=True)
    original_flags=flags.copy(deep=True)
    def clean(value):
        if hasattr(value,'tolist'):return clean(value.tolist())
        if isinstance(value,float) and not math.isfinite(value):return None
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [clean(v) for v in value]
        return value
    def pack(table):
        return clean(dict(columns=list(table.columns),index=[list(v) if isinstance(v,tuple) else v for v in table.index],
                    rows=table.astype(object).values.tolist(),attrs=table.attrs))
    try:
        options=deepcopy(row.get('call_options',{}))
        for key,form in row.get('parameter_forms',{}).items():
            if form=='tuple':options[key]=tuple(options[key])
            elif form=='iterator':options[key]=iter(options[key])
            elif form=='nan':options[key]=float('nan')
            elif form=='array':
                import numpy as np
                options[key]=np.asarray(options[key])
        checked_options={key:clean(value) for key,value in options.items()
                         if row.get('parameter_forms',{}).get(key)!='iterator'}
        kwargs={} if row.get('public_defaults') else dict(methods=(row['method'],),scope=row['scope'],roi=roi,
            filtered_columns=['X','Y'] if row['subset'] else None,
            outliers=flags if row['supplied'] else None,animal_min_flags=2,save=False,verbose=False)
        kwargs.update(options)
        result=getattr(exclusions,row['api'])(exp,**kwargs)
        pd.testing.assert_frame_equal(frame,original,check_exact=True)
        pd.testing.assert_frame_equal(other,original_other,check_exact=True)
        pd.testing.assert_frame_equal(flags,original_flags,check_exact=True)
        for key,value in owner_tables.items():pd.testing.assert_frame_equal(tables(exp)[key],value,check_exact=True)
        untouched='OC' if roi=='SCN' else 'SCN'
        if untouched in owner_tables:pd.testing.assert_frame_equal(tables(result)[untouched],owner_tables[untouched],check_exact=True)
        answer=dict(error_type=None,original_unchanged=True,flags_unchanged=True,
            raw_shared=result.data is raw,non_target_unchanged=True,
            summary_detached=tables(result)[roi] is not tables(exp)[roi],
            summary_alias_consistent=result.summary is tables(result)['SCN'],
            summary=pack(tables(result)[roi]),ledger=pack(result.exclusions),metadata=result.exclusion_summary,
            saved_files=sorted(p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()))
        if row.get('inspect_options'):
            import csv
            answer.update(saved_csv={name:list(csv.reader((output/name).open(newline='',encoding='utf-8')))
                                     for name in answer['saved_files']},
                request_unchanged=checked_options=={key:clean(value) for key,value in options.items()
                    if row.get('parameter_forms',{}).get(key)!='iterator'},
                raw_backrefs_unchanged=all(getattr(item,'experiment') is old for item,old in raw_refs),
                paths_preserved=all(getattr(exp,key,None)==value and getattr(result,key,None)==value for key,value in paths.items()),
                owner_class_preserved=type(result) is type(exp))
        return answer
    except Exception as error:
        return dict(error_type=type(error).__name__,error=str(error))


def validate(output):
    import gzip
    import runpy
    from reproducibility.normality_association_validation import comparison
    reference=runpy.run_path(str(ARCHIVE/'reference-producer.py'))['expected']
    rows=[]
    with gzip.open(output/'outlier-subject-identity-paired.jsonl.gz','xt',encoding='utf-8') as stream:
        for case in cases():
            actual=production(case,output/'cases'/case['key'])
            answer=reference(case)
            unchanged=answer==case['expected']
            agrees=unchanged and actual==answer
            rows.append(comparison(case['key'],'literal-subject-identity/accepted-independent-detector-flags',
                'functional-subject-and-whole-animal-controls/not-whole-parent-approval',
                actual,answer,agrees,unchanged,'all-summary-ledger-metadata-and-ownership-fields',0.,0.))
            stream.write(json.dumps(dict(key=case['key'],actual=actual,expected=answer,agrees=agrees),sort_keys=True)+'\n')
    return rows
