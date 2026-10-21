<!-- aiify app map: app=pyflash sources=4786b2e9166cf909 built=2026-10-21 by=claude -->
# App map: pyflash

## Overview
PyFLASH turns immunofluorescence confocal microscopy measurements exported from FLASH/ImageJ into tables, statistics and figures. It is for lab scientists who have a set of FLASH experiment folders, or a CSV table with one row per subject, and want to compare groups, look at relationships between measurements, and make publication figures. In the browser app you open or build an analysis, define experimental groups, explore measurements, run plots and multi-figure analysis pipelines, and export CSV files, Excel workbooks or a saved analysis. Long jobs run in the background so you can keep working, and every result comes with a Python script that recreates it.

## Screens

### Sidebar (always visible)
- **Navigation links:** Workspace, Folders, Groups, Process, Explore, Figures, Images, Export, and Plots & pipelines.
- **Dataset panel:** once data is open, shows the analysis name, either "Simulated data · 12 subjects" or "Loaded analysis", and a **Region** dropdown. The dropdown picks which brain-region summary every page shows; changing it does not reprocess anything.
- **Workspace help** (collapsible): a one-line description of each page, plus the location of the recovery copy that keeps your settings between sessions.
- **Job status panel:**
  - While a job runs: "Running: <name>… You can keep exploring." A comparison grid also shows a progress bar and a **Cancel after this cell** button.
  - When a job succeeds: "<name> is ready.", a **Download run script** button, and, for processing jobs, **Open completed analysis**.
  - When a job fails: "Processing failed: …" and **Download failed run script**.
  - **Live processing log** (collapsible) shows the latest log output.
- Warnings appear here if saved settings or saved runs could not be restored.

### Workspace
Opened from the **Workspace** link. This is where you open data and manage project setup.
- **Open data:**
  - **Input** chooses **Saved analysis** (a .pkl file) or **Subject table** (a .csv file).
  - **File path** with a **Browse** button.
  - For a subject table only: **Group column** (default "Condition") and **Subject column** (default "AnimalName").
  - **Open data** loads the file; **Use simulated example** loads a 12-subject, two-group demo.
- **Project setup:**
  - **Project name** sets the name of the batch that Process will create.
  - **Choose experiment folders** link goes to Folders.
  - **Load project setup** (JSON upload) and **Restore setup** bring back saved folder and group definitions.
  - **Save project setup** downloads `pyflash-project.json`.
- **Loaded data and provenance** (collapsible): metadata about the loaded analysis and where it came from.
- **House aesthetic** (collapsible): default figure styling. Fields are Figure width/height (inches), Save DPI, Point size, Line width, Axis label size, Tick label size, Legend font size, Font family and Matrix colour map. Buttons are **Save house aesthetic** and **Reset house aesthetic**.
- **Installation and optional features** (collapsible): dependency checks, with an **Install <package>** button for each missing requirement.
- **Other package functions** (collapsible): a **Package function** picker for supporting functions, each with its own form and reference.

### Folders
Opened from the **Folders** link, or from **Choose experiment folders** in Workspace.
- **Experiment root** (with **Browse**): the parent folder that holds your FLASH experiments. Processing writes its results here.
- **Choose experiments:**
  - **Discover folders** checks every immediate subfolder automatically.
  - **Name folders manually** gives an editable table with **Experiment** and **Folder** columns.
- **Folder checks** table: each experiment's Status ("Ready" or "Needs attention"), whether Images are "Available" or "Not found", and the Reason.
- **Folder layout details** (collapsible): the raw check results.
- **Processing options** (collapsible):
  - **Analysis cache folder**
  - **Object threshold**
  - **Import microscopy images** toggle; leave it off for a measurement-only analysis.
- **Use these folders** saves your choices and moves you on to Groups.

### Groups
Opened from the **Groups** link, or after **Use these folders**. Here you define the experimental conditions and which comparisons to make.
- **Design:**
  - **Single factor**
  - **Crossed (two factors)**: two side-by-side blocks, **Factor 1** and **Factor 2**.
