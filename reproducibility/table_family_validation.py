"""Keep full-table family receipts compatible with the complete workflow."""
from pathlib import Path


def replay(items, action, output, *, reference, family, shape, rtol=0., atol=0.):
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    from reproducibility.scientific_utility_contract import encode
    output = Path(output)
    rows, paired = [], []
    for index, item in enumerate(items):
        observation, error = {}, None
        try:
            action(item, observation, output / 'cases' / str(index))
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        declared_reference = reference(item) if callable(reference) else reference
        rows.append(comparison(item['key'], declared_reference, family,
            observation.get('actual'), observation.get('expected'), error is None, True, shape, rtol, atol))
        paired.append(encode({'item': item, **observation, 'error': error}))
    write_json(output / 'paired.json', paired)
    return rows
