"""Literal whole image-indexing contracts; these methods do not decode pixels.

The original authored directory/table fixture is independently retained by the
image-table contract. This extension predicts import returns, stored tables,
lookups, summary messages, cache branches and ownership before actual calls.
It is not a numerical-method vote or a whole-method coverage declaration.
"""
from pathlib import Path
from itertools import product
import copy,hashlib
import pandas as pd
from reproducibility import image_table_import_reference as original
from reproducibility.whole_condition_reference import table

CAPABILITIES=frozenset('PyFLASH.'+module+'.'+owner+'.importImages' for module,owner in
    (('experiment','Experiment'),('experiment','MiniExperiment'),('batch','Batch')))
COMPLETE_CAPABILITIES=frozenset()

def cases():
    for owner,location,progress,metadata,content in product(('Experiment','MiniExperiment','Batch'),original.LOCATIONS,
            (False,True,'default'),('plain','indexed'),('missing','empty','plain','formats','nested')):
        yield dict(key='.'.join(map(str,(owner,original.LOCATIONS.index(location),progress,metadata,content))),
            owner=owner,location=location,option=progress,metadata=metadata,content=content,cache='invalid')
    for location,progress,metadata,cache in product(original.LOCATIONS,(False,True,'default'),('plain','indexed'),('valid','empty','mixed')):
        yield dict(key='.'.join(map(str,('Batch',original.LOCATIONS.index(location),progress,metadata,'cached',cache))),
            owner='Batch',location=location,option=progress,metadata=metadata,content='plain',cache=cache)
    for progress,metadata in product((False,True,'default'),('plain','indexed')):
        yield dict(key='.'.join(map(str,('Batch','no-children',progress,metadata))),owner='Batch',
            location=original.LOCATIONS[0],option=progress,metadata=metadata,content='plain',cache='no-children')

def empty():
    return pd.DataFrame(columns=['AnimalName','Marker','ROI','ImageName','ImagePath','Extension'])

def lookup(frame):
    # Last owned row wins in the documented legacy animal/marker/ROI lookup.
    result={}
    for row in frame.to_dict('records'):
        result.setdefault(row['AnimalName'],{}).setdefault(row['Marker'],{})[row['ROI'] or row['ImageName']]=row['ImagePath']
    return result

