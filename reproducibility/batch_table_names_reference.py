"""Freeze native R make.unique names and complete batch table ownership."""
from pathlib import Path
from itertools import product
import json, hashlib
import pandas as pd
from reproducibility.reference_runtime import execute_queries, values
from reproducibility.scientific_utility_contract import table

OWNER = Path(__file__).resolve().parent


def cases():
    patterns = (('Data',), ('Data', 'Data_1'), ('Data_1', 'Data'),
                ('Data_2', 'Data'), ('Data', 'Data_1_1'), ())
    for index, groups in enumerate(product(patterns, repeat=2)):
        for reverse in (False, True):
            yield {'key': str(index) + '.' + str(reverse),
                   'groups': [list(part) for part in (groups[::-1] if reverse else groups)]}


def query(case):
    names = [name for group in case['groups'] for name in group]
    return {'key': case['key'], 'code': 'make.unique(c(' + ','.join(map(json.dumps, names)) + '),sep="_")'
            if names else 'character(0)'}


def production(case, names):
    from PyFLASH.batch import Batch
    from PyFLASH.experiment import MiniExperiment
    from PyFLASH.markers import Attribute
    from PyFLASH.conditions import condition, conditionList
    conditions = conditionList([condition('WT', 'WT', None, 'Genotype')])
    experiments, original = [], []
    for index, group in enumerate(case['groups']):
        exp = MiniExperiment('Experiment' + str(index), str(OWNER))
        for offset, name in enumerate(group):
            data = pd.DataFrame({'AnimalName': ['WT' + str(index + 1)], 'Measurement': [index * 10. + offset]})
            carrier = Attribute(name, data, exp)
            exp.data[name] = carrier
            original.append((carrier, data, table(data)))
        experiments.append(exp)
    batch = Batch('Original table name ownership', experiments, conditions, str(OWNER))
    try:
        result = batch._create_data_dict()
        assert result is None
        assert list(batch.data) == names, (list(batch.data), names)
        assert len(batch.data) == len(original)
        for (name, carrier), (retained, data, expected) in zip(batch.data.items(), original, strict=True):
            assert carrier is retained and carrier.df is data and table(data) == expected
        assert all(carrier.experiment is exp for exp in experiments for carrier in exp.data.values())
        return {'passed': True, 'actual': {name: table(carrier.df) for name, carrier in batch.data.items()}}
    except Exception as error:
        return {'passed': False, 'error': type(error).__name__ + ': ' + str(error),
                'actual': {name: table(carrier.df) for name, carrier in getattr(batch, 'data', {}).items()}}


def freeze():
    import PyFLASH.batch as module
    source = Path(module.__file__)
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before = digest(source)
    output = OWNER / 'batch-names-original'
    output.mkdir(exist_ok=False)
    items = list(cases())
    native = execute_queries([query(case) for case in items], output / 'native', name='batch-table-unique-names')
    rows = []
    for case, result in zip(items, native['rows'], strict=True):
        names = values(result)
        rows.append({'case': case, 'native': result, 'expected_names': names, **production(case, names)})
    assert digest(source) == before
    record = {'actual_calls': len(rows), 'failed': sum(not row['passed'] for row in rows),
              'source_unchanged': True, 'source_sha256': before, 'rows': rows}
    (output / 'before.json').write_text(json.dumps(record, indent=2) + '\n')
    (output / 'original-batch.py').write_bytes(source.read_bytes())
    (output / 'original-reference.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({key: record[key] for key in ('actual_calls', 'failed', 'source_unchanged')}), flush=True)


if __name__ == '__main__':
    freeze()
