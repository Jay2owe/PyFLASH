"""Whole functional flat-experiment condition tables and nested ownership."""
from pathlib import Path
from functools import lru_cache
import copy,json

ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-mini-conditions'
MANIFEST_SHA256='dc9204ac124c7ed0fb13d0088f8977f2f4cdf7fe7d8ea38edc25299aedf91bbe'
CAPABILITY='PyFLASH.experiment.MiniExperiment.set_condition_list'
CAPABILITY_PREFIXES={CAPABILITY:('whole-mini-condition.',)}
COMPLETE_CAPABILITIES=frozenset({CAPABILITY})

@lru_cache(maxsize=8)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))
def read(name):return _read((ARCHIVE/name).resolve())

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import mini_explicit_condition_reference as reference,mini_condition_fallback_reference as fallback,whole_condition_contract
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256);whole_condition_contract.check_identity()
    for module in (reference,fallback):assert Path(module.__file__).read_bytes()==(ARCHIVE/('accepted-'+Path(module.__file__).name)).read_bytes()
    before=read('private-index/run.json');assert before['passed'] and before['counts']=={'original':{'calls':432,'failed':54},'candidate':{'calls':432,'failed':0}}
    empty=read('empty-original/run.json');assert empty['actual_calls']==144 and empty['failed']==132 and not empty['source_changes']
    qualified=read('private-qualified/run.json');assert qualified['passed'] and qualified['source_unchanged'] and qualified['counts']=={'explicit':{'calls':576,'failed':0},'fallback':{'calls':864,'failed':0}}
    assert read('installed/installation.json')['qualified_controls']==1108
    predictions=read('private-qualified/predictions.json');assert predictions==read('explicit-first-observer/predictions.json')+read('empty-original/predictions.json')
    assert [row['case'] for row in predictions]==list(reference.cases())
    fallback_proof=read('fallback-original/run.json');assert fallback_proof['passed'] and fallback_proof['actual_calls']==864 and not fallback_proof['source_changes']
    assert read('fallback-original/predictions.json')==fallback.cases()
    assert read('observer-oracle-amendment.json')['reason']

@lru_cache(maxsize=8)
def _cases(path):
    explicit=[dict(key='whole-mini-condition.explicit.'+row['case']['key'],kind='explicit',case=row['case'],expected=row['expected']) for row in _read(path/'private-qualified/predictions.json')]
    fallback=[dict(key='whole-mini-condition.fallback.'+row['key'],reference_key=row['key'],kind='fallback',case=row['case'],expected=row['expected']) for row in _read(path/'fallback-original/predictions.json')]
    return explicit+fallback
def cases():return copy.deepcopy(_cases(ARCHIVE.resolve()))
@lru_cache(maxsize=8)
def _index(path):return {row['key']:row for row in _cases(path)}

def required_keys(capability):
    if capability!=CAPABILITY:return set()
    from reproducibility import mini_lifecycle_contract,mini_image_condition_contract,empty_parent_contract,parent_ownership_contract
    return ({row['key'] for row in cases()}|{row['key'] for row in mini_lifecycle_contract.cases()}|
        {row['key'] for row in mini_image_condition_contract.cases()}|
        {row['key'] for row in empty_parent_contract.cases() if row['case']['kind']=='mini'}|
        {row['key'] for row in parent_ownership_contract.cases() if row['kind']=='labels' and row['case']['kind']=='mini'})

def production(item,observation=None):
    assert item==_index(ARCHIVE.resolve())[item['key']]
    if item['kind']=='explicit':
        from reproducibility import mini_explicit_condition_reference as reference
        result=reference.production(item['case'],item['expected'])
        if observation is not None:observation.update(actual=result['actual'],expected=result['expected'])
        assert result['passed'],result['error'] or item['key']
        return result['actual']
    from reproducibility import mini_condition_fallback_reference as reference
    original=dict(key=item['reference_key'],case=item['case'],expected=item['expected']);observed={};actual=reference.production(original,observed)
    if observation is not None:observation.update(observed)
    return actual

def validate(output):
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity();output=Path(output)
    for folder,stem in [('explicit-first-observer','mini-explicit-factor-assignment'),('empty-original','mini-explicit-factor-assignment')]:
        queries=read(folder+'/native/'+stem+'-queries.json');native=execute_queries(queries,output/'native'/folder,name=stem)
        assert native['rows']==read(folder+'/native/'+stem+'-results.json')['rows']
    # The actual subclass fallback uses the unchanged authenticated parent R
    # arrays, but its 864 calls and all resulting tables are executed here.
    from reproducibility import whole_condition_contract
    queries=whole_condition_contract.read('native-original/whole-parent-factor-assignment-queries.json')
    native=execute_queries(queries,output/'native'/'fallback',name='whole-parent-factor-assignment')
    assert native['rows']==whole_condition_contract.read('native-original/whole-parent-factor-assignment-results.json')['rows']
    return replay(cases(),lambda item,observed,path:production(item,observed),output,
        reference='Native R categorical maps, subject lookup, literal matching and typed empty schemas; full actual subclass tables and literal ownership. Functional only, no statistical-method vote.',
        family='whole-flat-experiment-condition-tables',shape='every-summary-raw-image-cell-type-index-attribute-missing-label-factor-return-alias-and-nested-ownership')
