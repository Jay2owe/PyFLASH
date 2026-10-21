"""Functional save-dispatch contract; independent SQL selects complete points.

These checks establish finalization and point selection only. They do not certify
regression inference or rendered figure exports.
"""
import sqlite3
import numpy as np
import pandas as pd
from matplotlib.collections import PathCollection
from PyFLASH import from_dataframe, ConditionBuilder
from PyFLASH import plotting as P


def inputs(more):
    return pd.DataFrame([
        dict(AnimalName=f'{group}{i}', Diagnosis=group, Region=region,
             Season='Summer' if region.startswith(more) and i % 2 else 'Winter',
             A_Volume=float(i + offset + (100 if region == 'OC1' else 0)),
             A_Surface=float(i*i + offset + (200 if region == 'OC1' else 0)),
             A_Intensity=float(3*i + offset + (300 if region == 'OC1' else 0)))
        for group, offset in [('Control', 0), ('Case', 2)]
        for i in range(1, 6) for region in ('SCN1', 'OC1')
    ])


def production(case, path):
    frame=inputs(case['more']); before=frame.copy(deep=True)
    experiment=from_dataframe(
        frame, conditions=ConditionBuilder('Diagnosis').add('Control').add('Case').build(),
        name='region-factor-finalization', condition_col='Diagnosis',
        animal_col='AnimalName', region_col='Region',
        summaries={roi:frame[frame.Region.str.startswith(roi)].copy() for roi in ('SCN','OC')},
        fig_path=path/'unsaved', data_path=path/'data')
    writes=[]; events=[]; original_save=P.save_fig; original_run=P.run
    def observe(fig, directory, name, **kwargs):
        points=[]
        for ax in fig.axes:
            for collection in ax.collections:
                if case['kind']=='scatter3d' and hasattr(collection,'_offsets3d'):
                    points.append(np.column_stack(collection._offsets3d).tolist())
                elif isinstance(collection,PathCollection):
                    points.append(np.asarray(collection.get_offsets()).tolist())
        writes.append(dict(name=name, points=points,
                           annotations=[t.get_text() for ax in fig.axes for t in ax.texts]))
    def observe_run(*args, **kwargs):
        teardown=kwargs['teardown']
        def finished(ctx,state,result):
            teardown(ctx,state,result)
            progress=state.get('progress_state') or {}
            events.append(dict(roi=ctx.roi_base, factor=str(ctx.factor_value),
                               total=progress.get('total'), completed=progress.get('completed'), writes=len(writes)))
        kwargs['teardown']=finished
        return original_run(*args,**kwargs)
    P.save_fig=observe; P.run=observe_run
    try:
        arguments=dict(x='A_Volume',y='A_Surface',factor='Season',roi=case['roi'],
                       combine=case['combine'],normalize_x=False,normalize_y=False,save=True)
        if case['kind']=='scatter3d':
            P.plot_scatter_3d(experiment,z='A_Intensity',normalize_z=False,**arguments)
        else:
            P.plot_regressions(experiment,**arguments)
    finally:
        P.save_fig=original_save; P.run=original_run
        P.plt.close('all')
    pd.testing.assert_frame_equal(frame,before)
    assert not list((path/'unsaved').rglob('*'))
    return dict(writes=writes,events=events)


def check_result(case, actual):
    with sqlite3.connect(':memory:') as connection:
        inputs(case['more']).to_sql('measurements',connection,index=False)
        groups=connection.execute('SELECT DISTINCT Season FROM measurements WHERE Region LIKE ?',
                                  [case['roi']+'%']).fetchall()
        columns='A_Volume,A_Surface,A_Intensity' if case['kind']=='scatter3d' else 'A_Volume,A_Surface'
        expected=connection.execute(f'SELECT {columns} FROM measurements WHERE Region LIKE ?',
                                    [case['roi']+'%']).fetchall()
    assert len(actual['writes'])==(1 if case['combine'] else len(groups)), 'Incorrect number of finalized figures'
    points=[tuple(point) for write in actual['writes'] for collection in write['points'] for point in collection]
    assert sorted(points)==sorted(expected), 'Finalized points differ from selected-region SQL rows'
    assert len(actual['events'])==len(groups)
    assert all(event['total']==len(groups) for event in actual['events']), 'Progress counts another region'
