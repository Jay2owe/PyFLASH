# Slow Model Sweeps

## Symptoms

- `iterative_model_sweep` runs for a very long time with high CPU and no output
  until the end.
- Restarting after an interruption loses all progress.
- The call raises a validation error such as
  `model_preset must be 'ultra_compact', 'compact', or 'full'.`,
  `cv must be 'stratified5', 'stratifiedN', or 'loo'.`, or
  `search_strategy must be 'exhaustive' or 'beam'.`.

## Likely Causes

- Exhaustive search evaluates every predictor subset from size 1 to
  `max_features`, so cost grows combinatorially with the candidate-pool size.
- `model_preset="full"` multiplies each subset by a larger classifier grid;
  `"compact"` and `"ultra_compact"` are smaller.
- Leave-one-out cross-validation (`cv="loo"`) refits once per sample and is slow
  on larger datasets.
- Permutation testing (`permutations > 0`) repeats the whole scoring pass many
  times.
- Checkpointing was effectively off (`save=False`, or `checkpoint_every <= 0`),
  so nothing could be resumed.

## Fix

Shrink the predictor pool first, keep `max_features` small, screen with the
smallest preset, enable checkpoints, and use all cores:

```python
from PyFLASH import iterative_model_sweep

result = iterative_model_sweep(
    batch,
    target="Diagnosis",
    data_col_contains=["_Count", "_VolumeTotal"],
    data_col_exclude=["Raw"],
    max_features=2,
    model_preset="ultra_compact",
    cv="stratified5",
    permutations=0,          # add permutation testing only after narrowing
    save=True,
    checkpoint_every=50,     # flush partial results every 50 rows
    resume=True,             # resume a matching checkpoint after an interruption
    n_jobs=-1,               # use all cores
)
```

For a large candidate pool, switch to `search_strategy="beam"` with a sensible
`beam_width`: it expands only the best subsets from each level, which is much
faster but can miss the global-best subset. `parallel_backend="processes"` can
help very large exhaustive sweeps, at the cost of more startup overhead on
Windows.

## Check

`resume=True` only rejoins a checkpoint when `save=True` and `checkpoint_every`
is above zero; partial results are written into the same run folder as the final
outputs. After narrowing the model space, re-run the shortlist with `"compact"`
or `"full"` and `permutations > 0` for a confirmatory pass.

## Related Pages

- [iterative_model_sweep](../functions/iterative_model_sweep.md)
- [Run a model sweep](../workflows/run-model-sweep.md)
- [Model options](../parameters/model-options.md)
- [Model sweep outputs](../outputs/model-sweep-outputs.md)
- [Classification](../statistics/classification.md)
