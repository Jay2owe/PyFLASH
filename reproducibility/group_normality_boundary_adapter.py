from types import SimpleNamespace
from copy import deepcopy
import warnings,inspect
import pandas as pd
from PyFLASH import pipeline,plotting
from PyFLASH.config import Config
from reproducibility.one_way_contract import clean

def observe(case,folder):
    folder.mkdir(parents=True,exist_ok=False)
    summary=pd.DataFrame({'AnimalName':['S'+str(i) for i in range(12)],'Condition':['WT']*6+['AD']*6,'Signal':case['values']})
    exp=SimpleNamespace(summary=summary,summaries={'SCN':summary},fig_path=str(folder/'figures'),data_path=str(folder/'data'),
                        condition_list=[SimpleNamespace(name='WT'),SimpleNamespace(name='AD')])
    signature=inspect.signature(plotting.plot_mean_bars);calls=[]
    old=plotting.plot_mean_bars
    def capture(*args,**kwargs):
        try:signature.bind(*args,**kwargs);valid=True
        except TypeError:valid=False
        calls.append({'valid':valid,'parameters':kwargs})
    plotting.plot_mean_bars=capture
    settings={name:deepcopy(getattr(Config,name)) for name in ('EFFECT_SIZES','EFFECT_CI','CORRECTION_AUDIT')}
    try:
        Config.EFFECT_SIZES=False;Config.EFFECT_CI=False;Config.CORRECTION_AUDIT=False
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            result=pipeline.group_comparison(exp,control='WT',engine=case['engine'],filtered_columns=['Signal'],
                effect_ci=False,n_resamples=7,report_power=False,plot_volcano=False,plot_forest=False,
                plot_stats_matrix=False,plot_bars=True,run_label=case['key'],save=True,montage=False)
        answer={'results':result['results_table'].to_dict('records'),'skipped':result['skipped'].to_dict('records'),
                'descriptives':result['descriptives'].to_dict('records'),'bar_calls':calls}
        skipped=any(row['marker']=='Signal' for row in answer['skipped'])
        all_bound=all(call['valid'] for call in calls)
        observed={'skip_constant_marker':skipped,'bar_call_accepts_public_signature':all_bound}
        return {'complete_original_output':clean(answer),'functional_observation':observed,'agrees':observed==case['reference']}
    finally:
        plotting.plot_mean_bars=old
        for name,value in settings.items():setattr(Config,name,value)
