"""Independent native-R tracing, smoothing and GEOS boundary measurements."""
import copy,json,math
from pathlib import Path
from reproducibility import marker_nearest_reference as base

ROOT=Path(base.__file__).resolve().parents[1]
ORIGINAL=ROOT/'reproducibility/reference-sources/ventricle-row-ownership/ventricle-row-controls-frozen-before-v2/frozen-before.json'
FIELDS=('AnimalName','ImageROI','Hemisphere','Region','ROI')


def cases():
    result=[]
    for row in json.loads(ORIGINAL.read_text(encoding='utf-8'))['rows']:
        case=copy.deepcopy(row['case'])
        case['key']='ventricle-native.legacy.'+case['key']
        case['marker_groups']=['Region'];case['roi_groups']=['Region']
        result.append(case)
    template=copy.deepcopy(result[0])
    for field in ('AnimalName','ImageROI','Hemisphere','ROI'):
        case=copy.deepcopy(template);case['key']='ventricle-native.shared-region-different-'+field
        case['marker_groups']=['Region',field];case['roi_groups']=['Region',field]
        case['rows']=[{'region':'one',field:group,'x':x,'y':40.,'z':1.}
                      for group,x in (('first',1.),('second',30.),('first',8.),('second',42.))]
        case['rois']=[{'region':'one',field:group,'x':[x]*9,'y':[10.*j for j in range(9)]}
                      for group,x in (('second',40.),('first',5.))]
        result.append(case)
    case=copy.deepcopy(result[-4]);case['key']='ventricle-native.missing-subject-labels'
    for row in case['rows']:
        if row['AnimalName']=='first':row['AnimalName']=None
    for row in case['rois']:
        if row['AnimalName']=='first':row['AnimalName']=None
    result.append(case)
    case=copy.deepcopy(result[-1]);case['key']='ventricle-native.absent-other-subject'
    case['rois']=case['rois'][:1];result.append(case)
    native=json.loads((ROOT/'reproducibility/reference-sources/marker-calibration/native-imagej-v1/native.json').read_text(encoding='utf-8'))
    for pitch in range(3):
        objects=native['cases'][2*pitch:2*pitch+2]
        for missing in (False,True):
            case={'key':f'ventricle-native.calibrated-{pitch}.missing-line-{missing}',
                'marker_groups':['Region','AnimalName'],'roi_groups':['Region','AnimalName'],
                'pixels_per_micron':1.,'rows':[],
                'rois':[{'region':'SCN1','AnimalName':'Subject1',
                         'x':None if missing else [5.]*10,'y':list(range(10))}],
                'native_objects':objects}
            for item in objects:
                x,y,z=item['physical_centre']
                case['rows'].append({'region':'SCN1','AnimalName':'Subject1','x':x,'y':y,'z':z,
                                     'count':1,'pitch':item['pitch']})
            result.append(case)
    for kind in ('valid-zero-depth','zero-count','mixed-row-pitches'):
        case=copy.deepcopy(result[-2]);case['key']='ventricle-native.'+kind
        if kind=='valid-zero-depth':case['rows'][0]['z']=0.
        elif kind=='zero-count':case['rows'][0]['count']=0
        else:
            case['rows'][0]['pitch']=[.25,.5,2.]
            case['rows'][1]['pitch']=[2.,3.,.5]
        case.pop('native_objects',None)
        result.append(case)
    return result


