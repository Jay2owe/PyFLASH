"""Whole trace carrier/refusal profiles using native exact point distances."""
from pathlib import Path
import hashlib,inspect,json,shutil,time

BASE=Path.home()/'AppData/Local/PyFLASH'
OWNER=BASE/'trace-carrier-and-domain-original-20261008-v2'
GATE=BASE/'whole-image-tables-current-installed-20261008-v1/run.json'

def cases():
    patterns={'ordinary':([0,3,1],[0,4,1]),'restart':([100,0,1,2],[0,1,2,3]),
        'duplicates':([0,0,1,1,2],[0,0,1,1,2]),'distance-tie':([0,1,-1,0],[0,1,1,2]),
        'slope-boundary':([5,3,1],[0,1,2])}
    carriers=('list','tuple','int8','uint8','int64','uint64','float16','float32','float64','longdouble','bool','object','readonly-object')
    for name,(x,y) in patterns.items():
        for carrier in carriers:
            if carrier.startswith('uint') and min(x+y)<0:continue
            yield dict(key='trace-profile.'+name+'.'+carrier,x=x,y=y,carrier=carrier,kind='valid')
    big=2**2048
    dense_x=[0,big]+[i%7 for i in range(63)]
    dense_y=[0,1]+[i+2 for i in range(63)]
    for name,x,y in [('proposal-overflow',dense_x,dense_y),
            ('exact-large-coordinates',[big,big+3,big+1],[0,4,1]),
            ('mixed-original-cell',[2**60,0.,2**60+1],[0,1,2])]:
        for carrier in ('list','tuple','object','readonly-object'):
            yield dict(key='trace-profile.'+name+'.'+carrier,x=x,y=y,carrier=carrier,kind='valid')
    for name,x,y,domain in [('empty',[],[],'paired finite'),('single',[1],[1],'paired finite'),
        ('length',[1,2],[1],'paired finite'),('matrix',[[1,2]],[[1,2]],'paired finite'),
        ('scalar',1,2,'paired finite'),('missing',None,None,'paired finite'),
        ('nan',[1,float('nan')],[1,2],'paired finite'),('infinity',[1,2],[1,float('inf')],'paired finite'),
        ('complex-zero',[0j,1+0j],[0,1],'paired finite'),('complex',[1j,1+2j],[0,1],'paired finite'),
        ('text',['0','1'],[0,1],'paired finite'),('horizontal',[0,1,2],[1,1,1],'downward path')]:
        for carrier in ('literal','array','readonly-array'):
            yield dict(key='trace-profile.refusal.'+name+'.'+carrier,x=x,y=y,carrier=carrier,kind='refusal',message=domain)

def inputs(case):
    import numpy as np
    x,y=case['x'],case['y'];carrier=case['carrier']
    if carrier in ('literal','list'):return x,y
    if carrier=='tuple':return tuple(x),tuple(y)
    dtype=object if carrier in ('object','readonly-object') else None if 'array' in carrier else carrier
    x,y=np.asarray(x,dtype=dtype),np.asarray(y,dtype=dtype)
    if carrier.startswith('readonly'):x.flags.writeable=y.flags.writeable=False
    return x,y

