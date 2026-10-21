"""Freeze exact original represented means through object and sentinel storage."""
from pathlib import Path
import contextlib,io,json,hashlib,csv,math
from decimal import Decimal,localcontext
from statistics import mean
import mpmath as mp
import pandas as pd
from PyFLASH.experiment import MiniExperiment
from PyFLASH.markers import Attribute
from reproducibility.scientific_utility_contract import table
from reproducibility.reference_runtime import execute_queries,values
OWNER=Path(__file__).resolve().parent
SENTINEL='NOT_INCLUDED_IN_EXPERIMENT'

def cases():
    samples={
        'integer-rounding':[9007199254740993,SENTINEL,9007199254740994],
        'negative-integer-rounding':[-9007199254740993,SENTINEL,-9007199254740994],
        'integer-boundary':[9007199254740991,SENTINEL,2,2],
        'unsigned-boundary':[2**64-1,SENTINEL,2**64-2],
        'mixed-real':[9007199254740993,SENTINEL,.5],
        'large':[1e308,SENTINEL,1e308],
        'cancellation':[1e308,SENTINEL,1.,-1e308],
        'subnormal':[5e-324,SENTINEL,5e-324],
        'missing':[1,None,SENTINEL,3],
        'excluded':[SENTINEL,None,SENTINEL],
        'ordinary-object':[1,3,5],
        'integer-object':[9007199254740993,9007199254740994],
    }
    for key,sample in samples.items():
        for route in ('direct','csv'):
            for progress in (False,True):
                yield {'key':'.'.join((key,route,str(progress))),'values':sample,'route':route,'progress':progress}

def original_values(case):
    return [value for value in case['values'] if value is not None and value!=SENTINEL]

def answer(case):
    numbers=original_values(case)
    if not numbers:return SENTINEL
    with mp.workprec(4096):
        arbitrary=float(mp.fsum(mp.mpf(number) for number in numbers)/len(numbers))
    with localcontext() as context:
        context.prec=2048
        decimal=float(sum((Decimal.from_float(number) if isinstance(number,float) else Decimal(number)
                           for number in numbers),Decimal(0))/Decimal(len(numbers)))
    control=float(mean(numbers))
    assert arbitrary==decimal==control
    return arbitrary

def frame(case):
    return pd.DataFrame({'AnimalName':['A1']*len(case['values'])+['B2']*3,
                         'Value':pd.Series(case['values']+[3,SENTINEL,5],dtype=object)})

def expected(case):
    return pd.DataFrame({'AnimalName':['A1','B2'],'Value':[answer(case),4.],'Condition':['A','B']})

def production(case,expect,folder):
    experiment=MiniExperiment('Original exact object mean controls',str(folder))
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    original=frame(case)
    inputs={}
    if case['route']=='csv':
        source=folder/'Data.csv'
        with source.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.writer(stream);writer.writerow(original.columns);writer.writerows(original.itertuples(index=False,name=None))
        inputs[source.name]=hashlib.sha256(source.read_bytes()).hexdigest()
        with contextlib.redirect_stdout(io.StringIO()):experiment.importCSVs(progress=case['progress'])
    else:
        experiment.data={'Data':Attribute('Data',original,experiment)}
    carrier=experiment.data['Data'];before=table(carrier.df);alias=carrier.df
    try:
        with contextlib.redirect_stdout(io.StringIO()):result=experiment.createSummary(progress=case['progress'])
        pd.testing.assert_frame_equal(result,expect,check_exact=True)
        assert table(carrier.df)==before and carrier.df is alias
        assert result is experiment.summary is experiment.summaries['SCN']
        assert all(hashlib.sha256((folder/name).read_bytes()).hexdigest()==sha for name,sha in inputs.items())
        return {'passed':True,'actual':table(result),'input':before}
    except Exception as error:
        return {'passed':False,'error':type(error).__name__+': '+str(error),
                'actual':table(experiment.summary) if hasattr(experiment,'summary') else None,'input':before}

def query(case):
    numbers=original_values(case)
    return {'key':case['key'],'code':'mean(c('+','.join(repr(float(v)) for v in numbers)+'))' if numbers else 'NA_real_'}

def freeze():
    output=OWNER/'object-means-original';output.mkdir(exist_ok=False)
    import PyFLASH.experiment as module
    sources=[Path(module.__file__),Path(__import__('PyFLASH._summary_math',fromlist=['x']).__file__),Path(__file__)]
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before={str(p):digest(p) for p in sources};items=list(cases())
    native=execute_queries([query(case) for case in items],output/'native',name='original-object-double-transport')
    rows=[]
    for i,(case,result) in enumerate(zip(items,native['rows'],strict=True)):
        expect=expected(case)
        rows.append({'case':case,'native':result,'expected':table(expect),'independent_mean':answer(case),
                     **production(case,expect,output/'cases'/str(i))})
    after={str(p):digest(p) for p in sources};assert before==after
    record={'source_unchanged':True,'sources':before,'actual_calls':len(rows),
            'failed':sum(not row['passed'] for row in rows),'rows':rows,
            'independent_engines':'mpmath 4096-bit binary arithmetic and Decimal 2048-digit decimal arithmetic; statistics is a shared rational control.',
            'native_R_convention':'Original R double transport rounds large integers before its calculation. Retained unchanged, not counted as exact-integer reference.'}
    (output/'before.json').write_text(json.dumps(record,indent=2)+'\n')
    for path in sources:(output/('original-'+path.name)).write_bytes(path.read_bytes())
    print(json.dumps({k:record[k] for k in ('actual_calls','failed','source_unchanged')}),flush=True)
if __name__=='__main__':freeze()
