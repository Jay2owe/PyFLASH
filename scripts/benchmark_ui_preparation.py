"""Paired UI preparation benchmark; source data remains unchanged.

Accept a saved batch and a preserved baseline workspace module. Write raw timing,
environment and correctness evidence as JSON, never scientific outputs. Baseline
setup/import and pickle loading are measured separately from table preparation.
"""
import argparse
import gc
import importlib.util
import json
import platform
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--baseline-module", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pairs", type=int, default=10)
    args = parser.parse_args()
    if args.pairs < 3:
        parser.error("Use at least three paired trials.")
    import pandas as pd
    from PyFLASH.ui import services, workspace
    from PyFLASH.export import format_summary_for_display
    spec = importlib.util.spec_from_file_location("baseline_workspace", args.baseline_module)
    baseline = importlib.util.module_from_spec(spec); spec.loader.exec_module(baseline)
    started = time.perf_counter()
    batch = services.open_pickle(args.source)
    report = {"python": platform.python_version(), "os": platform.platform(), "cpu": platform.processor(),
              "source_bytes": Path(args.source).stat().st_size, "source_sha256": workspace.content_hash(args.source),
              "baseline_module_sha256": workspace.content_hash(args.baseline_module),
              "candidate_module_sha256": workspace.content_hash(workspace.__file__),
              "load_seconds": time.perf_counter() - started, "pandas": pd.__version__, "cases": {}}
    try:
        import psutil
        report["rss_before"] = psutil.Process().memory_info().rss
    except ImportError:
        psutil = None
    cases = {"real_saved_batch": batch,
             "frozen_example": workspace.load_table(workspace.DEMO_PATH, demo=True)}
    for name, target in cases.items():
        raw = services.summary_table(target, display=False)
        report["cases"][name] = {"rows": len(raw), "columns": len(raw.columns), "pairs": []}
        def old():
            table = baseline.measurement_table(target)
            metrics = baseline.numeric_columns(table)
            labels = dict(zip(table.columns, format_summary_for_display(table).columns))
            return table, metrics, labels
        def new():
            return workspace.measurement_catalogue(target, cache={})
        for pair in range(args.pairs):
            repeats = 30 if name == "frozen_example" else 1
            results, sample = {}, {"order": "AB" if pair % 2 == 0 else "BA", "repeats": repeats}
            for implementation in sample["order"]:
                gc.collect()
                started = time.perf_counter()
                for _ in range(repeats):
                    results[implementation] = (old if implementation == "A" else new)()
                sample[implementation] = (time.perf_counter() - started) / repeats
                print(name, pair, implementation, sample[implementation], flush=True)
            pd.testing.assert_frame_equal(results["A"][0], results["B"][0], check_exact=True)
            assert results["A"][1] == results["B"][1]
            assert all(results["A"][2][c] == results["B"][2][c] for c in results["B"][1])
            sample["speedup"] = sample["A"] / sample["B"]
            report["cases"][name]["pairs"].append(sample)
            del results
        cache = {}
        workspace.measurement_catalogue(target, cache=cache)
        warm = []
        for _ in range(5):
            started = time.perf_counter()
            workspace.measurement_catalogue(target, cache=cache)
            warm.append(time.perf_counter() - started)
        report["cases"][name]["warm_candidate_seconds"] = warm
        del cache
    gc.collect()
    if psutil:
        memory = psutil.Process().memory_info()
        report.update(rss_retained=memory.rss, peak_rss=getattr(memory, "peak_wset", None))
    assert workspace.content_hash(args.source) == report["source_sha256"], "Source changed during benchmark"
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(output, flush=True)


if __name__ == "__main__":
    main()
