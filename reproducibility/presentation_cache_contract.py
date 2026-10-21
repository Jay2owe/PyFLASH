"""Frozen significance text and opaque cache identity/ownership contracts."""
from pathlib import Path
import hashlib,json,pickle

FIXTURES=Path(__file__).with_name('fixtures')

def cases():
    return [r for name in ('annotation_complete_reference.json','stats_cache_complete_reference.json')
            for r in json.loads((FIXTURES/name).read_text(encoding='utf-8'))['rows']]

def check_identity():
    for name in ('annotation_complete_reference.json','stats_cache_complete_reference.json'):
        fixture=json.loads((FIXTURES/name).read_text(encoding='utf-8'))
        for path,expected in fixture['source_manifest'].items():
            if hashlib.sha256((Path(__file__).parent/path).read_bytes()).hexdigest()!=expected:
                raise ValueError('Original functional evidence changed: '+path)
        archive=Path(__file__).parent/'reference-sources/presentation-cache'
        if name=='annotation_complete_reference.json':
            original=json.loads((archive/'annotation-original-frozen.json').read_text(encoding='utf-8'))['rows']
        else:
            original=json.loads((archive/'cache-literal-original-frozen.json').read_text(encoding='utf-8'))['rows']
            original += [{**r,'kind':'random-state'} for r in json.loads((archive/'cache-rng-original-frozen.json').read_text(encoding='utf-8'))['rows']]
        if fixture['rows']!=original:
            raise ValueError('Functional inputs or answers differ from frozen before-correction evidence')

def production(case):
    from PyFLASH import stats
    if case['key'].startswith('annotation.'):
        from PyFLASH.aesthetics import pyflash_style_context
        import math
        style={**case['style'],'significance_thresholds':{float(k):v for k,v in case['style']['significance_thresholds'].items()}}
        with pyflash_style_context(**style):
            try:
                answer=stats.get_annotation(**case['parameters'])
                if isinstance(answer,float) and not math.isfinite(answer):answer=str(answer)
                return {'result':answer}
            except Exception as error:return {'error':type(error).__name__}
    if case['kind']!='random-state':
        from reproducibility import cache_literal_reference as reference
        return reference.clear_production(case) if case['kind']=='clear' else reference.production(case)
    import numpy as np
    from PyFLASH.config import Config
    p=case['parameters'];name=p['random_kind'];location=p['location']
    engines={kind.lower():kind for kind in ('PCG64','MT19937','Philox','SFC64')}
    rng=np.random.RandomState(p['seed']) if name=='legacy' else np.random.Generator(getattr(np.random,engines[name])(p['seed']))
    old=Config.EFFECT_CI_RANDOM_STATE
    def parameters(stream):
        Config.EFFECT_CI_RANDOM_STATE=stream if location=='session' else 0
        return None if location=='session' else ({'random_state':stream} if location=='direct-option' else {'interval':{'random_state':stream}})
    try:
        initial=pickle.dumps(rng,protocol=5);options=parameters(rng)
        def key(opts):return stats.stats_cache_key('Signal',['A','B'],['female'],opts)
        first=key(options)
        answer={'key_is_hashable':bool(hash(first) or True),'input_stream_not_consumed':pickle.dumps(rng,protocol=5)==initial,
                'repeated_unchanged_state_equal':first==key(options)}
        snapshot=pickle.dumps(first,protocol=5);rng.random(p['advance_count'])
        answer['advanced_state_differs']=first!=key(options)
        answer['key_snapshot_is_immutable']=pickle.dumps(first,protocol=5)==snapshot
        answer['restored_state_equal']=first==key(parameters(pickle.loads(initial)))
        answer['cloned_state_equal']=first==key(parameters(pickle.loads(initial)))
        return answer
    finally:Config.EFFECT_CI_RANDOM_STATE=old

def validate(output):
    from reproducibility.normality_association_validation import comparison
    check_identity();rows=[];paired=[]
    for case in cases():
        actual=production(case);expected=case['expected'];agrees=actual==expected
        rows.append(comparison(case['key'],'literal-probability-presentation/content-identity-and-stream-ownership',
            'functional-presentation-cache/no-additional-inference-vote',actual,expected,agrees,True,'all-functional-fields',0.,0.))
        paired.append({'case':case,'production':actual,'reference':expected,'agrees':agrees})
    (output/'presentation-cache-paired-data.json').write_text(json.dumps({'rows':paired},indent=2,allow_nan=False),encoding='utf-8')
    return rows
