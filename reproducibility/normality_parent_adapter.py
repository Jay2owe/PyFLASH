from copy import deepcopy
import warnings
import numpy as np
from PyFLASH import stats
from reproducibility.one_way_contract import clean

def production(case):
    figure=None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            parameters=deepcopy(case['parameters'])
            if case.get('group_form')=='numpy':parameters['df_list']=[np.asarray(group) for group in parameters['df_list']]
            if case.get('group_form')=='tuple':parameters['df_list']=[tuple(group) for group in parameters['df_list']]
            if case.get('group_form')=='series':
                import pandas as pd
                names=case.get('group_names',[None]*len(parameters['df_list']))
                parameters['df_list']=[pd.Series(group,name=name,dtype=float) for group,name in zip(parameters['df_list'],names)]
            if case.get('outer_form')=='generator':parameters['df_list']=(group for group in parameters['df_list'])
            normal,results,figure=stats.test_normality(**parameters)
        plot=None
        if figure is not None:
            plot={'size':figure.get_size_inches().tolist(),'axes':[
                {'xlabel':ax.get_xlabel(),'ylabel':ax.get_ylabel(),
                 'patches':[[float(r.get_x()),float(r.get_width()),float(r.get_height())] for r in ax.patches],
                 'lines':[{'x':np.asarray(line.get_xdata()).tolist(),'y':np.asarray(line.get_ydata()).tolist()} for line in ax.lines],
                 'texts':[text.get_text() for text in ax.texts]} for ax in figure.axes]}
        return clean({'normal':bool(normal),'results_dict':results,'figure':plot})
    except Exception as error:return {'error':type(error).__name__}
    finally:
        if figure is not None:
            from matplotlib import pyplot as plt
            plt.close(figure)
