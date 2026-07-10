# Launch The UI

## Goal

Start the optional Streamlit interface for point-and-click PyFLASH workflows.

## Before You Start

- Install PyFLASH in the environment you will use.
- Install the optional UI extra. Core `import PyFLASH` does not require
  Streamlit.

## Steps

From this repository, install the UI extra:

```powershell
python -m pip install -e ".[ui]"
```

Then launch the UI:

```powershell
pyflash-ui
```

If you are working directly from the repository and want the explicit Streamlit
command, use:

```powershell
python -m streamlit run PyFLASH/ui/app.py
```

## Check It Worked

- A browser opens to the PyFLASH UI.
- The landing page shows an environment or package check.
- The UI pages use the same PyFLASH functions documented in this wiki.

## Next

- [Installation](installation.md)
- [First batch](first-batch.md)
- [First plot spec](first-plot-spec.md)
- [API reference](../api-reference.md#streamlit-free-ui-services)
