"""Freeze complete public score tables against original R and mpmath answers."""
from pathlib import Path
import json, math, contextlib, io, hashlib
import pandas as pd
import mpmath as mp
from reproducibility.reference_runtime import execute_queries, values
from reproducibility.scientific_utility_contract import table
OWNER=Path(__file__).resolve().parent

def cases():
    samples={
        'ordinary':([1.,2.,4.,8.],[8.,4.,2.,1.]),
        'equal':([2.,2.,2.,2.],[4.,4.,4.,4.]),
        'zero':([0.,1.,2.,4.],[4.,2.,1.,.5]),
        'negative-count':([-1.,1.,2.,4.],[4.,2.,1.,.5]),
        'zero-volume':([1.,2.,4.,8.],[0.,2.,1.,.5]),
        'negative-volume':([1.,2.,4.,8.],[-1.,2.,1.,.5]),
        'missing-count':([None,2.,4.,8.],[4.,2.,1.,.5]),
        'missing-volume':([1.,2.,4.,8.],[None,2.,1.,.5]),
        'overflow':([1e308,1e307,1e306,1e305],[1e-308,1e-307,1e-306,1e-305]),
        'underflow':([1e-308,1e-307,1e-306,1e-305],[1e308,1e307,1e306,1e305]),
        'mixed-range':([1e308,1.,1e-308,0.],[1e-308,1.,1e308,1.]),
        'subnormal':([5e-324,1e-323,1.5e-323,2e-323],[5e-324]*4),
    }
    samples = {
        'infinite-count': ([math.inf,2.,4.,8.],[8.,4.,2.,1.]),
        'negative-infinite-count': ([-math.inf,2.,4.,8.],[8.,4.,2.,1.]),
        'infinite-volume': ([1.,2.,4.,8.],[math.inf,4.,2.,1.]),
        'negative-infinite-volume': ([1.,2.,4.,8.],[-math.inf,4.,2.,1.]),
        'both-infinite': ([math.inf,2.,4.,8.],[math.inf,4.,2.,1.]),
        'all-infinite-count': ([math.inf]*4,[8.,4.,2.,1.]),
        'all-infinite-volume': ([1.,2.,4.,8.],[math.inf]*4),
        'mixed-infinite-count': ([math.inf,-math.inf,None,1.],[8.,4.,2.,1.]),
    }
    for key,(count,volume) in samples.items():
        for surface in ('SATotal','SurfaceTotal'):
            for area in ('%AreaMean','ROI_%AreaMean'):
                for progress in (False,True):
                    yield {'key':'.'.join((key,surface,area,str(progress))),
                           'count':count,'volume':volume,'surface':surface,'area':area,'progress':progress}

def r_vector(numbers):
    return 'c('+','.join('NA_real_' if v is None else 'Inf' if v==math.inf else '-Inf' if v==-math.inf else repr(v) for v in numbers)+')'

def query(case):
    return {'key':case['key'],'code':'''local({
        count <- COUNT; volume <- VOLUME;
        z <- function(x) { valid <- !is.na(x); out <- rep(NA_real_,length(x));
            if(any(valid)) { selected <- x[valid]; n <- length(selected);
            magnitude <- max(abs(selected));
            if(any(!is.finite(selected))) out[valid] <- as.numeric(base::scale(selected))
            else if(n<2 || magnitude==0 || all(selected==selected[1])) out[valid] <- 0
            else out[valid] <- as.numeric(base::scale(selected/magnitude))*sqrt(n/(n-1)) }; out }
        nonnegative <- function(x) { x[x<0] <- NA_real_; log1p(x) }
        burden <- rowMeans(cbind(z(nonnegative(c(1,2,4,8))),z(nonnegative(volume)),
                    z(nonnegative(c(2,4,8,16))),z(nonnegative(c(5,10,20,40)))),na.rm=TRUE);
        logratio <- rep(NA_real_,length(count)); valid <- !is.na(count) & !is.na(volume) & count>=0 & volume>0;
        logratio[valid & count==0] <- 0;
        take <- valid & count>0; delta <- log(count[take])-log(volume[take]);
        logratio[take] <- pmax(delta,0)+log1p(exp(-abs(delta)));
        c(burden,z(logratio))
    })'''.replace('COUNT',r_vector(case['count'])).replace('VOLUME',r_vector(case['volume']))}

