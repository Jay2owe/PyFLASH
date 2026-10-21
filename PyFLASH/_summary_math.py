"""Keep pandas summary schemas while preserving extreme represented means."""
import math
from fractions import Fraction
import numpy as np


def _represented_mean(values):
    """Round the mean once, after summing the represented input values."""
    if not values:
        return math.nan
    if any(math.isinf(value) for value in values):
        positive = any(value == math.inf for value in values)
        negative = any(value == -math.inf for value in values)
        return math.nan if positive and negative else math.inf if positive else -math.inf
    exact = sum((Fraction(value.item() if isinstance(value, np.generic) else value)
                 for value in values), Fraction())
    return float(exact / len(values))


def _measurement_number(value):
    """Preserve integer digits before calculating a mixed-storage mean."""
    from numbers import Real
    if isinstance(value, Real):
        return value.item() if isinstance(value, np.generic) else value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return float(value)
    raise ValueError('Not a real measurement')


def grouped_mean(frame, by, columns):
    """Preserve pandas grouping/dtypes and repair numerically hazardous means.

    Ordinary nonnegative measurements retain the vectorized pandas path. Exact
    represented-input sums handle cancellation, overflow and subnormal groups.
    Missing observations remain excluded; opposite infinities remain undefined.
    """
    from pandas.api.types import is_numeric_dtype, is_complex_dtype, is_integer_dtype
    grouped = frame.groupby(by)
    result = grouped[columns].mean()
    for column in columns:
        series = frame[column]
        if not is_numeric_dtype(series.dtype) or is_complex_dtype(series.dtype):
            continue
        result_dtype = result[column].dtype
        precision = np.finfo(getattr(result_dtype, 'numpy_dtype', result_dtype))
        numbers = series.dropna().to_numpy(dtype=float)
        finite = numbers[np.isfinite(numbers)]
        nonzero = finite[finite != 0]
        hazardous = (np.isinf(numbers).any()
                     or (is_integer_dtype(series.dtype) and finite.size and np.max(np.abs(finite)) > 2**53 / max(1, len(numbers)))
                     or (finite.size and np.max(np.abs(finite)) > precision.max / max(1, len(numbers)))
                     or (finite.size and np.min(finite) < 0 < np.max(finite))
                     or (nonzero.size and np.min(np.abs(nonzero)) < precision.tiny))
        if not hazardous:
            continue
        for key, subset in grouped[column]:
            values = subset.dropna().tolist()
            result.at[key, column] = _represented_mean(values)
    return result


def _flat_summary_parts(frame, protected=()):
    """Average acquired measurements and retain excluded groups and metadata."""
    import pandas as pd
    from pandas.api.types import is_numeric_dtype
    sentinel = 'NOT_INCLUDED_IN_EXPERIMENT'
    protected = set(protected) | {'AnimalName', 'ImageROI', 'ROINameRaw', 'Condition', 'Label'}
    from numbers import Real
    numeric, metadata, masks, mixed = [], [], {}, {}
    for column in frame.columns:
        if column in {'AnimalName', 'ImageROI', 'ROINameRaw', 'Condition'}:
            continue
        series = frame[column]
        if column in protected:
            metadata.append(column)
        elif is_numeric_dtype(series.dtype):
            numeric.append(column)
        else:
            excluded = series.astype('string').str.contains(sentinel, regex=False, na=False)
            observed = series.notna() & ~excluded
            try:
                values = [_measurement_number(value) for value in series.loc[observed]]
            except (ValueError, TypeError, OverflowError):
                values = None
            if values is not None and (excluded.any() or
                    (observed.any() and all(isinstance(value, Real) for value in series.loc[observed]))):
                parsed = pd.Series(None, index=frame.index, dtype=object)
                parsed.loc[observed] = values
                mixed[column] = parsed
                masks[column] = excluded
            else:
                metadata.append(column)
    means = grouped_mean(frame, 'AnimalName', numeric)
    for column, series in mixed.items():
        means[column] = series.groupby(frame['AnimalName']).agg(
            lambda subset: _represented_mean(subset.dropna().tolist())).astype(float)
    # Keep acquired measurement order, independent of their storage dtype.
    means = means.reindex(columns=[column for column in frame.columns
                                   if column in numeric or column in mixed])
    for column, excluded in masks.items():
        missing = frame[column].isna()
        groups = frame['AnimalName']
        entirely_excluded = (excluded | missing).groupby(groups).all() & excluded.groupby(groups).any()
        if entirely_excluded.any():
            means[column] = means[column].astype(object)
            means.loc[entirely_excluded[entirely_excluded].index, column] = sentinel
    return means, frame.groupby('AnimalName')[metadata].first()
