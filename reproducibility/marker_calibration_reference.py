"""Native R distance/attribution from unchanged original Fiji physical points."""
from pathlib import Path
import json
from reproducibility import marker_nearest_reference as original

INPUT=Path(__file__).with_name('reference-sources')/'marker-calibration/native-imagej-v1/native.json'


def cases():
    native=json.loads(INPUT.read_text(encoding='utf-8'))['cases']
    return [dict(key=f'calibrated-native-distance.pitch-{i}',threshold=30,
                 left_groups=['Region'],right_groups=['Region'],coloc_column=None,
                 left=[dict(Region='SCN1',point=native[2*i]['physical_centre'])],
                 right=[dict(Region='SCN1',point=native[2*i+1]['physical_centre'])])
            for i in range(3)]


def query(case):
    return original.query(case)


def unpack(case,values):
    return original.unpack(case,values)
