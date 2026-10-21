"""Recalculate report equations and exact recorded resampling arrangements."""
import json
from reproducibility import effect_report_contract as contract
from reproducibility import effect_report_mathematical_reference as mathematical
from reproducibility.normality_association_validation import comparison

def validate(output):
    fixture = contract.check_identity()
    mathematical.draws_cache.clear()
    mathematical.interval_cache.clear()
    rows, paired = [], []
    for recorded in fixture['rows']:
        case = recorded['case']
        answer, draw_keys = mathematical.reference(case)
        actual = contract.production(case)
        unchanged = contract.equal(answer, recorded['expected']) and draw_keys == recorded['draw_keys']
        agrees = unchanged and contract.equal(actual, answer)
        rows.append(comparison(case['key'], 'accepted-independent-scalar-BCa-and-magnitude-composition',
            'complete-effect-report-composition/no-additional-child-or-RNG-implementation-vote',
            actual, answer, agrees, unchanged, 'all-overall-pairwise-family-fields-and-resampling-scope', 1e-9, 1e-12))
        paired.append({'case': case, 'production': actual, 'reference': answer,
                       'frozen_reference': recorded['expected'], 'draw_keys': draw_keys})
    if list(mathematical.draws_cache.values()) != fixture['arrangements']:
        raise ValueError('Effect-report resampling arrangements or independent endpoints changed')
    (output / 'effect-report-paired-data.json').write_text(json.dumps({
        'rows': paired, 'scope': fixture['scope'],
        'resampling_arrangements_unchanged': True}, indent=2, allow_nan=False), encoding='utf-8')
    return rows
