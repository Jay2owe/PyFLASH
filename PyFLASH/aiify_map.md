<!-- aiify app map: app=pyflash sources=6cfb5fe5b91ed37d -->
# App map: PyFLASH

## Overview
PyFLASH uses its existing scientific or workflow actions, the shared assistant panel and browser bridge. Local guidance, this map and the supplied verified shortcut are enabled by default. Extra web-route actions are optional. The assistant can use installed skills and files through its chosen local agent; it is not restricted to clicking the window.

## Screens

### Workspace
Open an analysis, import a subject table or start a project.

### Folders
Validate experiment folders before processing.

### Groups
Define factors, group colours and comparisons.

### Process
Build the analysis using saved folder and group choices.

### Explore
Inspect measurements and highlight the same subject in both views.

### Plots & pipelines
Choose a registered function, its data and declared options; run a recorded analysis.

### Images
Inspect microscopy images and representative selections.

### Export
Export workbooks or save a processed analysis.

## Tasks

### How to open an analysis
1. Use Workspace to open a trusted saved pickle or subject table. The live page supplies the current source to the assistant.

### How to inspect measurements
1. Open Explore and choose the region and metric; these selections do not rerun processing.

### How to check input folders
1. Use Folders, or describe PyFLASH.ui.services.validate_experiment_folder before running it.

### How to define experimental groups
1. Use Groups and preserve the recorded factors and comparison choices.

### How to process a project
1. Use Process or the registered PyFLASH.ui.jobs.start_processing action; inspect its recorded job.

### How to find a function
1. Use Plots & pipelines or action.list/action.describe over the exact PyFLASH action keys.

### How to run an analysis
1. Run a declared action. _input defaults to the UI source pinned at this message; _output is a new recorded folder.

### How to change figure appearance
1. Use the registered appearance controls or _style; scientific arguments stay separate.

### How to save work
1. Use Export and the existing save/export actions; preserve the loaded source.

### How to check assistant context
1. Use workspace.overview to read the selected source and the actual action catalogue.

## Terms

### Controls
The shared panel offers helper switches and the existing provider, model, effort and permission controls. Start New chat after changing helpers.

### Verified shortcut
workspace.overview reads this app's live or pinned native state in one call. It never starts an analysis or silently changes a task.
