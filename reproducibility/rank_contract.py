"""Complete rank parent reports retain every pre-correction request and answer."""
from pathlib import Path
from copy import deepcopy
from contextlib import nullcontext
import json,hashlib,warnings
from PyFLASH import stats
from PyFLASH.config import Config
from PyFLASH.aesthetics import pyflash_style_context
from reproducibility.one_way_contract import clean,equal
FIXTURE=Path(__file__).with_name('fixtures')/'rank_complete_reference.json'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'));root=Path(__file__).parent
    for path,expected in fixture['source_manifest'].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('Original rank evidence changed: '+path)
    original=[row for path in fixture['before_rounds'] for row in json.loads((root/path).read_text(encoding='utf-8'))['rows']]
    if fixture['rows']!=original:raise ValueError('Rank requests or answers differ from frozen before-correction evidence')
    return fixture

def production(case):
    names=('CORRECTION_AUDIT','CORRECTION_RESAMPLES','CORRECTION_EXACT_MAX');previous=[getattr(Config,n) for n in names]
    try:
        Config.CORRECTION_AUDIT=case.get('audit','cheap');Config.CORRECTION_RESAMPLES=case.get('count',20000);Config.CORRECTION_EXACT_MAX=case.get('exact_max',10000)
        try:
            with warnings.catch_warnings(),(pyflash_style_context(**case['style']) if 'style' in case else nullcontext()):
                warnings.simplefilter('ignore')
                p,labels,overall,result,method=stats.runKW(results_dict={'caller-note':'retained'},**deepcopy(case['parameters']))
            return clean({'pvalues':p,'annotations':labels,'overall':overall,'results_dict':result,'method':method})
        except Exception as error:return {'error':type(error).__name__}
    finally:
        for name,value in zip(names,previous):setattr(Config,name,value)
