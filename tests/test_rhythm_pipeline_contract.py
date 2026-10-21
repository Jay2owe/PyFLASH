from reproducibility import cosinor_table_contract, rhythm_pipeline_contract


def test_public_rhythm_pipeline_declarations_cover_every_expressible_table_case():
    declared = rhythm_pipeline_contract.cases()
    expressible = [row for row in cosinor_table_contract.cases()
                   if 'time_map' not in row['parameters']]
    assert len(declared) == len(expressible) == 213
    assert [item['table_case']['key'] for item in declared] == [
        row['key'] for row in expressible]
    assert rhythm_pipeline_contract.required_keys()[:len(declared)] == [
        item['key'] for item in declared]
    assert set(rhythm_pipeline_contract.required_keys()[len(declared):]) == set(
        rhythm_pipeline_contract.PARAMETER_REQUIRED_KEYS)


def test_public_rhythm_pipeline_matches_independent_table_answers_for_each_method():
    declared = rhythm_pipeline_contract.cases()
    representatives = {}
    for item in declared:
        method = item['table_case']['parameters']['method']
        representatives.setdefault(method, item)
    assert set(representatives) == {'pooled', 'population_mean', 'mixed'}
    for index, method in enumerate(('pooled', 'population_mean', 'mixed')):
        row, retained = rhythm_pipeline_contract.compare_case(representatives[method], index)
        assert row['status'] == 'agree', row
        assert retained['agrees']


def test_public_rhythm_pipeline_keeps_falsey_integer_group_column_labels():
    declared = next(item for item in rhythm_pipeline_contract.cases()
                    if item['table_case']['parameters']['group_col'] == 0)
    row, retained = rhythm_pipeline_contract.compare_case(declared)
    assert row['status'] == 'agree', row
    assert retained['production']['records'][0]['group'] == 'A'


def test_public_rhythm_parameter_mode_matches_independent_contracts_and_controls(tmp_path):
    rows = rhythm_pipeline_contract._validate_parameter(tmp_path)
    assert {row['contract'] for row in rows} == set(
        rhythm_pipeline_contract.PARAMETER_REQUIRED_KEYS)
    failures = [row for row in rows if row['status'] != 'agree']
    assert not failures, failures
