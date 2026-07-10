# Plot Spec Batch

## Goal

Run two registered plot entries from a JSON plot spec against one table.

## Code

```python
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from PyFLASH import run_spec

df = pd.DataFrame({
    "Subject": ["C1", "C2", "C3", "A1", "A2", "A3"],
    "Diagnosis": ["Control", "Control", "Control", "AD", "AD", "AD"],
    "GFAP Volume": [1.0, 1.1, 0.9, 2.0, 2.2, 2.1],
    "Iba1 Volume": [0.8, 0.7, 0.9, 1.4, 1.5, 1.3],
})

spec = {
    "plots": [
        {
            "type": "mean_bars",
            "data_cols": ["GFAP Volume"],
            "group_col": "Diagnosis",
            "subject_col": "Subject",
            "save": False,
            "save_normality": False,
        },
        {
            "type": "matrices",
            "data_cols": ["GFAP Volume", "Iba1 Volume"],
            "group_col": "Diagnosis",
            "subject_col": "Subject",
            "split_by": "all",
            "save": False,
        },
    ]
}

with TemporaryDirectory() as tmp:
    spec_path = Path(tmp) / "plots.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    results = run_spec(df, spec_path)

print([type(item).__name__ if item is not None else None for item in results])
```

## Result

`run_spec` returns a list with one item per `plots` entry. The first item is the
mean-bars result and the second is the matrix result. Each entry controls its
own saving behavior.

## Notes

JSON avoids an optional YAML dependency for this minimal example. In normal
projects, keep the spec file beside the analysis script so the exact plot batch
can be rerun.

## See Also

- [run_spec](../functions/run_spec.md)
- [Plot spec files](../data-structures/plot-spec-files.md)
- [plot_mean_bars](../functions/plot_mean_bars.md)
- [plot_matrices](../functions/plot_matrices.md)
