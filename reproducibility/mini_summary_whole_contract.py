"""Complete flat-summary aggregation, factor merge and atomic state contract."""
from pathlib import Path
from functools import lru_cache
import copy,json

ARCHIVE=Path(__file__).with_name('reference-sources')/'whole-mini-summary'
MANIFEST_SHA256='db7bdb5fe301352894018891731249a48c753a226c165890631f33ec03164418'
CAPABILITY='PyFLASH.experiment.MiniExperiment.createSummary'
CAPABILITY_PREFIXES={CAPABILITY:('whole-mini-summary.',)}
COMPLETE_CAPABILITIES=frozenset({CAPABILITY})

@lru_cache(maxsize=8)
def _read(path):return json.loads(path.read_text(encoding='utf-8'))

def read(name):return _read((ARCHIVE/name).resolve())

def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    from reproducibility import mini_summary_whole_reference as reference
    verify_manifest(ARCHIVE,'source-files.json',MANIFEST_SHA256)
    assert Path(reference.__file__).read_bytes()==(ARCHIVE/'mixed/mixed-factor-qualified-reference.py').read_bytes()
    original=read('original/run.json');qualified=read('qualified-private/run.json');late=read('late-qualified/run.json')
    assert original['actual_calls']==352 and original['failed']==304 and not original['source_changes']
    assert not read('first-private/run.json')['passed'] and not read('second-private/run.json')['passed']
    assert qualified['passed'] and qualified['actual_calls']==352 and qualified['control_calls']==1898 and not qualified['source_changes']
    before=read('late-qualified/before.json');assert before['actual_calls']==448 and before['failed']==384
    assert late['passed'] and late['actual_calls']==448 and not late['source_changes']
    assert qualified['candidate_sha256']==late['candidate_sha256']==read('installed/installation.json')['candidate_sha256']
    installed=read('installed-replay/run.json');assert installed['passed'] and installed['actual_calls']==448 and installed['control_calls']==1898 and not installed['source_changes']
    mixed=read('mixed/run.json');assert mixed['passed'] and mixed['actual_calls']==640 and not mixed['source_changes']
    assert mixed['unchanged_earlier_predictions']==448 and mixed['new_predictions']==192
    predictions=read('mixed/predictions.json')
    assert [row['case'] for row in predictions]==reference.cases()
    assert [row['expected'] for row in predictions[:352]]==[row['expected'] for row in original['rows']]
    assert [row['expected'] for row in predictions[:448]]==[row['expected'] for row in read('late-original/predictions.json')]
    for name in ('mini_shared_adapter_amendment_20261008_v2.json','mini_shared_adapter_amendment_20261008_v3.json','mini_shared_adapter_amendment_20261008_v4.json'):
        assert read(name)['reason']

def cases():
    return [dict(key='whole-mini-summary.'+row['case']['key'],case=copy.deepcopy(row['case']),expected=copy.deepcopy(row['expected'])) for row in read('mixed/predictions.json')]

def required_keys(capability):
    if capability!=CAPABILITY:return set()
    from reproducibility import mini_scientific_contract,mini_summary_routes_contract,mini_lifecycle_contract
    prefixes=mini_scientific_contract.CAPABILITY_PREFIXES[CAPABILITY]
    return ({item['key'] for item in cases()}
        |{item['key'] for item in mini_scientific_contract.cases() if item['key'].startswith(prefixes)}
        |{item['key'] for item in mini_summary_routes_contract.cases()}
        |{item['key'] for item in mini_lifecycle_contract.cases()})

def production(item,output,observation=None):
    from reproducibility import mini_summary_whole_reference as reference
    from reproducibility.reference_runtime import values
    from reproducibility.scientific_utility_contract import table
    frozen=next(row for row in read('mixed/predictions.json') if row['case']==item['case'])
    assert item['key']=='whole-mini-summary.'+frozen['case']['key'] and item['expected']==frozen['expected']
    answer=reference.expected(item['case'],values(frozen['native']))
    assert {key:table(value) if key!='error' else value for key,value in answer.items()}==item['expected']
    actual=reference.production(item['case'],answer,Path(output))
    if observation is not None:observation.update(actual=actual,expected=item['expected'])
    assert actual['passed'],actual.get('error')
    return actual,item['expected']

def validate(output):
    from reproducibility import mini_summary_whole_reference as reference
    from reproducibility.reference_runtime import execute_queries
    from reproducibility.table_family_validation import replay
    check_identity()
    queries=[reference.query(case) for case in reference.cases()]
    assert queries==read('mixed/native/whole-mini-mixed-factors-queries.json')
    native=execute_queries(queries,Path(output)/'native',name='whole-mini-mixed-factors',timeout=300)
    assert native['rows']==read('mixed/native/whole-mini-mixed-factors-results.json')['rows']
    return replay(cases(),lambda item,observed,path:production(item,path,observed),output,
        reference='Native R full grouped means and outer-joined summary tables with declared first-metadata, mapped-factor coalescing and atomic conflict policy; existing independent represented-number and score families remain required',
        family='whole-flat-summary-tables-and-factor-state',shape='every-summary-and-raw-table-cell-dtype-index-factor-refusal-source-and-return-ownership',rtol=0.,atol=0.)
