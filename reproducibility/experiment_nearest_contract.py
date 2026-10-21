"""Full public experiment pair orchestration against original-input native R."""
from pathlib import Path
import contextlib,hashlib,io,json,math,warnings

ARCHIVE=Path(__file__).with_name('reference-sources')/'experiment-nearest'
MANIFEST_SHA256='f5e272470080e41821dec1a47cee6ed5d51dc303e50e45c63cd2045166d9fea9'
CAPABILITY='PyFLASH.experiment.Experiment.addClosestDistances'
CAPABILITY_PREFIXES={CAPABILITY:('experiment-nearest.',)}
COMPLETE_CAPABILITIES=frozenset({CAPABILITY})


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import experiment_nearest_reference as reference
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
    frozen=json.loads((ARCHIVE/'native-v1/frozen.json').read_text(encoding='utf-8'))
    if [row['specification'] for row in frozen['rows']]!=reference.specifications():
        raise ValueError('Independent experiment-nearest inputs changed.')
    queries=json.loads((ARCHIVE/'native-v1/native-r/experiment-nearest-ordered-pairs-queries.json').read_text(encoding='utf-8'))
    if queries!=reference.queries(reference.specifications()):
        raise ValueError('Independent experiment-nearest expressions changed.')
    sources={Path(name).name:digest for name,digest in frozen['source_hashes'].items()}
    active=[(Path(reference.__file__),'reference.py'),
            (Path(reference.original.__file__),'marker_nearest_reference.py'),
            (reference.original.ORIGINAL,'frozen-before.json'),
            (Path(reference.original.__file__).with_name('reference-sources')/'marker-calibration/native-imagej-v1/native.json','native.json')]
    for path,key in active:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=sources[key]:
            raise ValueError('Independent experiment-nearest source changed: '+str(path))
    return frozen


def cases():
    frozen=json.loads((ARCHIVE/'native-v1/frozen.json').read_text(encoding='utf-8'))
    return [{'key':row['specification']['key']+'.'+backend+'.'+threshold_source+'.progress-'+str(progress),
             'specification':row['specification'],'pairs':row['pairs'],
             'backend':backend,'threshold_source':threshold_source,'progress':progress}
            for row in frozen['rows'] for backend in ('tree','fallback')
            for threshold_source in ('global','instance') for progress in (False,True)]


def required_keys(capability):
    return {item['key'] for item in cases()} if capability==CAPABILITY else set()


def add_reference_arrays(left,right,source,target,encoded):
    import numpy as np
    from reproducibility.marker_nearest_contract import decode
    expected=decode(encoded)
    for field in ('closest_flags','coloc_counts','contains','closest_counts'):
        if not all(math.isfinite(value) and value>=0 and value==int(value) for value in expected[field]):
            raise ValueError('Native experiment attribution must retain exact nonnegative integers.')
    for field in ('closest_flags','contains'):
        if not all(value in (0,1) for value in expected[field]):
            raise ValueError('Native experiment flags must be binary.')
    left[source+'_DistToClosest_'+target]=np.asarray(expected['distances'],dtype=float)
    for suffix,field,dtype in (
        ('_ClosestTo_','closest_flags',float),('_VolNumColoc_','coloc_counts',float),
        ('_VolContains_','contains',np.int8),('_NumColoc_','coloc_counts',float),
        ('_Contains_','contains',np.int8),('_NumClosestTo_','closest_counts',float)):
        right[target+suffix+source]=np.asarray(expected[field],dtype=dtype)


