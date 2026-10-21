"""Exact original-cell window controls; no additional external-method vote."""
from pathlib import Path
import json

ARCHIVE = Path(__file__).with_name('reference-sources') / 'mixed-mean-fidelity'
MANIFEST_SHA256 = 'afa1ef5dc5f2bc6f4473b6dab772ac4b17fe7510e5171d5c2900d6854e1743c7'
CAPABILITY_PREFIXES = {'PyFLASH.utils.moving_average': ('mixed-mean-fidelity.',)}
COMPLETE_CAPABILITIES = frozenset()


def read(name):
    return json.loads((ARCHIVE / name).read_text(encoding='utf-8'))


def check_identity():
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE, 'source-files.json', MANIFEST_SHA256)
    for kind, count in (('real', 48), ('complex', 12)):
        before = read(kind + '/before.json')
        assert before['actual_calls'] == count and before['failed'] == 6 and before['source_unchanged']


def cases():
    return [dict(key='mixed-mean-fidelity.' + kind + '.' + row['key'], kind=kind, row=row)
            for kind in ('real', 'complex') for row in read(kind + '/before.json')['rows']]


def production(item, observation=None):
    import numpy as np
    from PyFLASH import utils
    row = next(row for row in read(item['kind'] + '/before.json')['rows'] if row['key'] == item['row']['key'])
    assert row == item['row']
    if item['kind'] == 'real':
        values = row['values']; expected = row['expected']
    else:
        values = [real if not imaginary else complex(real, imaginary)
                  for real, imaginary in zip(row['real'], row['imaginary'])]
        expected = [complex(real, imaginary)
                    for real, imaginary in zip(row['expected_real'], row['expected_imaginary'])]
    data = tuple(values) if row['carrier'] == 'tuple' else np.asarray(values, dtype=object) if row['carrier'] in ('object', 'readonly') else values.copy()
    if row['carrier'] == 'readonly':
        data.flags.writeable = False
    result = utils.moving_average(data, row['width'])
    assert isinstance(result, np.ndarray) and str(result.dtype) == row['dtype']
    assert result.tolist() == expected
    np.testing.assert_array_equal(np.asarray(data, dtype=object), np.asarray(values, dtype=object))
    if row['carrier'] == 'readonly':
        assert not data.flags.writeable
    actual = dict(dtype=str(result.dtype), real=[value.real for value in result],
                  imaginary=[value.imag for value in result], input_unchanged=True)
    answer = dict(dtype=row['dtype'], real=[value.real for value in expected],
                  imaginary=[value.imag for value in expected], input_unchanged=True)
    if observation is not None:
        observation.update(actual=actual, expected=answer)
    return actual


def validate(output):
    from reproducibility.table_family_validation import replay
    check_identity()
    return replay(cases(), lambda item, observed, path: production(item, observed), output,
        reference='Audit-authored exact rational sums of original real/imaginary cells; supporting arithmetic, no additional independently published-method vote',
        family='mixed-numeric-window-fidelity', shape='complete-window-arrays-dtypes-readonly-flags-and-original-cells')
