"""Published scalar magnitude conventions, separate from inferential methods."""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
from reproducibility.reference_runtime import execute_queries

FIXTURE = Path(__file__).with_name('fixtures')/'effect_magnitude_reference.json'
SOURCE_ROOT = Path(__file__).with_name('reference-sources')/'effectsize-v1.0.0'
CAPABILITY = 'PyFLASH.stats_extra.interpret_magnitude'
BANDS = {'n/a':-1,'negligible':0,'small':1,'medium':2,'large':3}
CUTS = {'d':[.2,.5,.8],'r':[.1,.3,.5],
        'eta2':[.01,.06,.14],'omega2':[.01,.06,.14],'eps2':[.01,.06,.14]}


def cases():
    result = []
    for kind,cuts in CUTS.items():
        values = sorted({0.,.005,.025,.15,1.,-.4,-1.,
            *(sign*value for cut in cuts for value in
              (math.nextafter(cut,-math.inf),cut,math.nextafter(cut,math.inf)) for sign in (-1,1))})
        for value in values:
            result.append({'key':f'effect-magnitude.{len(result)}','capability':CAPABILITY,
                           'parameters':{'value':value,'kind':kind}})
    for kind in (*CUTS,'unknown'):
        for value in (None,'bad','nan','inf','-inf'):
            result.append({'key':f'effect-magnitude.{len(result)}','capability':CAPABILITY,
                           'parameters':{'value':value,'kind':kind}})
    for value in (.01,.3,-.8):
        result.append({'key':f'effect-magnitude.{len(result)}','capability':CAPABILITY,
                       'parameters':{'value':value,'kind':'unknown'}})
    return result


def reference(row):
    parameters = row['parameters']
    kind = parameters['kind']
    if kind not in CUTS:
        return [-1]
    try:
        value = Decimal(str(parameters['value']))
    except InvalidOperation:
        return [-1]
    if not value.is_finite():
        return [-1]
    if not kind.endswith('2'):
        value = abs(value)
    return [sum(value>=Decimal(str(cut)) for cut in CUTS[kind])]


def production(row):
    from PyFLASH.stats_extra import interpret_magnitude
    return [BANDS[interpret_magnitude(**row['parameters'])]]


def execute(output):
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    for name,expected in fixture['sources'].items():
        if hashlib.sha256((SOURCE_ROOT/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Published classifier source changed: '+name)
    if [{key:row[key] for key in ('key','capability','parameters')} for row in fixture['rows']]!=cases():
        raise ValueError('Frozen effect interpretation inputs changed.')
    native = execute_queries(fixture['native_queries'],output,name='effectsize-classifiers')
    for field in ('R','webR','wasm_sha256'):
        if native[field]!=fixture['native_runtime'][field]:
            raise ValueError('Published classifier runtime changed: '+field)
    return {row['key']:row for row in native['rows']}
