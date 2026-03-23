"""
Analysis iteration framework.

Two-layer design:
    1. Context  — carries state, supports nested iteration
    2. run()    — single entry point that wires iteration to action functions

Action function contract:
    def my_action(ctx: Context, state: dict, **kwargs) -> dict | None
        ctx   — current position in the data hierarchy
        state — shared dict for figures, axes, cross-iteration data
        return a dict of named results, or None to skip

Usage:
    # One-liner (what most users write):
    plot_mean_bars(batch1, filtered_cols, specificity=('Time', 'WeekEight'))

    # Which internally calls:
    run(batch1, over=['columns', 'conditions'], action=bar_action,
        columns=filtered_cols, specificity=('Time', 'WeekEight'))

    # Custom analysis — just write an action and plug it in:
    def count_objects(ctx, state):
        n = len(ctx.col_values())
        return {'column': ctx.column, 'condition': ctx.condition, 'n': n}

    results = run(batch1, over=['columns', 'conditions'],
                  action=count_objects, columns=my_cols)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, Callable, Literal
import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════
# CONTEXT
# ═══════════════════════════════════════════════════════════════

@dataclass
class Context:
    """
    All state for the current point in iteration.

    Action functions pull what they need by attribute name.
    Properties compute derived data on demand.
    """
    experiment: Any

    # ── Position in hierarchy ──────────────────────────────────
    condition: Optional[str] = None
    condition_obj: Any = None
    condition_index: int = 0

    animal: Optional[str] = None
    animal_index: int = 0

    scn: Optional[str] = None
    scn_index: int = 0

    column: Optional[str] = None
    column_index: int = 0

    factor: Optional[str] = None
    factor_value: Optional[str] = None
    factor_index: int = 0

    # ── Lazy data accessors ────────────────────────────────────

    @property
    def summary(self) -> pd.DataFrame:
        return self.experiment.summary

    @property
    def condition_df(self) -> pd.DataFrame:
        """Summary rows for the current condition."""
        if self.condition is None:
            return self.summary
        return self.summary[self.summary['Condition'] == self.condition]

    @property
    def factor_df(self) -> pd.DataFrame:
        """Summary rows for the current factor value."""
        if self.factor is None or self.factor_value is None:
            return self.summary
        return self.summary[self.summary[self.factor] == self.factor_value]

    @property
    def animal_df(self) -> pd.DataFrame:
        """Summary row(s) for the current animal."""
        if self.animal is None:
            return self.condition_df
        return self.summary[self.summary.index == self.animal]

    @property
    def color(self):
        return self.condition_obj.color if self.condition_obj else None

    @property
    def label(self):
        return self.condition_obj.label if self.condition_obj else (self.condition or '')

    @property
    def scn_dict(self):
        return self.experiment.getSCNDict()

    @property
    def num_conditions(self):
        return len(self.experiment.condition_list)

    @property
    def num_animals(self):
        if self.condition is None:
            return 0
        return len(self.scn_dict.get(self.condition, {}))

    @property
    def num_scns(self):
        if self.condition is None or self.animal is None:
            return 0
        return len(self.scn_dict.get(self.condition, {}).get(self.animal, []))

    def marker_df(self, marker_name) -> pd.DataFrame:
        """Get marker DataFrame filtered to the current context level."""
        df = self.experiment.data[marker_name].df.reset_index()
        if self.condition is not None:
            df = df[df['Condition'] == self.condition]
        if self.animal is not None:
            df = df[df['AnimalName'] == self.animal]
        if self.scn is not None:
            df = df[df['SCN'] == self.scn]
        return df

    def col_values(self, by='condition') -> pd.Series:
        """Current column's values at the current grouping level."""
        if self.column is None:
            raise ValueError("No column set in context")
        source = {
            'condition': self.condition_df,
            'factor': self.factor_df,
            'all': self.summary,
        }[by]
        return source[self.column].dropna()

    def col_animal_means(self, by='condition') -> pd.Series:
        """Per-animal means for the current column at the current level."""
        source = {
            'condition': self.condition_df,
            'factor': self.factor_df,
            'all': self.summary,
        }[by]
        return source.groupby('AnimalName')[self.column].mean().dropna()

    # ── Child context creation ─────────────────────────────────

    def _child(self, **overrides) -> 'Context':
        """Create a child context inheriting all current state."""
        fields = {
            'experiment': self.experiment,
            'condition': self.condition,
            'condition_obj': self.condition_obj,
            'condition_index': self.condition_index,
            'animal': self.animal,
            'animal_index': self.animal_index,
            'scn': self.scn,
            'scn_index': self.scn_index,
            'column': self.column,
            'column_index': self.column_index,
            'factor': self.factor,
            'factor_value': self.factor_value,
            'factor_index': self.factor_index,
        }
        fields.update(overrides)
        return Context(**fields)

    # ── Iterators ──────────────────────────────────────────────

    def iter_conditions(self):
        """Yield a child Context for each condition."""
        for i, cond in enumerate(self.experiment.condition_list):
            yield self._child(
                condition=cond.name,
                condition_obj=cond,
                condition_index=i,
            )

    def iter_animals(self):
        """Yield a child Context for each animal (within current condition, or all)."""
        if self.condition is not None:
            animals = self.scn_dict.get(self.condition, {})
            for i, animal in enumerate(animals):
                yield self._child(animal=animal, animal_index=i)
        else:
            idx = 0
            for c_ctx in self.iter_conditions():
                for a_ctx in c_ctx.iter_animals():
                    yield a_ctx._child(animal_index=idx)
                    idx += 1

    def iter_scns(self):
        """Yield a child Context for each SCN in the current animal."""
        if self.animal is None:
            raise ValueError("Must be at animal level to iterate SCNs")
        scns = self.scn_dict.get(self.condition, {}).get(self.animal, [])
        for i, scn in enumerate(scns):
            yield self._child(scn=scn, scn_index=i)

    def iter_factors(self, factor_name):
        """Yield a child Context for each unique value of a factor."""
        values = self.summary[factor_name].dropna().unique()
        # Order by condition list, then add any extras
        ordered = []
        for cond in self.experiment.condition_list:
            match = next((v for v in values if v in cond.name), None)
            if match and match not in ordered:
                ordered.append(match)
        for v in values:
            if v not in ordered:
                ordered.append(v)
        for i, val in enumerate(ordered):
            yield self._child(
                factor=factor_name,
                factor_value=val,
                factor_index=i,
            )

    def iter_columns(self, columns):
        """Yield a child Context for each column."""
        for i, col in enumerate(columns):
            yield self._child(column=col, column_index=i)


