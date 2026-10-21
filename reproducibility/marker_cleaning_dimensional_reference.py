"""Native-R full-table reference retained from the executed original producer.

All query, input and reconstruction functions below are verbatim. The original
48 typed/domain failures remain failures; no numeric allowances change.
"""
from itertools import product
import copy,json,math
import numpy as np
import pandas as pd
from reproducibility import marker_cleaning_reference as ref
ORIGINAL_INPUTS=ref.inputs
def inputs(case):
    frame,labels,areas=ORIGINAL_INPUTS(case)
    if case['route'].startswith('two-dimensional'):
        column=('A_' if case['header']=='prefixed' else '')+'ZM';frame=frame.drop(columns=column)
    if case['route'].endswith('region-only'):
        for value in areas.values():value.df=value.df.drop(columns='AnimalName')
    return frame,labels,areas

def cases():
    rows=[]
    for owner,header,profile,route in product(('cellMarker','objectMarker'),('raw','prefixed'),('positive','absent','nullable','empty'),('two-dimensional-no-area','two-dimensional-region-only','three-dimensional-region-only')):
        rows.append(dict(key='.'.join((owner,header,profile,route)),owner=owner,name='A',label=False,header=header,profile=profile,calibration='legacy',area='absent' if route=='two-dimensional-no-area' else 'exact',family='both' if owner=='objectMarker' else 'none',route=route))
    return rows

def query(case):
    ref.inputs=inputs
    try:return ref.query(case)
    finally:ref.inputs=ORIGINAL_INPUTS

def expected(case,values):
    ref.inputs=inputs
    try:return ref.expected(case,values)
    finally:ref.inputs=ORIGINAL_INPUTS
