"""Independent literal manual exclusions; outlier detection is separate."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,math
import numpy as np
import pandas as pd
from PyFLASH import exclusions
from reproducibility import manual_exclusion_reference as reference
FIXTURE=Path(__file__).with_name('fixtures')/'manual_exclusion_reference.json'

def cases():return json.loads(FIXTURE.read_text(encoding='utf-8'))['rows']

def capability(case):return 'PyFLASH.exclusions.'+case['api']

def owners(case):
    result=[capability(case)]
    if case.get('kind')=='handoff':result.append('PyFLASH.exclusions.'+case['options']['marked_api'])
    elif case.get('kind')=='stacked':result.append('PyFLASH.exclusions.mark_exclusions')
    return tuple(dict.fromkeys(result))

def answer(case):
    if case.get('kind') in ('handoff','stacked'):return reference.region_answer(case)
    expected=reference.answer(case)
    requested=case['options'].get('roi')
    region='CTX' if requested is None else requested[0] if isinstance(requested,list) else requested
    expected['ledger_regions']=[region]*len(expected['ledger'])
    expected['saved_regions']=[region]*len(expected['saved_ledger']) if expected['saved_ledger'] is not None else None
    return expected

def check_identity():
    fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
    reference_path=Path(reference.__file__)
    if hashlib.sha256(reference_path.read_bytes()).hexdigest()!=fixture['reference_sha256']:
        raise ValueError('Independent manual exclusion reference source changed.')
    if [{key:case[key] for key in ('key','api','options')} for case in fixture['rows'] if not case.get('kind')]!=reference.cases():
        raise ValueError('Frozen manual exclusion inputs changed.')
    if [{key:case[key] for key in ('key','api','kind','options')} for case in fixture['rows'] if case.get('kind')]!=reference.region_cases():
        raise ValueError('Frozen region handoff inputs changed.')
    for case in fixture['rows']:
        if answer(case)!=case['expected']:
            raise ValueError('Frozen manual exclusion answers changed: '+case['key'])

def value(item):
    if hasattr(item,'item'):item=item.item()
    if isinstance(item,float) and math.isnan(item):return '__nan__'
    return item


def frame_data(frame):return [[value(item) for item in row] for row in frame.itertuples(index=False,name=None)]


def production(case, output):
    if case.get('kind') in ('handoff','stacked'):return production_regions(case,output)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    frames={base:pd.DataFrame(reference.ROWS,columns=reference.COLUMNS) for base in ('SCN','CTX')}
    options=dict(case['options']);prior=options.pop('prior',None);prior_fill=options.pop('prior_fill','__default__')
    raw=object()
    exp=SimpleNamespace(summary=frames['SCN'],summaries=frames,data=raw,data_path=str(output),fig_path=str(output),condition_list=[])
    if prior in ('marked','applied'):
        fill='EXCLUDED_MANUAL:prior' if prior_fill=='__default__' else np.nan if prior_fill=='__nan__' else prior_fill
        exp.exclusions=pd.DataFrame([['S02','A','',2.,'manual','prior','cell',fill]],columns=reference.LEDGER)
        exp.exclusion_summary={'prior':'retained original metadata'}
        if prior=='applied':
            for column in ('A','B'):
                exp.summaries['SCN'][column]=exp.summaries['SCN'][column].astype(object)
                exp.summaries['SCN'].loc[1,column]='EXCLUDED_MANUAL:prior'
    originals={base:frame.copy(deep=True) for base,frame in frames.items()}
    old_ledger=getattr(exp,'exclusions',None)
    old_ledger=old_ledger.copy(deep=True) if old_ledger is not None else None
    api=case['api'];function=getattr(exclusions,api)
    if api=='clear_exclusions':clean=function(exp)
    elif api in ('apply_exclusions','mark_exclusions'):
        alias=options.pop('alias',False)
        if 'subjects' in options and not alias:options['animals']=options.pop('subjects')
        if options.get('fill')=='__nan__':options['fill']=np.nan
        clean=function(exp,**options)
    else:
        subjects=options.pop('subjects')
        if options.get('fill')=='__nan__':options['fill']=np.nan
        clean=function(exp,subjects,verbose=False,**options)
    for base,original in originals.items():pd.testing.assert_frame_equal(exp.summaries[base],original)
    if old_ledger is not None:pd.testing.assert_frame_equal(exp.exclusions,old_ledger)
    assert clean is not exp and clean.data is raw
    assert clean.summary is clean.summaries['SCN']
    saved=list(output.glob('Exclusions/*.csv'))
    saved_regions=None
    if saved:
        transport=pd.read_csv(saved[0],keep_default_na=False)
        if list(transport.columns)!=reference.LEDGER+['roi']:
            raise ValueError('Saved exclusion ledger is missing explicit region ownership.')
        saved_regions=transport['roi'].tolist()
        saved_rows=frame_data(transport[reference.LEDGER])
    else:saved_rows=None
    # CSV is a textual transport: parse finite original values back to their
    # declared numeric input type; sentinel strings remain literal.
    if saved_rows:
        for row in saved_rows:
            try:row[3]=float(row[3])
            except ValueError:pass
    return {'frames':{base:frame_data(frame) for base,frame in clean.summaries.items()},
            'columns':list(clean.summary.columns),'dtypes':{base:[str(dtype) for dtype in frame.dtypes] for base,frame in clean.summaries.items()},
            'ledger_columns':list(clean.exclusions.columns),'ledger':frame_data(clean.exclusions),
            'summary':getattr(clean,'exclusion_summary',None),'saved_ledger':saved_rows,
            'ledger_regions':clean.exclusions.attrs.get('_pyflash_exclusion_rois',[]),
            'saved_regions':saved_regions}


def validate(output):
    from reproducibility.normality_association_validation import comparison
    from PyFLASH._persistence import write_json
    check_identity();output=Path(output);rows=[];paired=[]
    for index,case in enumerate(cases()):
        expected=answer(case)
        try:actual=production(case,output/'manual-exclusion-cases'/str(index));error=None
        except Exception as failure:
            error=type(failure).__name__+': '+str(failure)
            actual={'execution_error':error}
        agrees=actual==expected and error is None
        rows.append(comparison(case['key'],'literal-complete-manual-replacement-and-region-ownership',
            'functional-manual-exclusions/no-statistical-inference-vote',actual,expected,agrees,
            expected==case['expected'],'complete-tables-dtypes-ledger-reload-and-output-fields',0.,0.))
        paired.append({'case':case,'production':actual,'reference':expected,'agrees':agrees,'error':error})
        # Preserve each completed answer before the next independent request.
        write_json(output/'manual-exclusion-paired-data.json',{'rows':paired})
    return rows


def production_regions(case,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    frames={base:pd.DataFrame(reference.ROWS,columns=reference.COLUMNS) for base in ('SCN','CTX')}
    originals={base:frame.copy(deep=True) for base,frame in frames.items()}
    raw=object()
    exp=SimpleNamespace(summary=frames['SCN'],summaries=frames,data=raw,condition_list=[])
    options=case['options']
    if case['kind']=='handoff':
        if options['marked_api']=='mark_exclusions':
            marked=exclusions.mark_exclusions(exp,cells=[('S02','A')],roi=options['marked_roi'],reason='review')
        else:
            marked=getattr(exclusions,options['marked_api'])(exp,'S02',roi=options['marked_roi'],reason='review',verbose=False)
        clean=exclusions.apply_exclusions(marked,roi=options['override'])
    else:
        first,second=options['order']
        marked=exclusions.mark_exclusions(exp,cells=[('S02','A')],roi=first,reason='first region')
        marked=exclusions.mark_exclusions(marked,cells=[('S02','B')],roi=second,reason='second region')
        clean=exclusions.apply_exclusions(marked)
    for base,original in originals.items():
        pd.testing.assert_frame_equal(exp.summaries[base],original)
        pd.testing.assert_frame_equal(marked.summaries[base],original)
    assert clean is not exp and clean.data is raw and clean.summary is clean.summaries['SCN']
    return {'frames':{base:frame_data(frame) for base,frame in clean.summaries.items()},
            'columns':list(clean.summary.columns),'dtypes':{base:[str(dtype) for dtype in frame.dtypes] for base,frame in clean.summaries.items()},
            'ledger_columns':list(clean.exclusions.columns),'ledger':frame_data(clean.exclusions),
            'summary':clean.exclusion_summary,'saved_ledger':None,'saved_regions':None,
            'ledger_regions':clean.exclusions.attrs.get('_pyflash_exclusion_rois',[])}
