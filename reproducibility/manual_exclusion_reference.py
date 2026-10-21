"""Literal functional reference: no PyFLASH, pandas, or statistical engine."""
import copy

COLUMNS=['AnimalName','Condition','A','B','Label']
ROWS=[['S01','WT',1.,10.,'one'],['S02','WT',2.,20.,'two'],['S03','KO',3.,30.,'three']]
LEDGER=['AnimalName','column','group','original_value','kind','reason','scope','fill']
APIS=('apply_exclusions','mark_exclusions','exclude_animals','mark_animals','exclude_subjects','mark_subjects')


def cases():
    rows=[]
    for api in APIS:
        scenarios=[('single',{'subjects':['S02']}),('two',{'subjects':['S01','S03']}),
                   ('reasons',{'subjects':{'S01':'damaged','S03':'wrong genotype'}}),
                   ('unknown',{'subjects':['missing']}),('empty',{'subjects':[]}),
                   ('one-column',{'subjects':['S02'],'columns':['B']}),
                   ('no-columns',{'subjects':['S02'],'columns':[]}),
                   ('unknown-column',{'subjects':['S02'],'columns':['missing']}),
                   ('repeated-subject',{'subjects':['S02','S02']}),
                   ('repeated-column',{'subjects':['S02'],'columns':['A','A']}),
                   ('reason',{'subjects':['S02'],'reason':'damaged section'}),
                   ('alternate-roi',{'subjects':['S02'],'roi':'CTX'})]
        if api.startswith('exclude_') or api=='apply_exclusions':
            scenarios += [('numeric-fill',{'subjects':['S02'],'fill':-9.}),
                          ('nan-fill',{'subjects':['S02'],'fill':'__nan__'}),
                          ('custom-token',{'subjects':['S02'],'fill':'REVIEW'})]
        if api in ('apply_exclusions','mark_exclusions'):
            scenarios += [('single-cell',{'cells':[['S01','B']]}),
                          ('cells-and-subjects',{'cells':[['S01','B']],'subjects':['S02']}),
                          ('unknown-cell',{'cells':[['S01','missing']]}),
                          ('subjects-alias',{'subjects':['S02'],'alias':True})]
        else:
            scenarios += [('string-subject',{'subjects':'S02'})]
            if api.startswith('exclude_'):
                scenarios += [('save',{'subjects':['S02'],'save':True,'run_label':'accepted'})]
        scenarios += [('none-roi',{'subjects':['S02'],'roi':None}),
                      ('one-roi-list',{'subjects':['S02'],'roi':['SCN']}),
                      ('two-roi-list',{'subjects':['S02'],'roi':['SCN','CTX']}),
                      ('empty-reason',{'subjects':['S02'],'reason':''}),
                      ('none-reason',{'subjects':['S02'],'reason':None})]
        if api=='apply_exclusions':
            scenarios += [('explicit-manual-kind',{'subjects':['S02'],'kind':'manual'}),
                          ('outlier-kind',{'subjects':['S02'],'kind':'outlier'}),
                          ('no-requests',{})]
        if api=='mark_exclusions':scenarios += [('no-requests',{})]
        if api in ('apply_exclusions','mark_exclusions'):
            scenarios += [('repeated-cell',{'cells':[['S02','A'],['S02','A']]})]
        if api=='apply_exclusions' or api.startswith('exclude_'):
            scenarios += [('zero-fill',{'subjects':['S02'],'fill':0.})]
        for name,options in scenarios:
            rows.append({'key':'manual-exclusion.'+api+'.'+name,'api':api,'options':options})
    for mode in ('empty','marked','applied'):
        rows.append({'key':'manual-exclusion.clear_exclusions.'+mode,'api':'clear_exclusions','options':{'prior':mode}})
    for fill in ('__default__','__nan__',-9.):
        rows.append({'key':'manual-exclusion.apply_exclusions.ledger-'+str(fill),'api':'apply_exclusions',
                     'options':{'prior':'marked','prior_fill':fill,'roi':'SCN'}})
    return rows


