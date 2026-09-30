# Soteras et al. manuscript analysis scripts

These command-line scripts call public PyFLASH application programming
interfaces (APIs) to rerun numerical analyses described in the supplied
`Soteras_et_al_Nature_2026 last.pdf`. They read original inputs, create a new
output directory, and record file hashes, effective parameters, package/source
versions, complete-case counts and success/failure. They do not modify source
data or save figures.

**Status:** all 48 displayed Figure 1H/I estimates match the confirmed human batch
when using `--coefficient-definition submitted_figure` with the original cohort.
Independent numerical tests also verify the written-Methods model. This is not
yet a certified reproduction of every final paper result or bootstrap interval. The
original random seed, full per-panel exclusion lists, Dunn correction choices,
and sensitivity profile list were not present in the recovered notebooks.
Approved original result tables are needed to establish numerical equality.
The confirmed final input batches are `human.pkl`, `batch1.pkl` and `CK1I.pkl`.
Data are supplied separately; participant-level data are not bundled here.

The existing [verification receipt](verification.json) describes an earlier
45-participant Methods reconstruction with a candidate device exclusion. Its
file hashes and test count belong to that earlier run, rather than the current
scripts or the submitted-figure comparison described above.

## What each script runs

- `01_prepare_mouse_batches.py`: rebuilds the saved time-course and inhibitor
  batch definitions from original FLASH exports via `create_batch`. Preserves
  saved condition ordering/comparisons and excludes the failed-injection animal
  `NLGFVeh20` from the inhibitor summary. Original processing defaults are
  threshold 30, pixel-size setting 3.51998900003 and fallback section thickness
  13 micrometres. Images are not imported. New cache pickles retain the complete
  imported batch; the exported inhibitor summary applies the exclusion.
- `02_human_associations.py`: Figure 1H separate age–volume and volume–M10
  ordinary least-squares models, diagnosis interaction terms, sex adjustment
  in both and age adjustment in volume–M10; standardized coefficients and
  group-stratified 10,000-resample bootstrap intervals; separate one-sided
  Control–MCI/AD slope tests. Figure 1I raw and age/sex-adjusted Spearman
  correlations, residualizing **raw values within diagnosis before ranking**.
  M10 means activity during the most active ten hours.
  **The submitted figure and written Methods differ:** the figure's age–volume
  coefficients (-0.11/-0.59/-0.79) match an unadjusted age model. Use
  `--coefficient-definition submitted_figure` to reproduce those values, or the
  default `manuscript_methods` to include the sex adjustment written in the PDF.
  Volume–M10 retains age/sex adjustment in both definitions.
- `03_panel_statistics.py`: explicitly configured one-way analysis of variance
  with Tukey comparisons, or Kruskal–Wallis with Dunn comparisons, through
  `PyFLASH.stats`. Reports per-group sample counts, mean, standard error and
  Shapiro normality test. It never chooses a test or removes outliers silently.
- `04_human_covariate_sensitivity.py`: explicitly named covariate/outcome
  profiles via `pipeline.linear_model`; numeric covariates at their sample
  means, categorical levels equally weighted, conventional model standard
  errors and uncorrected two-sided contrasts. The example profile is not a
  recovered final paper profile.
- `05_grouped_associations.py`: explicitly configured grouped Pearson
  correlations and separate ordinary least-squares fits for Figure 1G and
  marker/behaviour associations such as Figure 3L–O. The marker columns, animal
  exclusions and time-point pooling must be supplied from the original analysis.
- `06_compare_manuscript_annotations.py`: compares all six Figure 1H coefficients
  and 42 Figure 1I correlations with their displayed two-decimal values. It reports
  discrepancies and fails when any annotation differs. Matching these annotations
  does not establish original confidence intervals or all underlying precision.

Correlation APIs also return bootstrap interval diagnostics. These are additional
outputs: the manuscript's nominal correlation P values do not depend on them.
The human association script uses seed 20260930 as an explicit reconstruction
seed; it is not claimed to be the original paper seed. Standardization follows
the current PyFLASH API: full model-cohort means and population standard deviations.

## Run from this repository

Install this checkout in a Python environment using the repository's standard
installation instructions. This checkout must provide the named APIs; a package
release predating them cannot run these scripts. CSV inputs are also accepted.
Only load pickle files from a trusted source.