TRACE='''
trace_line <- function(x,y) {
 starts <- order(y,-x,seq_along(x))
 for (start in starts) {
  path <- start; current <- start
  repeat {
   candidates <- which(y>y[current])
   if (!length(candidates)) break
   distances <- (x[candidates]-x[current])^2+(y[candidates]-y[current])^2
   next_index <- candidates[which.min(distances)]
   if (x[next_index]-x[current] < -2*(y[next_index]-y[current])) break
   path <- c(path,next_index); current <- next_index
  }
  if (length(path)>1) {
   smooth <- function(values) {
    padded <- c(rep(values[1],4),values,rep(tail(values,1),4))
    vapply(seq_along(values),function(i) sum(padded[i:(i+8)])/9,numeric(1))
   }
   return(cbind(smooth(x[path]),smooth(y[path])))
  }
 }
 stop("No downward path")
}
project <- function(point,line) {
 best <- Inf; nearest <- c(NA_real_,NA_real_)
 for (j in seq_len(nrow(line)-1)) {
  first <- line[j,]; vector <- line[j+1,]-first
  denominator <- sum(vector^2)
  weight <- if (denominator==0) 0 else max(0,min(1,sum((point-first)*vector)/denominator))
  candidate <- first+weight*vector
  distance <- sqrt(sum((point-candidate)^2))
  if (distance<best) { best <- distance; nearest <- candidate }
 }
 c(best,nearest)
}
'''


def group(case,row,roi=False):
    fields=[field for field in FIELDS if field in case['marker_groups'] and field in case['roi_groups']]
    return tuple(row.get('region') if field=='Region' else row.get(field) for field in fields)


def query(case):
    commands=[TRACE,'answer <- numeric(0)']
    rois=case.get('argument_rois',case['rois'])
    for row in case['rows']:
        matched=[roi for roi in rois if group(case,roi,True)==group(case,row)]
        valid=(all(value is not None and math.isfinite(float(value)) for value in (row['x'],row['y'],row['z']))
               and (row['z']!=0 or 'pitch' in row) and row.get('count',1)!=0)
        if not matched or not valid:
            commands.append('answer <- c(answer,Inf)');continue
        assert len(matched)==1
        roi=matched[0]
        sx,sy=(row['pitch'][:2] if 'pitch' in row else (1/case['pixels_per_micron'],)*2)
        if roi['x'] is None:
            commands.append('answer <- c(answer,'+base.number(1024*sx-row['x'])+')');continue
        commands.extend([
            'line <- trace_line('+base.vector(roi['x'])+','+base.vector(roi['y'])+')',
            'line[,1] <- line[,1]*'+base.number(sx),
            'line[,2] <- line[,2]*'+base.number(sy),
            'answer <- c(answer,project(c('+base.number(row['x'])+','+base.number(row['y'])+'),line)[1])'])
    commands.append('answer')
    return {'key':case['key'],'code':'local({\n'+'\n'.join(commands)+'\n})'}


def trace_queries(case):
    queries=[]
    for index,roi in enumerate(case.get('argument_rois',case['rois'])):
        if roi['x'] is not None:
            queries.append({'key':case['key']+'.line-'+str(index),
                'code':'local({'+TRACE+'; as.vector(t(trace_line('+base.vector(roi['x'])+','+base.vector(roi['y'])+')))})'})
    return queries


def geos_answer(case,lines):
    from shapely.geometry import LineString,Point
    answers=[];rois=case.get('argument_rois',case['rois'])
    for row in case['rows']:
        matched=[(index,roi) for index,roi in enumerate(rois) if group(case,roi,True)==group(case,row)]
        valid=(all(value is not None and math.isfinite(float(value)) for value in (row['x'],row['y'],row['z']))
               and (row['z']!=0 or 'pitch' in row) and row.get('count',1)!=0)
        if not matched or not valid:answers.append('__inf__');continue
        assert len(matched)==1
        index,roi=matched[0]
        sx,sy=(row['pitch'][:2] if 'pitch' in row else (1/case['pixels_per_micron'],)*2)
        if roi['x'] is None:answers.append(1024*sx-row['x']);continue
        raw=lines[case['key']+'.line-'+str(index)]
        line=LineString([(raw[j]*sx,raw[j+1]*sy) for j in range(0,len(raw),2)])
        answers.append(line.distance(Point(row['x'],row['y'])))
    return answers


def encode(value):
    if isinstance(value,float) and not math.isfinite(value):
        return '__nan__' if math.isnan(value) else '__inf__' if value>0 else '__neginf__'
    if isinstance(value,list):return [encode(item) for item in value]
    if isinstance(value,dict):return {key:encode(item) for key,item in value.items()}
    return value
