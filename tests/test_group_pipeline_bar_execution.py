"""The pipeline's secondary bars execute the actual plotting API and save output."""
import pandas as pd
from PyFLASH import pipeline,plotting

def test_secondary_bar_chart_executes_and_exports(tmp_path,monkeypatch):
    frame=pd.DataFrame({'AnimalName':['S'+str(i) for i in range(12)],
        'Condition':['WT']*6+['AD']*6,'Signal':[0.,1.,2.,0.,1.,2.,1.,2.,3.,1.,2.,3.]})
    calls=[];original=plotting.plot_mean_bars
    def run_actual(*args,**kwargs):
        try:
            answer=original(*args,**kwargs);calls.append({'completed':True});return answer
        except Exception as error:
            calls.append({'completed':False,'error':repr(error)});raise
    monkeypatch.setattr(plotting,'plot_mean_bars',run_actual)
    result=pipeline.group_comparison(frame,control='WT',filtered_columns=['Signal'],
        dataframe_kwargs={'fig_path':str(tmp_path/'figures'),'data_path':str(tmp_path/'data')},
        effect_ci=False,n_resamples=7,report_power=False,plot_volcano=False,plot_forest=False,
        plot_stats_matrix=False,plot_bars=True,run_label='actual-secondary-bar',save=True,montage=False)
    assert len(result['results_table'])==1
    assert calls==[{'completed':True}],calls
    assert list(tmp_path.rglob('*.svg'))
