"""Exercise real collector methods and actual in-memory figure attachments."""
from copy import deepcopy
import inspect,math
from PyFLASH import report
from PyFLASH.config import Config


def decode(obj):
    if isinstance(obj,dict):return {key:decode(item) for key,item in obj.items()}
    if isinstance(obj,list):return [decode(item) for item in obj]
    if isinstance(obj,str):return {'__nan__':math.nan,'__inf__':math.inf}.get(obj,obj)
    return obj


def frames():
    namespace={'__name__':'PyFLASH.validation_frame_probe','report':report,'inspect':inspect}
    exec('''def outer():
    caller=inspect.currentframe()
    def nested():
        inner=inspect.currentframe()
        live=report.live_frame_ids()
        wanted={id(frame.frame) for frame in inspect.stack()}
        report.emit({'kind':'inside'})
        current=report.records_since(0,alive=live)
        return {'caller_present':id(caller) in live,'nested_present':id(inner) in live,'ancestors_exact':live==wanted,
                'current_records':current},caller
    return nested()
''',namespace)
    report.start();answer,retained_frame=namespace['outer']()
    answer['stale_records']=report.records_since(0,alive=report.live_frame_ids())
    report.start();report.emit({'kind':'outside'})
    answer['originless_records']=report.records_since(0,alive=set())
    del retained_frame
    return answer


def production(case):
    previous=Config.RECORD_STATS;report.collect();Config.RECORD_STATS=case.get('automatic',False)
    try:
        if case['variant']=='emission-attachment':
            from matplotlib.figure import Figure
            figure=Figure();returns=[]
            if case['armed']:report.start()
            for item in case['records']:
                returns.append(report.emit(decode(deepcopy(item)),figure=figure,plotted_data=[1,2],
                    analysis={'method':'literal'},sources=[],append_plotted_data=case['append']))
            return {'records':report.collect(),'attachment':deepcopy(report.attachment_for(figure)),'returns':returns}
        if case['variant']=='frames':return frames()
        if case['variant']=='attachment':
            from matplotlib.figure import Figure
            figure=Figure();observed=[];returns=[]
            for event in case['events']:
                returns.append(report.attach(figure,**decode(deepcopy(event))))
                observed.append(deepcopy(report.attachment_for(figure)))
            copied=report.attachment_for(figure);copied['only_in_copy']='changed'
            return {'attachments':observed,'fresh_figure':report.attachment_for(Figure()),
                'top_level_copy':'only_in_copy' not in report.attachment_for(figure),'returns':returns}
        observed=[]
        for event in case['events']:
            op=event['operation'];function=getattr(report,op)
            if op=='emit':result=function(decode(deepcopy(event['record'])))
            elif op=='records_since':result=function(decode(event['index']),alive=None if event.get('alive') is None else set())
            else:result=function()
            observed.append({'operation':op,'returned':deepcopy(result),'count':report.count(),'active':report.is_active()})
        return {'events':observed,'final_records':deepcopy(report.records_since(0))}
    except Exception as error:return {'error':type(error).__name__}
    finally:report.collect();Config.RECORD_STATS=previous
