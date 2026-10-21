# Picture-first workflow design preview

Open `index.html` in a browser. It is self-contained apart from its local CSS and
JavaScript; no installation or server is needed.

Four interactive design examples: group means, relationships, object
distributions and the group-comparison pipeline. Choose a thumbnail, edit inputs,
inspect a simulated run, restore earlier inputs, and try light/dark appearance.
The bottom state selector exposes missing-input, changed-input and running states.

All graphs and progress are explicitly schematic. No analysis is submitted.
Measurement and group names come from the existing verified batch1 workflow;
the preview does not load its private source data. Source defaults were checked
against `PyFLASH.plotting` and `PyFLASH.pipeline.group_comparison` on 2026-10-04.
The handful of options shown is a proposed interaction, not a complete adapter.

Interaction choices are saved under `pyflash-picture-design-v1` in this page's
browser storage. Reset preview clears those design choices. No live workspace
settings or running jobs are modified.

Budgets for this local design only: first schematic result drawn within one
second; switching examples with controls and result redrawn within 500 ms.
These are distinct from live dataset import, server work and scientific analysis.

Decision record: `docs/ui-preset-workflow-rework-plan.md`. The four-screen review
precedes wider production implementation. Browser checks live in
`scripts/check_ui_rework_preview.py`.
