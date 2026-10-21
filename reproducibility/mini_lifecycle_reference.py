"""Freeze original R CSV means and subject/factor ownership across flat tables."""
from pathlib import Path
import csv,io,json,contextlib,hashlib,shutil
import pandas as pd
from reproducibility.reference_runtime import execute_queries,values
from reproducibility.scientific_utility_contract import table
OWNER=Path(__file__).resolve().parent

def cases():
    from itertools import product
    for count,subject,progress,images,codes,route in product(range(1,5),('AnimalName','Subject Code'),
                                      (False,True),(False,True),(False,True),('steps','process')):
        yield {'key':'.'.join(map(str,(count,subject,progress,images,codes,route))),
               'tables':count,'subject':subject,'progress':progress,'images':images,'codes':codes,'route':route}

def inputs(case):
    files={}
    for j in range(1,case['tables']+1):
        buffer=io.StringIO(newline='');writer=csv.writer(buffer)
        writer.writerow([case['subject']]+(['Treatment'] if j==1 else [])+['Amount'+str(j)])
        for animal,offset,treatment in (('A1',0,'Control'),('A2',10,'Control'),('B1',20,'Treated'),('B2',30,'Treated')):
            label=('001' if treatment=='Control' else '002') if case['codes'] else treatment
            for value in (1,3):
                writer.writerow([animal]+([label] if j==1 else [])+[value+offset+j])
        files['Data'+str(j)+'.csv']=buffer.getvalue()
    return files

def query(case):
    expressions=[]
    for text in inputs(case).values():
        expressions.append('local({d<-read.csv(text='+json.dumps(text)+',colClasses="character",check.names=FALSE); '
            'as.numeric(tapply(as.numeric(d[[ncol(d)]]),d[[1]],mean))})')
    return {'key':case['key'],'code':'c('+','.join(expressions)+')'}

def expected(case,numbers):
    animals=['A1','A2','B1','B2'];labels=['Control','Control','Treated','Treated']
    result=pd.DataFrame({'AnimalName':animals,'Amount1':pd.Series(numbers[:4],dtype=float),'Treatment':labels})
    for j in range(2,case['tables']+1):result['Amount'+str(j)]=pd.Series(numbers[4*(j-1):4*j],dtype=float)
    result['Condition']=labels
    raw={}
    for j in range(1,case['tables']+1):
        contents={'AnimalName':[a for a in animals for _ in (0,1)]}
        if j==1:contents['Treatment']=[label for label in labels for _ in (0,1)]
        contents['Amount'+str(j)]=[v+offset+j for offset in (0,10,20,30) for v in (1,3)]
        contents['Condition']=[label for label in labels for _ in (0,1)]
        if j!=1:contents['Treatment']=[label for label in labels for _ in (0,1)]
        raw['Data'+str(j)]=pd.DataFrame(contents)
    return result,raw

def production(case,expect,raw,folder):
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.conditions import condition,conditionList
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    files=inputs(case)
    for name,text in files.items():(folder/name).write_text(text,encoding='utf-8',newline='')
    digests={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in files}
    conditions=conditionList([condition('Control','Control',None,'Treatment'),condition('Treated','Treated',None,'Treatment')])
    experiment=MiniExperiment('Original full flat CSV lifecycle',str(folder),subject_column=case['subject'],
        factor_mappings={'Treatment':{'001':'Control','002':'Treated'}} if case['codes'] else {})
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            if case['route']=='process':
                result=experiment.processData(import_images=case['images'],progress=case['progress'])
                assert result is None
            else:
                imported=experiment.importCSVs(progress=case['progress'])
                assert imported is experiment.data
                result=experiment.createSummary(progress=case['progress'])
                assert result is experiment.summary
                if case['images']:experiment.importImages(progress=case['progress'])
            returned=experiment.set_condition_list(conditions)
        pd.testing.assert_frame_equal(experiment.summary,expect,check_exact=True)
        for name,expected_frame in raw.items():
            pd.testing.assert_frame_equal(experiment.data[name].df,expected_frame,check_exact=True)
            assert experiment.data[name].experiment is experiment
        assert returned is experiment.condition_list is conditions
        assert experiment.summary is experiment.summaries['SCN']
        assert all(hashlib.sha256((folder/name).read_bytes()).hexdigest()==sha for name,sha in digests.items())
        if case['images']:assert experiment.images.empty and experiment.imagesDict=={}
        return {'passed':True,'actual':table(experiment.summary),
                'raw_actual':{name:table(value.df) for name,value in experiment.data.items()}}
    except Exception as error:
        return {'passed':False,'error':type(error).__name__+': '+str(error),
                'actual':table(experiment.summary) if hasattr(experiment,'summary') else None,
                'raw_actual':{name:table(value.df) for name,value in experiment.data.items()}}

def freeze():
    output=OWNER/'lifecycle-original';output.mkdir(exist_ok=False)
    assert shutil.disk_usage(output).free>100*1024**2
    import PyFLASH.experiment as module
    source=Path(module.__file__);digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before=digest(source);items=list(cases())
    native=execute_queries([query(case) for case in items],output/'native',name='flat-csv-lifecycle')
    rows=[]
    for i,(case,row) in enumerate(zip(items,native['rows'],strict=True)):
        numbers=values(row)
        assert numbers==[float(2+offset+j) for j in range(1,case['tables']+1) for offset in (0,10,20,30)]
        expect,raw=expected(case,numbers)
        rows.append({'case':case,'native':row,'expected':table(expect),'raw_expected':{name:table(frame) for name,frame in raw.items()},
                     **production(case,expect,raw,output/'cases'/str(i))})
    assert digest(source)==before
    result={'source_unchanged':True,'source_sha256':before,'actual_calls':len(rows),
            'failed':sum(not row['passed'] for row in rows),'rows':rows,
            'scope':'CSV tables, factor metadata propagation and absent-image lifecycle only; acquired-image lifecycle remains separately gated.'}
    (output/'before.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'original-reference.py').write_bytes(Path(__file__).read_bytes())
    (output/'original-experiment.py').write_bytes(source.read_bytes())
    print(json.dumps({k:result[k] for k in ('actual_calls','failed','source_unchanged')}),flush=True)
if __name__=='__main__':freeze()
