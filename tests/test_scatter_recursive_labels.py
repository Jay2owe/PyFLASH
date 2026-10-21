"""Region and specificity queues keep labels on actual 3D scatter axes."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from PyFLASH import from_dataframe, ConditionBuilder
from PyFLASH import plotting as P


@pytest.mark.parametrize('queue',['regions','specificities','regions-and-metrics'])
def test_recursive_3d_calls_preserve_labels_and_selected_points(queue,tmp_path,monkeypatch):
    frame=pd.DataFrame([
        dict(AnimalName=f'{group}{i}',Diagnosis=group,Region=region,
             A_Volume=float(i+shift),B_Volume=float(2*i+shift),
             A_Surface=float(i*i+shift),A_Intensity=float(3*i+shift))
        for group,offset in [('Control',0),('Case',2)]
        for i in range(1,4) for region,shift in [('SCN1',offset),('OC1',offset+100)]])
    experiment=from_dataframe(frame,
        conditions=ConditionBuilder('Diagnosis').add('Control').add('Case').build(),
        name='recursive-labels',condition_col='Diagnosis',animal_col='AnimalName',region_col='Region',
        summaries={roi:frame[frame.Region.str.startswith(roi)].copy() for roi in ('SCN','OC')},
        fig_path=tmp_path/'unsaved',data_path=tmp_path/'data')
    labels={'A_Volume':'Measured volume','B_Volume':'Other volume',
            'A_Surface':'Measured surface','A_Intensity':'Measured intensity'}
    writes=[]
    def observe(fig,path,name,**kwargs):
        ax=fig.axes[0]
        writes.append(dict(labels=(ax.get_xlabel(),ax.get_ylabel(),ax.get_zlabel()),
                           points=[tuple(point) for collection in ax.collections if hasattr(collection,'_offsets3d')
                                   for point in np.column_stack(collection._offsets3d).tolist()]))
    monkeypatch.setattr(P,'save_fig',observe)
    kwargs=dict(x='A_Volume',y='A_Surface',z='A_Intensity',column_labels=labels,
                combine=True,normalize_x=False,normalize_y=False,normalize_z=False,save=True)
    if queue.startswith('regions'):kwargs['roi']=['SCN','OC']
    else:kwargs.update(roi='OC',specificity=[('Diagnosis','Control'),('Diagnosis','Case')])
    if queue=='regions-and-metrics':kwargs['x']=['A_Volume','B_Volume']
    try:P.plot_scatter_3d(experiment,**kwargs)
    finally:P.plt.close('all')
    assert len(writes)==(4 if queue=='regions-and-metrics' else 2)
    for write in writes:
        assert write['labels'][0] in (labels['A_Volume'],labels['B_Volume'])
        assert write['labels'][1:]==(labels['A_Surface'],labels['A_Intensity'])
        assert write['points']
    if queue=='specificities':
        expected=sorted(frame.loc[frame.Region.eq('OC1'),['A_Volume','A_Surface','A_Intensity']].itertuples(index=False,name=None))
        assert sorted(point for write in writes for point in write['points'])==expected
    elif queue=='regions':
        expected=sorted(frame[['A_Volume','A_Surface','A_Intensity']].itertuples(index=False,name=None))
        assert sorted(point for write in writes for point in write['points'])==expected
    assert not list((tmp_path/'unsaved').rglob('*'))
