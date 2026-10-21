"""Native full CSV summaries, shared subject factors and empty-table lifecycle."""
from pathlib import Path
import contextlib,csv,hashlib,io,itertools,json,shutil,sys,time,traceback
ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
BASE=Path.home()/'AppData/Local/PyFLASH'
OWNER=BASE/'whole-mini-shared-factors-original-20261008-v1'
GATE=BASE/'new-policies-and-direct-release-20261008-v1/run.json'

def cases():
    rows=[dict(key='mini-shared.'+'.'.join(map(str,values)),tables=values[0],factors=values[1],codes=values[2],
        route=values[3],progress=values[4],images=values[5],sparse=values[6],conflict=None)
      for values in itertools.product(range(5),(1,2),(False,True),('steps','process'),(False,True),(False,True),(False,True))]
    for factor,progress,route,images,count in itertools.product(('Treatment','Sex'),(False,True),('steps','process'),(False,True),(2,3)):
        rows.append(dict(key=f'mini-shared.conflict.{factor}.{progress}.{route}.{images}.{count}',tables=count,factors=2,
            codes=False,route=route,progress=progress,images=images,sparse=False,conflict=factor))
    assert len(rows)==352
    for count,nf,codes,route,progress,images in itertools.product((2,3,4),(1,2),(False,True),('steps','process'),(False,True),(False,True)):
        rows.append(dict(key=f'mini-shared.late.{count}.{nf}.{codes}.{route}.{progress}.{images}',tables=count,factors=nf,
            codes=codes,route=route,progress=progress,images=images,sparse=False,conflict=None,late_first=True))
    assert len(rows)==448
    for count,nf,codes,route,progress,images,late in itertools.product((2,3,4),(1,2),(False,True),('steps','process'),(False,True),(False,True),(False,True)):
        rows.append(dict(key=f'mini-shared.mixed.{count}.{nf}.{codes}.{route}.{progress}.{images}.{late}',tables=count,factors=nf,
            codes=codes,route=route,progress=progress,images=images,sparse=False,conflict=None,late_first=late,mixed_codes=True))
    assert len(rows)==640
    return rows

def factors(case):return ['Treatment','Sex'][:case['factors']]

def inputs(case):
    result={}
    for j in range(1,case['tables']+1):
        text=io.StringIO(newline='');writer=csv.writer(text)
        writer.writerow(['AnimalName',*factors(case),'Amount'+str(j)])
        for index,(animal,offset) in enumerate(zip(('A1','A2','B1','B2'),(0,10,20,30))):
            if case['sparse'] and (j==2 and animal=='A2' or j==3 and animal=='B1'):continue
            treatment='Control' if index<2 else 'Treated';sex='F' if index%2==0 else 'M'
            if j==2 and animal=='A1':
                if case['conflict']=='Treatment':treatment='Treated'
                if case['conflict']=='Sex':sex='M'
            use_codes=case['codes'] ^ bool(case.get('mixed_codes') and j%2==0)
            metadata=[('001' if treatment=='Control' else '002') if use_codes else treatment]
            if case['factors']==2:metadata.append(('0' if sex=='F' else '1') if use_codes else sex)
            for value in (1,3):writer.writerow([animal,*metadata,value+offset+j])
        content=text.getvalue()
        if case.get('late_first') and j==1:
            rows=list(csv.reader(io.StringIO(content)));filtered=io.StringIO(newline='')
            csv.writer(filtered).writerows([rows[0],*(row for row in rows[1:] if row[0]!='B2')])
            content=filtered.getvalue()
        result['Data'+str(j)+'.csv']=content
    return result