def mp_scores(case):
    with mp.workprec(4096):
        def z(numbers):
            result=[math.nan]*len(numbers)
            valid=[(i,mp.mpf(x)) for i,x in enumerate(numbers) if x is not None and not mp.isnan(x)]
            if not valid:return result
            mean=mp.fsum(x for _,x in valid)/len(valid)
            std=mp.sqrt(mp.fsum((x-mean)**2 for _,x in valid)/len(valid))
            for i,x in valid:result[i]=float((x-mean)/std) if std else 0.
            return result
        log=lambda nums:[None if x is None or x<0 else mp.log1p(mp.mpf(x)) for x in nums]
        parts=[z(log(nums)) for nums in ([1,2,4,8],case['volume'],[2,4,8,16],[5,10,20,40])]
        burden=[math.fsum(part[i] for part in parts if not math.isnan(part[i]))/
                sum(not math.isnan(part[i]) for part in parts) for i in range(4)]
        logs=[None if c is None or v is None or c<0 or v<=0 else mp.log1p(mp.mpf(c)/mp.mpf(v))
              for c,v in zip(case['count'],case['volume'])]
        # The published summary standardizes represented log values; cast once
        # before standardization so underflowed log values follow float storage.
        return burden+z([None if x is None else float(x) for x in logs])

def input_frame(case):
    return pd.DataFrame({'AnimalName':['A1','B2','C3','D4'],'M_Count':case['count'],
        'M_VolumeTotal':case['volume'],'M_IntDenTotal':[1.,2.,4.,8.],
        'M_'+case['surface']:[2.,4.,8.,16.],'M_'+case['area']:[5.,10.,20.,40.]})

def expected(case, numbers):
    result=input_frame(case)
    result['Condition']=['A','B','C','D']
    result['M_burdenScore']=numbers[:4]
    result['M_fragmentationScore']=numbers[4:]
    return result

def production(case, expect):
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.markers import Attribute
    experiment=MiniExperiment('Original complete score tables',str(OWNER))
    frame=input_frame(case);carrier=Attribute('Measurements',frame,experiment)
    experiment.data={'Measurements':carrier}; original=table(frame)
    try:
        with contextlib.redirect_stdout(io.StringIO()):actual=experiment.createSummary(progress=case['progress'])
        pd.testing.assert_frame_equal(actual,expect,check_exact=False,rtol=2e-12,atol=2e-14)
        assert table(frame)==original and carrier.df is frame
        assert actual is experiment.summary and actual is experiment.summaries['SCN']
        return {'passed':True,'actual':table(actual),'input':original}
    except Exception as error:
        return {'passed':False,'error':type(error).__name__+': '+str(error),
                'actual':table(experiment.summary) if hasattr(experiment,'summary') else None,'input':original}

def freeze():
    output=OWNER/'scores-nonfinite-original';output.mkdir(exist_ok=False)
    import PyFLASH.experiment as module
    source=Path(module.__file__);digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before=digest(source);items=list(cases())
    native=execute_queries([query(case) for case in items],output/'native',name='marker-summary-scores')
    rows=[]
    for case,row in zip(items,native['rows'],strict=True):
        numbers=values(row);independent=mp_scores(case)
        for a,b in zip(numbers,independent,strict=True):
            assert (math.isnan(a) and math.isnan(b)) or math.isclose(a,b,rel_tol=2e-12,abs_tol=2e-14),(case['key'],a,b)
        expect=expected(case,numbers)
        rows.append({'case':case,'native':row,'mpmath':independent,'expected':table(expect),**production(case,expect)})
    assert digest(source)==before
    result={'source_unchanged':True,'source_sha256':before,'actual_calls':len(rows),
            'failed':sum(not row['passed'] for row in rows),'rows':rows}
    (output/'before.json').write_text(json.dumps(result,indent=2,allow_nan=True)+'\n')
    (output/'original-reference.py').write_bytes(Path(__file__).read_bytes())
    (output/'original-experiment.py').write_bytes(source.read_bytes())
    print(json.dumps({k:result[k] for k in ('actual_calls','failed','source_unchanged')}),flush=True)
if __name__=='__main__':freeze()