- For each factor:
  - **Factor name**
  - An editable table with columns **Label**, **Short**, **Color** and **Style**:
    - **Color** takes a palette name, a CSS colour name, a #hex code, or blank for automatic.
    - **Style** takes fill, hollow, or a hatch pattern such as ///.
  - **Comparison mode**:
    - **Explicit pairs**, which adds a **Pairs to compare** picker
    - **All pairs**
    - **Versus control**, which adds a **Control group** picker
    - **Sequential**, for single-factor designs only
    - **None**
  - **Explanation template (<> is replaced with each label)**
- **Crossed comparisons** (crossed designs only):
  - **Comparison mode**
  - **Restrict comparisons within factor (within_factor)**
  - **Order groups by factor (order_by)**
  - **Explanation template (<> is replaced with each label)**
- **Preview:** coloured swatches for each group, the comparisons it resolves to, and an **Explanation expansion** section. Errors such as "Did you mean…?" appear inline, and a warning appears if two groups share a short name.
- **Save groups** checks the design, saves it, and goes to Process.

### Process
Opened from the **Process** link, or after **Save groups**.
- A status line tells you either what still needs setting up ("Choose experiment folders.", "Define the experimental groups.") or "Folders and groups are ready to process."
- **Processing inputs** (collapsible, open by default): the project name, the folder, a table of groups, the object threshold, and whether microscopy images are included.
- **Advanced** (collapsible):
  - **Reprocess cached analysis** ignores any saved analysis and processes the files again.
  - **Reload microscopy images** is only available while reprocessing.
- **Process experiments** starts processing in the background. It is disabled while another job runs.
- **Inspect measurements** link (shown once data is open) goes to Explore.

### Explore
Opened from the **Explore** link. This is the app's default page; Workspace also lands here after opening data.
- **Explore** heading with a **Highlight subject** dropdown that picks one subject to emphasise in both charts.
- **Group distribution:** a box plot with subject points for one measurement, by group.
- **Measurement relationship:** a scatter plot of two measurements. Clicking a point highlights that subject in both charts.
- **Explore controls** (sidebar):
  - **Groups** (multi-select)
  - **Find a measurement**, shown only when there are more than 200 measurements
  - **Distribution measurement**
  - **Relationship horizontal axis**
  - **Relationship vertical axis**
  - **Appearance** (collapsible):
    - **Plot height**
    - **Point size**
    - **Label size**
    - **Show legend**
    - **Start numeric axes at zero**
    - **Edit one view**, with a **View appearance** picker for styling one chart separately
- **Measurements and missing values** (collapsible): the table of the rows and measurements on screen, with a count of missing or excluded values.
  - **Prepare shown table** builds that table as a CSV in the background.
  - Then **Download shown table** and **Download table script** appear.

### Plots & pipelines
Opened from the **Plots & pipelines** link. The **Figures** and **Images** links also open this page, with a figure or image view already selected.

**Left side, "Choose a picture"**
- **Find a plot or pipeline** search box.
- **Task** filter: All, Compare groups, Examine relationships, Explore measurements, Explore changes over time, Fit models, Inspect images.
- **Picture cards:** each card is one kind of figure or pipeline. Clicking a card selects it; nothing runs until you press the run button.
  - **Plots:** Bars & subject points, Relationships, Distributions, Paired measurements, Matrices, Effects & coefficients, Compare relationships, Volcano, Proportions & counts, Marker overlap, Measurement profiles, Time & rhythm, Images & locations, Study tables & group key, Statistical power.
  - **Pipelines:** Group comparison, Dataset overview, Relationships pipeline, Adjusted relationships, Linear models, Rhythm analysis, Model exploration.
- **Catalogue coverage** (collapsible): **Download input and execution coverage**.

**Right side, the editor for the chosen picture**
- **Plot type** dropdown, when a card has several variants. For example, Bars & subject points offers "Group means & subject points", "Subject & region spread" and "Saved adjusted group means".
- **Input fields** are grouped into sections that differ by plot, such as **Data**, **Comparison** or **Association**. Pipelines number them **1 · Data**, **2 · Analysis** and **3 · Outputs**. Typical fields:
  - **Measurements**
  - **Horizontal measurement** and **Vertical measurement**
  - **Compare against**
  - **Method**
  - **Significance uses**
  - **Number of bins**
  - **Experiment**, for the object-location view only
