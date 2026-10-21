"""Original CSV bytes and independent native-R/Python CSV identity routes.

CSV subject fields are opaque, trimmed text. Numeric-looking labels, leading
zeros and missing-value spellings are identities; only empty fields are missing.
"""
import csv, io, json

ALIASES=('AnimalName','Animal Name','Animal ID','ID','Id','id','Subject ID')
SAMPLES={
    'numeric': ['1','2','3'],
    'zeros': ['001','1','0002','2'],
    'near-integer': ['1','1.000009','1.000000001','2.00000001'],
    'big-integer': ['9007199254740992','9007199254740993','9223372036854775808'],
    'spellings': ['NA','NaN','nan','null','NULL','None'],
    'notation': ['1.0','1','1e0','+1','01'],
    'text': ['AD1','Control2',' alpha 3 ','A,B','A"B'],
    'empty': ['',' ','Subject1',''],
}
def cases():
    rows=[]
    for column in ALIASES:
        for name, identifiers in SAMPLES.items():
            for labels in (False, True):
                stream=io.StringIO(newline='')
                writer=csv.writer(stream, lineterminator='\n')
                writer.writerow([column,'Value'])
                writer.writerows((value,index+1) for index,value in enumerate(identifiers))
                label_stream=io.StringIO(newline='')
                label_writer=csv.writer(label_stream,lineterminator='\n')
                label_writer.writerow(['ID','Label'])
                label_writer.writerows((value.strip(),'Group'+str(index+1))
                                       for index,value in enumerate(identifiers) if value.strip())
                rows.append({'key':column+'.'+name+'.'+str(labels),'column':column,
                             'csv':stream.getvalue(),
                             'labels':label_stream.getvalue() if labels else None,
                             'explicit':column if column=='Subject ID' else None})
    return rows

def parsed(case):
    raw=list(csv.DictReader(io.StringIO(case['csv'])))
    identities=[row[case['column']].strip() for row in raw]
    label_map={row['ID'].strip():row['Label'] for row in csv.DictReader(io.StringIO(case['labels']))} if case['labels'] else {}
    return [{'AnimalName':label_map.get(identity,identity),'Value':int(row['Value'])}
            for identity,row in zip(identities,raw,strict=True) if identity]

def query(case):
    # Force character parsing in the published parser, preventing identifier
    # inference. Native labels remain strings, independently of Python parsing.
    code='d <- read.csv(text='+json.dumps(case['csv'])+',colClasses="character",check.names=FALSE,na.strings=NULL);'
    code+='ids <- trimws(d[['+json.dumps(case['column'])+']]);keep <- nzchar(ids);ids <- ids[keep];'
    if case['labels']:
        code+='labels <- read.csv(text='+json.dumps(case['labels'])+',colClasses="character",check.names=FALSE,na.strings=NULL);'
        code+='idx <- match(ids,trimws(labels[[1]]));hit <- !is.na(idx);ids[hit] <- labels[[2]][idx[hit]];'
    return {'key':case['key'],'code':'local({'+code+'ids})'}
