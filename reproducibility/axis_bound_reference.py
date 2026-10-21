"""Retain complete scalar display-bound profiles, not a science-method vote."""
from pathlib import Path
from fractions import Fraction
from decimal import Decimal
import hashlib, inspect, json, math, shutil, time

BASE=Path.home()/'AppData/Local/PyFLASH'
OWNER=BASE/'axis-bound-whole-qualified-20261008-v3'
GATE=BASE/'image-table-whole-private-20261008-v2/run.json'

def cases():
    import numpy as np
    import pandas as pd
    for exponent in (-323,-308,-200,-20,-2,0,2,20,200,307):
        for multiplier in (-9.75,-4.0,-1.0,1.0,4.0,9.75):
            value=multiplier*10.**exponent
            if not math.isfinite(value) or value==0: continue
            for edge,point in [('exact',value),('below',float(np.nextafter(value,-np.inf))),('above',float(np.nextafter(value,np.inf)))]:
                yield dict(key=f'axis-bound.grid.{exponent}.{multiplier}.{edge}',value=point,kind='numeric')
    for name,value in [('zero',0),('negative-zero',-0.),('none',None),('nan',math.nan),('pandas-na',pd.NA),
            ('false',False),('true',True),('largest',float.fromhex('0x1.fffffffffffffp+1023')),
            ('negative-largest',-float.fromhex('0x1.fffffffffffffp+1023')),
            ('infinity',math.inf),('negative-infinity',-math.inf),('huge-int',10**400),
            ('text','1.0'),('complex',1+0j),('fraction',Fraction(2,3)),('decimal',Decimal('1.5')),
            ('list',[1.]),('tuple',(1.,)),('array',np.asarray([1.])),('zero-d-array',np.asarray(1.))]:
        yield dict(key='axis-bound.domain.'+name,value=value,kind='domain')
    for dtype in ('int8','int16','int32','int64','uint8','uint64','float16','float32','float64','longdouble','bool'):
        yield dict(key='axis-bound.dtype.'+dtype,value=np.asarray(42 if dtype!='bool' else True,dtype=dtype)[()],kind='numeric')

def prediction(value):
    """Exhaustively compare independently constructed exact grid candidates."""
    import numpy as np
    import pandas as pd
    import sympy as sp
    if value is None or value is pd.NA: return dict(value=0,type='int')
    if isinstance(value,np.generic):value=value.item()
    if isinstance(value,float) and math.isnan(value):return dict(value=0,type='int')
    if not isinstance(value,(int,float)):return dict(error='TypeError')
    if isinstance(value,float) and not math.isfinite(value):return dict(error='ValueError')
    if value==0:return dict(value=0,type='int')
    if isinstance(value,int): exact=sp.Rational(value)
    else: exact=sp.Rational(*value.as_integer_ratio())
    maximum=sp.Rational(*float.fromhex('0x1.fffffffffffffp+1023').as_integer_ratio())
    if abs(exact)>maximum:return dict(error='ValueError')
    magnitude=len(str(abs(exact.p)))-len(str(exact.q))
    while abs(exact)<sp.Integer(10)**magnitude:magnitude-=1
    while abs(exact)>=sp.Integer(10)**(magnitude+1):magnitude+=1
    step=sp.Integer(5)*sp.Integer(10)**(magnitude-1)
    eligible=[]
    for multiple in range(-25,26):
        rational=step*multiple
        try:
            import mpmath as mp
            converted=float(str(sp.N(rational,400)))
            with mp.workprec(4096):
                other=float(mp.nstr(mp.mpf(int(rational.p))/mp.mpf(int(rational.q)),1000))
            assert converted==float(Fraction(int(rational.p),int(rational.q)))
            assert converted==other, (str(rational), converted, other)
        except OverflowError:continue
        if math.isfinite(converted) and sp.Rational(*converted.as_integer_ratio())>=exact:
            eligible.append(converted)
    if not eligible:return dict(error='ValueError')
    return dict(value=min(eligible),type='float')

def describe(case):
    value=case['value']
    return dict(key=case['key'],kind=case['kind'],input_type=type(value).__module__+'.'+type(value).__name__,
                input_repr=repr(value))

def run():
    assert not OWNER.exists();OWNER.mkdir()
    deadline=time.monotonic()+28800
    while not GATE.exists() or json.loads(GATE.read_text()).get("status")!="finished":
        if time.monotonic()>deadline:raise TimeoutError('Earlier owned check did not finish')
        time.sleep(5)
    import numpy as np
    import sympy as sp
    from PyFLASH import utils
    paths=[Path(utils.__file__),Path(__file__)]
    sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for i,p in enumerate(paths):shutil.copyfile(p,OWNER/('original-'+str(i)+'-'+p.name))
    (OWNER/'native-rational-source.py').write_text(inspect.getsource(sp.Rational.__float__),encoding='utf-8')
    items=list(cases());answers=[dict(case=describe(c),expected=prediction(c['value'])) for c in items]
    retained=json.loads((BASE/'axis-bound-whole-original-20261008-v1/before.json').read_text())
    assert [r['case'] for r in answers]==[r['case'] for r in retained['rows']]
    changes=[dict(case=current['case'],original=old['expected'],qualified=current['expected']) for current,old in zip(answers,retained['rows']) if current['expected']!=old['expected']]
    assert len(changes)==1 and changes[0]['case']['key']=='axis-bound.grid.-308.1.0.above'
    (OWNER/'transport-amendment.json').write_text(json.dumps(dict(original_calls=211, original_disagreements=1, production_changes=False, unchanged_inputs=True, unchanged_grid=True, changed_scalar_transports=changes, qualification='400-digit native SymPy exact rational evaluation and independent 4096-bit native mpmath division agree before binary64 conversion. Original SymPy Rational.__float__ used its default short evaluation and differed by one subnormal spacing; retain every original answer and observation.'),indent=2)+'\n')
    (OWNER/'predictions.json').write_text(json.dumps(answers,indent=2,allow_nan=False)+'\n')
    rows=[]
    for case,answer in zip(items,answers):
        try:
            with np.errstate(all='raise'): result=utils.round_up_to_nearest_5(case['value'])
            actual=dict(value=result,type=type(result).__name__)
        except Exception as error:actual=dict(error=type(error).__name__)
        rows.append(dict(**answer,actual=actual,passed=actual==answer['expected']))
    changes=[name for name,sha in sources.items() if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha]
    data=dict(status='finished',actual_calls=len(rows),failed=sum(not r['passed'] for r in rows),rows=rows,
              sources=sources,source_changes=changes,sympy_version=sp.__version__,
              scope='Complete scalar display-bound profiles, finite/unsupported/missing admission and exact returned types. Native SymPy rationals enumerate half-decade candidates; custom display policy, no independent scientific-method vote.')
    (OWNER/'before.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({k:data[k] for k in ('actual_calls','failed','source_changes')}),flush=True)

if __name__=='__main__':run()