def production(item,observation=None,*,experiment_class=None):
    import numpy as np
    import pandas as pd
    from PyFLASH import markers
    from PyFLASH.experiment import Experiment
    from reproducibility.marker_nearest_contract import configuration,frame,table,equal
    from reproducibility import marker_calibration_contract as calibration
    exp=object.__new__(experiment_class or Experiment);exp.name='native ordered experiment';exp.data={}
    sentinel=object();exp._unrelated_state=sentinel
    ignored=object.__new__(markers.Antibody);ignored.name='Ignored';ignored.df=pd.DataFrame({'ordinary':[3.,7.]})
    ignored.df.attrs={'carrier':'unrelated non-spatial antibody'};ignored._unrelated_state=sentinel
    exp.data['ignored-key']=ignored
    expected={};objects={}
    for descriptor in item['specification']['markers']:
        name=descriptor['name'];cls=markers.objectMarker if descriptor['class']=='object' else markers.cellMarker
        if 'native' in descriptor:
            with warnings.catch_warnings(),contextlib.redirect_stdout(io.StringIO()):
                warnings.simplefilter('ignore')
                obj=cls(name,calibration.frame(descriptor['native']),exp,None)
            expected[name]=calibration.expected_frame(descriptor['native'],name,False)
            pd.testing.assert_frame_equal(obj.df,expected[name],check_exact=True)
        else:
            obj=object.__new__(cls);obj.name=name;obj.experiment=exp
            obj.df=frame(descriptor['case'],descriptor['side'],name)
            expected[name]=obj.df.copy(deep=True)
        if item['threshold_source']=='instance':obj.threshold=item['specification']['threshold']
        elif hasattr(obj,'threshold'):del obj.threshold
        obj._unrelated_state=sentinel
        objects[name]=obj;exp.data['key-'+name]=obj
    data_identity=exp.data
    identities={name:obj.df for name,obj in objects.items()}
    originals={name:obj.df.copy(deep=True) for name,obj in objects.items()}
    ignored_identity=ignored.df;ignored_original=ignored.df.copy(deep=True)
    expected_order=list(exp.data)
    for pair in item['pairs']:
        case=pair['case'];source,target=case['source'],case['target']
        add_reference_arrays(expected[source],expected[target],source,target,pair['expected'])
    config={'backend':item['backend'],'threshold_source':item['threshold_source'],
            'case':{'threshold':item['specification']['threshold']}}
    with configuration(config),contextlib.redirect_stdout(io.StringIO()):
        returned=exp.addClosestDistances(progress=item['progress'])
    n=len(objects)
    actual={'tables':{name:table(obj.df) for name,obj in objects.items()},
        'ignored':table(ignored.df),'data_order':list(exp.data),
        'retains_data_mapping':exp.data is data_identity,
        'retains_marker_tables':all(obj.df is identities[name] for name,obj in objects.items()),
        'retains_ignored_table':ignored.df is ignored_identity,
        'retains_unrelated_state':exp._unrelated_state is ignored._unrelated_state is sentinel and
                                 all(obj._unrelated_state is sentinel for obj in objects.values()),
        'return':returned,'summary':exp._last_closest_summary}
    answer={'tables':{name:table(df) for name,df in expected.items()},
        'ignored':table(ignored_original),'data_order':expected_order,
        'retains_data_mapping':True,'retains_marker_tables':True,'retains_ignored_table':True,
        'retains_unrelated_state':True,'return':None,
        'summary':f'{n} markers | {n*(n-1)} pairwise distance calculations'}
    if observation is not None:observation.update(actual=actual,expected=answer)
    for name,obj in objects.items():
        pd.testing.assert_frame_equal(obj.df[originals[name].columns],originals[name],check_exact=True)
        distance=[column for column in obj.df.columns if '_DistToClosest_' in column]
        exact=[column for column in obj.df.columns if column not in distance]
        pd.testing.assert_frame_equal(obj.df[exact],expected[name][exact],check_exact=True)
        pd.testing.assert_frame_equal(obj.df[distance],expected[name][distance],check_exact=False,rtol=1e-9,atol=0.)
    equal(actual,answer)
    return actual,answer


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    from reproducibility.reference_runtime import execute_queries,values
    from reproducibility import experiment_nearest_reference as reference
    from reproducibility.marker_nearest_contract import equal
    frozen=check_identity();output=Path(output)
    specifications=[row['specification'] for row in frozen['rows']]
    native=execute_queries(reference.queries(specifications),output/'native-r',
                           name='experiment-nearest-ordered-pairs',timeout=180)
    for key,value in frozen['runtime'].items():
        if native[key]!=value:raise ValueError('Independent experiment-nearest runtime changed: '+key)
    equal(reference.answers(specifications,native['rows'],values),frozen['rows'])
    from reproducibility.paired_checkpoint import PairedCheckpoint
    journal=PairedCheckpoint(output,'experiment-nearest')
    rows=[];paired=[]
    for item in cases():
        observation={};error=None
        try:production(item,observation)
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        actual,answer=observation.get('actual'),observation.get('expected')
        rows.append(comparison(item['key'],'Native R 4.6.0 ordered original marker pairs and installed Fiji calibrated centres',
            'published-independent-distance/complete-experiment-orchestration-contract',actual,answer,error is None,True,
            'every-ordered-pair-complete-original-and-derived-tables-ownership-and-nonspatial-carrier',1e-9,0.))
        paired.append({'item':item,'actual':actual,'expected':answer,'error':error})
        journal.append(paired[-1])
    write_json(output/'experiment-nearest-paired.json',{'rows':paired,'scope':frozen['scope']})
    return rows