```powershell
cd "C:\path\to\PyFLASH"
python reproduce/soteras_2026/02_human_associations.py --input "C:\paper-data\human.pkl" --out "C:\paper-rerun\human" --coefficient-definition submitted_figure
python reproduce/soteras_2026/06_compare_manuscript_annotations.py --results "C:\paper-rerun\human" --out "C:\paper-rerun\human-annotation-check"
```

The confirmed batch contains 46 rows, including 14 labelled AD (Alzheimer's
disease). Its original cohort matches the displayed correlations and listed peak
sample counts. The author suggested identifying the device failure by lowest AD
activity, but that candidate is **included in the submitted figures**. Its removal
changes the displayed results and sample counts. The original device-failure
identity cannot be established from low activity alone; check the producing data
or incident record before applying an additional exclusion. The candidate run is
preserved as a separate local sensitivity check, not certified paper reproduction.

If an additional exclusion is confirmed, apply it consistently with script 02's
`--paper-device-failure-subject`, and for other human scripts put the same identifier in each job's
`exclude_subjects`, or pass the sensitivity script's
`--paper-device-failure-subject` flag. Copy example JSON files to a separate
local settings folder and fill in approved values before running:

```powershell
cd "C:\path\to\PyFLASH"
python reproduce/soteras_2026/03_panel_statistics.py --input "C:\paper-data\human.pkl" --panels "C:\paper-settings\human-panels.json" --out "C:\paper-rerun\human-panels"
python reproduce/soteras_2026/04_human_covariate_sensitivity.py --input "C:\paper-data\human.pkl" --profiles "C:\paper-settings\human-profiles.json" --out "C:\paper-rerun\human-sensitivity"
python reproduce/soteras_2026/05_grouped_associations.py --input "C:\paper-data\human.pkl" --jobs "C:\paper-settings\human-associations.json" --out "C:\paper-rerun\human-pearson"
```

Mouse panels can use the confirmed batch pickles directly, or summaries rebuilt
from original exported tables:

```powershell
cd "C:\path\to\PyFLASH"
python reproduce/soteras_2026/01_prepare_mouse_batches.py --timecourse "C:\paper-data\2, 4, and 8 Weeks" --ck1i "C:\paper-data\CK1I" --out "C:\paper-rerun\mouse-batches"
python reproduce/soteras_2026/03_panel_statistics.py --input "C:\paper-data\batch1.pkl" --panels "C:\paper-settings\timecourse-panels.json" --out "C:\paper-rerun\timecourse-panels"
python reproduce/soteras_2026/03_panel_statistics.py --input "C:\paper-data\CK1I.pkl" --panels "C:\paper-settings\inhibitor-panels.json" --out "C:\paper-rerun\inhibitor-panels"
```

Declare Dunn's original multiplicity correction explicitly, for example
`"dunn_correction": "holm"` **only if Holm was used originally**. The manuscript
says Dunn but does not name its correction. PyFLASH defaults must not substitute
Conover or choose a correction automatically. Per-panel `expected_n` is optional
and causes a failure if complete-case counts differ.

The stored `Morning-eveningpeakratio` equals morning/evening in the confirmed
human batch. The supplied manuscript states **evening/morning**. Use
`"transform": "reciprocal"` for the manuscript definition; use the default
identity transform only to reproduce an original analysis of the stored column.
The figure's plotted ratio is evening/morning; reproducing the stored column
directly would instead analyze its inverse and can change P values. After the candidate device exclusion, the AD
morning/evening/ratio complete-case counts are 12/12/11; the unexcluded batch has
13/13/12, agreeing with the submitted Methods. Preserve the original cohort for
the submitted-figure reproduction.

## Verify

```powershell
cd "C:\path\to\PyFLASH\reproduce\soteras_2026"
python -m unittest test_reproduction -v
```

The focused tests compare models against independent statsmodels calculations,
residual Spearman and Pearson results against SciPy, and Tukey comparisons against
statsmodels. Duplicate subjects and overwriting existing outputs are rejected.
Add `--reference-dir` to script 02 or `--reference` to script 03 to compare approved
original CSV tables with the same column/row ordering (relative tolerance 1e-8,
absolute tolerance 1e-10).

Raw actigraphy preprocessing, MRI segmentation, Prism-only tests, wheel-running
preprocessing and CLOCKCyteR analyses are separate producers and are not rerun by
these scripts. FLASH image quantification has its own recorded-run replay guide.