- **Groups** (multi-select; blank means all groups).
- **Imported images and representative selections** (collapsible, image views only): the image table, an editable table of representative-image choices, and **Apply representative selections**.
- **Advanced** (collapsible):
  - **Additional settings** picker
  - **Exact empty values**, with **Input to clear**, **Use** and **Apply empty value**
  - **Compare analysis choices**, with **Settings to compare**, a "<setting> values" box per setting (one choice per line), and **Compare these choices**
- **Edit appearance** checkbox: per-figure styling, plus **Additional appearance options**.
- A count line such as "N subjects with selected measurements · M rows", and any input errors.
- **Create plot** (for plots) or **Run pipeline** (for pipelines) runs in the background. **Reset inputs** restores the package defaults.
- **Result:**
  - **Restore this run's inputs**
  - The figure previews, with **Columns** and **Result page** pickers and a "Download <file name>" button under each figure
  - Result tables, each with **Download complete result table**
  - **Download equivalent Python script**
  - **Recorded settings and run log** (collapsible)
- **Comparison of choices** (after a comparison grid finishes):
  - **Outcome to compare**
  - A chart of outcomes sorted by value, above a matrix showing which choices produced each one, and a table of every cell
  - **Download complete grid script**
  - **Choice to use** and **Use these settings**
- **Inputs and transformations for this run** (collapsible): the exact inputs that will be sent.
- **Function reference** (collapsible): signature, a table of inputs and defaults, documentation, and **Download call template (inputs required)**.
- **Saved runs** (collapsible): **Completed run** and **Reopen this run**.
- **Run a saved figure specification** (collapsible):
  - **Saved specification file** path
  - **Or choose a saved specification** upload (YAML/JSON/TOML)
  - **Validate and run specification**

### Export
Opened from the **Export** link.
- **Measurements:**
  - **Prepare region summary** builds the full CSV in the background.
  - Then **Download region summary** (`summary.csv`) and **Download result script** appear.
- **Excel workbooks** (processed FLASH batches only):
  - Checkboxes **Summary**, **Per-object data** and **Behaviour**.
  - **Workbook filters and names** (collapsible): for each workbook, **Include matching columns**, **Exclude matching columns** (comma-separated patterns) and **File name**.
  - **Workbook destination**.
  - **Export selected workbooks**.
  - **Workbook export log** (collapsible) and **Download result script**.
  - Subject-table data shows a note that only CSV export is available.
- **Save analysis:**
  - **Analysis file** (a .pkl path).
  - **Save analysis** saves the measurements and representative-image choices. You then see "Saved analysis: <path>" and **Download result script**.
- **Export package reference** (collapsible): a **Package function** picker for export-related functions.

## Tasks

### How to open a saved analysis
1. Go to **Workspace**.
2. Set **Input** to **Saved analysis**.
3. Type the .pkl path in **File path**, or click **Browse**.
4. Click **Open data** (PyFLASH.ui.services.open_pickle). The app moves to Explore.

### How to open a CSV subject table
1. Go to **Workspace** and set **Input** to **Subject table**.
2. Enter the .csv path in **File path**, or use **Browse**.
3. Set **Group column** and **Subject column** to match your CSV headers.
4. Click **Open data** (PyFLASH.ui.workspace.load_table).

### How to try the app with example data
1. Go to **Workspace**.
2. Click **Use simulated example**. This loads 12 simulated subjects in two groups, without real images.

### How to start a new project from FLASH experiment folders
1. In **Workspace**, enter a **Project name**.
2. Click **Choose experiment folders**.
3. Follow the next three tasks: choose experiment folders, define groups, then process the experiments.

### How to choose and check experiment folders
1. Go to **Folders**.
2. Set **Experiment root**, or use **Browse**.
3. Under **Choose experiments**:
   - pick **Discover folders** to check every subfolder (PyFLASH.ui.services.discover_experiments), or
   - pick **Name folders manually** and fill the **Experiment** / **Folder** table (PyFLASH.ui.services.validate_experiment_folder).
