from copy import deepcopy
import warnings
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba
from PyFLASH import stats
from reproducibility.one_way_contract import clean
from reproducibility import comparison_geometry_reference as reference
equal=reference.same

def snapshot(ax,line_start,text_start,patch_start):
    return clean({'ylim':list(ax.get_ylim()),
        'lines':[{'x':list(line.get_xdata()),'y':list(line.get_ydata()),'color':list(to_rgba(line.get_color())),
            'lw':line.get_linewidth(),'zorder':line.get_zorder(),'clip_on':line.get_clip_on()} for line in ax.lines[line_start:]],
        'texts':[{'x':text.get_position()[0],'y':text.get_position()[1],'text':text.get_text(),'size':text.get_fontsize(),
            'weight':text.get_fontweight(),'color':list(to_rgba(text.get_color())),'clip_on':text.get_clip_on()} for text in ax.texts[text_start:]],
        'anchors':[{'x':patch.get_x(),'y':patch.get_y(),'width':patch.get_width(),'height':patch.get_height(),'gid':patch.get_gid()} for patch in ax.patches[patch_start:]]})

def production(case):
    figure,ax=plt.subplots();p=deepcopy(case['parameters']);groups=deepcopy(case['groups'])
    if case.get('annotations_kind')=='numpy_float32':p['annotations']=np.asarray(p['annotations'],dtype=np.float32)
    elif case.get('annotations_kind')=='numpy_int64':p['annotations']=np.asarray(p['annotations'],dtype=np.int64)
    count=len(groups);positions=case['positions'];mode=case.get('scatter_mode','points')
    try:
        if case.get('kind')!='renderer':
            ax.bar(positions,[0.]*count,width=.8)
            if mode=='points':
                for i,group in enumerate(groups):
                    try:values=reference.sample(group)
                    except ValueError:values=[]
                    if values:ax.scatter([positions[i]]*len(values),[float(v) for v in values],edgecolors=case['scatter_colors'][i])
        ax.set_xlim(case['xlim']);ax.set_ylim(case['ylim'])
        if case.get('autoscale'):ax.set_autoscaley_on(True)
        initial=(len(ax.lines),len(ax.texts),len(ax.patches));unchanged=snapshot(ax,*initial)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            if case.get('kind')=='renderer':
                center=p.pop('centers');tokens=p.pop('comparisons');labels=p.pop('annotations')
                value=stats.draw_comparison_brackets(None if case.get('axes_mode')=='none' else ax,center,tokens,labels,**p);field='bracket_top'
            else:
                method=getattr(stats,case.get('method','plot_comparison_lines_from_figdata'))
                value=method(None if mode=='none' else ax,None if case.get('bar_mode')=='none' else ax,None if case.get('axes_mode')=='none' else ax,
                    group_values=None if case.get('fallback') else groups,**p);field='maximum'
        return clean({field:value,**snapshot(ax,*initial)})
    except Exception as error:
        return {'error':type(error).__name__,'axes_unchanged':equal(snapshot(ax,*initial),unchanged)}
    finally:plt.close(figure)
