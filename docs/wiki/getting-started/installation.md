# Installation

## Goal

Install PyFLASH in the Python environment you will use for analysis.

## Before You Start

- PyFLASH requires Python 3.9 or newer.
- The package name on PyPI is `PyFLASH-analysis`.
- The import name in Python is `PyFLASH`.

## Steps

Install the released package:

```powershell
python -m pip install PyFLASH-analysis
```

For local development from this repository, install the editable package from
the project root:

```powershell
python -m pip install -e .
```

Install the optional Streamlit UI dependencies only when you want the UI:

```powershell
python -m pip install -e ".[ui]"
```

If you installed from PyPI and want the UI extra, use:

```powershell
python -m pip install "PyFLASH-analysis[ui]"
```

## Check It Worked

Run a small import check in the same environment:

```powershell
python -c "from PyFLASH import create_batch, from_dataframe, run_spec; print('PyFLASH import ok')"
```

The command should print `PyFLASH import ok`.

## Next

- [First batch](first-batch.md)
- [First table-backed batch](first-table-batch.md)
- [Launch the UI](launch-the-ui.md)
- [create_batch](../functions/create_batch.md)
- [from_dataframe](../functions/from_dataframe.md)