4. Read the **Folder checks** table. Fix anything marked "Needs attention".
5. Optionally open **Processing options** to set **Analysis cache folder**, **Object threshold** and **Import microscopy images**.
6. Click **Use these folders**.

### How to define experimental groups and colours
1. Go to **Groups** and set **Design** to **Single factor**.
2. Enter a **Factor name**.
3. Add one row per group, with **Label**, an optional **Short** name, an optional **Color**, and an optional **Style**.
4. Pick a **Comparison mode**. Use **Pairs to compare** or **Control group** if that mode asks for them.
5. Check the **Preview** (PyFLASH.ui.services.preview_conditions).
6. Click **Save groups** (PyFLASH.ui.services.build_conditions).

### How to set up a two-factor (crossed) design
1. In **Groups**, set **Design** to **Crossed (two factors)**.
2. Fill **Factor 1** and **Factor 2**, giving each a name and a table of groups. Put a **Style** on the second factor so bars sharing a colour can still be told apart.
3. Under **Crossed comparisons**, choose **Comparison mode**.
4. Optionally set **Restrict comparisons within factor** and **Order groups by factor**.
5. Check **Preview**, then click **Save groups**.

### How to process the experiments
1. Go to **Process** and confirm it says "Folders and groups are ready to process."
2. Optionally, under **Advanced**, turn on **Reprocess cached analysis** and/or **Reload microscopy images**.
3. Click **Process experiments** (PyFLASH.ui.jobs.start_processing).
4. Watch progress in the sidebar status panel, and its **Live processing log** (PyFLASH.ui.jobs.read_job, PyFLASH.ui.jobs.log_tail).
5. When it says "<name> is ready.", click **Open completed analysis**.

### How to check whether a job is still running or why it failed
1. Look at the sidebar status panel (PyFLASH.ui.jobs.latest_job).
2. Expand **Live processing log** for the output (PyFLASH.ui.jobs.log_tail).
3. If it failed, use **Download failed run script** to keep the recorded settings.

### How to save and reload a project setup
1. In **Workspace**, click **Save project setup** to download `pyflash-project.json` (PyFLASH.ui.project_io.save_project).
2. To reload it later, use **Load project setup** to pick the JSON file.
3. Click **Restore setup** (PyFLASH.ui.project_io.load_project). This restores folders and groups without processing anything.

### How to switch which brain region is shown
1. Once data is open, use the **Region** dropdown in the sidebar.
2. Explore, Export and Plots & pipelines all switch to that region's measurements.

### How to look at one measurement across groups
1. Go to **Explore**.
2. In **Explore controls**, pick a **Distribution measurement**.
3. Read the **Group distribution** chart.

### How to plot two measurements against each other quickly
1. In **Explore**, set **Relationship horizontal axis** and **Relationship vertical axis**.
2. Read the **Measurement relationship** chart.

### How to highlight one animal or subject
1. In **Explore**, pick the subject from **Highlight subject**, or click its point in either chart.
2. That subject is emphasised in both charts. Choose **All subjects** to clear it.

### How to show only some groups in Explore
1. In **Explore controls**, use **Groups** and keep only the groups you want.

### How to change the look of the Explore charts
1. In **Explore controls**, open **Appearance**.
2. Adjust **Plot height**, **Point size**, **Label size**, **Show legend** and **Start numeric axes at zero**.
3. To style one chart only, tick **Edit one view**, then choose it in **View appearance**.

### How to see the measurement table and missing values
1. In **Explore**, open **Measurements and missing values** (PyFLASH.ui.services.summary_table).
2. The caption under the table gives the row count and the number of missing or excluded values.

### How to download the table I'm looking at in Explore
1. In **Explore**, open **Measurements and missing values**.
2. Click **Prepare shown table**.
3. When the job finishes, click **Download shown table**. **Download table script** gives a script that recreates it.

### How to export the region summary as CSV
1. Go to **Export**.
2. Click **Prepare region summary** (PyFLASH.ui.services.export_summary_csv).
3. When the job finishes, click **Download region summary**.

