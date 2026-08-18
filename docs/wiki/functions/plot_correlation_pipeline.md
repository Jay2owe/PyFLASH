# plot_correlation_pipeline

## Summary

`plot_correlation_pipeline` is the plotting-module compatibility wrapper for
the full [`correlation`](correlation.md) pipeline. Registry name:
`correlation_pipeline`.

The wrapper keeps every public `plot_*` function reachable through
`PyFLASH.spec.PLOT_REGISTRY` while still forwarding directly to
`PyFLASH.pipeline.correlation`.

## Usage

Prefer the registry short-name or the top-level pipeline function:

```python
from PyFLASH import correlation

correlation(
    batch,
    data_cols=["Marker1_Count", "Marker2_Count"],
    gate="p",
)
```

The equivalent plotting-wrapper call is:

```python
from PyFLASH.plotting import plot_correlation_pipeline

plot_correlation_pipeline(
    batch,
    data_cols=["Marker1_Count", "Marker2_Count"],
    gate="p",
)
```

## Notes

All parameters and outputs are documented on [`correlation`](correlation.md).
This wrapper is describe-layer covered through the pipeline manifest and
structured correlation records.

## See Also

- [`correlation`](correlation.md)
- [Matrix plots](../plot-types/matrix-plots.md)
- [Correlation statistics](../statistics/correlation.md)