def query(case):
    declared='c('+','.join(json.dumps(name) for name in factors(case))+')'
    tables='list('+','.join('read.csv(text='+json.dumps(text)+',colClasses="character",check.names=FALSE)' for text in inputs(case).values())+')'
    code='''local({
      fs<-FACTORS; tables<-TABLES; out<-NULL; invalid<-FALSE
      for(j in seq_along(tables)) {
        d<-tables[[j]]; amount<-paste0("Amount",j);d[[amount]]<-as.numeric(d[[amount]])
        m<-aggregate(d[amount],by=list(AnimalName=d$AnimalName),FUN=mean)
        metadata<-d[!duplicated(d$AnimalName),c("AnimalName",fs),drop=FALSE]
        m<-merge(m,metadata,by="AnimalName",sort=TRUE)
        if(is.null(out)) out<-m else {
          paired<-merge(out[c("AnimalName",fs)],m[c("AnimalName",fs)],by="AnimalName",suffixes=c(".left",".right"))
          normalize<-function(v,f) {
            if(f=="Treatment")v<-ifelse(v=="001","Control",ifelse(v=="002","Treated",v))
            if(f=="Sex")v<-ifelse(v=="0","F",ifelse(v=="1","M",v))
            v
          }
          for(f in fs) if(any(normalize(paired[[paste0(f,".left")]],f)!=normalize(paired[[paste0(f,".right")]],f)))invalid<-TRUE
          original_names<-names(out)
          out<-merge(out,m,by="AnimalName",all=TRUE,sort=TRUE,suffixes=c(".left",".right"))
          for(f in fs) {
            left<-out[[paste0(f,".left")]];right<-out[[paste0(f,".right")]]
            out[[f]]<-ifelse(is.na(left),right,left)
          }
          out<-out[c(original_names,amount)]
        }
      }
      if(invalid) "REFUSE" else {
        if(is.null(out))out<-data.frame(AnimalName=character(),Condition=character(),stringsAsFactors=FALSE)
        else out$Condition<-gsub("[^A-Za-z]","",out$AnimalName)
        encode<-function(d) {
          c(as.character(nrow(d)),as.character(ncol(d)),names(d),
            unlist(lapply(seq_len(nrow(d)),function(i) vapply(d,function(col) {
              v<-col[i];if(is.na(v))"N" else if(is.numeric(v))paste0("D:",sprintf("%.17g",v))else paste0("S:",v)
            },character(1))),use.names=FALSE))
        }
        pre<-encode(out)
        for(f in fs) {
          if(!f%in%names(out))out[[f]]<-character(nrow(out))
          if(f=="Treatment")out[[f]]<-ifelse(out[[f]]=="001","Control",ifelse(out[[f]]=="002","Treated",out[[f]]))
          if(f=="Sex")out[[f]]<-ifelse(out[[f]]=="0","F",ifelse(out[[f]]=="1","M",out[[f]]))
        }
        out$Condition<-if(nrow(out))apply(out[fs],1,paste0,collapse="")else character()
        c(pre,"@POST@",encode(out))
      }
    })'''.replace('FACTORS',declared).replace('TABLES',tables)
    return dict(key=case['key'],code=code)

def decode(tokens):
    import pandas as pd
    count,columns=int(tokens[0]),int(tokens[1]);names=tokens[2:2+columns];values=tokens[2+columns:]
    assert len(values)==count*columns
    data={}
    for column,name in enumerate(names):
        cells=values[column::columns]
        if name.startswith('Amount'):data[name]=pd.Series([float(cell[2:]) if cell!='N' else float('nan') for cell in cells],dtype=float)
        else:data[name]=pd.Series([cell[2:] if cell!='N' else None for cell in cells],dtype=object)
    return pd.DataFrame(data)

def expected(case,values):
    if values==['REFUSE']:return dict(error='ValueError')
    marker=values.index('@POST@')
    return dict(before=decode(values[:marker]),after=decode(values[marker+1:]))