def answer(case):
    options=case['options'];api=case['api'];requested=options.get('roi')
    base='CTX' if requested is None else requested[0] if isinstance(requested,list) else requested
    kind=options.get('kind','manual')
    frames={'SCN':copy.deepcopy(ROWS),'CTX':copy.deepcopy(ROWS)}
    ledger=[];dtypes={base:['object','object','float64','float64','object'] for base in frames}
    summary=None
    if api=='clear_exclusions':
        if options['prior']=='applied':
            frames['SCN'][1][2]='EXCLUDED_MANUAL:prior';frames['SCN'][1][3]='EXCLUDED_MANUAL:prior'
            dtypes['SCN'][2:4]=['object','object']
        return {'frames':frames,'columns':COLUMNS,'dtypes':dtypes,'ledger_columns':LEDGER,
                'ledger':[],'summary':None,'saved_ledger':None}
    applying=api=='apply_exclusions' or api.startswith('exclude_')
    subjects=options.get('subjects',[])
    if isinstance(subjects,str):subjects=[subjects]
    records=[]
    for subject,column in options.get('cells',[]):
        records.append((subject,column,options.get('reason') or '','cell'))
    items=list(subjects.items()) if isinstance(subjects,dict) else [(name,options.get('reason') or '') for name in subjects]
    for subject,reason in items:
        for column in options.get('columns',['A','B']):records.append((subject,column,reason,'animal'))
    if options.get('prior')=='marked':records=[('S02','A','prior','cell')]
    scope=('ledger' if options.get('prior')=='marked' or (api=='apply_exclusions' and 'subjects' not in options and 'cells' not in options) else
           'animal' if 'subjects' in options and not options.get('cells') else
           'cell' if options.get('cells') else 'manual')
    for subject,column,reason,record_scope in records:
        if column not in COLUMNS:continue
        index=next((i for i,row in enumerate(frames[base]) if row[0]==subject),None)
        if index is None:continue
        c=COLUMNS.index(column);value=frames[base][index][c]
        fill=options.get('fill')
        if options.get('prior')=='marked' and fill is None:
            fill=options.get('prior_fill','__default__')
            if fill=='__default__':fill=None
        if fill is None:fill=('EXCLUDED_MANUAL' if kind=='manual' else 'EXCLUDED_OUTLIER')+(':'+reason if reason else '')
        # Marking evaluates a separate scratch table, so duplicate requests
        # observe earlier writes in the ledger while the returned data stay intact.
        prior=next((entry[7] for entry in reversed(ledger) if entry[0]==subject and entry[1]==column),value)
        original=prior if not applying else value
        ledger.append([subject,column,'',original,kind,reason,record_scope,fill])
        if applying:
            frames[base][index][c]=fill
            if isinstance(fill,str) and fill!='__nan__':dtypes[base][c]='object'
    summary={'action':'exclude' if applying else 'mark','scope':scope,'roi':base,
             'n_excluded_cells':len(ledger),'n_animals_affected':len({entry[0] for entry in ledger}),
             'reasons':sorted({entry[5] for entry in ledger if entry[5]})}
    return {'frames':frames,'columns':COLUMNS,'dtypes':dtypes,'ledger_columns':LEDGER,
            'ledger':ledger,'summary':summary,'saved_ledger':ledger if options.get('save') and ledger else None}


def region_cases():
    result=[]
    for marked_api in ('mark_exclusions','mark_animals','mark_subjects'):
        for region in ('SCN','CTX'):
            for override in (None,'SCN','CTX'):
                result.append({'key':'marked-roi.'+marked_api+'.'+region+'.'+str(override),
                    'api':'apply_exclusions','kind':'handoff',
                    'options':{'marked_api':marked_api,'marked_roi':region,'override':override}})
    for first,second in (('SCN','CTX'),('CTX','SCN')):
        result.append({'key':'mixed-exclusion.'+first+'.'+second,'api':'apply_exclusions','kind':'stacked',
                       'options':{'order':[first,second]}})
    return result


def region_answer(case):
    options=case['options']
    frames={base:copy.deepcopy(ROWS) for base in ('SCN','CTX')}
    dtypes={base:['object','object','float64','float64','object'] for base in frames}
    if case['kind']=='handoff':
        selected=['A'] if options['marked_api']=='mark_exclusions' else ['A','B']
        target=options['marked_roi'] if options['override'] is None else options['override']
        records=[(target,column,'review','cell' if options['marked_api']=='mark_exclusions' else 'animal') for column in selected]
    else:
        first,second=options['order']
        records=[(first,'A','first region','cell'),(second,'B','second region','cell')]
    ledger=[];regions=[]
    for region,column,reason,scope in records:
        index=COLUMNS.index(column)
        original=frames[region][1][index]
        token='EXCLUDED_MANUAL:'+reason
        frames[region][1][index]=token;dtypes[region][index]='object'
        ledger.append(['S02',column,'',original,'manual',reason,scope,token]);regions.append(region)
    distinct=list(dict.fromkeys(regions))
    summary={'action':'exclude','scope':'ledger','roi':distinct[0] if len(distinct)==1 else 'multiple',
             'n_excluded_cells':len(ledger),'n_animals_affected':1,'reasons':sorted({row[5] for row in ledger})}
    if len(distinct)>1:summary['rois']=sorted(distinct)
    return {'frames':frames,'columns':COLUMNS,'dtypes':dtypes,'ledger_columns':LEDGER,
            'ledger':ledger,'summary':summary,'saved_ledger':None,'saved_regions':None,'ledger_regions':regions}
