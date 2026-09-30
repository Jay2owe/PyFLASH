"""Load a supplied artificial subject table and run PyFLASH group statistics.

Inputs: data/summary.csv (12 simulated subjects, two groups), relative to this
script. Outputs: imported_summary.csv, group_statistics.csv, demo_state.pkl,
and run_info.json in --output. No source files are modified. An existing output
directory is rejected. This minimal numerical demo does not generate figures.
"""
import argparse
import json
import math
import platform
import time
from importlib.metadata import version
from pathlib import Path


def run(input_path, output):
    started = time.perf_counter()
    import pandas as pd
    from PyFLASH import from_dataframe, load_state, save_state
    from PyFLASH.stats import multipleComparisons

    source = pd.read_csv(input_path)
    required = {"AnimalName", "Condition", "Signal_MeanIntensity"}
    if not required.issubset(source.columns):
        raise ValueError(f"Missing required columns: {required - set(source.columns)}")
    if len(source) != 12 or source["AnimalName"].nunique() != 12:
        raise ValueError("The supplied demo must have exactly 12 distinct subjects.")
    if source.groupby("Condition").size().to_dict() != {"A": 6, "B": 6}:
        raise ValueError("The supplied demo must have 6 subjects in each of A and B.")
    if not source["Signal_MeanIntensity"].map(math.isfinite).all():
        raise ValueError("Demo signal values must be finite.")
    output.mkdir(parents=True, exist_ok=False)
    experiment = from_dataframe(
        source, name="Simulated demonstration", group_col="Condition",
        subject_col="AnimalName", comparisons=[("A", "B")],
        file_path=str(output), source_paths=[str(input_path)],
    )
    metric = "Signal_MeanIntensity"
    groups = [experiment.summary.loc[experiment.summary["Condition"] == name, metric]
              for name in ("A", "B")]
    # Two independent groups; force a Welch t-test to make the demo reproducible.
    test, posthoc, _, results = multipleComparisons(
        experiment, groups, ax=None, fig=None, scatter=None, bar=None,
        stats_test="welch", draw=False, save_normality=False,
        save_name="group_statistics", output_dir=str(output),
    )
    expected = json.loads((Path(__file__).resolve().parent / "expected_result.json").read_text(encoding="utf-8"))
    for name, values in zip(("A", "B"), groups):
        if not math.isclose(float(values.mean()), expected["group_means"][name], rel_tol=1e-9):
            raise AssertionError(f"Unexpected simulated group mean: {name}")
    statistic, pvalue = results["Welch's T Test"]
    if not math.isclose(float(statistic), expected["welch_t"], rel_tol=1e-8):
        raise AssertionError("Unexpected Welch test statistic")
    if not math.isclose(float(pvalue), expected["welch_p"], rel_tol=1e-6):
        raise AssertionError("Unexpected Welch test p-value")
    experiment.summary.to_csv(output / "imported_summary.csv", index=False)
    state = output / "demo_state.pkl"
    save_state(experiment, str(state))
    restored = load_state(str(state), verbose=False)
    pd.testing.assert_frame_equal(experiment.summary, restored.summary)
    info = {"dataset": "entirely simulated", "subjects": 12,
            "subjects_per_group": {"A": 6, "B": 6}, "metric": metric,
            "group_means": {name: float(values.mean()) for name, values in zip(("A", "B"), groups)},
            "test": test, "posthoc": posthoc, "python": platform.python_version(),
            "welch_t": float(statistic), "welch_p": float(pvalue),
            "pyflash": version("PyFLASH-analysis"),
            "elapsed_seconds": round(time.perf_counter() - started, 3)}
    (output / "run_info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(info, indent=2))
    print(f"Demo passed; outputs: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parent / "data/summary.csv")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "output")
    args = parser.parse_args()
    run(args.input.resolve(), args.output.resolve())
