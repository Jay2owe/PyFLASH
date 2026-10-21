"""Reuse external answers only at their recorded method/input boundary."""
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path


def integral_power_values(output, *, recompute=False):
    """Verify reference source, inputs, versions and precision before reuse.

    Candidate package edits do not change the independent quadrature. The
    receipt explicitly distinguishes reuse from fresh reference execution.
    Production still runs for every case in the complete comparison set.
    """
    from reproducibility import native_power, power_integral
    fixture = power_integral.FIXTURE
    evidence = json.loads(fixture.read_text(encoding='utf-8'))
    source_hash = hashlib.sha256(Path(power_integral.__file__).read_bytes()).hexdigest()
    if evidence['reference_code_sha256'] != source_hash:
        raise ValueError('Independent power integral code changed; preserve and review the reference.')
    actual_versions = {name:version(name) for name in evidence['versions']}
    if actual_versions != evidence['versions']:
        raise ValueError('Independent power integral versions changed; recompute and review the reference.')
    inputs = [{key:row[key] for key in ('key','capability','parameters')} for row in evidence['rows']]
    if inputs != native_power.cases():
        raise ValueError('Frozen integral power inputs changed.')
    rows, receipts = [], []
    fixture_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
    for row in evidence['rows']:
        identity = {'method_source_sha256':source_hash, 'versions':actual_versions,
                    'input':{key:row[key] for key in ('key','capability','parameters')},
                    'settings':{'precision_decimal_digits':45}}
        key = hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        values = power_integral.reference(row) if recompute else [
            math.nan if value is None else value for value in row['expected']]
        rows.append((row, values))
        receipts.append({'key':row['key'], 'reference_key':key, 'identity':identity,
                         'reused':not recompute, 'fixture':str(fixture.resolve()),
                         'fixture_sha256':fixture_hash, 'values':[
                             value if math.isfinite(value) else None for value in values]})
    from reproducibility.run import write_json
    write_json(Path(output)/'integral-reference-receipt.json', {
        'schema_version':1, 'scope':'independent quadrature only; production runs afresh',
        'execution':'fresh reference computation' if recompute else 'verified frozen reference reuse',
        'rows':receipts})
    return rows