# ═══════════════════════════════════════════════════════════════
# LEVEL DISPATCH
# ═══════════════════════════════════════════════════════════════

Level = Literal['columns', 'conditions', 'animals', 'scns', 'factors']

_ITER_MAP = {
    'columns':    lambda ctx, kw: ctx.iter_columns(kw['columns']),
    'conditions': lambda ctx, kw: ctx.iter_conditions(),
    'animals':    lambda ctx, kw: ctx.iter_animals(),
    'scns':       lambda ctx, kw: ctx.iter_scns(),
    'factors':    lambda ctx, kw: ctx.iter_factors(kw['factor']),
}


# ═══════════════════════════════════════════════════════════════
# RUN — the single entry point
# ═══════════════════════════════════════════════════════════════

def run(experiment, over, action,
        columns=None, factor=None, specificity=None,
        setup=None, teardown=None,
        **action_kwargs) -> dict:
    """
    Iterate over one or more levels and apply an action at the innermost level.

    Parameters
    ----------
    experiment : Experiment or Batch
    over : str or list[str]
        Iteration level(s). Single string = one level.
        List = nested: ['columns', 'conditions'] iterates columns as the
        outer loop, conditions as the inner loop.
    action : callable(ctx, state, **kwargs) -> dict | None
        Called at the innermost level. Returns named results.
    columns : list[str]
        Required when 'columns' is in `over`.
    factor : str
        Required when 'factors' is in `over`.
    specificity : tuple (column_name, value1, value2, ...) or None
        Filters summary before iteration.
    setup : callable(ctx, state) -> None
        Called at the start of each outermost iteration.
        Use to create figures, axes, etc. and store in state.
    teardown : callable(ctx, state, results) -> None
        Called at the end of each outermost iteration.
        Use to save figures, print summaries, etc.
    **action_kwargs
        Passed through to the action function.

    Returns
    -------
    dict of {name: [values]}

    Examples
    --------
    # Single level
    run(batch, over='conditions', action=my_fn)

    # Nested: outer=columns, inner=conditions
    run(batch, over=['columns', 'conditions'], action=my_fn,
        columns=filtered_cols)

    # With figure setup/teardown
    def make_fig(ctx, state):
        fig, ax = plt.subplots()
        state['fig'] = fig
        state['ax'] = ax

    def save_fig_td(ctx, state, results):
        state['fig'].savefig(f'{ctx.column}.svg')
        plt.close(state['fig'])

    run(batch, over=['columns', 'conditions'], action=bar_action,
        columns=cols, setup=make_fig, teardown=save_fig_td)
    """
    if isinstance(over, str):
        over = [over]

    # Apply specificity filter
    _orig_summary = None
    if specificity is not None:
        _orig_summary = experiment.summary
        key, *raw_values = specificity
        values = []
        for v in raw_values:
            if isinstance(v, (list, tuple, set, np.ndarray, pd.Series, pd.Index)):
                values.extend(list(v))
            else:
                values.append(v)

        if key in experiment.summary.columns and len(values) > 0:
            col = experiment.summary[key]
            if (
                pd.api.types.is_object_dtype(col)
                or pd.api.types.is_string_dtype(col)
                or pd.api.types.is_categorical_dtype(col)
            ):
                norm_col = col.astype(str).str.strip().str.casefold()
                norm_values = {str(v).strip().casefold() for v in values}
                mask = norm_col.isin(norm_values)
            else:
                mask = col.isin(values)
            experiment.summary = experiment.summary[mask].copy()

    root = Context(experiment=experiment)
    iter_kwargs = {'columns': columns, 'factor': factor}
    all_results = {}
    state = {}

    def _accumulate(result):
        if result is None:
            return
        for key, value in result.items():
            all_results.setdefault(key, []).append(value)

    def _recurse(ctx, levels):
        if not levels:
            result = action(ctx, state, **action_kwargs)
            _accumulate(result)
            return

        current, *remaining = levels
        is_outer = (current == over[0])

        for child_ctx in _ITER_MAP[current](ctx, iter_kwargs):
            if is_outer and setup is not None:
                setup(child_ctx, state)

            _recurse(child_ctx, remaining)

            if is_outer and teardown is not None:
                teardown(child_ctx, state, all_results)

    try:
        _recurse(root, over)
    finally:
        # Always restore summary, even if plotting/stats raises.
        if _orig_summary is not None:
            experiment.summary = _orig_summary

    return all_results


# ═══════════════════════════════════════════════════════════════
# SHORTHAND
# ═══════════════════════════════════════════════════════════════

def apply_per(experiment, level, action, **kwargs):
    """Single-level shorthand for run()."""
    return run(experiment, over=level, action=action, **kwargs)
