"""Own obligations for actual inherited spatial consumers, never borrowed passes."""
from functools import lru_cache
from pathlib import Path
import contextlib,copy,io,json

ARCHIVE=Path(__file__).with_name('reference-sources')/'inherited-spatial'
MANIFEST_SHA256='65e3efad64ab18844e563a39bf08aeb411e1ad1633fd8c40954261b7f7437456'
CAPABILITIES=frozenset(
    ['PyFLASH.markers.'+owner+'.'+method for owner in ('objectMarker','cellMarker')
     for method in ('find_closest_distances_between_markers','find_distance_to_ventricle')]+
    ['PyFLASH.experiment.MiniExperiment.'+method for method in ('addClosestDistances','addVentricleDistances')])
COMPLETE_CAPABILITIES=CAPABILITIES
CAPABILITY_PREFIXES={name:('inherited-spatial.',) for name in CAPABILITIES}

@lru_cache(maxsize=8)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))

def read(name):return _read((ARCHIVE/name).resolve())

@lru_cache(maxsize=4)
def _index(path):return {item['key']:item for item in _read(path)}

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import marker_nearest_contract as nearest, experiment_nearest_contract as parent, ventricle_native_contract as boundary, marker_calibration_contract as calibration
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    originals={}
    for kind,module in (('nearest',nearest),('parent-nearest',parent),('boundary',boundary),('parent-boundary',boundary),('calibration',calibration)):
        module.check_identity()
        originals[kind]={item['key']:item for item in module.cases()}
    proof=read('run.json');items=read('predictions.json')
    assert proof['passed'] and proof['actual_calls']==2744 and not proof['source_changes']
    assert len(items)==len({item['key'] for item in items})==len(proof['rows'])==2744
    for item,row in zip(items,proof['rows'],strict=True):
        # JSON freezes the parent's marker-kind tuples as lists. Compare the
        # complete serialized inputs, without dropping any field or value.
        assert json.dumps(item['case'],sort_keys=True)==json.dumps(originals[item['kind']][item['case']['key']],sort_keys=True)
        assert item['key']==row['key'] and item['capability']==row['capability']
        assert item['capability'] in CAPABILITIES and row['passed'] and row['error'] is None

def cases():return copy.deepcopy(read('predictions.json'))

def _sklearn_keys():
    from reproducibility import marker_nearest_contract as nearest
    return {row['case']['key'] for row in json.loads(nearest.SKLEARN.read_text())['rows']}

def required_keys(capability):
    if capability not in CAPABILITIES:return set()
    selected=[item for item in read('predictions.json') if item['capability']==capability]
    keys={item['key'] for item in selected};corroborated=_sklearn_keys()
    keys.update(item['key']+'.sklearn' for item in selected if item['kind']=='nearest' and item['case']['case']['key'] in corroborated)
    return keys

def production(item,output=None,observation=None):
    from PyFLASH import markers
    from PyFLASH.experiment import MiniExperiment
    from reproducibility import marker_nearest_contract as nearest, experiment_nearest_contract as parent, ventricle_native_contract as boundary, marker_calibration_contract as calibration
    assert item==_index((ARCHIVE/'predictions.json').resolve())[item['key']]
    kind=item['kind'];case=item['case'];detail={}
    with contextlib.redirect_stdout(io.StringIO()):
        if kind=='nearest':actual,expected=nearest.production(case,detail,left_class=getattr(markers,item['owner']),right_class=getattr(markers,item['target']))
        elif kind=='calibration':actual,expected=calibration.production(case,observation=detail)
        elif kind=='parent-nearest':actual,expected=parent.production(case,detail,experiment_class=MiniExperiment)
        elif kind=='boundary':actual,expected=boundary.production(case,detail,marker_class=getattr(markers,item['owner']))
        elif kind=='parent-boundary':actual,expected=boundary.production(case,detail,experiment_class=MiniExperiment)
        else:raise ValueError('Unknown inherited spatial operation: '+kind)
    if observation is not None:observation.update(actual=actual,expected=expected)
    (boundary.equal if kind in ('boundary','parent-boundary') else nearest.equal)(actual,expected)
    return actual,expected

def validate(output):
    from reproducibility import marker_nearest_contract as nearest, experiment_nearest_contract as parent, ventricle_native_contract as boundary, marker_calibration_contract as calibration
    from reproducibility.table_family_validation import replay
    check_identity();output=Path(output)
    # Re-execute authenticated original native expressions in a standalone family
    # run as well. These results supply reference freshness, not subclass passes
    # or additional independent votes.
    fresh=[]
    for name,module in (('nearest',nearest),('parent',parent),('boundary',boundary),('calibration',calibration)):
        with contextlib.redirect_stdout(io.StringIO()):fresh.extend(module.validate(output/'original-native-replay'/name))
    assert all(row['status']=='agree' for row in fresh), 'Original native spatial answers no longer agree.'
    reference='Actual inherited class against unchanged authenticated native R, scikit-learn and ImageJ arrays; reference reuse is not an additional independent vote'
    rows=[];items=cases();corroborated=_sklearn_keys()
    for label,kinds,rtol,atol in (
        ('nearest',('nearest','parent-nearest'),1e-9,0.),
        ('calibration',('calibration',),1e-12,0.),
        ('boundary',('boundary','parent-boundary'),1e-12,1e-12)):
        selected=[item for item in items if item['kind'] in kinds]
        group=replay(selected,lambda item,observed,path:production(item,path,observed),output/label,
            reference=reference,family='inherited-spatial-complete-table-contract',
            shape='every-scientific-column-dtype-index-missing-value-return-and-state-identity',rtol=rtol,atol=atol)
        rows.extend(group)
        for item,row in zip(selected,group,strict=True):
            if item['kind']=='nearest' and item['case']['case']['key'] in corroborated:
                extra=copy.deepcopy(row);extra['contract']=item['key']+'.sklearn';rows.append(extra)
    return rows