def prediction(case):
    import numpy as np
    import sympy as sp
    if case['kind']=='refusal':return dict(error='ValueError',message_contains=case['message'])
    x,y=inputs(case)
    def exact(v):
        if isinstance(v,(bool,int,np.integer,np.bool_)):return sp.Integer(int(v))
        return sp.Rational(*v.as_integer_ratio())
    points=[sp.Point2D(exact(a),exact(b),evaluate=False) for a,b in zip(x,y)]
    eligible=list(range(len(points)));answer=[];distance_comparisons=0
    while len(eligible)>1:
        minimum=min(points[i].y for i in eligible)
        top=[i for i in eligible if points[i].y==minimum]
        current=max(top,key=lambda i:points[i].x);start=current;path=[current]
        while True:
            options=[i for i in eligible if points[i].y>points[current].y]
            if not options:break
            distances=[points[current].distance(points[i])**2 for i in options]
            distance_comparisons+=len(distances)
            chosen=options[min(range(len(options)),key=lambda i:distances[i])]
            if points[chosen].x-points[current].x < -2*(points[chosen].y-points[current].y):break
            path.append(chosen);current=chosen
        if len(path)>1:answer=path;break
        eligible.remove(start)
    if not answer:return dict(error='ValueError',message_contains='downward path')
    def dtype(values):
        # The declared storage policy preserves original large integer cells
        # whenever a Python mixed-float sequence would discard a digit.
        naive=np.asarray(values)
        if not isinstance(values,np.ndarray) and naive.dtype.kind in 'fc':
            if any(isinstance(v,int) and v!=float(n.real) for v,n in zip(values,naive)):
                return 'object'
        return str(naive.dtype)
    return dict(selected_x=[int(x[i]) if isinstance(x[i],(np.integer,np.bool_)) else x[i] for i in answer],
        selected_y=[int(y[i]) if isinstance(y[i],(np.integer,np.bool_)) else y[i] for i in answer],
        indices=answer,x_dtype=dtype(x),y_dtype=dtype(y),native_distance_comparisons=distance_comparisons)

def encode(value):
    import numpy as np
    if isinstance(value,np.floating):return encode(float(value))
    if isinstance(value,np.generic):return encode(value.item())
    if isinstance(value,complex):return {'real':value.real,'imaginary':value.imag}
    if isinstance(value,list):return [encode(v) for v in value]
    if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
    if isinstance(value,float) and not __import__('math').isfinite(value):return repr(value)
    return value

def run():
    assert not OWNER.exists();OWNER.mkdir()
    deadline=time.monotonic()+28800
    while not GATE.exists() or json.loads(GATE.read_text()).get('status')!='finished':
        if time.monotonic()>deadline:raise TimeoutError('Earlier owned check did not finish')
        time.sleep(5)
    import numpy as np
    import sympy as sp
    from PyFLASH import utils
    paths=[Path(utils.__file__),Path(__file__)]
    sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for i,p in enumerate(paths):shutil.copyfile(p,OWNER/('original-'+str(i)+'-'+p.name))
    (OWNER/'native-distance-source.py').write_text(inspect.getsource(sp.Point2D.distance),encoding='utf-8')
    items=list(cases());predictions=[dict(case=encode(case),expected=encode(prediction(case))) for case in items]
    (OWNER/'predictions.json').write_text(json.dumps(predictions,indent=2)+'\n')
    rows=[]
    for case,predicted in zip(items,predictions):
        x,y=inputs(case);before_x=np.array(x,dtype=object,copy=True);before_y=np.array(y,dtype=object,copy=True)
        expected=predicted['expected'];actual=None;error=None
        try:
            a,b,indices=utils.trace_downward_nearest(x,y)
            actual=dict(selected_x=encode(a.tolist()),selected_y=encode(b.tolist()),indices=indices.tolist(),x_dtype=str(a.dtype),y_dtype=str(b.dtype))
            assert actual=={k:v for k,v in expected.items() if k not in ('x','native_distance_comparisons')}
            np.testing.assert_array_equal(np.array(x,dtype=object),before_x)
            np.testing.assert_array_equal(np.array(y,dtype=object),before_y)
            a[0]=0;b[0]=0
            np.testing.assert_array_equal(np.array(x,dtype=object),before_x)
            np.testing.assert_array_equal(np.array(y,dtype=object),before_y)
        except ValueError as exc:
            actual=dict(error='ValueError',message=str(exc))
            if expected.get('error')!='ValueError' or expected['message_contains'] not in str(exc):error=str(exc)
        except Exception as exc:error=type(exc).__name__+': '+str(exc)
        rows.append(dict(**predicted,actual=actual,passed=error is None,error=error))
    changes=[name for name,sha in sources.items() if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha]
    data=dict(status='finished',actual_calls=len(rows),failed=sum(not r['passed'] for r in rows),rows=rows,sources=sources,source_changes=changes,
        scope='Complete custom trace carrier and refusal profiles; native SymPy point distances plus authored selection policy, complete returned coordinates/indices/storage and copy ownership, no independently published full-trace method vote')
    (OWNER/'before.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({k:data[k] for k in ('actual_calls','failed','source_changes')}),flush=True)

if __name__=='__main__':run()
