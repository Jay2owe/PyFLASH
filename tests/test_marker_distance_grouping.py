from pathlib import Path
import hashlib,json,math
import numpy as np
import pandas as pd
import pytest
from PyFLASH import markers
from PyFLASH.config import Config
FROZEN=Path(__file__).resolve().parents[1]/'reproducibility/reference-sources/marker-distance-grouping/frozen-before'
CASES=json.loads((FROZEN/'frozen-before.json').read_text(encoding='utf-8'))['rows']

def frame(case,side,name):
    columns=case[side+'_groups']+[name+'_RawXM',name+'_RawYM',name+'_ZM']
    if side=='left' and case['coloc_column']:columns.append(case['coloc_column'])
    rows=[]
    for row in case[side]:
        values=[row.get(field) for field in case[side+'_groups']]+row['point']
        if side=='left' and case['coloc_column']:values.append(row.get('coloc'))
        rows.append(values)
    df=pd.DataFrame(rows,columns=columns)
    if case.get('index_group'):df=df.set_index(case['index_group'])
    elif case.get('duplicate_index'):df.index=[4]*len(df)
    return df

@pytest.mark.parametrize('record',CASES,ids=[row['case']['key']+'.'+row['backend'] for row in CASES])
def test_complete_nearest_marker_outputs_against_frozen_arithmetic(record,monkeypatch):
    case=record['case'];expected=record['reference']
    left=object.__new__(markers.Antibody);left.name='L';left.df=frame(case,'left','L')
    right=object.__new__(markers.Antibody);right.name='R';right.df=frame(case,'right','R')
    originals=[left.df.copy(deep=True),right.df.copy(deep=True)]
    monkeypatch.setattr(Config,'THRESHOLD',case['threshold'])
    monkeypatch.setattr(markers,'cKDTree',markers._TREE_PENDING if record['backend']=='tree' else None)
    assert left.find_closest_distances_between_markers(right) is left.df
    actual={'distances':['__inf__' if math.isinf(float(value)) else float(value) for value in left.df['L_DistToClosest_R']],
            'closest_flags':right.df['R_ClosestTo_L'].tolist(),'coloc_counts':right.df['R_VolNumColoc_L'].tolist(),
            'contains':right.df['R_VolContains_L'].tolist(),'closest_counts':right.df['R_NumClosestTo_L'].tolist()}
    assert actual==expected
    for marker,original in zip((left,right),originals):pd.testing.assert_frame_equal(marker.df[original.columns],original)
    assert right.df['R_NumColoc_L'].tolist()==expected['coloc_counts']
    assert right.df['R_Contains_L'].tolist()==expected['contains']
    assert str(right.df['R_VolContains_L'].dtype)=='int8'


def test_missing_group_keys_match_without_conflating_literal_names():
    df=pd.DataFrame({'Region':[None,np.nan,'None','nan'],'AnimalName':['S1']*4})
    groups=markers.Antibody._group_row_positions(df,['AnimalName','Region'])
    assert groups[('S1',None)].tolist()==[0,1]
    assert groups[('S1','None')].tolist()==[2]
    assert groups[('S1','nan')].tolist()==[3]
