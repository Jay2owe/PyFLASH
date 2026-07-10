# Import Errors

## Symptoms

- `ModuleNotFoundError: No module named 'PyFLASH'` when you run `import PyFLASH`.
- `import PyFLASH` works, but `pyflash-ui` is not found or `import streamlit`
  fails.
- `run_spec` on a `.yaml` file raises `ImportError: PyYAML is required to load
  .yaml spec files.`; a `.toml` file raises the matching
  `tomllib (Python 3.11+) or tomli is required for .toml specs.`
- The first access of `PyFLASH.plotting`, `PyFLASH.pipeline`, `PyFLASH.stats`,
  or a pipeline (`correlation`, `data_overview`, …) raises an import error even
  though `import PyFLASH` itself succeeded.

## Likely Causes

- PyFLASH is installed in a different interpreter than the one running your code
  (a common Jupyter kernel or virtual-environment mismatch).
- PyFLASH is not installed in the active environment at all.
- An optional extra is missing. Streamlit and PyYAML (`ui`), `pointpats`
  (`spatial`), and `dabest` (`estimation`) are **not** installed by the base
  package.
- Heavy analysis submodules load lazily, so an import problem inside
  `plotting`/`pipeline`/`stats` only surfaces on first use, not at
  `import PyFLASH`.

## Fix

Install the package into the environment you actually run:

```bash
pip install -e .
```

The distribution name on PyPI is `PyFLASH-analysis`; the import name is always
`PyFLASH`. For the Streamlit UI and YAML spec support, install the UI extra:

```bash
pip install -e ".[ui]"
```

Other extras: `.[spatial]` (`pointpats`), `.[estimation]` (`dabest`),
`.[windows]` (`pywin32`). PyYAML alone can be added with `pip install pyyaml`.

Core scientific dependencies (`pandas`, `numpy`, `matplotlib`, `seaborn`,
`scipy`, `statsmodels`, `scikit-posthocs`, `scikit-learn`, `openpyxl`,
`read-roi`, `Pillow`) install automatically with the base package. A bare
`import PyFLASH` deliberately avoids loading matplotlib, seaborn, scipy, and
statsmodels; they load on first access of a plotting or pipeline entry point.

## Check

Confirm the interpreter and install location match:

```bash
python -c "import PyFLASH, sys; print(sys.executable); print(PyFLASH.__file__)"
```

If you use Jupyter, run the same line in a kernel cell to verify the kernel
points at the same environment. To confirm the plotting stack loads, force one
lazy submodule:

```python
import PyFLASH
PyFLASH.plotting  # forces the heavy import; raises here if a dependency is missing
```

## Related Pages

- [Installation](../getting-started/installation.md)
- [Launch the UI](../getting-started/launch-the-ui.md)
- [run_spec](../functions/run_spec.md)
- [Plot spec files](../data-structures/plot-spec-files.md)
- [UI problems](ui-problems.md)
