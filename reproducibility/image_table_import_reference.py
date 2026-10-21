"""Whole getter lifecycle using real authored directory indexing, no pixels."""
from pathlib import Path
import contextlib, copy, hashlib, io, json, shutil
from itertools import product
import pandas as pd
from reproducibility.whole_condition_reference import table

BASE=Path.home()/'AppData/Local/PyFLASH'
OWNER=BASE/'image-table-real-import-original-20261008-v2'
LOCATIONS=('Images','Results/Presentation Images/Images','Results/Analysis Images/Segmentation')

def cases():
    for owner,location,option,state,metadata in product(('Experiment','MiniExperiment','Batch'),LOCATIONS,
            (False,True,'default'),('missing','invalid'),('plain','indexed')):
        yield dict(key='.'.join(map(str,(owner,LOCATIONS.index(location),option,state,metadata))),
                   owner=owner,location=location,option=option,state=state,metadata=metadata)

def normalize(value,root):
    if isinstance(value,str): return value.replace(str(root),'$CASE')
    if isinstance(value,list): return [normalize(v,root) for v in value]
    if isinstance(value,dict): return {k:normalize(v,root) for k,v in value.items()}
    return value

def prepare(case,root):
    from PyFLASH.experiment import Experiment,MiniExperiment
    from PyFLASH.batch import Batch
    def experiment(name,condition):
        obj=object.__new__(MiniExperiment if case['owner']=='MiniExperiment' else Experiment)
        obj.name=name; obj.data={};obj.markers={'M'};obj.factor=['Treatment']
        obj.source_root=str(root/name);obj.filePath=str(root/name/'Data Analysis')
        frame=pd.DataFrame({'AnimalName':['A1'],'Condition':[condition],'Treatment':['T'+condition]})
        frame.attrs={'acquired':{'name':name}}
        obj.summaries={'SCN':frame.set_index('AnimalName') if case['metadata']=='indexed' else frame}
        obj.imagesDict={'old':{'caller':['retained-before-import']}}
        if case['state']=='invalid':obj.images=['not a table']
        folder=root/name/case['location']/'A1'
        folder.mkdir(parents=True)
        for filename in ('M_RHSCN1.PNG','M_LHSCN1.png'):
            (folder/filename).write_bytes(b'Authored indexing fixture; pixel decoding is outside this contract.\n')
        (folder/'ignored.txt').write_text('not an image extension\n')
        (root/name/case['location']/'root-level.png').write_bytes(b'not in an animal folder\n')
        expected=pd.DataFrame([{'AnimalName':'A1','Marker':'M','ROI':roi,'ImageName':'M_'+roi,
             'ImagePath':str(folder/filename),'Extension':'.png','Condition':condition,'Treatment':'T'+condition}
             for roi,filename in (('LHSCN1','M_LHSCN1.png'),('RHSCN1','M_RHSCN1.PNG'))])
        return obj,expected
    first,expected=experiment('E1','G1')
    if case['owner']!='Batch': return first,expected,[first]
    second,other=experiment('E2','G2')
    obj=object.__new__(Batch);obj.name='Batch';obj.data={};obj.factor=['Treatment'];obj.markers={'M'}
    obj.experiment_list=[first,second];obj.imagesDict={'old':{'caller':['retained-before-import']}}
    obj.summaries={'SCN':pd.DataFrame({'Experiment':['E1','E2'],'AnimalName':['A1','A1'],
                  'Condition':['G1','G2'],'Treatment':['TG1','TG2']})}
    if case['metadata']=='indexed':obj.summaries['SCN']=obj.summaries['SCN'].set_index('AnimalName')
    if case['state']=='invalid':obj.images=['not a table']
    expected['Experiment']='E1';other['Experiment']='E2'
    # Literal declared table order after refreshing Condition and Treatment.
    full=pd.concat([expected,other],ignore_index=True)
    full=full[['AnimalName','Marker','ROI','ImageName','ImagePath','Extension','Experiment','Condition','Treatment']]
    return obj,full,[first,second]

def production(case,root):
    obj,expected,children=prepare(case,root)
    summaries=[(child,copy.deepcopy(child.summaries)) for child in children]
    parent=copy.deepcopy(obj.summaries)
    target=expected.copy()
    if case['option'] is False:
        target=target[[c for c in ('Experiment','AnimalName','Marker','ROI','ImageName','ImagePath','Extension') if c in target]]
    predicted=normalize(dict(returned=table(target),stored=table(expected)),root)
    result=None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result=obj.getImageTable() if case['option']=='default' else obj.getImageTable(include_summary=case['option'])
        pd.testing.assert_frame_equal(result,target,check_exact=True)
        pd.testing.assert_frame_equal(obj.images,expected,check_exact=True)
        assert result is not obj.images
        for child,before in summaries:
            pd.testing.assert_frame_equal(child.summaries['SCN'],before['SCN'],check_exact=True)
            assert child.summaries['SCN'].attrs==before['SCN'].attrs
        pd.testing.assert_frame_equal(obj.summaries['SCN'],parent['SCN'],check_exact=True)
        # The legacy animal/marker/ROI lookup uses the final ordered owner;
        # experiment identity remains explicit in the complete image table.
        final='E2' if case['owner']=='Batch' else 'E1'
        expected_dict={'A1':{'M':{roi:str(root/final/case['location']/'A1'/filename)
                  for roi,filename in (('LHSCN1','M_LHSCN1.png'),('RHSCN1','M_RHSCN1.PNG'))}}}
        assert obj.imagesDict==expected_dict
        observed=normalize(dict(returned=table(result),stored=table(obj.images)),root)
        assert observed==predicted
        result.iloc[0,result.columns.get_loc('Marker')]='caller-edit'
        assert obj.images.iloc[0]['Marker']=='M'
        return dict(passed=True,expected=predicted,actual=observed,error=None)
    except Exception as error:
        actual=normalize(dict(returned=None if result is None else table(result),stored=table(obj.images)),root)
        return dict(passed=False,expected=predicted,actual=actual,error=type(error).__name__+': '+str(error))

def capture():
    assert not OWNER.exists();OWNER.mkdir()
    paths=[Path('PyFLASH/experiment.py'),Path('PyFLASH/batch.py'),Path(__file__)]
    sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for i,p in enumerate(paths):shutil.copyfile(p,OWNER/('original-'+str(i)+'-'+p.name))
    inputs=list(cases());(OWNER/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    retained=json.loads((BASE/'image-table-real-import-original-20261008-v1/before.json').read_text())
    rows=[dict(case=case,**production(case,OWNER/'cases'/case['key'])) for case in inputs]
    assert [r['expected'] for r in rows]==[r['expected'] for r in retained['rows']]
    (OWNER/'observation-amendment.json').write_text(json.dumps(dict(original_prediction_unchanged=True, original_calls=retained['actual_calls'], original_failures=retained['failed'], amendment='Capture the observed complete table encodings, including attributes, before caller mutation instead of repeating the already compared predicted table in successful diagnostic output. Original assertions, file identities, full predictions and failures are unchanged.'),indent=2)+'\n')
    changes=[name for name,sha in sources.items() if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha]
    data=dict(status='finished',actual_calls=len(rows),failed=sum(not r['passed'] for r in rows),rows=rows,
              sources=sources,source_changes=changes,
              scope='Real nonempty import on missing/invalid cache, three layouts, both summary-index carriers, every public getter switch and all three owners. Literal file identities and metadata; no image pixel decoding or science-method vote.')
    (OWNER/'before.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({k:data[k] for k in ('actual_calls','failed','source_changes')}),flush=True)

if __name__=='__main__':capture()
