# Use The Streamlit UI

## Goal

Run common PyFLASH workflows through the optional Streamlit interface: open or
create a project, build groups, import a batch, browse summaries, run plots or
specs, manage images, export workbooks, and save pickles.

The UI calls the same core functions as Python workflows through
`PyFLASH.ui.services`; it does not use a separate analysis engine.

## Inputs

- PyFLASH installed with the optional UI extra.
- Experiment folders or an existing PyFLASH `.pkl`.
- Group/condition design information.
- Optional plot spec files.
- Optional image metadata if using image, representative-image, or location
  pages.

## Minimal Path

Install and launch:

```bash
pip install -e ".[ui]"
pyflash-ui
```

Equivalent launch command from the project checkout:

```bash
python -m streamlit run PyFLASH/ui/app.py
```

Then open an existing `.pkl` or create a batch from experiment folders inside
the UI.

## Full Workflow

1. Start the UI with `pyflash-ui` or the Streamlit module command.
2. Use the project/open controls to load an existing pickle, or set up a new
   project with `batch_path`, experiment paths, optional `pickle_path`, and
   image-import settings.
3. Build groups in the UI. The group builder replays a JSON-style spec
   through `GroupBuilder`, so the preview should match Python-created groups.
4. Validate experiment folders before starting a long import. The UI checks the
   same folder patterns used by batch creation.
5. Run batch creation. The UI service captures progress output from
   `create_batch` and returns the created or cached `Batch`.
6. Browse summary tables. Use ROI-base selection and column filters to confirm
   the imported data.
7. Run quick plots by registry name, or run a plot spec file. The UI resolves
   aliases such as `data_cols`, `group_col`, `subject_col`, and `filter_by` the
   same way the spec runner does.
8. Use image and representative-image pages only when the batch has imported
   image metadata.
9. Export Excel workbooks or save the current batch pickle from the export/save
   controls.

## Outputs

UI actions write the same outputs as their Python equivalents:

| UI action | Core route | Main outputs |
|---|---|---|
| Open pickle | `load_state` | Loaded `Batch` or experiment-like object in the UI session. |
| Save pickle | `save_state` | `.pkl` file. |
| Build batch | `create_batch` | `Batch`, optional pickle cache, standard batch output paths. |
| Quick plot | registered plot callable | Figures under `batch.fig_path` when saved. |
| Plot spec | `run_spec` | One result per entry, plus files created by saved entries. |
| Image tools | image plotting functions | Image grids, representative panels, or location figures. |
| Export | `batch.export_all_excel` | `.xlsx` workbooks and `*_RegexFilters.txt` reports. |

Most output files land below:

```text
<batch-output>/Results/Python Figures/
<batch-output>/Exports/
```

## Troubleshooting

- UI import fails: install with the UI extra and launch from an environment that
  can import PyFLASH.
- Batch creation fails quickly: validate the experiment folder and condition
  design before rerunning.
- A quick plot rejects a parameter: check the target function page; the UI drops
  unknown keys after alias resolution.
- No image tools are available: rebuild or load a batch with image metadata.
- Exports fail on regex: simplify the include/exclude pattern and retry.
- The UI has stale state: save the current pickle, restart the Streamlit app,
  and reopen the pickle.

## Next Steps

- [Launch the UI](../getting-started/launch-the-ui.md)
- [Create a batch](create-a-batch.md)
- [Build groups](build-conditions.md)
- [Plot from a spec](plot-from-spec.md)
- [Export Excel workbooks](export-excel-workbooks.md)
- [Streamlit-free UI services](../developer/ui-services.md)
- [UI troubleshooting](../troubleshooting/ui-problems.md)
