"""Preserve dense whole-trajectory predictions using native R full search.

This custom tracing policy is functional geometry evidence, not a published
scientific tracing method. R searches every eligible original row; production
uses a bounded proposal for dense neighborhoods. No figure is saved.
"""
from pathlib import Path
import hashlib, json, shutil, sys, time

BASE = Path.home()/'AppData/Local/PyFLASH'
OWNER = BASE / 'dense-downward-trace-original-20261008-v1'
GATE = BASE / 'image-table-identity-private-20261008-v1/run.json'

def cases():
    for size in (33, 65, 129):
        patterns = {
            'far-first': [[0,0],[10000,1]]+[[i%7,i+2] for i in range(size-2)],
            'dense-ties': [[0,0],[10000,1]]+[[(-1 if i%2 else 1)*(i//2+1),i//2+2] for i in range(size-2)],
            'restart': [[100000,0],[0,1],[10000,2]]+[[i%5,i+3] for i in range(size-3)],
            'exact-slope': [[256,0],[10000,1]]+[[256-2*(i+2),i+2] for i in range(size-2)],
        }
        for name, points in patterns.items():
            for order, supplied in enumerate((points,list(reversed(points)),points[7:]+points[:7])):
                yield dict(key=f'dense-trace.{name}.{size}.order{order}',points=supplied)

def query(case):
    values=','.join(str(v) for p in case['points'] for v in p)
    # Separate complete relational search, with no production proposal/bounds.
    code='''local({p<-matrix(c(INPUTS),ncol=2,byrow=TRUE); active<-seq_len(nrow(p)); ans<-integer();
      while(length(active)>1) {
        starts<-active[p[active,2]==min(p[active,2])]; current<-starts[which.max(p[starts,1])]; start<-current; path<-current;
        repeat {
          nexts<-active[p[active,2]>p[current,2]]; if(!length(nexts)) break;
          delta<-sweep(p[nexts,,drop=FALSE],2,p[current,],"-");
          chosen<-nexts[which.min(rowSums(delta*delta))];
          if(p[chosen,1]-p[current,1] < -2*(p[chosen,2]-p[current,2])) break;
          current<-chosen; path<-c(path,current)
        }
        if(length(path)>1) {ans<-path; break}; active<-active[active!=start]
      }
      if(!length(ans)) numeric() else as.numeric(t(cbind(p[ans,,drop=FALSE],ans-1)))
    })'''.replace('INPUTS',values)
    return dict(key=case['key'],code=code)

def run():
    assert not OWNER.exists(); OWNER.mkdir()
    deadline=time.monotonic()+28800
    while not GATE.exists() or json.loads(GATE.read_text()).get('status')!='finished':
        if time.monotonic()>deadline: raise TimeoutError('Previous owned qualification did not finish')
        time.sleep(5)
    import numpy as np
    from PyFLASH import utils
    from reproducibility.reference_runtime import execute_queries
    paths=[Path(utils.__file__),Path(__file__)]
    sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for i,p in enumerate(paths): shutil.copyfile(p,OWNER / ('original-'+str(i)+'-'+p.name))
    inputs=list(cases()); (OWNER/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    answers=execute_queries([query(c) for c in inputs],OWNER/'native',name='dense-downward-trace')
    expected={row['key']:np.asarray(row['values']).reshape(-1,3).tolist() for row in answers['rows']}
    (OWNER/'predictions.json').write_text(json.dumps(expected,indent=2)+'\n')
    rows=[]
    branch_line=utils.trace_downward_nearest.__code__.co_firstlineno + next(
        i for i,line in enumerate(__import__('inspect').getsourcelines(utils.trace_downward_nearest)[0]) if 'eligible=y_order[lower:upper]' in line)
    for case in inputs:
        for carrier in ('int64','float64','list','tuple','readonly'):
            p=np.asarray(case['points'],dtype=float if carrier=='float64' else np.int64)
            x,y=p[:,0].copy(),p[:,1].copy()
            if carrier=='list': x,y=x.tolist(),y.tolist()
            if carrier=='tuple': x,y=tuple(x.tolist()),tuple(y.tolist())
            if carrier=='readonly': x.flags.writeable=y.flags.writeable=False
            original=np.column_stack((x,y)).copy(); visits=[]
            def trace(frame,event,arg):
                if frame.f_code is utils.trace_downward_nearest.__code__ and event=='line' and frame.f_lineno==branch_line:
                    visits.append(frame.f_locals['upper']-frame.f_locals['lower'])
                return trace
            actual=None; error=None
            try:
                sys.settrace(trace)
                a,b,indices=utils.trace_downward_nearest(x,y)
                actual=np.column_stack((a,b,indices)).tolist()
                assert a.dtype==np.asarray(x).dtype and b.dtype==np.asarray(y).dtype
                np.testing.assert_array_equal(np.column_stack((x,y)),original)
                if carrier=='readonly': assert not x.flags.writeable and not y.flags.writeable
                assert actual==expected[case['key']]
            except Exception as exc: error=type(exc).__name__+': '+str(exc)
            finally: sys.settrace(None)
            rows.append(dict(case=case,carrier=carrier,expected=expected[case['key']],actual=actual,
                             passed=error is None,error=error,dense_branch_neighborhoods=visits))
    changes=[name for name,sha in sources.items() if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha]
    data=dict(status='finished',actual_calls=len(rows),failed=sum(not r['passed'] for r in rows),rows=rows,
              sources=sources,source_changes=changes,dense_branch_calls=sum(bool(r['dense_branch_neighborhoods']) for r in rows),
              scope='Whole dense custom trajectories, full returned coordinates/indices/dtypes and input ownership; native R exhaustive-search functional policy, no extra independent scientific-method vote')
    (OWNER/'before.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({k:data[k] for k in ('actual_calls','failed','source_changes','dense_branch_calls')}),flush=True)

if __name__=='__main__': run()