def production(case,answer,folder):
    import pandas as pd
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.conditions import condition,conditionList,zipConditionLists
    from reproducibility.scientific_utility_contract import table
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    files=inputs(case)
    for name,text in files.items():(folder/name).write_text(text,encoding='utf-8',newline='')
    fingerprints={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in files}
    mappings={'Treatment':{'001':'Control','002':'Treated'}}
    if case['factors']==2:mappings['Sex']={'0':'F','1':'M'}
    experiment=MiniExperiment('Whole flat-table lifecycle',str(folder),factor_mappings=mappings)
    groups=conditionList([condition(label,label,None,'Treatment') for label in ('Control','Treated')])
    if case['factors']==2:
        sex=conditionList([condition(label,label,None,'Sex') for label in ('F','M')])
        groups=conditionList(zipConditionLists(groups,sex))
    previous_summary=experiment.summary.copy(deep=True);previous_summaries=getattr(experiment,'summaries',None);previous_items=dict(previous_summaries or {});observed={};caught=None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            if case['route']=='process':
                returned=experiment.processData(import_images=case['images'],progress=case['progress'])
                assert returned is None
            else:
                returned=experiment.importCSVs(progress=case['progress']);assert returned is experiment.data
                imported={name:carrier.df.copy(deep=True) for name,carrier in experiment.data.items()}
                returned=experiment.createSummary(progress=case['progress']);assert returned is experiment.summary
                for name,frame in imported.items():pd.testing.assert_frame_equal(experiment.data[name].df,frame,check_exact=True)
                if case['images']:experiment.importImages(progress=case['progress'])
            observed['before']=table(experiment.summary)
            assert 'error' not in answer,'Conflicting factors were accepted'
            pd.testing.assert_frame_equal(experiment.summary,answer['before'],check_exact=True)
            returned=experiment.set_condition_list(groups);assert returned is experiment.condition_list is groups
            observed['after']=table(experiment.summary)
            pd.testing.assert_frame_equal(experiment.summary,answer['after'],check_exact=True)
            assert experiment.summary is experiment.summaries['SCN']
            assert len(experiment.data)==case['tables']
            assert all(carrier.experiment is experiment for carrier in experiment.data.values())
            for name,text in files.items():
                source=list(csv.DictReader(io.StringIO(text)));frame=experiment.data[name[:-4]].df
                target=pd.DataFrame({'AnimalName':[row['AnimalName'] for row in source]})
                for factor in factors(case):target[factor]=[mappings.get(factor,{}).get(row[factor],row[factor]) for row in source]
                column='Amount'+name[4:-4];target[column]=pd.Series([int(row[column]) for row in source],dtype='int64')
                target['Condition']=[''.join(str(target.loc[i,f]) for f in factors(case)) for i in target.index]
                pd.testing.assert_frame_equal(frame,target,check_exact=True)
            if case['images']:assert experiment.images.empty and experiment.imagesDict=={}
            else:assert getattr(experiment,'images',None) is None and getattr(experiment,'imagesDict',{})=={}
    except Exception as exc:caught=exc
    observed['refusal']=None if caught is None else dict(type=type(caught).__name__,message=str(caught))
    unchanged=all(hashlib.sha256((folder/name).read_bytes()).hexdigest()==sha for name,sha in fingerprints.items())
    if 'error' in answer:
        passed=isinstance(caught,ValueError) and getattr(experiment,'summaries',None) is previous_summaries and unchanged
        passed=passed and dict(getattr(experiment,'summaries',{}) or {}).keys()==previous_items.keys()
        passed=passed and all(experiment.summaries[key] is value for key,value in previous_items.items())
        try:pd.testing.assert_frame_equal(experiment.summary,previous_summary,check_exact=True)
        except AssertionError:passed=False
    else:passed=caught is None and unchanged
    return dict(passed=passed,actual=observed,input_files_unchanged=unchanged,
        error=None if passed else (type(caught).__name__+': '+str(caught) if caught else 'Unexpected accepted conflict'))

def run():
    assert not OWNER.exists();OWNER.mkdir()
    (OWNER/'run.json').write_text(json.dumps(dict(status='waiting-for-owned-release-checks',passed=False,actual_calls=0)))
    deadline=time.monotonic()+28800
    while not GATE.exists() or json.loads(GATE.read_text()).get('status')!='finished':
        if time.monotonic()>deadline:raise TimeoutError('Owned preceding checks did not finish')
        time.sleep(5)
    assert shutil.disk_usage(BASE).free>512*1024**2
    from reproducibility.reference_runtime import execute_queries,values
    from reproducibility.scientific_utility_contract import table
    import PyFLASH.experiment as module
    paths=[Path(__file__),Path(module.__file__)];sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for path in paths:shutil.copyfile(path,OWNER/('original-'+path.name))
    rows=[]
    try:
        items=cases();native=execute_queries([query(case) for case in items],OWNER/'native',name='whole-flat-shared-factors',timeout=300)
        predicted=[dict(case=case,native=row,expected={key:table(value) if key!='error' else value for key,value in expected(case,values(row)).items()}) for case,row in zip(items,native['rows'],strict=True)]
        (OWNER/'predictions.json').write_text(json.dumps(predicted,indent=2)+'\n')
        for index,(case,row) in enumerate(zip(items,native['rows'],strict=True)):
            answer=expected(case,values(row));rows.append(dict(**predicted[index],**production(case,answer,OWNER/'cases'/str(index))))
        changes=[name for name,sha in sources.items() if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha]
        record=dict(status='finished',passed=all(row['passed'] for row in rows) and not changes,actual_calls=len(rows),failed=sum(not row['passed'] for row in rows),rows=rows,sources=sources,source_changes=changes,
          scope='Native R full CSV aggregation and consistent shared factor ownership, including zero tables, sparse subjects, categorical codes, all progress/image/process switches and explicit conflicts. Custom lifecycle contract, no independently published whole microscopy-pipeline vote.')
    except Exception as exc:record=dict(status='finished',passed=False,actual_calls=len(rows),rows=rows,sources=sources,error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc())
    (OWNER/'run.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k not in ('rows','sources','traceback')}),flush=True)
    return record['passed']
if __name__=='__main__':raise SystemExit(0 if run() else 1)
