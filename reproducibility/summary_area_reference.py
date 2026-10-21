"""Candidate-free full summary schemas and native-R normalization equations."""
from pathlib import Path
import json

NATIVE = Path(__file__).with_name('receipt.json')


def cases():
    native = json.loads(NATIVE.read_text())
    assert native['passed'] and native['source_unchanged']
    return [{'key': '.'.join((str(measured['density']), area_column, str(volume_column), str(sections), str(thickness), str(progress))),
             'native': measured, 'area_column': area_column, 'volume_column': volume_column,
             'sections': sections, 'thickness': thickness, 'progress': progress}
            for measured in native['answers'] for area_column in ('Area(pixel)', 'Area(um^2)', 'Area')
            for volume_column in (None, 'Volume', 'Volume(micron^3)', 'Volume(mm^3)')
            for sections in (1, 2) for thickness in (13., 20.) for progress in (False, True)]


def query(case):
    area = case['native']['physical_area']
    pixel_area = case['native']['pixel_area']
    measured_area = pixel_area if case['area_column'] == 'Area(pixel)' else area
    commands = [f'area <- {area!r}', f'thickness <- {case["thickness"]!r}',
                'volume <- area*thickness', 'normal_volume <- volume/100000000',
                'count_raw <- 2', f'measured_area <- {measured_area!r}',
                'answer <- c(count_raw/normal_volume,count_raw,measured_area)']
    if case['volume_column']:
        commands.append('measured_volume <- volume' + ('/1000000000' if case['volume_column'] == 'Volume(mm^3)' else ''))
        commands.append('answer <- c(answer,measured_volume,measured_volume/normal_volume)')
    commands.append('c(answer,area,volume,normal_volume,1/normal_volume,volume/area)')
    return {'key': case['key'], 'code': 'local({' + ';'.join(commands) + '})'}


def expected(case, numbers):
    import pandas as pd
    names = ['M_Count', 'M_CountRaw', case['area_column'] + 'Mean']
    if case['volume_column']:
        names += [case['volume_column'] + 'Mean', case['volume_column'] + 'Total']
    names += ['ROI_Area', 'ROI_Volume', 'Volume0p1mm3', 'CountNormFactor', 'ROI_Thickness']
    assert len(numbers) == len(names)
    values = dict(zip(names, numbers))
    # Complete order and metadata are a literal public table policy, composed
    # with separately calculated native numeric results, never a candidate table.
    ordered = {'AnimalName': ['Subject1']}
    for name in names[:len(names)-5]:
        ordered[name] = [float(values[name])]
    ordered['Condition'] = ['Subject']
    ordered['numSections'] = [case['sections']]
    for name in names[-5:]:
        ordered[name] = [float(values[name])]
    return pd.DataFrame(ordered)
