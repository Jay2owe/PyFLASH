"""Independent event-ledger specification of public reporting lifecycle."""
from copy import deepcopy
import math


def value(obj):
    if isinstance(obj,dict):return {key:value(item) for key,item in obj.items()}
    if isinstance(obj,list):return [value(item) for item in obj]
    if obj in ('__nan__','__inf__') if isinstance(obj,str) else False:return None
    return obj


def index(value):
    if value=='__inf__':return None
    if value=='__nan__':return None
    try:return int(value)
    except (TypeError,ValueError,OverflowError):return None


def report(case):
    if case['variant']=='emission-attachment':
        records=[];attachments=[];events=[]
        for item in case['records']:
            if (case['armed'] or case['automatic']) and isinstance(item,dict):
                records.append(value(item))
                events.append({'record':item,'plotted_data':[1,2],'analysis':{'method':'literal'},'sources':[],
                    'statistics_status':'complete','append_plotted_data':case['append']})
                attachments=report({'variant':'attachment','events':events})['attachments']
        return {'records':records,'attachment':attachments[-1] if attachments else {},'returns':[None]*len(case['records'])}
    if case['variant']=='frames':return {'caller_present':True,'nested_present':True,'ancestors_exact':True,'stale_records':[],
        'current_records':[{'kind':'inside'}],'originless_records':[{'kind':'outside'}]}
    if case['variant']=='attachment':
        accumulated={};observed=[]
        for event in case['events']:
            for key,item in event.items():
                if key=='record':accumulated.setdefault('statistics',[]).extend([] if item is None else [value(item)])
                elif key=='append_plotted_data':continue
                elif item is not None:
                    if key=='analysis':accumulated.setdefault(key,{}).update(item)
                    elif key=='plotted_data' and event.get('append_plotted_data') and key in accumulated:accumulated[key]+=item
                    else:accumulated[key]=deepcopy(item)
            accumulated.setdefault('statistics',[])
            observed.append(deepcopy(accumulated))
        return {'attachments':observed,'fresh_figure':{},'top_level_copy':True,'returns':[None]*len(observed)}
    records=[];armed=False;observed=[]
    for event in case['events']:
        op=event['operation'];result=None
        if op=='start':records=[];armed=True
        elif op=='emit':
            if armed or case['automatic']:
                armed=True
                if isinstance(event['record'],dict):records.append(value(event['record']))
        elif op=='collect':result=deepcopy(records);records=[];armed=False
        elif op=='count':result=len(records)
        elif op=='is_active':result=bool(armed or case['automatic'])
        elif op=='records_since':
            position=index(event['index']);result=deepcopy(records[position:]) if position is not None else []
        observed.append({'operation':op,'returned':result,'count':len(records),'active':bool(armed or case['automatic'])})
    return {'events':observed,'final_records':deepcopy(records)}