### How to export Excel workbooks
1. Go to **Export**. This needs a processed FLASH batch, not a subject table.
2. Tick **Summary**, **Per-object data** and/or **Behaviour**.
3. Optionally open **Workbook filters and names** and set **Include matching columns**, **Exclude matching columns** and **File name**.
4. Optionally set **Workbook destination**. Leave it blank to use the analysis export folder.
5. Click **Export selected workbooks** (PyFLASH.ui.services.export_excel).
6. Check **Workbook export log** to see the result.

### How to save the current analysis to a file
1. Go to **Export** and find **Save analysis**.
2. Edit the **Analysis file** path (.pkl).
3. Click **Save analysis** (PyFLASH.ui.services.save_batch). You'll see "Saved analysis: <path>".

### How to make a bar chart of group means
1. Go to **Plots & pipelines** and click the **Bars & subject points** card.
2. Leave **Plot type** on "Group means & subject points".
3. Under **Data**, choose **Measurements**. Under **Comparison**, set the statistical test and normalisation if needed.
4. Optionally restrict **Groups**.
5. Click **Create plot** (action mean_bars).

### How to make any other plot
1. In **Plots & pipelines**, type in **Find a plot or pipeline**, or filter by **Task**.
2. Click a picture card, then pick its variant in **Plot type**. For example, Relationships has "Two-measurement relationship" (regressions) and "Three-measurement relationship" (scatter_3d).
3. Fill the inputs in each section, and **Groups** if shown.
4. Click **Create plot**.
5. View the figures under **Result**. Download each one with its "Download <file name>" button.

### How to run an analysis pipeline (group comparison, correlations, linear models, rhythms…)
1. In **Plots & pipelines**, click a pipeline card:
   - **Group comparison** (group_comparison_pipeline)
   - **Dataset overview** (data_overview_pipeline)
   - **Relationships pipeline** (correlation_pipeline)
   - **Adjusted relationships** (adjusted_correlation_pipeline)
   - **Linear models** (linear_model_pipeline)
   - **Rhythm analysis** (rhythm_pipeline)
   - **Model exploration** (iterative_model_sweep)
2. Fill **1 · Data**, **2 · Analysis**, **2 · Model** or **2 · Rhythm**, and **3 · Outputs**.
3. Click **Run pipeline**.
4. Review the figures and result tables. Use **Download complete result table** for each table.

### How to change a plot's colours, sizes or fonts
1. For one figure: in the plot's editor, tick **Edit appearance**. Change figure size, DPI, point size, line width, font sizes, font family or matrix colour map. Use **Additional appearance options** for figure-specific labels, axis ranges and colours.
2. For all new figures: in **Workspace**, open **House aesthetic**, edit the values, and click **Save house aesthetic**. **Reset house aesthetic** restores the package defaults.
3. Appearance changes apply to the next run. Earlier results keep the settings they were made with.

### How to change advanced settings or clear an input
1. In the plot's editor, open **Advanced**.
2. Pick settings in **Additional settings**. Removing one restores its default.
3. To send an explicit empty value, open **Exact empty values**:
   - choose **Input to clear**
   - choose **Use** (Package default / No value / Empty list)
   - click **Apply empty value**
4. **Reset inputs** clears the whole draft for that plot.

### How to compare different analysis settings side by side
1. In the plot's editor, open **Advanced**, then **Compare analysis choices**.
2. Pick **Settings to compare**. Enter one value per line in each "<setting> values" box.
3. Click **Compare these choices** (PyFLASH.ui.jobs.start_sweep). The sidebar shows progress, and **Cancel after this cell** stops it after the current combination.
4. Under **Comparison of choices**, choose **Outcome to compare** to see every combination ranked by that outcome.
5. To keep one combination, pick it in **Choice to use** and click **Use these settings** (PyFLASH.ui.sweeps.promote_cell).

### How to get the Python script that reproduces a result
1. After a run, click **Download equivalent Python script** under **Result**, or **Download run script** in the sidebar status panel.
2. Exports and saves have their own **Download result script** button. Comparison grids have **Download complete grid script**.
3. To get a blank call for a function, open **Function reference** and click **Download call template (inputs required)**.

### How to reopen an earlier plot run
1. In **Plots & pipelines**, open **Saved runs**.
2. Choose the **Completed run** and click **Reopen this run**.
3. On a result already showing, **Restore this run's inputs** puts back exactly the inputs and appearance used.

