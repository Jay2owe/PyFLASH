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
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Literal
import numpy as np
import pandas as pd

from IF_analysis.utils import filter_df_by_specificity, flatten_specificity_values


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

    region: Optional[str] = None
    region_index: int = 0

    column: Optional[str] = None
    column_index: int = 0

    factor: Optional[str] = None
    factor_value: Optional[str] = None
    factor_index: int = 0

    # ── ROI base for multi-region support ──────────────────────
    roi_base: Optional[str] = None

    # ── Lazy data accessors ────────────────────────────────────

    @property
    def summary(self) -> pd.DataFrame:
        if self.roi_base is not None and hasattr(self.experiment, 'summaries'):
            return self.experiment.summaries.get(self.roi_base, self.experiment.summary)
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
    def region_dict(self):
        return self.experiment.getRegionDict(roi_base=self.roi_base)

    # Backward compat aliases
    @property
    def scn_dict(self):
        return self.region_dict

    @property
    def num_conditions(self):
        return len(self.experiment.condition_list)

    @property
    def num_animals(self):
        if self.condition is None:
            return 0
        return len(self.region_dict.get(self.condition, {}))

    @property
    def num_regions(self):
        if self.condition is None or self.animal is None:
            return 0
        return len(self.region_dict.get(self.condition, {}).get(self.animal, []))

    # Backward compat alias
    @property
    def num_scns(self):
        return self.num_regions

    def marker_df(self, marker_name) -> pd.DataFrame:
        """Get marker DataFrame filtered to the current context level."""
        df = self.experiment.data[marker_name].df.reset_index()
        if self.condition is not None:
            df = df[df['Condition'] == self.condition]
        if self.animal is not None:
            df = df[df['AnimalName'] == self.animal]
        if self.region is not None:
            df = df[df['Region'] == self.region]
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

    # ── Backward compat ───────────────────────────────────────

    @property
    def scn(self):
        return self.region

    @scn.setter
    def scn(self, value):
        self.region = value

    @property
    def scn_index(self):
        return self.region_index

    @scn_index.setter
    def scn_index(self, value):
        self.region_index = value

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
            'region': self.region,
            'region_index': self.region_index,
            'column': self.column,
            'column_index': self.column_index,
            'factor': self.factor,
            'factor_value': self.factor_value,
            'factor_index': self.factor_index,
            'roi_base': self.roi_base,
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
            animals = self.region_dict.get(self.condition, {})
            for i, animal in enumerate(animals):
                yield self._child(animal=animal, animal_index=i)
        else:
            idx = 0
            for c_ctx in self.iter_conditions():
                for a_ctx in c_ctx.iter_animals():
                    yield a_ctx._child(animal_index=idx)
                    idx += 1

    def iter_regions(self):
        """Yield a child Context for each region (section) in the current animal."""
        if self.animal is None:
            raise ValueError("Must be at animal level to iterate regions")
        regions = self.region_dict.get(self.condition, {}).get(self.animal, [])
        for i, rgn in enumerate(regions):
            yield self._child(region=rgn, region_index=i)

    # Backward compat alias
    iter_scns = iter_regions

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

Level = Literal['columns', 'conditions', 'animals', 'regions', 'scns', 'factors']

_ITER_MAP = {
    'columns':    lambda ctx, kw: ctx.iter_columns(kw['columns']),
    'conditions': lambda ctx, kw: ctx.iter_conditions(),
    'animals':    lambda ctx, kw: ctx.iter_animals(),
    'regions':    lambda ctx, kw: ctx.iter_regions(),
    'scns':       lambda ctx, kw: ctx.iter_regions(),  # backward compat alias
    'factors':    lambda ctx, kw: ctx.iter_factors(kw['factor']),
}


# ═══════════════════════════════════════════════════════════════
# RUN — the single entry point
# ═══════════════════════════════════════════════════════════════

def run(experiment, over, action,
        columns=None, factor=None, specificity=None,
        roi_base=None,
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
    roi_base : str or None
        Which ROI type to use (e.g. 'SCN', 'OC'). Determines which
        summary and region dict the Context uses.
    setup : callable(ctx, state) -> None
        Called at the start of each outermost iteration.
    teardown : callable(ctx, state, results) -> None
        Called at the end of each outermost iteration.
    **action_kwargs
        Passed through to the action function.

    Returns
    -------
    dict of {name: [values]}
    """
    if isinstance(over, str):
        over = [over]

    # Apply specificity filter
    _orig_summaries = None
    if specificity is not None:
        if hasattr(experiment, 'summaries') and experiment.summaries:
            _orig_summaries = {k: v.copy() for k, v in experiment.summaries.items()}
            for k, v in experiment.summaries.items():
                filtered = filter_df_by_specificity(v, specificity)
                if len(filtered) < len(v):
                    experiment.summaries[k] = filtered.copy()
        else:
            _orig_summaries = {'_legacy': experiment.summary}
            filtered = filter_df_by_specificity(experiment.summary, specificity)
            if len(filtered) < len(experiment.summary):
                experiment.summary = filtered.copy()

    root = Context(experiment=experiment, roi_base=roi_base)
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
        if _orig_summaries is not None:
            if '_legacy' in _orig_summaries:
                experiment.summary = _orig_summaries['_legacy']
            else:
                experiment.summaries = _orig_summaries

    return all_results


# ═══════════════════════════════════════════════════════════════
# SHORTHAND
# ═══════════════════════════════════════════════════════════════

def apply_per(experiment, level, action, **kwargs):
    """Single-level shorthand for run()."""
    return run(experiment, over=level, action=action, **kwargs)
