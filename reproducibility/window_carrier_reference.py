"""Freeze full-window carrier, width and admission answers before any repair."""
from pathlib import Path
import copy,hashlib,inspect,json,math,shutil,sys,time,traceback
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
BASE=Path.home()/'AppData/Local/PyFLASH'
OWNER=BASE/'whole-window-carriers-original-20261008-v1'
GATE=BASE/'whole-utility-and-image-controls-20261008-v1/run.json'

def encode(value):
    import numpy as np
    if isinstance(value,np.ndarray):return dict(shape=list(value.shape),dtype=str(value.dtype),values=encode(value.tolist()))
    if isinstance(value,np.generic):
        if value.dtype.kind=='c':return dict(real=encode(value.real),imaginary=encode(value.imag))
        if value.dtype.kind=='f':return dict(ratio=[str(v) for v in value.as_integer_ratio()]) if np.isfinite(value) else str(value)
        return encode(value.item())
    if isinstance(value,complex):return dict(real=encode(value.real),imaginary=encode(value.imag))
    if isinstance(value,float):return dict(hex=value.hex())
    if isinstance(value,(list,tuple)):return [encode(v) for v in value]
    if isinstance(value,dict):return {str(k):encode(v) for k,v in value.items()}
    if value is None or isinstance(value,(str,int,bool)):return value
    return dict(type=type(value).__module__+'.'+type(value).__name__,value=str(value))

def inputs(case):
    import numpy as np
    from fractions import Fraction
    from decimal import Decimal
    carrier=case['carrier'];pattern=case['pattern']
    values={'ordinary':[1,3,6,2,4],'signed':[1,-3,6,-2,4],
      'complex':[1+2j,3-5j,6+1j,2-3j,4+2j],
      'mixed':[2**53+1,1.,-(2**53),2,4.],
      'tiny':[float.fromhex('0x0.0000000000001p-1022')]*5,
      'empty':[],'matrix':[[1,2],[3,4]],'scalar':2,
      'text':['a','b','c'],'missing':[1,None,3],
      'decimal':[Decimal('1.1'),Decimal('2.2'),Decimal('3.3')],
      'fraction':[Fraction(1,3),Fraction(2,7),Fraction(-4,9)]}[pattern]
    if carrier=='list':data=copy.deepcopy(values)
    elif carrier=='tuple':data=tuple(copy.deepcopy(values))
    else:
        dtype=object if carrier in ('object','readonly-object') else np.float64 if carrier in ('readonly','strided') else np.dtype(carrier)
        data=np.asarray(values,dtype=dtype)
        if carrier=='strided':
            owner=np.empty(len(data)*2,dtype=data.dtype);owner[::2]=data;owner[1::2]=99;data=owner[::2]
        if carrier in ('readonly','readonly-object'):data.flags.writeable=False
    width=case['width']
    widths={'numpy-int':np.int64(3),'numpy-float':np.float64(3),'boolean':True,'none':None,'text':'3','complex':3+0j}
    return data,widths.get(width,width) if isinstance(width,str) else width

def cases():
    carriers=['bool','int8','uint8','int16','uint16','int32','uint32','int64','uint64',
      'float16','float32','float64','longdouble','complex64','complex128','clongdouble',
      'object','list','tuple','readonly','readonly-object','strided']
    rows=[]
    for carrier in carriers:
        for width in (-1,0,1,.5,2,3,4,7,'numpy-int','boolean'):
            rows.append(dict(key=f'window-carrier.ordinary.{carrier}.{width}',pattern='ordinary',carrier=carrier,width=width))
    for pattern,carriers in [('complex',['complex64','complex128','clongdouble','object','list','tuple','readonly-object']),
      ('mixed',['object','list','tuple','readonly-object']),('tiny',['float64','longdouble','object','list','tuple','readonly-object']),
      ('fraction',['object','list','tuple']),('decimal',['object','list','tuple']),
      ('text',['str','object','list','tuple']),('missing',['object','list','tuple']),
      ('empty',['float64','object','list','tuple']),('matrix',['float64','object','list','tuple']),
      ('scalar',['float64','object'])]:
        for carrier in carriers:
            for width in (1,2,3,7):rows.append(dict(key=f'window-carrier.{pattern}.{carrier}.{width}',pattern=pattern,carrier=carrier,width=width))
    for carrier in ('float64','object','list','tuple'):
        for width in ('numpy-float','none','text','complex',2.5):
            rows.append(dict(key=f'window-carrier.width-domain.{carrier}.{width}',pattern='ordinary',carrier=carrier,width=width))
    return rows