### How to view microscopy images or pick representative images
1. Click **Images** in the sidebar, or the **Images & locations** card in **Plots & pipelines**.
2. Choose **Plot type**: images, representative_images, or locations. For locations, pick an **Experiment**.
3. Open **Imported images and representative selections** to see the image table (PyFLASH.batch.Batch.getImageTable).
4. Edit the representative-image table and click **Apply representative selections** (PyFLASH.ui.services.set_representative_selections).
5. Choose markers under **Images** and options under **Layout**, then click **Create plot**.

### How to run a saved figure recipe file
1. In **Plots & pipelines**, open **Run a saved figure specification**.
2. Enter a **Saved specification file** path, or use **Or choose a saved specification** to upload a YAML, JSON or TOML file.
3. Click **Validate and run specification** (PyFLASH.queue.run_spec_queue).

### How to fix a missing package or optional feature
1. In **Workspace**, open **Installation and optional features** (PyFLASH.dependencies.check). Plot editors also show these warnings when a requirement is missing.
2. Click **Install <package>** next to the warning (PyFLASH.ui.jobs.start_dependency_repair).

### How to see what a measurement name means
1. Ask the assistant to explain the name (PyFLASH.export.convert_name, PyFLASH.export.lookup_description). For per-object measurement names, use PyFLASH.export.convert_raw_name.

### How to see what data is loaded and where it came from
1. In **Workspace**, open **Loaded data and provenance** (PyFLASH.ui.services.batch_overview).

### How to use a supporting package function that isn't a plot
1. In **Workspace**, open **Other package functions**. For export helpers, use **Export package reference** on **Export**.
2. Choose it in **Package function**, fill its form, and click **Run <function name>**.

## Terms

### Analysis / batch
The processed set of measurements from one or more experiments, plus any imported images. It is saved as a .pkl file and opened as a **Saved analysis**.

### Subject table
A CSV file with one row per subject (animal), a group column and measurement columns. It is an alternative to processing FLASH folders.

### Experiment root
The parent folder that holds the FLASH experiment folders. Processing writes its results here.

### Region
The brain-region summary being viewed, chosen in the sidebar **Region** dropdown. Each region has its own set of measurements.

### Subject
The independent unit in the statistics, usually one animal. Region-level and object-level values are nested within subjects.

### Group / condition
An experimental group defined on the Groups page, with a label, short name, colour and optional style.

### Factor
A variable that defines groups, such as genotype or treatment. A **crossed** design combines two factors into every combination of their levels.

### Short name
The abbreviation for a group used in file names and comparisons. Each must be unique.

### Style
A group's second visual marker, after colour: fill, hollow, or a hatch pattern. Use it on the second factor of a crossed design.

### Comparison mode
Which group comparisons the statistics test: Explicit pairs, All pairs, Versus control, Sequential, or None.

### Explanation template
Text in which `<>` is replaced by each group's label, giving a longer description of that group.

### Object threshold
A processing setting passed unchanged to experiment processing when a batch is built from the folders.

### Object measurement
A measurement of an individual segmented object, such as one cell, rather than a per-subject summary. Distribution, proportion and overlap plots use these.

### Pipeline
A multi-step analysis that produces many figures and tables in one run. Each run also writes an overview montage that tiles the most important figures.

### House aesthetic
The default figure styling applied to every new plot unless that plot overrides it.

### Package default
Leaving an input untouched, so the underlying PyFLASH function uses its own default.

### Compare analysis choices (grid)
Running one plot or pipeline over every combination of the settings you list, then comparing the outcomes before choosing one to keep.

### Representative images
The images chosen to represent each group. They are saved with the analysis.

### Result script / equivalent Python script
A downloadable Python file that recreates a result from verified inputs in a new output folder.

### Saved figure specification
A YAML, JSON or TOML file describing figures to make. The app checks it before running it.

### Significance uses (p / fdr)
Whether significance is judged on raw p-values, or on false-discovery-rate q-values (p-values adjusted for running many tests).

### Excluded value
A value marked as an outlier or removed by hand. It is treated as missing in analysis but kept, with its tag, in the tables.
