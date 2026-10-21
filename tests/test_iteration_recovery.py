from types import SimpleNamespace

import pandas as pd
import pytest

from PyFLASH.iteration import Context, run


def experiment(summary, conditions):
    return SimpleNamespace(
        summary=summary,
        condition_list=[SimpleNamespace(name=name) for name in conditions],
    )


@pytest.mark.parametrize('values', [[0, 2, 1], [False, True]])
def test_factor_iteration_preserves_numeric_and_false_values(values):
    frame = pd.DataFrame({'Dose': values})
    target = experiment(frame, ['control', 'treated'])
    contexts = list(Context(target).iter_factors('Dose'))
    assert [item.factor_value for item in contexts] == values
    assert [item.factor_index for item in contexts] == list(range(len(values)))
    pd.testing.assert_frame_equal(target.summary, frame)


def test_factor_order_uses_exact_condition_membership():
    frame = pd.DataFrame({
        'Condition': ['male', 'female', 'other'],
        'Sex': ['male', 'female', 'other'],
    })
    target = experiment(frame, ['female', 'male'])
    assert [item.factor_value for item in Context(target).iter_factors('Sex')] == [
        'female', 'male', 'other',
    ]


def test_filter_preflight_failure_preserves_every_original_summary(monkeypatch):
    first = pd.DataFrame({'Time': ['early', 'late'], 'value': [1, 2]})
    invalid = pd.DataFrame([['early', 'early']], columns=['Time', 'Time'])
    target = experiment(first, ['control'])
    original = {'first': first, 'invalid': invalid}
    target.summaries = original
    from PyFLASH.utils import filter_df_by_specificity
    def fail_later(frame, specificity):
        if frame is invalid:
            raise RuntimeError('Later summary could not be filtered')
        return filter_df_by_specificity(frame, specificity)
    monkeypatch.setattr('PyFLASH.iteration.filter_df_by_specificity', fail_later)
    with pytest.raises(RuntimeError, match='Later summary'):
        run(target, 'conditions', lambda *_: {}, specificity=('Time', 'early'))
    assert target.summaries is original
    assert target.summaries['first'] is first
    pd.testing.assert_frame_equal(first, pd.DataFrame({'Time': ['early', 'late'], 'value': [1, 2]}))


def test_repeated_levels_only_call_outer_hooks_once_per_outer_iteration():
    target = experiment(pd.DataFrame(), ['a', 'b'])
    events = []
    result = run(
        target, ['conditions', 'conditions'],
        lambda ctx, state: {'condition': ctx.condition},
        setup=lambda ctx, state: events.append(('setup', ctx.condition)),
        teardown=lambda ctx, state, results: events.append(('teardown', ctx.condition)),
    )
    assert result == {'condition': ['a', 'b', 'a', 'b']}
    assert events == [('setup', 'a'), ('teardown', 'a'), ('setup', 'b'), ('teardown', 'b')]