def prepare(case,root):
    root=Path(root)
    obj,expected,children=original.prepare(dict(case,state='invalid'),root)
    child_expected=[]
    for child in children:
        folder=root/child.name/case['location']
        target=expected[expected.Experiment==child.name].drop(columns='Experiment').copy() if case['owner']=='Batch' else expected.copy()
        target=target.reset_index(drop=True)
        if case['content'] in ('empty','missing'):
            # Delete only these tiny, just-authored indexing fixtures.
            for name in ('M_LHSCN1.png','M_RHSCN1.PNG'):(folder/'A1'/name).unlink()
            if case['content']=='missing':
                (folder/'A1'/'ignored.txt').unlink();(folder/'root-level.png').unlink()
                (folder/'A1').rmdir();folder.rmdir()
            target=empty()
        elif case['content']=='formats':
            for name in ('M_LHSCN1.png','M_RHSCN1.PNG'):(folder/'A1'/name).unlink()
            rows=[]
            # Literal, independently declared enumeration of every accepted
            # extension, mixed case, duplicate ROI and deterministic file order.
            for suffix in ('.bmp','.jpeg','.JPG','.png','.TIF','.tiff'):
                path=folder/'A1'/('M_LHSCN1'+suffix);path.write_bytes(b'Authored filename indexing fixture; no pixel decoding.\n')
                row=target.iloc[0].to_dict();row.update(ROI='LHSCN1',ImageName='M_LHSCN1',ImagePath=str(path),Extension=suffix.lower());rows.append(row)
            target=pd.DataFrame(rows,columns=target.columns)
        elif case['content']=='nested':
            path=folder/'A1'/'nested'/'M_LHSCN1.png';path.parent.mkdir();path.write_bytes(b'Authored nested indexing fixture.\n')
            duplicate=target.iloc[[0]].copy();duplicate['ImagePath']=str(path)
            target=pd.concat([target.iloc[[0]],duplicate,target.iloc[[1]]],ignore_index=True)
        if case['cache']=='valid' or case['cache']=='mixed' and child is children[0]:
            child.images=target.copy(deep=True)
        elif case['cache']=='empty':child.images=empty();target=empty()
        child_expected.append(target)
    if case['cache']=='no-children':
        obj.experiment_list=[];children=[];child_expected=[]
    if case['owner']=='Batch':
        chunks=[]
        for child,frame in zip(children,child_expected,strict=True):
            if len(frame):
                frame=frame.copy();frame['Experiment']=child.name;chunks.append(frame)
        expected=pd.concat(chunks,ignore_index=True) if chunks else empty()
        if chunks:expected=expected[['AnimalName','Marker','ROI','ImageName','ImagePath','Extension','Experiment','Condition','Treatment']]
    else:expected=child_expected[0]
    if len(expected):summary=f"{len(expected)} images | 1 subjects | 1 markers"
    elif case['owner']=='Batch':summary='No Images found across experiments'
    elif case['content']=='missing':summary='No Images folder found'
    else:summary='0 images | 0 subjects | 0 markers'
    prediction=original.normalize(dict(table=table(expected),lookup=lookup(expected),summary=summary,
        image_root=None if case['owner']=='Batch' or case['content']=='missing' else str(root/obj.name/case['location']),
        returned_stored=True),root)
    obj._unrelated_import_state=object()
    for child in children:child._unrelated_import_state=object()
    return obj,children,expected,child_expected,prediction

def observe(case,root,prepared,prediction):
    obj,children,expected,child_expected,declared=prepared
    assert declared==prediction
    owners=list(dict.fromkeys([obj,*children]))
    summaries=[(owner,copy.deepcopy(owner.summaries)) for owner in owners]
    data=[(owner,owner.data,copy.copy(owner.data)) for owner in owners]
    states=[(owner,dict(owner.__dict__)) for owner in owners]
    files={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in Path(root).rglob('*') if path.is_file()}
    result=None;error=None
    try:
        result=obj.importImages() if case['option']=='default' else obj.importImages(progress=case['option'])
        pd.testing.assert_frame_equal(result,expected,check_exact=True)
        assert result is obj.images
        assert obj.imagesDict==lookup(expected)
        for owner,before in summaries:
            assert owner.summaries.keys()==before.keys()
            for key in before:pd.testing.assert_frame_equal(owner.summaries[key],before[key],check_exact=True)
        for owner,carrier,before in data:assert owner.data is carrier and owner.data==before
        mutable={'images','imagesDict','image_root','_last_image_import_summary'}
        for owner,before in states:
            assert all(owner.__dict__.get(key) is value for key,value in before.items() if key not in mutable)
            assert set(owner.__dict__)-set(before)<=mutable
        for child,target in zip(children,child_expected,strict=True):pd.testing.assert_frame_equal(child.images,target,check_exact=True)
        assert files=={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in Path(root).rglob('*') if path.is_file()}
    except Exception as caught:error=type(caught).__name__+': '+str(caught)
    stored=getattr(obj,'images',None)
    encoded=table(stored) if isinstance(stored,pd.DataFrame) else dict(invalid_type=type(stored).__name__,value=repr(stored))
    actual=original.normalize(dict(table=encoded,lookup=obj.imagesDict,summary=getattr(obj,'_last_image_import_summary',None),
        image_root=None if case['owner']=='Batch' else getattr(obj,'image_root',None),returned_stored=result is obj.images),root)
    return dict(case=case,expected=prediction,actual=actual,error=error,passed=error is None and actual==prediction)
