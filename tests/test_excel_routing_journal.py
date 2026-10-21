"""Completed routing answers survive interruption without quadratic writes."""
import json

import pytest

from reproducibility import excel_orchestration_contract as routing


def prepare(monkeypatch, observer):
    monkeypatch.setattr(routing, 'check_identity', lambda: None)
    monkeypatch.setattr(routing, 'check_parameter_coverage', lambda: {'save_path'})
    monkeypatch.setattr(routing, 'cases', lambda: [{'key': 'first'}, {'key': 'second'}])
    monkeypatch.setattr(routing, 'observe', observer)


def test_complete_answers_written_once_with_durable_case_journal(monkeypatch, tmp_path):
    from PyFLASH import _persistence
    original = _persistence.write_json
    writes = []
    def capture(path, payload):
        writes.append(path.name)
        original(path, payload)
    monkeypatch.setattr(_persistence, 'write_json', capture)
    prepare(monkeypatch, lambda row, output: {'values': [1, None, 3]})
    assert len(routing.validate(tmp_path)) == 2
    journal = [json.loads(line) for line in
               (tmp_path / 'excel-orchestration-paired.jsonl').read_text().splitlines()]
    receipt = json.loads((tmp_path / 'excel-orchestration-paired.json').read_text())
    assert receipt['rows'] == journal
    assert receipt['covered_parameters'] == ['save_path']
    assert writes == ['excel-orchestration-paired.json']


def test_interruption_preserves_completed_answers_and_refuses_overwrite(monkeypatch, tmp_path):
    def observe(row, output):
        if row['key'] == 'second':
            raise KeyboardInterrupt('interrupted')
        return {'values': [4, None]}
    prepare(monkeypatch, observe)
    with pytest.raises(KeyboardInterrupt):
        routing.validate(tmp_path)
    journal = tmp_path / 'excel-orchestration-paired.jsonl'
    before = journal.read_bytes()
    assert json.loads(before)['case']['key'] == 'first'
    assert not (tmp_path / 'excel-orchestration-paired.json').exists()
    with pytest.raises(FileExistsError):
        routing.validate(tmp_path)
    assert journal.read_bytes() == before


def test_case_failure_is_retained_and_later_cases_still_run(monkeypatch, tmp_path):
    def observe(row, output):
        if row['key'] == 'first':
            raise ValueError('original failure')
        return {'values': [2]}
    prepare(monkeypatch, observe)
    rows = routing.validate(tmp_path)
    answers = json.loads((tmp_path / 'excel-orchestration-paired.json').read_text())['rows']
    assert 'original failure' in answers[0]['error']
    assert not answers[0]['agrees'] and answers[1]['agrees']
    assert len(rows) == 2
