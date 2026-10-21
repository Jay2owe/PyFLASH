"""Full public-table families must coexist in the real workflow's CSV receipt."""
import csv
import json
from pathlib import Path
from reproducibility import mini_exclusion_contract as exclusions
from reproducibility import mini_score_contract as scores
from reproducibility import mini_nonfinite_score_contract as nonfinite
from reproducibility import mini_lifecycle_contract as lifecycle
from reproducibility import mini_image_condition_contract as images
from reproducibility import mini_object_mean_contract as object_means
from reproducibility import parent_ownership_contract as ownership
from reproducibility import mini_csv_refresh_contract as refresh
from reproducibility.table_family_validation import replay
from reproducibility.run import write_csv


def test_actual_public_tables_write_one_complete_mixed_family_receipt(tmp_path):
    combined = []
    for module in (exclusions, scores, nonfinite, lifecycle, images, object_means, ownership, refresh):
        item = module.cases()[0]
        if module in (lifecycle, images, object_means, refresh):
            action = lambda value, observation, path, module=module: module.production(value, path, observation)
        else:
            action = lambda value, observation, path, module=module: module.production(value, observation)
        output = tmp_path / module.__name__.rsplit('.', 1)[-1]
        rows = replay([item], action, output, reference='Retained original full table',
                      family=module.__name__, shape='all-declared-table-fields')
        assert rows[0]['status'] == 'agree'
        assert rows[0]['family'] == module.__name__
        assert json.loads((output / 'paired.json').read_text())[0]['error'] is None
        combined.extend(rows)
    target = tmp_path / 'comparisons.csv'
    write_csv(target, combined)
    records = list(csv.DictReader(target.open(encoding='utf-8')))
    assert len(records) == 8
    assert all(row['status'] == 'agree' and row['frozen_reference_agrees'] == 'True' for row in records)
    assert len({row['contract'] for row in records}) == 8


def test_failure_retains_original_nonfinite_inputs_and_complete_csv_schema(tmp_path):
    item = nonfinite.cases()[0]
    def fail(value, observation, path):
        observation['actual'] = {'observed': 'Inf'}
        observation['expected'] = {'observed': 'NaN'}
        raise AssertionError('Original scientific disagreement')
    rows = replay([item], fail, tmp_path, reference='Original native R', family='native-infinite-score', shape='whole-table')
    assert rows[0]['status'] == 'disagree'
    paired = json.loads((tmp_path / 'paired.json').read_text())[0]
    assert paired['item']['case']['count'][0] == 'Inf'
    assert paired['error'] == 'AssertionError: Original scientific disagreement'
    assert paired['actual'] == {'observed': 'Inf'}
    write_csv(tmp_path / 'comparisons.csv', rows)
