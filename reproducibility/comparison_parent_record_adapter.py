from copy import deepcopy
import inspect
from PyFLASH import report
from reproducibility import comparison_parent_inference_adapter as parent

def indexed_parent(case):
    def source_frame(*args,**kwargs):
        frame=parent.pd.DataFrame(*args,**kwargs)
        labels=case['source_index']
        frame.index=parent.pd.MultiIndex.from_tuples(list(map(tuple,labels))) if labels and isinstance(labels[0],list) else labels
        return frame
    source=inspect.getsource(parent.production)
    assert source.count('pd.DataFrame(')==2
    namespace=dict(parent.__dict__);namespace['_source_frame']=source_frame
    exec(compile(source.replace('pd.DataFrame(','_source_frame('),'<indexed-public-parent-call>','exec'),namespace)
    return namespace['production'](case)

def production(case):
    state=report._STATE;original=report.emit;plotted=[]
    report._STATE={"active":False,"records":[],"origins":[]}
    def capture(record,**kwargs):
        frame=kwargs.get('plotted_data')
        if frame is not None:plotted.extend(frame.to_dict(orient='records'))
        return original(record,**kwargs)
    try:
        report.start();report.emit=capture
        returned=indexed_parent(case) if 'source_index' in case else parent.production(case);records=report.collect()
        return {'returned':returned,'records':records,'plotted_data':plotted}
    finally:
        report.emit=original;report._STATE=state
