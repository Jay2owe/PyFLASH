"""Complete direct nearest-marker tables against independently frozen native R.

Both production backends are exercised. Table ownership and attributed counts
use the full native-R composed contract, never a scalar-only vote.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path

ARCHIVE = Path(__file__).with_name('reference-sources') / 'marker-nearest'
FROZEN = ARCHIVE / 'native-originals-v1/frozen.json'
MANIFEST_SHA256 = 'c331b55843b1ad511c91b43bd70f80e697a8b2a1777dd644e0afa150f6a55617'
FROZEN_SHA256 = 'b53dec36754997f4f5f787621e6789e1d43418503f28596ecb43611fe1703450'
DOMAIN_MANIFEST_SHA256 = '0a8c6f5922948856affe23effb70f5ee6647faf548ebb13124bdbb88da7cacfa'
DOMAINS = ARCHIVE / 'native-domains-v1/frozen.json'
DOMAINS_SHA256 = '78da43195984ae8dd0fbd7e623732922fc546797cf5b53087594a653f89f85f5'
SKLEARN = ARCHIVE / 'sklearn-originals-v1/frozen.json'
SKLEARN_SHA256 = '58c56e47b30ab0efd7b1be058a12f9429918c30c34e1742ce8dfb8f34649e42b'
CAPABILITY = 'PyFLASH.markers.Antibody.find_closest_distances_between_markers'
CAPABILITY_PREFIXES = {CAPABILITY: ('marker-nearest.',)}
# The whole-output replay passed 484 comparisons with unchanged source. This
# certifies the direct prepared-coordinate operation only; image import and
# calibration, experiment orchestration and summaries require their own proofs.
COMPLETE_CAPABILITIES = frozenset({CAPABILITY})


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-manifest.json', MANIFEST_SHA256)
    verify_manifest(ARCHIVE, 'domain-amendment-manifest.json', DOMAIN_MANIFEST_SHA256)
    from reproducibility import marker_nearest_reference as reference
    if hashlib.sha256(FROZEN.read_bytes()).hexdigest() != FROZEN_SHA256:
        raise ValueError('Nearest-marker frozen answers changed.')
    fixture = json.loads(FROZEN.read_text(encoding='utf-8'))
    if hashlib.sha256(Path(reference.__file__).read_bytes()).hexdigest() != fixture['reference_source_sha256']:
        raise ValueError('Nearest-marker native reference source changed.')
    if hashlib.sha256(reference.ORIGINAL.read_bytes()).hexdigest() != fixture['original_input_sha256']:
        raise ValueError('Original nearest-marker inputs changed.')
    if [row['case'] for row in fixture['rows']] != reference.cases():
        raise ValueError('Nearest-marker declared inputs changed.')
    from reproducibility import marker_nearest_domain_reference as domains, marker_nearest_sklearn_reference as sklearn_reference
    for path,digest,module in ((DOMAINS,DOMAINS_SHA256,domains),(SKLEARN,SKLEARN_SHA256,sklearn_reference)):
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Nearest-marker frozen answers changed: '+str(path))
        payload=json.loads(path.read_text(encoding='utf-8'))
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()!=payload['reference_source_sha256' if module is domains else 'reference_code_sha256']:
            raise ValueError('Nearest-marker independent reference source changed.')
    if [row['case'] for row in json.loads(DOMAINS.read_text(encoding='utf-8'))['rows']]!=domains.cases():
        raise ValueError('Nearest-marker domain inputs changed.')
    return fixture


def cases():
    rows=json.loads(FROZEN.read_text(encoding='utf-8'))['rows']+json.loads(DOMAINS.read_text(encoding='utf-8'))['rows']
    return [{'key': 'marker-nearest.' + row['case']['key'] + '.' + backend + '.' + threshold_source,
             'case':row['case'], 'expected':row['expected'], 'backend':backend,
             'threshold_source':threshold_source}
            for row in rows
            for backend in ('tree', 'fallback') for threshold_source in ('global','instance')]


def required_keys(capability):
    if capability != CAPABILITY:
        return set()
    original_keys = {row['case']['key'] for row in json.loads(SKLEARN.read_text(encoding='utf-8'))['rows']}
    items = cases()
    return {row['key'] for row in items} | {
        row['key'] + '.sklearn' for row in items
        if row['case']['key'] in original_keys
    }


def decode(value):
    if isinstance(value,str) and value in ('__nan__','__inf__','__neginf__'):
        return {'__nan__':math.nan,'__inf__':math.inf,'__neginf__':-math.inf}[value]
    if isinstance(value,list):return [decode(v) for v in value]
    if isinstance(value,dict):return {k:decode(v) for k,v in value.items()}
    return value


def encode(value):
    import numpy as np
    if isinstance(value,np.ndarray):return encode(value.tolist())
    if isinstance(value,np.generic):return encode(value.item())
    if isinstance(value,float) and not math.isfinite(value):
        return '__nan__' if math.isnan(value) else '__inf__' if value>0 else '__neginf__'
    if isinstance(value,(list,tuple)):return [encode(v) for v in value]
    if isinstance(value,dict):return {str(k):encode(v) for k,v in value.items()}
    return value


def table(frame):
    return {'columns':list(frame.columns),'index':encode(frame.index.tolist()),
            'index_name':frame.index.name,'dtypes':frame.dtypes.astype(str).tolist(),
            'attrs':encode(frame.attrs),'rows':encode(list(frame.itertuples(index=False,name=None)))}


def frame(case, side, name):
    import pandas as pd
    columns=case[side+'_groups']+[name+'_RawXM',name+'_RawYM',name+'_ZM']
    if side=='left' and case['coloc_column']:columns.append(case['coloc_column'])
    rows=[]
    for row in case[side]:
        values=[row.get(field) for field in case[side+'_groups']]+row['point']
        if side=='left' and case['coloc_column']:values.append(row.get('coloc'))
        rows.append(values)
    result=pd.DataFrame(rows,columns=columns)
    if case.get('index_group'):result=result.set_index(case['index_group'])
    elif case.get('duplicate_index'):result.index=[4]*len(result)
    result.attrs={'original-source':'native-marker-nearest-fixture','side':side}
    return result


@contextmanager
def configuration(item):
    from PyFLASH import markers
    from PyFLASH.config import Config
    prior_tree,prior_threshold=markers.cKDTree,Config.THRESHOLD
    markers.cKDTree=markers._TREE_PENDING if item['backend']=='tree' else None
    Config.THRESHOLD=item['case']['threshold'] if item['threshold_source']=='global' else -999.
    try:yield
    finally:markers.cKDTree,Config.THRESHOLD=prior_tree,prior_threshold


def production(item, observation=None, *, left_class=None, right_class=None):
    from PyFLASH import markers
    import numpy as np
    import pandas as pd
    left=object.__new__(left_class or markers.Antibody);left.name='L';left.df=frame(item['case'],'left','L')
    right=object.__new__(right_class or markers.Antibody);right.name='R';right.df=frame(item['case'],'right','R')
    sentinel=object();left._unrelated_state=sentinel;right._unrelated_state=sentinel
    if item['threshold_source']=='instance':left.threshold=item['case']['threshold']
    originals=[obj.df.copy(deep=True) for obj in (left,right)]
    left_identity,right_identity=left.df,right.df
    expected_left,expected_right=[obj.copy(deep=True) for obj in originals]
    expected=decode(item['expected'])
    for field in ('closest_flags','coloc_counts','contains','closest_counts'):
        assert all(math.isfinite(v) and v>=0 and v==int(v) for v in expected[field]), 'Native attribution must contain exact nonnegative integers.'
    for field in ('closest_flags','contains'):
        assert all(v in (0,1) for v in expected[field]), 'Native flags must be binary.'
    expected_left['L_DistToClosest_R']=np.asarray(expected['distances'],dtype=float)
    for name,field,dtype in (
        ('R_ClosestTo_L','closest_flags',float),('R_VolNumColoc_L','coloc_counts',float),
        ('R_VolContains_L','contains',np.int8),('R_NumColoc_L','coloc_counts',float),
        ('R_Contains_L','contains',np.int8),('R_NumClosestTo_L','closest_counts',float)):
        expected_right[name]=np.asarray(expected[field],dtype=dtype)
    with configuration(item):
        returned=left.find_closest_distances_between_markers(right)
    actual={'left':table(left.df),'right':table(right.df),
            'returns_original_left':returned is left_identity,'retains_original_right':right.df is right_identity,
            'unrelated_state_retained':left._unrelated_state is right._unrelated_state is sentinel}
    answer={'left':table(expected_left),'right':table(expected_right),
            'returns_original_left':True,'retains_original_right':True,'unrelated_state_retained':True}
    if observation is not None:
        observation.update(production=actual,reference=answer)
    # Every original column, dtype, missing mask, row index and attribute is
    # checked separately from the complete derived scientific output tables.
    for obj,original in zip((left,right),originals,strict=True):
        pd.testing.assert_frame_equal(obj.df[original.columns],original,check_exact=True)
        assert obj.df.attrs==original.attrs
    pd.testing.assert_frame_equal(right.df,expected_right,check_exact=True)
    return actual,answer


def equal(actual,expected):
    import numpy as np
    if isinstance(expected,dict):
        assert isinstance(actual,dict) and actual.keys()==expected.keys()
        for key in expected:equal(actual[key],expected[key])
    elif isinstance(expected,list):
        assert isinstance(actual,list) and len(actual)==len(expected)
        for left,right in zip(actual,expected,strict=True):equal(left,right)
    elif isinstance(expected,float) and math.isfinite(expected):
        assert np.isclose(actual,expected,rtol=1e-9,atol=0.),(actual,expected)
    else:assert actual==expected,(actual,expected)


def validate(output):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    from reproducibility.reference_runtime import execute_queries, values
    from reproducibility import marker_nearest_reference as reference
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    fixture=check_identity()
    native=execute_queries([reference.query(row['case']) for row in fixture['rows']],output/'native-r',
                           name='complete-marker-nearest',timeout=180)
    for key,value in fixture['runtime'].items():
        if native[key]!=value:raise ValueError('Nearest-marker native runtime changed: '+key)
    for frozen,row in zip(fixture['rows'],native['rows'],strict=True):
        equal(encode(reference.unpack(frozen['case'],list(values(row)))),frozen['expected'])
    from reproducibility import marker_nearest_domain_reference as domains, marker_nearest_sklearn_reference as sklearn_reference
    domain_fixture=json.loads(DOMAINS.read_text(encoding='utf-8'))
    native_domains=execute_queries([domains.query(row['case'],aligned=aligned)
        for row in domain_fixture['rows'] for aligned in (False,True)],output/'native-domains',
        name='marker-nearest-domains',timeout=180)
    for key,value in domain_fixture['runtime'].items():
        if native_domains[key]!=value:raise ValueError('Nearest-marker domain reference runtime changed: '+key)
    domain_rows={row['key']:row for row in native_domains['rows']}
    for frozen in domain_fixture['rows']:
        for aligned,field in ((False,'raw'),(True,'expected')):
            row=domain_rows[frozen['case']['key']+('.aligned' if aligned else '.raw')]
            equal(encode(reference.unpack(frozen['case'],list(values(row)))),frozen[field])
    import sklearn
    sklearn_fixture=json.loads(SKLEARN.read_text(encoding='utf-8'))
    if sklearn.__version__!=sklearn_fixture['sklearn']:
        raise ValueError('Nearest-marker scikit-learn reference version changed.')
    sklearn_answers={row['case']['key']:row['expected'] for row in sklearn_fixture['rows']}
    for frozen in fixture['rows']:
        answer=encode(sklearn_reference.answer(frozen['case']))
        equal(answer,sklearn_answers[frozen['case']['key']]);equal(answer,frozen['expected'])
    from reproducibility.paired_checkpoint import PairedCheckpoint
    journal=PairedCheckpoint(output,'marker-nearest')
    rows,paired=[],[]
    for item in cases():
        actual=answer=None;error=None;observation={}
        try:
            actual,answer=production(item,observation);equal(actual,answer)
        except Exception as exc:
            error=type(exc).__name__+': '+str(exc)
            actual,answer=observation.get('production'),observation.get('reference')
        agrees=error is None
        rows.append(comparison(item['key'],'Native R 4.6.0 stats::dist and full native grouping/attribution',
            'published-independent-distance/complete-composed-table-contract',actual,answer,agrees,True,
            'all-scientific-columns-original-tables-dtypes-indices-ownership',1e-9,0.))
        paired.append({'item':item,'actual':actual,'expected':answer,'error':error,'agrees':agrees})
        journal.append(paired[-1])
        if item['case']['key'] in sklearn_answers:
            rows.append(comparison(item['key']+'.sklearn','Published scikit-learn 1.8.0 KDTree plus SQLite/literal attribution',
                'independent-nearest-geometry/composed-functional-table-contract',actual,answer,agrees,True,
                'complete-tables-against-both-independent-geometry-families',1e-9,0.))
    write_json(output/'marker-nearest-paired.json',{'rows':paired,'scope':fixture['scope']})
    return rows
