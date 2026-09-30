# Small simulated PyFLASH demo

The supplied [data/summary.csv](data/summary.csv) contains twelve artificial
subjects: six in group A and six in group B, with two fluorescence intensity
measurements per subject. It is less than 1 KB. All values are simulated;
the group difference is deliberately built in and has no biological meaning.

The values are whole-stack pixel means from the companion FLASH demo's twelve
two-channel TIFF stacks. The source generator, seed (20260930), and per-slice
pixel truth are available in
[FLASH's demo folder](https://github.com/Jay2owe/FLASH/tree/master/demo).
This table is supplied independently so FLASH and Fiji are not needed to run
the PyFLASH demo. Intensities are arbitrary units; subjects are the independent
units, not the five image slices used to produce each subject's mean.

## Run

Install Python 3.10 or later and PyFLASH as described in the main README.
Download or clone this repository, then run from its root:

```bash
python demo/run_demo.py
```

The script imports the table through PyFLASH's `from_dataframe`, runs a
two-sided independent-groups Welch t-test through PyFLASH, saves the imported
experiment, reloads it, and checks that its table is unchanged. It checks the
group means and test result against [expected_result.json](expected_result.json).
No plots or additional optional dependencies are required.

Expected console output includes `Demo passed`, 12 subjects, 6 per group,
means of approximately **40.89737** (A) and **51.88691** (B), a Welch statistic
of approximately **-18.63249**, and **p = 4.28538e-9**.

The script writes these files to `demo/output/`:

- `imported_summary.csv`: the twelve subjects after PyFLASH import.
- `group_statistics.csv`: PyFLASH's statistical results and diagnostic checks.
- `demo_state.pkl`: the saved PyFLASH experiment; load only pickles you trust.
- `run_info.json`: group sizes, means, test results, versions, and elapsed time.

Expected running time on a normal desktop or laptop is **under 1 minute**, after
installation. Timing includes imports and writing outputs; it excludes package
installation. Exact times and dependency versions for the verification run are
listed in the main README.

The output folder must not already exist. To keep a previous run, choose a new
output folder:

```bash
python demo/run_demo.py --output demo/output-second-run
```

## Use your own tabular data

Start with the `from_dataframe` call in `run_demo.py`: supply your table, subject
column and group column, then choose the measured column and appropriate
comparisons. The checks and expected numbers in this demo apply only to the
supplied artificial table. For importing raw FLASH measurement exports,
use the main README's `create_batch` example and expected data layout.
