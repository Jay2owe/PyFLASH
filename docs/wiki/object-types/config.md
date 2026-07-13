# Config

## Summary

`Config` is PyFLASH's package-wide settings object. It is a class with global
attributes, not an instance that you create. Changing `Config.SOME_SETTING`
affects later PyFLASH operations in the current Python process.

Use explicit function arguments when a function provides them. Use `Config`
when you need to change a package-wide default such as colocalisation threshold,
save behavior, colors, aliases, montage filename, or figure layout behavior.

## How To Create It

Import it:

```python
from PyFLASH import Config

print(Config.THRESHOLD)
```

Modify attributes directly:

```python
from PyFLASH import Config

old = Config.SAVE_MODE
try:
    Config.SAVE_MODE = False
    # run plotting code here
finally:
    Config.SAVE_MODE = old
```

Use a `try` / `finally` block in scripts and tests so temporary global changes
are restored.

## Important Attributes

| Attribute | Meaning |
|---|---|
| `THRESHOLD` | Default colocalisation threshold used by automatic object-marker colocalisation cleaning. |
| `PIXEL_SIZE` | Microns per pixel used by coordinate conversions. |
| `SECTION_THICKNESS_UM` | Fallback section thickness in microns when ROI volume is unavailable. |
| `FALLBACK_USERS` | Optional usernames used by path resolution when moving data between machines. |
| `AB`, `CK`, `TOTAL_LABEL`, `COUNT_LABEL`, `CUBED` | Display-label constants used by naming and export helpers. |
| `COLORS` | Named PyFLASH palette. Condition builders resolve these keys before matplotlib color names. |
| `SAVE_MODE` | Global default for whether figure-saving helpers should save outputs. |
| `MONTAGE_FILENAME` | Filename stem for pipeline overview montages. The default starts with `!` so it sorts first in file browsers. |
| `SKIP_EXISTING` | When supported by saving code, skip saving outputs that already exist. |
| `EXPORT_HTML` | Save interactive HTML alongside supported plots when enabled. |
| `STATS_CACHE` | Cache statistical results within a session when enabled. |
| `HOUSE_STYLE` | Apply PyFLASH's default matplotlib style when plotting modules load. |
| `USE_PYFLASH_LAYOUT` | Use PyFLASH layout adjustments when saving figures. |
| `EFFECT_SIZES` | Compute effect sizes alongside p-values where supported. |
| `EFFECT_CI` | Compute bootstrap confidence intervals for supported effect sizes. |
| `EFFECT_CI_RESAMPLES` | Number of bootstrap resamples for effect-size confidence intervals. |
| `ALIASES` | Manual path/name alias overrides. `create_batch` combines these with auto-generated aliases. |

## Common Methods

`Config` itself does not define instance methods. Related module-level helpers
live in `PyFLASH.config`:

| Function | Use |
|---|---|
| `apply_matplotlib_fast_path()` | Lazily apply faster matplotlib rendering settings and keep SVG text editable. |
| `generate_palettes(colors=None)` | Generate blend palette strings from color pairs. |
| `check_directory(file_path)` | Resolve a path, including optional `Config.FALLBACK_USERS` substitutions. |

## Accepted By

`Config` is read by import, plotting, pipeline, export, path, and statistics
code. Users usually do not pass it as an argument. They set class attributes
before running the operation that needs the changed default.

## Returned By

`Config` is imported from the package:

```python
from PyFLASH import Config
```

It is not returned by a factory function.

## Examples

Change the colocalisation threshold for a batch creation call:

```python
from PyFLASH import Config, create_batch

old = Config.THRESHOLD
try:
    Config.THRESHOLD = 50
    batch = create_batch(
        "threshold-50",
        groups,
        "/path/to/output-folder",
        experiments="/path/to/experiment-parent-folder",
    )
finally:
    Config.THRESHOLD = old
```

This global setting is the value used by automatic object-marker
colocalisation cleaning. The `objectMarker.threshold` constructor value is
stored on the object, but current automatic cleaning calls
`addColocData(Config.THRESHOLD)`; call `addColocData(threshold)` explicitly if
you need to recompute colocalisation columns with a different threshold.

Customize condition color keys:

```python
from PyFLASH import Config, GroupBuilder

Config.COLORS["control_grey"] = "#787a7c"

groups = (
    GroupBuilder("Diagnosis")
    .add("Control", "Control", color="control_grey")
    .add("AD", "AD", color="red")
    .build()
)
```

Restore the historical montage filename:

```python
from PyFLASH import Config

Config.MONTAGE_FILENAME = "00 - Overview Montage"
```

Add manual aliases that should override auto-generated aliases:

```python
from PyFLASH import Config

Config.ALIASES.update({
    "WeekEight": "W8",
    "Genotype": "GT",
})
```

## Notes

- `Config` changes are process-global. They affect later operations until you
  change them back.
- `import PyFLASH` stays lightweight; plotting-related matplotlib settings are
  applied lazily when plotting or figure saving touches matplotlib.
- SVG text is kept editable by the matplotlib fast-path helper.
- `Config.ALIASES` is read during `create_batch`. Updating it after a batch is
  created does not automatically rewrite `batch.aliases`.

## See Also

- [Groups](conditions.md)
- [Saving parameters](../parameters/saving.md)
- [Figure folders](../outputs/figure-folders.md)
- [Pipeline run folders](../outputs/pipeline-run-folders.md)
- [Developer docs maintenance](../developer/docs-maintenance.md)