def prediction(case):
    import numpy as np
    import sympy as S
    from sympy.stats import FiniteRV,E
    from fractions import Fraction
    data,width=inputs(case);array=np.asarray(data)
    if width is None or isinstance(width,(str,complex)):return dict(error='TypeError')
    if width<2:return dict(output=encode(array),aliases_supplied_array=isinstance(data,np.ndarray))
    if isinstance(width,(float,np.floating)):return dict(error='TypeError')
    if array.ndim!=1 or not array.size:return dict(error='ValueError')
    if case['pattern'] in ('text','missing','decimal'):return dict(error='TypeError')
    width=int(width)
    # Literal list/tuple cells are the original measurements, before NumPy's
    # common-dtype coercion can erase an integer beside a floating cell.
    original_cells=list(data)
    padded=[original_cells[0]]*(width//2)+original_cells+[original_cells[-1]]*(width//2)
    dtype=object if array.dtype.kind=='O' else np.complex128 if array.dtype.kind=='c' else np.float64
    if array.dtype.kind in 'fc' and array.dtype.itemsize>(16 if array.dtype.kind=='c' else 8):dtype=array.dtype
    def exact(value):
        if isinstance(value,(bool,int,np.integer,np.bool_)):return S.Integer(int(value))
        if isinstance(value,Fraction):return S.Rational(value.numerator,value.denominator)
        return S.Rational(*value.as_integer_ratio())
    def mean(window):
        v=FiniteRV('OriginalWindowIndex',{S.Integer(i):S.Rational(1,len(window)) for i in range(len(window))},check=True)
        expression=S.Piecewise(*[(exact(value),S.Eq(v,i)) for i,value in enumerate(window[:-1])],(exact(window[-1]),True))
        return float(E(expression))
    complex_values=array.dtype.kind=='c' or any(isinstance(v,(complex,np.complexfloating)) for v in padded)
    out=[]
    for start in range(len(padded)-width+1):
        window=padded[start:start+width]
        out.append(complex(mean([v.real for v in window]),mean([v.imag for v in window])) if complex_values else mean(window))
    if complex_values and array.dtype.kind not in ('O','c'):dtype=np.complex128
    return dict(output=encode(np.asarray(out,dtype=dtype)),aliases_supplied_array=False)

def production(case,expected):
    import numpy as np
    from PyFLASH import utils
    data,width=inputs(case);before=encode(data)
    writable=data.flags.writeable if isinstance(data,np.ndarray) else None
    result=None;error=None
    try:result=utils.moving_average(data,width)
    except Exception as exc:error=exc
    assert encode(data)==before
    assert (data.flags.writeable if isinstance(data,np.ndarray) else None)==writable
    if 'error' in expected:
        assert error is not None and isinstance(error,{'TypeError':TypeError,'ValueError':ValueError}[expected['error']]),repr(error)
        return dict(error=type(error).__name__,declared_error=expected['error'],input_unchanged=True)
    assert error is None,repr(error)
    assert isinstance(result,np.ndarray)
    actual=dict(output=encode(result),aliases_supplied_array=result is data,input_unchanged=True)
    assert str(result.dtype)==expected['output']['dtype'] and list(result.shape)==expected['output']['shape']
    assert actual['aliases_supplied_array']==expected['aliases_supplied_array']
    if width<2:assert actual['output']==expected['output']
    else:
        target=np.asarray([complex(v['real']['hex'] and float.fromhex(v['real']['hex']),float.fromhex(v['imaginary']['hex']))
          if isinstance(v,dict) and 'real' in v else float.fromhex(v['hex']) for v in expected['output']['values']])
        np.testing.assert_allclose(np.asarray(result,dtype=target.dtype),target,rtol=1e-12,atol=0,equal_nan=True)
        original=encode(data);result.flat[0]=0 if result.flat[0]!=0 else 1;assert encode(data)==original
    return actual

def run():
    assert not OWNER.exists();OWNER.mkdir()
    def write(record):(OWNER/'run.json').write_text(json.dumps(record,indent=2)+'\n')
    write(dict(status='waiting-for-owned-utility-checks',passed=False,actual_calls=0))
    deadline=time.monotonic()+28800
    while not GATE.exists() or json.loads(GATE.read_text()).get('status')!='finished':
        if time.monotonic()>deadline:raise TimeoutError('Owned preceding checks did not finish')
        time.sleep(5)
    assert shutil.disk_usage(BASE).free>512*1024**2
    import numpy as np,sympy as S
    from sympy.stats import FiniteRV,E
    from PyFLASH import utils
    sources={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(__file__),Path(utils.__file__))}
    for path in (Path(__file__),Path(utils.__file__)):shutil.copyfile(path,OWNER/('original-'+path.name))
    native={}
    for function in (FiniteRV,E):
        path=Path(inspect.getsourcefile(function));relative=path.relative_to(Path(S.__file__).parent)
        target=OWNER/'native-source'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        native[str(relative)]=hashlib.sha256(path.read_bytes()).hexdigest()
    rows=[]
    try:
        # Every expected output/refusal is written before the first production call.
        predicted=[dict(case=case,expected=prediction(case)) for case in cases()]
        (OWNER/'predictions.json').write_text(json.dumps(predicted,indent=2)+'\n')
        write(dict(status='running',passed=False,actual_calls=0,sources=sources))
        for item in predicted:
            actual=None;error=None
            try:actual=production(item['case'],item['expected']);passed=True
            except Exception as exc:passed=False;error=type(exc).__name__+': '+str(exc)
            rows.append(dict(**item,actual=actual,passed=passed,error=error))
        changes=[name for name,sha in sources.items() if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha]
        record=dict(status='finished',passed=all(row['passed'] for row in rows) and not changes,actual_calls=len(rows),
          failed=sum(not row['passed'] for row in rows),rows=rows,sources=sources,source_changes=changes,native_sources=native,
          versions=dict(numpy=np.__version__,sympy=S.__version__),longdouble_bits=np.finfo(np.longdouble).bits,
          scope='Complete new carrier/width/admission/copy controls and native exact finite-index SymPy expectations, supporting declared edge-padded means; no new published whole smoothing implementation vote.')
    except Exception as exc:record=dict(status='finished',passed=False,actual_calls=len(rows),rows=rows,sources=sources,error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc())
    write(record);print(json.dumps({k:v for k,v in record.items() if k not in ('rows','sources','native_sources','traceback')}),flush=True)
    return record['passed']
if __name__=='__main__':raise SystemExit(0 if run() else 1)
