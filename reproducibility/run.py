"""Retain independent comparisons, coverage, replay, tests and browser evidence.

Run `python -m reproducibility.run --full --require-complete`. Each pass gets
its own directory. Numerical agreement and complete scientific coverage are
separate gates; missing coverage is never a pass. See WORKFLOW.md.
"""
from __future__ import annotations

import argparse
import ast
import csv
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

from reproducibility.cases import ATOL, RTOL, FIXTURE, inputs, load_expected

ROOT = Path(__file__).resolve().parents[1]
# Bind metadata caches to the runner code loaded by this process, not only to
# the source currently on disk. A long-lived process can outlive an edit and
# otherwise write old builder output under the edited source identity.
RUNNER_SOURCE_AT_IMPORT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
FINALIZATION_RESERVE_BYTES = 8 * 1024**2
FINALIZATION_RESERVE_NAME = "finalization-space-reserve.bin"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_clean(value):
    import math
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_clean(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [json_clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path, value):
    from PyFLASH._persistence import write_json as atomic_write
    atomic_write(path,json_clean(value))


def create_finalization_reserve(output, *, size_bytes=FINALIZATION_RESERVE_BYTES):
    """Preallocate space for a compact failure report and terminal run receipt."""
    path = Path(output) / FINALIZATION_RESERVE_NAME
    with path.open("wb") as stream:
        block = b"\0" * min(1024 * 1024, size_bytes)
        remaining = size_bytes
        while remaining:
            chunk = block[:min(len(block), remaining)]
            stream.write(chunk)
            remaining -= len(chunk)
        stream.flush()
        os.fsync(stream.fileno())
    return path


def release_finalization_reserve(output):
    (Path(output) / FINALIZATION_RESERVE_NAME).unlink(missing_ok=True)


class SnapshotCopyError(RuntimeError):
    def __init__(self, source, cause, completed, expected):
        self.source = Path(source)
        self.cause = cause
        self.completed = completed
        self.expected = expected
        super().__init__(f"Could not snapshot {self.source}: {cause}")


def copy_snapshot_file(source, target, *, attempts=6, retry_delay=0.25):
    """Copy one source atomically, hash bytes while copying and retry brief IO races."""
    source, target = Path(source), Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(attempts):
        temporary = None
        try:
            before = source.stat()
            with source.open("rb") as src:
                descriptor, name = tempfile.mkstemp(
                    dir=target.parent, prefix=f".{target.name}.", suffix=".snapshot-tmp")
                temporary = Path(name)
                digest = hashlib.sha256()
                copied = 0
                with os.fdopen(descriptor, "wb") as dst:
                    for chunk in iter(lambda: src.read(1024 * 1024), b""):
                        dst.write(chunk)
                        digest.update(chunk)
                        copied += len(chunk)
                    dst.flush()
            after = source.stat()
            if copied != before.st_size or after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
                raise RuntimeError(f"Source changed during snapshot: {source}")
            os.replace(temporary, target)
            return {"path": str(source), "size_bytes": copied,
                    "sha256": digest.hexdigest(), "mtime_ns": after.st_mtime_ns}
        except OSError as error:
            last_error = error
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            transient = isinstance(error, (FileNotFoundError, PermissionError)) or getattr(error, "winerror", None) in {
                5, 32, 33, 53, 64, 121, 995
            }
            if not transient or attempt + 1 >= attempts:
                raise
            time.sleep(retry_delay * (2 ** attempt))
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink(missing_ok=True)
    raise last_error or RuntimeError(f"Snapshot failed without an IO error: {source}")


def snapshot_sources(sources, snapshots, *, workers=4, progress_path=None):
    """Copy an immutable source set with bounded workers and durable progress."""
    sources, snapshots = list(sources), Path(snapshots)
    if workers < 1 or workers > 8:
        raise ValueError("Snapshot worker count must be between 1 and 8.")
    total_bytes = sum(source.stat().st_size for source in sources)
    progress = {"schema_version": 1, "status": "running", "expected_files": len(sources),
                "expected_bytes": total_bytes, "completed_files": 0, "copied_bytes": 0,
                "workers": workers, "updated_at": datetime.now(timezone.utc).isoformat()}
    if progress_path is not None:
        write_json(progress_path, progress)
    results = {}
    remaining = iter(sources)
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pyflash-snapshot")
    pending = {}
    failure = None
    try:
        for _ in range(workers):
            source = next(remaining, None)
            if source is None:
                break
            target = snapshots / source.relative_to(ROOT)
            pending[executor.submit(copy_snapshot_file, source, target)] = source
        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                source = pending.pop(future)
                try:
                    record = future.result()
                except Exception as error:
                    failure = SnapshotCopyError(source, error, len(results), len(sources))
                    break
                results[source] = record
                progress["completed_files"] = len(results)
                progress["copied_bytes"] += record["size_bytes"]
                progress["updated_at"] = datetime.now(timezone.utc).isoformat()
                if progress_path is not None and (len(results) % 50 == 0 or len(results) == len(sources)):
                    write_json(progress_path, progress)
                next_source = next(remaining, None)
                if next_source is not None:
                    target = snapshots / next_source.relative_to(ROOT)
                    pending[executor.submit(copy_snapshot_file, next_source, target)] = next_source
            if failure is not None:
                for future in pending:
                    future.cancel()
                break
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    if failure is not None:
        progress.update(status="failed", failed_source=str(failure.source),
                        error=f"{type(failure.cause).__name__}: {failure.cause}",
                        updated_at=datetime.now(timezone.utc).isoformat())
        if progress_path is not None:
            write_json(progress_path, progress)
        raise failure from failure.cause
    progress.update(status="finished", updated_at=datetime.now(timezone.utc).isoformat())
    if progress_path is not None:
        write_json(progress_path, progress)
    return [results[source] for source in sources]


def record_snapshot_failure(output, receipt, error, *, stage, progress_path=None):
    """Persist an honest failed-before-start receipt and traceback."""
    output = Path(output)
    error_trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    failure = dict(receipt)
    failure.update(status="failed-before-start", passed=False, stage=stage,
                   failed_at=datetime.now(timezone.utc).isoformat(),
                   numerical_gate=False, scientific_completeness_gate=False,
                   workflow_gate=False if receipt.get("workflow_gate") is not None else None,
                   error=error_trace, snapshot_failure=str(error),
                   partial_snapshot_retained=(output / "sources").exists(),
                   workflow_stages_started=False)
    if progress_path is not None and Path(progress_path).is_file():
        try:
            failure["snapshot_progress"] = json.loads(Path(progress_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            failure["snapshot_progress"] = {"read_error": "Progress receipt could not be read."}
    write_json(output / "run-started.json", failure)
    write_json(output / "run.json", failure)
    write_json(output / "snapshot-failure.json", failure)
    (output / "snapshot-failure.log").write_text(error_trace, encoding="utf-8")
    print(f"Receipt: {output / 'run.json'}", flush=True)
    return failure


def pack_numerical_values(values):
    """Keep infinity signs and NaN separate when writing strict JSON."""
    import math
    return {'values':[v if math.isfinite(v) else None for v in values],
            'nonfinite':[None if math.isfinite(v) else 'positive_infinity' if v==math.inf
                         else 'negative_infinity' if v==-math.inf else 'nan' for v in values]}


def python_command(*, native_metadata=False):
    # Windows' launcher can select a different installation of the same version.
    # Store installs expose the actual executable inside sys.prefix; use it so
    # child processes retain this interpreter's site-packages and dependencies.
    actual = Path(sys.prefix)/"python.exe"
    executable = str(actual) if os.name == "nt" and actual.is_file() else sys.executable
    if native_metadata and os.name == 'nt':
        return [executable, str(ROOT/'reproducibility/check_bootstrap.py')]
    return [executable]


def versions():
    result = {"python":sys.version.split()[0]}
    from PyFLASH.dependencies import registry
    names = set(registry()) | {"PyFLASH-analysis","numpy","pandas","scipy","statsmodels","pingouin","mpmath","sympy","shapely","astropy","pycircstat2","reprofig","pytest","streamlit",
                 "build","mkdocs","mkdocs-material","mkdocs-awesome-pages-plugin","playwright","uv"}
    for name in sorted(names):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = "unavailable"
    return result


def freeze_references(reason):
    """Explicit reference-only fixture creation; never run during verification."""
    from reproducibility.comparisons import reference_values
    if FIXTURE.exists():
        raise ValueError("Reference fixture already exists; preserve it and review a versioned revision.")
    if not reason.strip():
        raise ValueError("A scientific reason is required.")
    FIXTURE.parent.mkdir(parents=True,exist_ok=True)
    write_json(FIXTURE,{"schema_version":1,"reason":reason,
        "created_at":datetime.now(timezone.utc).isoformat(),"inputs":inputs(),
        "versions":versions(),"reference_code_sha256":sha256(Path(__file__).with_name("comparisons.py")),
        "rtol":RTOL,"atol":ATOL,"rows":reference_values()})


def _build_inventory():
    """Build immutable callable/options metadata independently of execution."""
    from PyFLASH.spec import PLOT_REGISTRY
    rows = []
    trees = {}

    def declarations(path):
        if path not in trees:
            trees[path] = ast.parse(path.read_text(encoding="utf-8"))
        return trees[path]

    tests = {p.name:p.read_text(encoding="utf-8") for p in (ROOT/"tests").glob("test_*.py")}
    modules = ("stats","stats_extra","modelling","pipeline","association_coefficients",
               "association_correlations","experiment","batch","dataframe","markers",
               "exclusions","iteration","image_io","conditions","report")
    from reproducibility.scientific_geometry_contract import SCIENTIFIC_UTILITIES, CAPABILITY_PREFIXES
    from reproducibility.correlation_pipeline_contract import CAPABILITY_PREFIXES as correlation_prefixes
    from reproducibility.adjusted_correlation_pipeline_contract import (
        CAPABILITY_PREFIXES as adjusted_correlation_prefixes,
    )
    from reproducibility.category_counts_contract import CAPABILITY_PREFIXES as category_count_prefixes
    modules = modules + ('utils',)
    for module in modules:
        path = ROOT/"PyFLASH"/(module+".py")
        if not path.is_file():
            continue
        tree = declarations(path)
        from reproducibility.method_inventory import method_declarations
        inherited_methods = {}
        for owner, function, defined_on in method_declarations(tree):
            inherited_methods.setdefault(owner, []).append((owner, function))
        for node in tree.body:
            functions = [(None,node)] if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) else (
                inherited_methods.get(node.name, []) if isinstance(node,ast.ClassDef) else [])
            for owner,func in functions:
                if module=="utils" and func.name not in SCIENTIFIC_UTILITIES:
                    continue
                if func.name.startswith("_"):
                    continue
                key = f"PyFLASH.{module}."+(owner+"." if owner else "")+func.name
                kind = ('functional-image-input-and-resource-control' if module=='image_io' else
                        'functional-request-validation' if module.startswith('association_') and func.name=='normalize_specs' else
                        'functional-design-construction' if module=='conditions' else
                        'functional-selection-or-orchestration' if module=='iteration' else
                        'functional-table-selection' if module=='stats' and func.name=='extract_p_and_stats_from_results' else
                        'functional-probability-presentation' if module=='stats' and func.name=='get_annotation' else
                        'functional-cache-identity-and-ownership' if module=='stats' and func.name in {'stats_cache_key','clear_stats_cache'} else
                        'functional-report-presentation-and-export' if module=='stats' and func.name in {'results_to_excel','print_comparison_results'} else
                        'scientific-callable')
                rows.append({"capability":key,"kind":kind,
                             "options":ast.unparse(func.args),"status":"not-fully-independently-validated",
                             "integration_tests":";".join(name for name,source in tests.items() if func.name in source)})
    for alias,target in PLOT_REGISTRY.items():
        module,name = target.rsplit(".",1) if "." in target else ("PyFLASH.plotting",target)
        tree = declarations((ROOT/Path(*module.split("."))).with_suffix(".py"))
        declaration = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == name)
        rows.append({"capability":alias,"kind":"registered-plot-or-pipeline",
                     "options":ast.unparse(declaration.args),"status":"not-fully-independently-validated",
                     "integration_tests":";".join(file for file,source in tests.items() if name in source)})
    # A callable plot is still part of the public package when no registry
    # alias names it. Do not hide legacy plotting entry points from the gate.
    registered = {target if "." in target else "PyFLASH.plotting."+target
                  for target in PLOT_REGISTRY.values()}
    for node in declarations(ROOT/"PyFLASH"/"plotting.py").body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("plot_"):
            key = "PyFLASH.plotting."+node.name
            if key not in registered:
                rows.append({"capability":key,"kind":"unregistered-public-plot",
                    "options":ast.unparse(node.args),"status":"not-fully-independently-validated",
                    "integration_tests":";".join(file for file,source in tests.items() if node.name in source)})
    prefixes = {
        "PyFLASH.modelling.iterative_best_fit": ("iterative-best-fit.",),
        "PyFLASH.modelling._PyFLASHOrdinalLogistic.fit": ("ordinal-zero.","ordinal-constant.","ordinal-native-fit."),
        "PyFLASH.modelling._PyFLASHOrdinalLogistic.predict": ("ordinal-zero.","ordinal-prediction.","ordinal-native-fit."),
        "PyFLASH.modelling._PyFLASHOrdinalLogistic.predict_proba": ("ordinal-zero.","ordinal-prediction.","ordinal-native-fit."),
        "mean_bars": ("mean-bars.",),
        "PyFLASH.report.build_comparison_record": ("comparison-record.","comparison-record-audit."),
        "PyFLASH.stats.multipleComparisons": ("comparison-parent-inference.","comparison-parent-routing.","comparison-parent-model-scope.","comparison-parent-auto-scope.","comparison-parent-effect.","parent-interval.","comparison-parent-cache.","comparison-parent-record."),
        "PyFLASH.pipeline.group_comparison": ("group-normality-boundary.",),
        "PyFLASH.pipeline.linear_model": ("linear-parent-native.",),
        "linear_model_pipeline": ("linear-parent-native.",),
        "linear_model_coefficient_forest": ("linear-forest-native.",),
        "PyFLASH.modelling.run_linear_model_pipeline": ("linear-wrapper-native.",),
        "PyFLASH.stats.runITTest": ("ttest.",),
        "PyFLASH.stats_extra.cohens_d": ("effect.cohen.",),
        "PyFLASH.stats_extra.hedges_g": ("effect.hedges.",),
        "PyFLASH.stats_extra.rank_biserial": ("effect.rank_biserial.",),
        "PyFLASH.stats_extra.effect_ci": ("bootstrap.","scale-interval."),
        "PyFLASH.stats_extra.adjust_pvalues": ("correction.",),
        "PyFLASH.stats_extra.fit_cosinor": ("cosinor.",),
        "PyFLASH.stats_extra.cosinor_group_test": ("group-rhythm.",),
        "PyFLASH.stats_extra.cosinor_table": ("population-rhythm.", "mixed-rhythm.", "cosinor-table."),
        "PyFLASH.stats_extra.correction_audit": ("calibration.",),
        "PyFLASH.stats.fisher_z_se": ("fisher.se.",),
        "PyFLASH.stats.fisher_z_correlation_difference": ("fisher.difference.",),
        "PyFLASH.stats.zou_correlation_difference_ci": ("zou.",),
        "PyFLASH.stats.cauchy_combination_test": ("cauchy.",),
        "PyFLASH.stats_extra.iqr_bounds": ("iqr.",),
        "PyFLASH.stats_extra.mad_modified_z": ("mad.",),
        "PyFLASH.stats_extra.anova_effect_sizes": ("anova.effect.",),
        "PyFLASH.stats_extra.icc1": ("icc1.",),
        "PyFLASH.stats_extra.circular_stats": ("circular.descriptive.",),
        "PyFLASH.stats_extra.fit_growth_curve": ("growth.",),
    }
    prefixes.update(CAPABILITY_PREFIXES)
    prefixes.update(correlation_prefixes)
    prefixes.update(adjusted_correlation_prefixes)
    prefixes.update(category_count_prefixes)
    from reproducibility.rhythm_pipeline_contract import CAPABILITY_PREFIXES as rhythm_pipeline_prefixes
    for capability,names in rhythm_pipeline_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.association_interval_contract import CAPABILITY_PREFIXES as interval_prefixes
    prefixes.update(interval_prefixes)
    from reproducibility.association_fisher_contract import CAPABILITY_PREFIXES as fisher_prefixes
    for capability,names in fisher_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.dataframe_identifier_contract import CAPABILITY_PREFIXES as identifier_prefixes
    for capability,names in identifier_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.dataframe_recoding_contract import CAPABILITY_PREFIXES as recoding_prefixes
    for capability,names in recoding_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.dataframe_metadata_contract import CAPABILITY_PREFIXES as metadata_prefixes
    for capability,names in metadata_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.dataframe_comparison_contract import CAPABILITY_PREFIXES as dataframe_comparison_prefixes
    for capability,names in dataframe_comparison_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.dataframe_whole_contract import CAPABILITY_PREFIXES as dataframe_whole_prefixes
    for capability,names in dataframe_whole_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.excel_export_contract import CAPABILITY_PREFIXES as excel_prefixes
    for capability,names in excel_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.excel_region_contract import CAPABILITY_PREFIXES as region_prefixes
    for capability,names in region_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.excel_orchestration_contract import CAPABILITY_PREFIXES as excel_orchestration_prefixes
    for capability,names in excel_orchestration_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.excel_workbook_schema_contract import CAPABILITY_PREFIXES as workbook_schema_prefixes
    from reproducibility.excel_literal_cell_contract import CAPABILITY_PREFIXES as literal_cell_prefixes
    from reproducibility.excel_coupled_contract import CAPABILITY_PREFIXES as coupled_client_prefixes
    from reproducibility.excel_destination_contract import CAPABILITY_PREFIXES as destination_prefixes
    from reproducibility.excel_region_selection_contract import CAPABILITY_PREFIXES as region_selection_prefixes
    from reproducibility.excel_measurement_map_contract import CAPABILITY_PREFIXES as measurement_map_prefixes
    from reproducibility.excel_all_mapping_workbook_contract import CAPABILITY_PREFIXES as all_mapping_workbook_prefixes
    from reproducibility.excel_positive_label_semantics_contract import CAPABILITY_PREFIXES as positive_label_prefixes
    from reproducibility.excel_mean_wording_semantics_contract import CAPABILITY_PREFIXES as mean_wording_prefixes
    from reproducibility.excel_distance_presentation_contract import CAPABILITY_PREFIXES as distance_presentation_prefixes
    from reproducibility.excel_filter_controls_contract import CAPABILITY_PREFIXES as filter_controls_prefixes
    from reproducibility.excel_summary_lifecycle_contract import CAPABILITY_PREFIXES as lifecycle_export_prefixes
    from reproducibility.surface_volume_unit_contract import CAPABILITY_PREFIXES as surface_volume_unit_prefixes
    for extra_prefixes in (workbook_schema_prefixes, literal_cell_prefixes, coupled_client_prefixes, destination_prefixes, region_selection_prefixes, measurement_map_prefixes, all_mapping_workbook_prefixes, positive_label_prefixes, mean_wording_prefixes, distance_presentation_prefixes, surface_volume_unit_prefixes, filter_controls_prefixes, lifecycle_export_prefixes):
        for capability,names in extra_prefixes.items():
            prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.outlier_request_contract import CAPABILITY_PREFIXES as request_prefixes
    for capability,names in request_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.outlier_subject_identity_contract import CAPABILITY_PREFIXES as outlier_identity_prefixes
    for capability,names in outlier_identity_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.outlier_ledger_source_contract import CAPABILITY_PREFIXES as outlier_ledger_prefixes
    for capability,names in outlier_ledger_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.outlier_options_contract import CAPABILITY_PREFIXES as outlier_option_prefixes
    for capability,names in outlier_option_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.ordinal_binary_glm_contract import CAPABILITY_PREFIXES as binary_prefixes
    for capability,names in binary_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.marker_threshold_contract import CAPABILITY_PREFIXES as marker_threshold_prefixes
    for capability,names in marker_threshold_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.marker_nearest_contract import CAPABILITY_PREFIXES as marker_nearest_prefixes
    for capability,names in marker_nearest_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.marker_calibration_contract import CAPABILITY_PREFIXES as calibration_prefixes
    for capability,names in calibration_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.experiment_nearest_contract import CAPABILITY_PREFIXES as experiment_nearest_prefixes
    for capability,names in experiment_nearest_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.ventricle_native_contract import CAPABILITY_PREFIXES as ventricle_prefixes
    for capability,names in ventricle_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.summary_area_contract import CAPABILITY_PREFIXES as summary_area_prefixes
    for capability,names in summary_area_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.mini_scientific_contract import CAPABILITY_PREFIXES as mini_prefixes
    for capability,names in mini_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.mini_exclusion_contract import CAPABILITY_PREFIXES as mini_exclusion_prefixes
    for capability,names in mini_exclusion_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.mini_score_contract import CAPABILITY_PREFIXES as mini_score_prefixes
    for capability,names in mini_score_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.mini_lifecycle_contract import CAPABILITY_PREFIXES as mini_lifecycle_prefixes
    for capability,names in mini_lifecycle_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.mini_image_condition_contract import CAPABILITY_PREFIXES as mini_image_prefixes
    for capability,names in mini_image_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.mini_nonfinite_score_contract import CAPABILITY_PREFIXES as mini_nonfinite_prefixes
    for capability,names in mini_nonfinite_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.mini_object_mean_contract import CAPABILITY_PREFIXES as mini_object_prefixes
    for capability,names in mini_object_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.parent_ownership_contract import CAPABILITY_PREFIXES as parent_ownership_prefixes
    for capability,names in parent_ownership_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.mini_csv_refresh_contract import CAPABILITY_PREFIXES as csv_refresh_prefixes
    for capability,names in csv_refresh_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.empty_parent_contract import CAPABILITY_PREFIXES as empty_parent_prefixes
    for capability,names in empty_parent_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.marker_assignment_contract import CAPABILITY_PREFIXES as marker_assignment_prefixes
    for capability,names in marker_assignment_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.inherited_mini_metadata_contract import CAPABILITY_PREFIXES as inherited_metadata_prefixes
    for capability,names in inherited_metadata_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.region_assignment_contract import CAPABILITY_PREFIXES as region_assignment_prefixes
    for capability,names in region_assignment_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.display_summary_contract import CAPABILITY_PREFIXES as display_summary_prefixes
    for capability,names in display_summary_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility import roi_analysis_contract, mixed_mean_fidelity_contract, whole_condition_contract, image_table_contract, axis_bound_contract, trace_policy_contract, window_carrier_contract, mini_summary_whole_contract, inherited_spatial_contract, inherited_mini_csv_contract, inherited_roi_contract, coloc_annotation_contract, mini_condition_whole_contract, image_import_whole_contract, marker_cleaning_options_contract, marker_cleaning_edges_contract, marker_cleaning_whole_contract
    for contract in (roi_analysis_contract, mixed_mean_fidelity_contract, whole_condition_contract, image_table_contract, axis_bound_contract, trace_policy_contract, window_carrier_contract, mini_summary_whole_contract, inherited_spatial_contract, inherited_mini_csv_contract, inherited_roi_contract, coloc_annotation_contract, mini_condition_whole_contract, image_import_whole_contract, marker_cleaning_options_contract, marker_cleaning_edges_contract, marker_cleaning_whole_contract):
        for capability,names in contract.CAPABILITY_PREFIXES.items():
            prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.ecdf_public_contract import CAPABILITY_PREFIXES as ecdf_prefixes
    for capability,names in ecdf_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.marker_region_contract import CAPABILITY_PREFIXES as marker_region_prefixes
    for capability,names in marker_region_prefixes.items():
        prefixes[capability]=prefixes.get(capability,())+names
    from reproducibility.marker_factor_region_contract import CAPABILITY_PREFIXES as factor_region_prefixes
    from reproducibility.object_mean_contract import CAPABILITY_PREFIXES as object_mean_prefixes
    for selected_prefixes in (factor_region_prefixes, object_mean_prefixes):
        for capability, names in selected_prefixes.items():
            prefixes[capability] = prefixes.get(capability, ()) + names
    from reproducibility.scientific_utility_contract import (
        CAPABILITY_PREFIXES as utility_prefixes,
        COMPLETE_CAPABILITIES as complete_utilities,
        required_keys as utility_required_keys,
    )
    from reproducibility.dataframe_lifecycle_contract import (
        COMPLETE_CAPABILITIES as lifecycle_capabilities,
        required_keys as lifecycle_required_keys,
    )
    for capability, names in utility_prefixes.items():
        prefixes[capability] = prefixes.get(capability, ()) + names
    for capability in lifecycle_capabilities:
        prefixes[capability] = ('dataframe-lifecycle.',)
    # Only these bounded scalar methods have complete parameter/return-field
    # contracts here. No effect helper certifies a bootstrap, plot or pipeline.
    from reproducibility.scalar_contracts import cases as scalar_cases
    from reproducibility.helper_contracts import cases as helper_cases
    from reproducibility.cauchy_contract import cases as cauchy_cases
    from reproducibility.native_power import cases as power_cases
    from reproducibility.proportion_contract import cases as proportion_cases
    from reproducibility.auc_contract import cases as auc_cases
    from reproducibility.multiplicity_contract import cases as multiplicity_cases
    from reproducibility.fdr_family_contract import cases as fdr_family_cases
    from reproducibility.circular_contract import cases as circular_cases
    from reproducibility.circular_linear_contract import cases as circular_linear_cases
    from reproducibility.watson_williams_contract import cases as watson_williams_cases
    from reproducibility.iterative_best_fit_contract import required_keys as iterative_best_fit_required_keys
    from reproducibility.iteration_contract import cases as iteration_cases
    from reproducibility.dispersion_contract import cases as dispersion_cases
    from reproducibility.iteration_run_contract import cases as iteration_run_cases
    from reproducibility.conditions_contract import cases as conditions_cases
    from reproducibility.comparison_index_contract import cases as comparison_index_cases
    from reproducibility.effect_magnitude_contract import cases as effect_magnitude_cases
    from reproducibility.permutation_contract import cases as permutation_cases
    from reproducibility.cosinor_contract import cases as cosinor_cases
    from reproducibility.group_rhythm_contract import cases as group_rhythm_cases
    from reproducibility.cosinor_table_contract import cases as cosinor_table_cases
    from reproducibility.image_io_contract import cases as image_io_cases
    from reproducibility.bootstrap_options_contract import cases as bootstrap_option_cases
    from reproducibility.scale_interval_contract import cases as scale_interval_cases
    from reproducibility.anderson_contract import cases as anderson_cases
    from reproducibility.normality_parent_validation import required_keys as normality_parent_required_keys
    from reproducibility.comparison_geometry_contract import required_keys as comparison_geometry_required_keys, CAPABILITIES as comparison_geometry_capabilities
    from reproducibility.group_description_contract import cases as group_description_cases
    from reproducibility.regression_record_contract import cases as regression_record_cases, capability as regression_record_capability
    from reproducibility.report_serialization_contract import cases as report_serialization_cases, capability as report_serialization_capability
    from reproducibility.record_digest_contract import cases as record_digest_cases
    from reproducibility.collector_contract import cases as collector_cases, owners as collector_owners
    from reproducibility.ordinal_parameter_contract import cases as ordinal_parameter_cases, CAPABILITIES as ordinal_parameter_capabilities
    from reproducibility.comparison_record_audit_contract import required_keys as comparison_record_required_keys
    from reproducibility.growth_contract import cases as growth_full_cases
    from reproducibility.outlier_contract import cases as outlier_cases, capability as outlier_capability
    from reproducibility.effect_report_contract import cases as effect_report_cases
    from reproducibility.dunnett_contract import cases as dunnett_cases
    from reproducibility.finite_scale_contract import cases as finite_scale_cases
    from reproducibility.scalar_input_contract import cases as scalar_input_cases
    from reproducibility.presentation_cache_contract import cases as presentation_cache_cases
    from reproducibility.variance_student_contract import cases as variance_student_cases
    from reproducibility.variance_student_validation import native_cases as variance_student_native_cases
    from reproducibility.mann_whitney_contract import cases as mann_whitney_cases
    from reproducibility.mann_whitney_validation import native_cases as mann_whitney_native_cases
    from reproducibility.print_export_contract import cases as print_export_cases
    from reproducibility.one_way_validation import required_keys as one_way_required_keys
    from reproducibility.welch_one_way_validation import required_keys as welch_one_way_required_keys
    from reproducibility.rank_validation import required_keys as rank_required_keys
    from reproducibility.two_way_validation import required_keys as two_way_required_keys
    from reproducibility.linear_model_validation import required_keys as linear_model_required_keys
    from reproducibility.scalar_multiplicity_contract import cases as scalar_multiplicity_cases
    from reproducibility.extreme_inference_contract import required_keys as extreme_inference_keys
    from reproducibility.interaction_slope_contract import cases as interaction_slope_cases
    from reproducibility.association_specs_contract import cases as association_request_cases, capability as association_request_capability
    from reproducibility.mixed_variance_boundary_contract import cases as mixed_variance_cases
    from reproducibility.mixed_rhythm_contract import zero_noise_cases
    from reproducibility.minp_contract import cases as minp_cases
    from reproducibility.value_permutation_contract import cases as value_permutation_cases
    from reproducibility.correction_report_contract import cases as correction_report_cases
    from reproducibility.manual_exclusion_contract import cases as manual_exclusion_cases, owners as manual_exclusion_owners
    required = {}
    for case in manual_exclusion_cases():
        for owner in manual_exclusion_owners(case):
            required.setdefault(owner,set()).add(case['key'])
    for case in regression_record_cases():
        required.setdefault(regression_record_capability(case),set()).add(case['key'])
    for case in report_serialization_cases():
        required.setdefault(report_serialization_capability(case),set()).add(case['key'])
    required.setdefault('PyFLASH.report.build_comparison_record',set()).update(comparison_record_required_keys())
    required.setdefault('PyFLASH.report.render_digest',set()).update(case['key'] for case in record_digest_cases())
    for case in collector_cases():
        for owner in collector_owners(case):required.setdefault(owner,set()).add(case['key'])
    for capability in ordinal_parameter_capabilities:
        required.setdefault(capability,set()).update(case['key'] for case in ordinal_parameter_cases())
    required.setdefault('PyFLASH.report.describe_group',set()).update(row['key'] for row in group_description_cases())
    for capability in comparison_geometry_capabilities:
        required.setdefault(capability,set()).update(comparison_geometry_required_keys())
    for case in scalar_cases():
        required.setdefault(case['capability'], set()).add('scalar.'+case['key'])
    for case in helper_cases():
        required.setdefault(case['capability'], set()).add('helper.'+case['key'])
    for case in comparison_index_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in effect_magnitude_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in permutation_cases():
        required.setdefault(case['capability'],set()).add(case['key'])
        required.setdefault('PyFLASH.stats_extra.attainable_p_floor',set()).add(case['key']+'.floor')
    for case in cosinor_cases():
        required.setdefault(case['capability'],set()).add(case['key'])
    for case in group_rhythm_cases():
        required.setdefault(case['capability'],set()).add(case['key'])
    for case in cosinor_table_cases():
        required.setdefault(case['capability'],set()).update([case['key'],case['key']+'.raw-inputs'])
    from reproducibility.rhythm_pipeline_contract import required_keys as rhythm_pipeline_required_keys
    rhythm_keys = rhythm_pipeline_required_keys()
    for capability in ('PyFLASH.pipeline.rhythm', 'rhythm_pipeline'):
        required.setdefault(capability,set()).update(rhythm_keys)
    for case in mixed_variance_cases():
        required.setdefault(case['capability'],set()).add(case['key'])
    for case in zero_noise_cases():
        required.setdefault('PyFLASH.stats_extra.cosinor_table',set()).add(case['key']+'.no-finite-fit')
    for case in minp_cases():
        if not case.get('selected_fields_only'):
            required.setdefault(case['capability'],set()).add(case['key'])
    for case in value_permutation_cases():
        required.setdefault(case['capability'],set()).add(case['key'])
    for case in correction_report_cases():
        required.setdefault(case['capability'],set()).add(case['key'])
    for case in cauchy_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in power_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in proportion_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in auc_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in multiplicity_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in fdr_family_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in circular_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in circular_linear_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in watson_williams_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in iteration_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    required.setdefault('PyFLASH.modelling.iterative_best_fit', set()).update(
        iterative_best_fit_required_keys())
    for case in dispersion_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in iteration_run_cases():
        required.setdefault(case['capability'], set()).add(case['key'])
    for case in conditions_cases():
        for capability in case['capabilities']:
            required.setdefault(capability, set()).add(case['key'])
    for case in image_io_cases():
        for capability in case['capabilities']:
            required.setdefault(capability, set()).add(case['key'])
        if case['kind']!='helper':
            required.setdefault('PyFLASH.image_io.observe_image_reads',set()).add(case['key'])
    for case in bootstrap_option_cases():
        required.setdefault('PyFLASH.stats_extra.effect_ci',set()).add(case['key'])
    for case in scale_interval_cases():
        required.setdefault('PyFLASH.stats_extra.effect_ci',set()).add(case['key'])
    for case in anderson_cases():
        required.setdefault('PyFLASH.stats.modified_anderson',set()).add(case['key'])
    for case in growth_full_cases():
        required.setdefault('PyFLASH.stats_extra.fit_growth_curve',set()).add(case['key'])
    for case in outlier_cases():
        required.setdefault(outlier_capability(case),set()).add(case['key'])
    for case in effect_report_cases():
        required.setdefault('PyFLASH.stats_extra.effect_sizes_for_test',set()).add(case['key'])
    for case in dunnett_cases():
        required.setdefault('PyFLASH.stats_extra.dunnett_vs_control',set()).add(case['key'])
    for case in finite_scale_cases():
        required.setdefault('PyFLASH.stats_extra.'+case['method'],set()).add(case['key'])
    for case in scalar_input_cases():
        required.setdefault('PyFLASH.stats_extra.'+case['method'],set()).add(case['key'])
    for case in presentation_cache_cases():
        capability = ('get_annotation' if case['key'].startswith('annotation.') else
                      'clear_stats_cache' if case['kind']=='clear' else 'stats_cache_key')
        required.setdefault('PyFLASH.stats.'+capability,set()).add(case['key'])
    for case in variance_student_cases():
        capability = 'test_equal_variance' if case['kind']=='variance' else 'runITTest'
        required.setdefault('PyFLASH.stats.'+capability,set()).add(case['key'])
    for case in variance_student_native_cases():
        if case['role']=='independent-native-corroboration':
            capability = 'runITTest' if case['query']['key'].startswith('student-native.') else 'test_equal_variance'
            required.setdefault('PyFLASH.stats.'+capability,set()).add(case['query']['key'])
    for case in mann_whitney_cases():
        required.setdefault('PyFLASH.stats.mwu_multiple_comparisons',set()).add(case['key'])
    for case in mann_whitney_native_cases():
        if case['role']=='independent-native-corroboration':
            required.setdefault('PyFLASH.stats.mwu_multiple_comparisons',set()).add(case['query']['key'])
    for case in print_export_cases():
        capability='print_comparison_results' if case['kind']=='print' else 'results_to_excel'
        required.setdefault('PyFLASH.stats.'+capability,set()).add(case['key'])
    required.setdefault('PyFLASH.stats.runOWA',set()).update(one_way_required_keys())
    required.setdefault('PyFLASH.stats.test_normality',set()).update(normality_parent_required_keys())
    required.setdefault('PyFLASH.stats.runWelchOWA',set()).update(welch_one_way_required_keys())
    required.setdefault('PyFLASH.stats.runKW',set()).update(rank_required_keys())
    required.setdefault('PyFLASH.stats.runTWA',set()).update(two_way_required_keys())
    required.setdefault('PyFLASH.stats.runLinearModel',set()).update(linear_model_required_keys())
    for case in scalar_multiplicity_cases():
        required.setdefault('PyFLASH.stats.'+case['method'],set()).add(case['key'])
    required.setdefault('PyFLASH.stats.runITTest',set()).update(extreme_inference_keys('student'))
    for case in interaction_slope_cases():
        required.setdefault('PyFLASH.stats.interaction_slope_difference',set()).add(case['key'])
    for case in association_request_cases():
        required.setdefault(association_request_capability(case),set()).add(case['key'])
    from reproducibility.experiment_path_contract import APIS as folder_lookup_apis, required_keys as folder_lookup_keys
    for api in folder_lookup_apis:
        required.setdefault('PyFLASH.experiment.'+api,set()).update(folder_lookup_keys(api))
    # File discovery is a functional path policy, not microscopy inference.
    for row in rows:
        if row['capability'] in {'PyFLASH.experiment.'+api for api in folder_lookup_apis}:
            row['kind']='functional-experiment-folder-discovery'
    # Direct arithmetic/geometry envelopes and lifecycle interfaces cannot
    # certify whole microscopy procedures, table imports or fitted pipelines.
    for capability in complete_utilities:
        required.setdefault(capability, set()).update(utility_required_keys(capability))
    for capability in lifecycle_capabilities:
        required.setdefault(capability, set()).update(lifecycle_required_keys(capability))
    from reproducibility import dataframe_whole_contract as whole_dataframe
    for capability in whole_dataframe.COMPLETE_CAPABILITIES:
        required.setdefault(capability,set()).update(whole_dataframe.required_keys(capability))
    for row in rows:
        if row['capability'] in whole_dataframe.COMPLETE_CAPABILITIES:
            row['kind']='functional-whole-dataframe-input-adaptation'

    from reproducibility.marker_nearest_contract import (
        COMPLETE_CAPABILITIES as nearest_capabilities,
        required_keys as nearest_required_keys,
    )
    for capability in nearest_capabilities:
        required.setdefault(capability, set()).update(nearest_required_keys(capability))
        from reproducibility.marker_calibration_contract import cases as calibration_cases
        required.setdefault(capability, set()).update(item['key'] for item in calibration_cases())

    from reproducibility.experiment_nearest_contract import (
        COMPLETE_CAPABILITIES as experiment_nearest_capabilities,
        required_keys as experiment_nearest_required_keys,
    )
    for capability in experiment_nearest_capabilities:
        required.setdefault(capability,set()).update(experiment_nearest_required_keys(capability))

    from reproducibility.ventricle_native_contract import (
        COMPLETE_CAPABILITIES as ventricle_capabilities,
        required_keys as ventricle_required_keys,
    )
    for capability in ventricle_capabilities:
        required.setdefault(capability,set()).update(ventricle_required_keys(capability))

    from reproducibility.experiment_metadata_contract import CAPABILITIES as metadata_capabilities, required_keys as metadata_keys
    from reproducibility.marker_assignment_contract import COMPLETE_CAPABILITIES as assignment_capabilities, required_keys as assignment_keys
    from reproducibility.display_summary_contract import COMPLETE_CAPABILITIES as display_capabilities, required_keys as display_keys
    for capability in display_capabilities:
        required.setdefault(capability,set()).update(display_keys(capability))
    from reproducibility import roi_analysis_contract, whole_condition_contract, image_table_contract, axis_bound_contract, trace_policy_contract, window_carrier_contract, mini_summary_whole_contract, inherited_spatial_contract, inherited_mini_csv_contract, inherited_roi_contract, coloc_annotation_contract, mini_condition_whole_contract, image_import_whole_contract, marker_cleaning_options_contract, marker_cleaning_edges_contract, marker_cleaning_whole_contract
    for contract in (roi_analysis_contract, whole_condition_contract, image_table_contract, axis_bound_contract, trace_policy_contract, window_carrier_contract, mini_summary_whole_contract, inherited_spatial_contract, inherited_mini_csv_contract, inherited_roi_contract, coloc_annotation_contract, mini_condition_whole_contract, image_import_whole_contract, marker_cleaning_options_contract, marker_cleaning_edges_contract, marker_cleaning_whole_contract):
        for capability in contract.COMPLETE_CAPABILITIES:
            required.setdefault(capability,set()).update(contract.required_keys(capability))
    for row in rows:
        if row['capability'] in (whole_condition_contract.CAPABILITY, mini_condition_whole_contract.CAPABILITY):
            row['kind']='functional-categorical-assignment-and-table-ownership'
        if row['capability'] in marker_cleaning_whole_contract.CAPABILITIES:
            row['kind']='functional-whole-marker-cleaning-and-ownership'
        if row['capability'] in image_import_whole_contract.CAPABILITIES:
            row['kind']='functional-whole-image-filename-indexing-and-ownership'
        if row['capability'] in image_table_contract.CAPABILITIES:
            row['kind']='functional-image-table-retrieval-refresh-and-ownership'
        if row['capability'] in coloc_annotation_contract.CAPABILITIES:
            row['kind']='functional-colocalisation-table-annotation'
        if row['capability'] in axis_bound_contract.CAPABILITIES:
            row['kind']='functional-custom-scalar-display-bound-policy'
        if row['capability'] in trace_policy_contract.CAPABILITIES:
            row['kind']='functional-custom-whole-downward-trace-policy'
    for row in rows:
        if row['capability'] in display_capabilities:
            row['kind']='functional-display-summary-presentation-and-ownership'
    for capability in assignment_capabilities:
        required.setdefault(capability,set()).update(assignment_keys(capability))
    for row in rows:
        if row['capability'] in assignment_capabilities:
            row['kind']='functional-marker-table-ownership'
    for capability in metadata_capabilities:
        required.setdefault(capability,set()).update(metadata_keys(capability))
    from reproducibility.inherited_mini_metadata_contract import CAPABILITIES as inherited_metadata_capabilities, required_keys as inherited_metadata_keys
    for capability in inherited_metadata_capabilities:
        required.setdefault(capability,set()).update(inherited_metadata_keys(capability))
    for row in rows:
        if row['capability'] in metadata_capabilities | inherited_metadata_capabilities:
            row['kind']='functional-experiment-metadata-and-paths'

    from reproducibility.region_assignment_contract import CAPABILITIES as region_assignment_capabilities, required_keys as region_assignment_keys
    for capability in region_assignment_capabilities:
        required.setdefault(capability,set()).update(region_assignment_keys(capability))
    for row in rows:
        if row['capability'] in region_assignment_capabilities:
            row['kind']='functional-whole-region-assignment'

    from reproducibility.csv_export_contract import CAPABILITIES as csv_capabilities, required_keys as csv_keys
    for capability in csv_capabilities:
        required.setdefault(capability,set()).update(csv_keys(capability))
    for row in rows:
        if row['capability'] in csv_capabilities | inherited_mini_csv_contract.CAPABILITIES:
            row['kind']='functional-csv-serialization-and-batch-destinations'

    from reproducibility import scientific_geometry_contract as native_geometry
    native_polyline_keys = {
        'geometry-polyline.' + case['key'] + '.' + carrier
        for case in native_geometry.read('polyline-native-frozen-v1/inputs.json')
        for carrier in ('list', 'tuple', 'array')
    }
    required.setdefault('PyFLASH.utils.points_to_polyline_distance', set()).update(native_polyline_keys)
    for direction, owner in (('microns-to-pixels', 'convert_microns_to_pixels'),
                             ('pixels-to-microns', 'convert_pixels_to_microns')):
        required.setdefault('PyFLASH.utils.' + owner, set()).update(
            'geometry-conversion.' + direction + '.' + case['key']
            for case in native_geometry.read('native-imagej-geometry-comparisons-v1/paired.json')['conversions']
        )
    for row in rows:
        if row['capability'] in lifecycle_capabilities:
            row['kind'] = 'functional-table-adapter-lifecycle'
    from reproducibility import condition_key_contract
    for capability in condition_key_contract.COMPLETE_CAPABILITIES:
        required.setdefault(capability, set()).update(condition_key_contract.required_keys(capability))
        prefixes[capability] = condition_key_contract.CAPABILITY_PREFIXES[capability]
    for row in rows:
        if row['capability'] in condition_key_contract.COMPLETE_CAPABILITIES:
            row['kind'] = 'functional-condition-legend-encoding-and-carriers'
    from reproducibility import excel_whole_export_contract
    whole_exports = excel_whole_export_contract.declaration()
    for capability in excel_whole_export_contract.COMPLETE_CAPABILITIES:
        required.setdefault(capability, set()).update(whole_exports['required'][capability])
        prefixes[capability] = tuple(sorted(set(prefixes.get(capability, ())) |
                                          set(whole_exports['prefixes'][capability])))
    for row in rows:
        if row['capability'] in excel_whole_export_contract.COMPLETE_CAPABILITIES:
            row['kind'] = 'functional-whole-batch-workbook-transport'
    from reproducibility import outlier_whole_contract
    whole_outliers=outlier_whole_contract.declaration()
    for capability in outlier_whole_contract.COMPLETE_CAPABILITIES:
        required.setdefault(capability,set()).update(whole_outliers['required'][capability])
        prefixes[capability]=tuple(sorted(set(prefixes.get(capability,()))|set(whole_outliers['prefixes'][capability])))
    for row in rows:
        if row['capability'] in outlier_whole_contract.COMPLETE_CAPABILITIES:
            row['kind']='scientific-outlier-parent-composition-and-functional-ledger-application'
    return {'rows': rows, 'prefixes': {key: list(value) for key, value in prefixes.items()},
            'required': {key: sorted(value) for key, value in required.items()}}


_INVENTORY_CACHE = None


def _inventory_base_identity():
    from reproducibility.workflow_engine import source_identity
    from PyFLASH.spec import PLOT_REGISTRY
    # Definitions can change which inputs are read; every source addition and
    # deletion invalidates discovery. Historical output arrays are not definitions.
    sources = (list((ROOT / 'PyFLASH').rglob('*.py')) + list((ROOT / 'reproducibility').glob('*.py'))
               + list((ROOT / 'tests').glob('*.py')))
    return {'sources': source_identity(ROOT, sources), 'registry': dict(PLOT_REGISTRY),
            'versions': versions(), 'runner_source_at_import': RUNNER_SOURCE_AT_IMPORT_SHA256}


def _inventory_index_path():
    from reproducibility.workflow import cache_root
    return cache_root() / 'inventory-dependencies' / 'index.json'


def _inventory_identity():
    from reproducibility.workflow_engine import dependency_identity, digest_value
    base = _inventory_base_identity()
    try:
        stored = json.loads(_inventory_index_path().read_text(encoding='utf-8'))
        payload = stored['payload']
        if payload['base'] == base and stored['sha256'] == digest_value(payload):
            files, directories = dependency_identity(ROOT, payload['files'], payload['directories'])
            return {'catalogue_base': base, 'files': files, 'directories': directories}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {'catalogue_base': base, 'discovery_required': True}


def _save_inventory_dependencies(base, capture):
    from reproducibility.workflow_engine import atomic_json, digest_value
    if not capture.unchanged() or _inventory_base_identity() != base:
        raise RuntimeError('Metadata sources changed while discovering verification inputs')
    # Bytecode is rebuildable; authoritative Python sources are already in base.
    files = sorted(name for name in capture.files if not name.endswith(('.pyc', '.pyo')))
    payload = {'base': base, 'files': files, 'directories': sorted(capture.directories)}
    atomic_json(_inventory_index_path(), {'schema_version': 1, 'payload': payload, 'sha256': digest_value(payload)})


def _inventory_metadata():
    """Authenticate one catalogue before comparing execution scenarios."""
    global _INVENTORY_CACHE
    from reproducibility.workflow_engine import MetadataCache, ReadCapture
    if _INVENTORY_CACHE is None:
        from reproducibility.workflow import cache_root
        _INVENTORY_CACHE = MetadataCache(cache_root() / 'inventory')
    identity = _inventory_identity()
    captured = []
    def build():
        with ReadCapture(ROOT) as capture:
            result = _build_inventory()
        capture.files = {name: value for name, value in capture.files.items() if '__pycache__' not in Path(name).parts}
        capture.directories = {name: value for name, value in capture.directories.items() if '__pycache__' not in Path(name).parts}
        if not capture.unchanged():
            raise RuntimeError('Metadata inputs changed during catalogue construction')
        captured.append(capture)
        return result
    if identity.get('discovery_required'):
        metadata = build()
        _save_inventory_dependencies(identity['catalogue_base'], captured[-1])
        identity = _inventory_identity()
        metadata, _ = _INVENTORY_CACHE.get(identity, lambda: metadata, _inventory_identity)
    else:
        metadata, _ = _INVENTORY_CACHE.get(identity, build, _inventory_identity)
        if captured and 'catalogue_base' in identity:
            # A changed fixture may point at additional files without changing code.
            _save_inventory_dependencies(identity['catalogue_base'], captured[-1])
            updated = _inventory_identity()
            if updated != identity:
                metadata, _ = _INVENTORY_CACHE.get(updated, lambda: metadata, _inventory_identity)
    return metadata


def _inventory_execution_status(metadata, executed_contracts):
    """Compare obligations without mutating the authenticated catalogue."""
    from copy import deepcopy
    rows, prefixes = deepcopy(metadata['rows']), metadata['prefixes']
    executed = set(executed_contracts)
    # Sort once rather than scanning every contract list repeatedly.
    from bisect import bisect_left
    names = sorted(executed)
    for row in rows:
        contracts = metadata['required'].get(row['capability'])
        found = set()
        for prefix in prefixes.get(row['capability'], ('\0',)):
            index = bisect_left(names, prefix)
            while index < len(names) and names[index].startswith(prefix):
                found.add(names[index])
                index += 1
        row['executed_subcontracts'] = ';'.join(sorted(found))
        if found:
            row['status'] = 'partially-validated-contract'
        if contracts:
            required = set(contracts)
            row['executed_subcontracts'] = ';'.join(sorted(found | (required & executed)))
            if required <= executed:
                row['status'] = 'validated-complete-contract'
    return rows


def inventory(executed_contracts=()):
    """Apply execution status to an authenticated, independently owned catalogue."""
    return _inventory_execution_status(_inventory_metadata(), executed_contracts)


def write_csv(path, rows, columns=None):
    with Path(path).open("w",encoding="utf-8",newline="") as stream:
        writer = csv.DictWriter(stream,fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def numerical_pass(output):
    """Retain completed comparisons and an explicit failure before other gates."""
    rows = []
    try:
        return _numerical_pass_impl(output, rows)
    except Exception as error:
        present = {id(row) for row in rows}
        rows.extend(row for row in getattr(error, 'partial_rows', ()) if id(row) not in present)
        capabilities = inventory(row['contract'] for row in rows if row['status'] == 'agree')
        columns = ['contract', 'reference', 'family', 'status']
        write_csv(output / 'comparisons.csv', rows, columns=None if rows else columns)
        grid = [{key: row[key] for key in columns} for row in rows]
        failures = list(getattr(error, 'family_failures', ()))
        journal_error = None
        journal = output / 'reference-family-progress.json'
        if journal.exists():
            try:
                previous = json.loads(journal.read_text(encoding='utf-8'))
                known = {item['name'] for item in failures}
                failures.extend(item for item in previous if item['status'] == 'execution-failure'
                                and item['name'] not in known)
            except (OSError, ValueError, KeyError, TypeError) as journal_failure:
                journal_error = type(journal_failure).__name__ + ': ' + str(journal_failure)
        grid.extend({'contract': item['name'], 'reference': item['module'],
                     'family': 'reference-execution', 'status': 'execution-failure'} for item in failures)
        if not getattr(error, 'family_failures', ()):
            grid.append({'contract': 'numerical-pass', 'reference': type(error).__name__,
                         'family': 'reference-execution', 'status': 'execution-failure'})
        grid.extend({'contract': row['capability'], 'reference': 'complete method/option/plot contract',
                     'family': 'coverage', 'status': row['status'] if row['status'] == 'validated-complete-contract'
                     else 'unexecuted-complete-contract'} for row in capabilities)
        write_csv(output / 'outcome-grid.csv', grid, columns)
        write_csv(output / 'capabilities.csv', capabilities,
                  columns=None if capabilities else ['capability', 'kind', 'options', 'status', 'integration_tests'])
        write_json(output / 'numerical-failure.json', {
            'status': 'execution-failure', 'passed': False, 'numerical_gate': False,
            'scientific_completeness_gate': False, 'comparisons_retained': len(rows),
            'error': type(error).__name__ + ': ' + str(error), 'traceback': traceback.format_exc(),
            'family_failures': failures, 'journal_error': journal_error})
        error.partial_rows = rows
        error.partial_capabilities = capabilities
        raise


def _numerical_pass_impl(output, rows):
    import numpy as np
    from reproducibility.comparisons import reference_values,pyflash_values
    expected = load_expected()
    if expected["inputs"] != inputs():
        raise ValueError("Frozen input identity changed; reference fixtures need an explicit reviewed revision.")
    current = reference_values()
    saved = {(row[0],row[1]):row[3] for row in expected["rows"]}
    ours = pyflash_values()
    from reproducibility.bootstrap_reference import FIXTURE as bootstrap_fixture, reference_rows
    from PyFLASH.stats_extra import effect_ci
    bootstrap = json.loads(bootstrap_fixture.read_text(encoding="utf-8"))
    if bootstrap["inputs"] != inputs():
        raise ValueError("Frozen bootstrap inputs changed.")
    for recorded, row in zip(bootstrap["rows"], reference_rows(), strict=True):
        contract = f"bootstrap.{row['kind']}.{row['case']}.{row['confidence']}"
        reference = "analytic-bca/shared-numpy-draws"
        current.append((contract,reference,"analytic/independent-interval-formula",row["expected"]))
        saved[(contract,reference)] = recorded["expected"]
        a,b = inputs()[row["case"]]
        ours[contract] = effect_ci(a,b,eftype=row["kind"],confidence=row["confidence"],
                                   n_resamples=row["resamples"],random_state=row["seed"])
    from reproducibility import extended
    additional = json.loads(extended.FIXTURE.read_text(encoding="utf-8"))
    if additional["inputs"] != extended.inputs():
        raise ValueError("Frozen extended inputs changed.")
    current.extend(extended.reference_values())
    ours.update(extended.pyflash_values())
    saved.update({(row[0], row[1]): row[3] for row in additional["rows"]})
    linear = json.loads(extended.LINEAR_FIXTURE.read_text(encoding="utf-8"))
    if linear["inputs"] != extended.inputs():
        raise ValueError("Frozen analytic linear inputs changed.")
    current.extend(extended.linear_reference_values())
    saved.update({(row[0], row[1]): row[3] for row in linear["rows"]})
    from reproducibility import scalar_contracts
    scalar = json.loads(scalar_contracts.FIXTURE.read_text(encoding='utf-8'))
    if [{key: row[key] for key in ('key', 'capability', 'parameters')} for row in scalar['rows']] != scalar_contracts.cases():
        raise ValueError('Frozen scalar contract inputs changed.')
    for row in scalar['rows']:
        contract = 'scalar.'+row['key']
        reference_name = 'exact-rational-and-50-digit-formulas'
        current.append((contract, reference_name, 'analytic/independent-complete-scalar-fields', scalar_contracts.reference(row)))
        saved[(contract, reference_name)] = row['expected']
        ours[contract] = scalar_contracts.production(row)
    from reproducibility import helper_contracts
    helper = json.loads(helper_contracts.FIXTURE.read_text(encoding='utf-8'))
    if [{key: row[key] for key in ('key', 'capability', 'parameters')} for row in helper['rows']] != helper_contracts.cases():
        raise ValueError('Frozen helper contract inputs changed.')
    for row in helper['rows']:
        contract = 'helper.'+row['key']
        reference_name = 'exact-rational-order-statistics-and-50-digit-formulas'
        current.append((contract, reference_name, 'analytic/independent-complete-helper-fields', helper_contracts.reference(row)))
        saved[(contract, reference_name)] = row['expected']
        ours[contract] = helper_contracts.production(row)
    from reproducibility import comparison_index_contract
    index_fixture = json.loads(comparison_index_contract.FIXTURE.read_text(encoding='utf-8'))
    if [{key:row[key] for key in ('key','capability','parameters','selected')} for row in index_fixture['rows']] != json.loads(json.dumps(comparison_index_contract.cases())):
        raise ValueError('Frozen comparison index inputs changed.')
    for row in index_fixture['rows']:
        contract = row['key']
        reference_name = 'literal-matrix-cell-addresses/sqlite'
        current.append((contract,reference_name,'functional/independent-complete-table-selection',comparison_index_contract.reference(row)))
        saved[(contract,reference_name)] = row['expected']
        ours[contract] = comparison_index_contract.production(row)
    from reproducibility import effect_magnitude_contract
    magnitude_fixture = json.loads(effect_magnitude_contract.FIXTURE.read_text(encoding='utf-8'))
    magnitude_native = effect_magnitude_contract.execute(output/'native-r')
    for row in magnitude_fixture['rows']:
        contract = row['key']
        reference_name = 'literal-decimal-published-magnitude-bands'
        current.append((contract,reference_name,'functional/complete-scalar-interpretation',effect_magnitude_contract.reference(row)))
        saved[(contract,reference_name)] = row['expected']
        ours[contract] = effect_magnitude_contract.production(row)
        if 'reference_kind' in row:
            reference_name = 'effectsize-1.0.0/unchanged-native-r-classifier'
            values = [magnitude_native[row['reference_kind']]['values'][row['native_index']]]
            current.append((contract,reference_name,'published-conventions/complete-scalar-interpretation',values))
            saved[(contract,reference_name)] = row['expected']
    from reproducibility import permutation_contract
    from reproducibility.reference_runtime import values as native_values
    permutation_fixture = json.loads(permutation_contract.FIXTURE.read_text(encoding='utf-8'))
    permutation_native = {row['key']:row for row in permutation_contract.execute(output/'native-r')['rows']}
    from PyFLASH.stats_extra import attainable_p_floor
    for row in permutation_fixture['rows']:
        contract = row['key']
        ours[contract] = permutation_contract.production(row)
        frozen = native_values({'values':row['mathematical_values'],'nonfinite':row['mathematical_nonfinite']})
        reference_name = 'exact-label-enumeration-fractions-and-70-digit-tails'
        current.append((contract,reference_name,'analytic/complete-null-with-common-sampled-draws',permutation_contract.mathematical(row)))
        saved[(contract,reference_name)] = frozen
        reference_name = 'PMCMRplus-pinned-unchanged-native-R-per-arrangement'
        current.append((contract,reference_name,'published-native-inference/independent-enumeration-common-sampled-draws',native_values(permutation_native[contract])))
        saved[(contract,reference_name)] = frozen
        floor_contract = contract+'.floor'
        offset = 5+2*int(frozen[4])
        ours[floor_contract] = [attainable_p_floor(**row['parameters'])]
        reference_name = 'exact-minimum-of-full-independent-null-table'
        current.append((floor_contract,reference_name,'analytic/complete-attainable-floor',
                        [np.min(permutation_contract.mathematical(row)[offset:])]))
        saved[(floor_contract,reference_name)] = [np.min(frozen[offset:])]
    from reproducibility import cosinor_contract
    cosinor_fixture=json.loads(cosinor_contract.FIXTURE.read_text(encoding='utf-8'))
    cosinor_native={row['key']:row for row in cosinor_contract.execute(output/'native-r')['rows']}
    for row in cosinor_fixture['rows']:
        contract=row['key']
        ours[contract]=cosinor_contract.production(row)
        frozen=native_values(row['mathematical'])
        reference_name='70-digit-cosinor-linear-and-profiled-stationary-equations'
        current.append((contract,reference_name,'analytic/complete-fixed-and-free-cosinor',cosinor_contract.mathematical(row)))
        saved[(contract,reference_name)]=frozen
        if row['reference_kind']!='mathematical-only':
            reference_name=('published-cosinor-and-cosinor2-pinned-native-R' if row['reference_kind']=='published-fixed'
                            else 'base-R-independent-profiled-continuous-period-solver')
            current.append((contract,reference_name,'independent-native-R/complete-cosinor',native_values(cosinor_native[contract])))
            saved[(contract,reference_name)]=frozen
    from reproducibility import group_rhythm_contract
    group_fixture=json.loads(group_rhythm_contract.FIXTURE.read_text(encoding='utf-8'))
    group_native={row['key']:row for row in group_rhythm_contract.execute(output/'native-r')['rows']}
    for recorded in group_fixture['rows']:
        contract=recorded['key']
        ours[contract]=group_rhythm_contract.production(recorded)
        frozen=native_values(recorded['mathematical'])
        name='80-digit-nested-harmonic-SVD-and-F-tail'
        current.append((contract,name,'analytic/complete-harmonic-group-test',group_rhythm_contract.mathematical(recorded)))
        saved[(contract,name)]=frozen
        if contract not in group_fixture['native_diagnostics']:
            name='native-R-raw-input-nested-harmonic-ANOVA'
            current.append((contract,name,'independent-native-R/complete-harmonic-group-test',native_values(group_native[contract])))
            saved[(contract,name)]=frozen
    from reproducibility import population_rhythm_contract
    population_fixture=json.loads(population_rhythm_contract.FIXTURE.read_text(encoding='utf-8'))
    population_native={row['key']:row for row in population_rhythm_contract.execute(output/'native-r')['rows']}
    for recorded in population_fixture['rows']:
        contract=recorded['key']
        ours[contract]=population_rhythm_contract.production(recorded)
        frozen=native_values(recorded['mathematical'])
        name='80-digit-subject-harmonics-and-population-covariance'
        current.append((contract,name,'analytic/complete-population-branch-only',population_rhythm_contract.mathematical(recorded)))
        saved[(contract,name)]=frozen
        if contract not in population_fixture['native_diagnostics']:
            name='published-native-R-population-cosinor-and-amplitude-variance'
            current.append((contract,name,'independent-native-R/complete-population-branch-only',native_values(population_native[contract])))
            saved[(contract,name)]=frozen
    from reproducibility import mixed_rhythm_contract
    mixed_fixture=json.loads(mixed_rhythm_contract.FIXTURE.read_text(encoding='utf-8'))
    mixed_native={row['key']:row for row in mixed_rhythm_contract.execute(output/'native-r')['rows']}
    for recorded in mixed_fixture['rows']:
        contract=recorded['key']
        ours[contract]=mixed_rhythm_contract.production(recorded)
        frozen=native_values(recorded['mathematical'])
        name='70-digit-profiled-Gaussian-likelihood-and-observed-information'
        current.append((contract,name,'analytic/complete-mixed-branch-only',mixed_rhythm_contract.mathematical(recorded)))
        saved[(contract,name)]=frozen
        name='native-R-independent-variance-score-and-active-information'
        current.append((contract,name,'independent-native-R/complete-mixed-branch-only',native_values(mixed_native[contract])))
        saved[(contract,name)]=frozen
    from reproducibility import mixed_variance_boundary_contract
    small_fixture=json.loads(mixed_variance_boundary_contract.FIXTURE.read_text(encoding='utf-8'))
    small_native={r['key']:r for r in mixed_variance_boundary_contract.execute(output/'native-r')['rows']}
    for recorded in small_fixture['rows']:
        case=recorded['case'];contract=case['key'];ours[contract]=mixed_variance_boundary_contract.production(case)
        frozen=native_values(recorded['mathematical'])
        name='70-digit-profiled-Gaussian-likelihood-small-positive-variance'
        current.append((contract,name,'analytic/same-independent-likelihood-family-small-variance',mixed_variance_boundary_contract.mathematical(case)))
        saved[(contract,name)]=frozen
        name='native-R-independent-variance-score-small-positive-variance'
        current.append((contract,name,'independent-native-R/same-likelihood-family-small-variance',native_values(small_native[contract])))
        saved[(contract,name)]=frozen
    from reproducibility import minp_contract
    minp_fixture=json.loads(minp_contract.FIXTURE.read_text(encoding='utf-8'))
    minp_native={row['key']:row for row in minp_contract.execute(output/'native-r')['rows']}
    for row in minp_fixture['rows']:
        contract=row['key']
        ours[contract]=minp_contract.production(row)
        frozen=native_values(row['expected'])
        for reference_name,current_values in (
            ('exact-Fraction-event-unions-and-discrete-CDF-boundaries',minp_contract.reference(row)),
            ('base-R-row-predicates-and-IEEE-cutoff-predecessor',native_values(minp_native[row.get('reference_key',contract)]))):
            scope=('selected-calibration-fields' if row.get('selected_fields_only') else 'complete-supplied-null-minP-and-pair-alignment')
            current.append((contract,reference_name,'independent/'+scope,current_values))
            saved[(contract,reference_name)]=frozen
    from reproducibility import value_permutation_contract
    value_fixture=json.loads(value_permutation_contract.FIXTURE.read_text(encoding='utf-8'))
    value_native={row['key']:row for row in value_permutation_contract.execute(output/'native-r')['rows']}
    for row in value_fixture['rows']:
        contract=row['key']
        ours[contract]=value_permutation_contract.production(row)
        frozen=native_values(row['expected'])
        for reference_name,current_values in (
            ('exact-rational-MSE-and-70-digit-two-sided-t-tails',value_permutation_contract.mathematical(row)),
            ('native-R-stats-pairwise-pooled-t-tests',native_values(value_native[contract]))):
            current.append((contract,reference_name,'independent/complete-value-null-common-recorded-arrangements',current_values))
            saved[(contract,reference_name)]=frozen
    from reproducibility import cauchy_contract, decimal_cauchy
    cauchy = json.loads(cauchy_contract.FIXTURE.read_text(encoding='utf-8'))
    if [{key: row[key] for key in ('key', 'capability', 'parameters')} for row in cauchy['rows']] != cauchy_contract.cases():
        raise ValueError('Frozen Cauchy contract inputs changed.')
    for row in cauchy['rows']:
        contract = row['key']
        ours[contract] = cauchy_contract.production(row)
        for reference_name, reference_function in (
            ('90-digit-mpmath-cotangent', cauchy_contract.reference),
            ('95-digit-decimal-series', decimal_cauchy.reference)):
            current.append((contract, reference_name, 'analytic/independent-complete-cauchy-fields', reference_function(row)))
            saved[(contract, reference_name)] = row['expected']
    from reproducibility import native_power
    power = json.loads(native_power.FIXTURE.read_text(encoding='utf-8'))
    native = native_power.execute(output/'native-r')
    if native['wasm_sha256'] != power['wasm_sha256'] or native['R'] != power['R']:
        raise ValueError('Native R runtime identity changed; preserve the fixture and review a versioned revision.')
    if [{key: row[key] for key in ('key', 'capability', 'parameters')} for row in power['rows']] != native_power.cases():
        raise ValueError('Frozen native power inputs changed.')
    for row, recorded in zip(native['rows'], power['rows'], strict=True):
        reference_name = 'R-4.6.0/native-noncentral-t-and-uniroot'
        values = [float('nan') if value is None else value for value in row['values']]
        current.append((row['key'], reference_name, 'independent-R-estimator-and-tail', values))
        saved[(row['key'], reference_name)] = recorded['values']
        ours[row['key']] = native_power.production(row)
    from reproducibility import power_integral
    from reproducibility.reference_reuse import integral_power_values
    for row, values in integral_power_values(output):
        name = 'mpmath-45-digit-Gaussian-gamma-integral-and-beta-quantile'
        current.append((row['key'], name, 'independent-integral-tail-and-root', values))
        saved[(row['key'], name)] = row['expected']
    from reproducibility import proportion_contract
    from reproducibility.reference_runtime import values as native_values
    proportion = json.loads(proportion_contract.FIXTURE.read_text(encoding='utf-8'))
    fresh = proportion_contract.execute(output / 'native-r-proportion')
    if fresh['wasm_sha256'] != proportion['wasm_sha256'] or fresh['R'] != proportion['R']:
        raise ValueError('Native contingency reference runtime changed.')
    if [{key: row[key] for key in ('key','capability','parameters')}
        for row in proportion['rows']] != proportion_contract.cases():
        raise ValueError('Frozen contingency-table inputs changed.')
    for row, recorded in zip(fresh['rows'], proportion['rows'], strict=True):
        key = row['key']
        name = 'R-4.6.0-native-contingency-test'
        current.append((key,name,'independent-R-estimator-and-tail',native_values(row)))
        saved[(key,name)] = native_values(recorded)
        name = 'exact-hypergeometric-and-80-digit-chi-square-tail'
        current.append((key,name,'independent-count-enumeration-and-tail',proportion_contract.mathematical(row)))
        saved[(key,name)] = native_values({'values':recorded['mathematical_values'],
                                         'nonfinite':recorded['mathematical_nonfinite']})
        ours[key] = proportion_contract.production(row)
    from reproducibility import auc_contract
    auc = json.loads(auc_contract.FIXTURE.read_text(encoding='utf-8'))
    fresh = auc_contract.execute(output / 'native-r-auc')
    if fresh['wasm_sha256'] != auc['wasm_sha256'] or fresh['R'] != auc['R']:
        raise ValueError('Native time-course integration reference runtime changed.')
    if [{key: row[key] for key in ('key','capability','parameters')} for row in auc['rows']] != auc_contract.cases():
        raise ValueError('Frozen time-course integration inputs changed.')
    if sha256(Path(auc_contract.__file__)) != auc['reference_code_sha256']:
        raise ValueError('Time-course integration reference code changed.')
    for row, recorded in zip(fresh['rows'], auc['rows'], strict=True):
        key = row['key']
        name = 'R-4.6.0-native-piecewise-quadrature'
        current.append((key,name,'independent-R-quadrature-and-complete-table',native_values(row)))
        saved[(key,name)] = native_values(recorded)
        name = 'exact-rational-piecewise-integral'
        current.append((key,name,'analytic-complete-subject-table',auc_contract.mathematical(row)))
        saved[(key,name)] = recorded['mathematical_values']
        ours[key] = auc_contract.production(row)
    from reproducibility import multiplicity_contract
    multiplicity = json.loads(multiplicity_contract.FIXTURE.read_text(encoding='utf-8'))
    fresh = multiplicity_contract.execute(output/'native-r-multiplicity')
    if fresh['wasm_sha256'] != multiplicity['wasm_sha256'] or fresh['R'] != multiplicity['R']:
        raise ValueError('Native multiplicity reference runtime changed.')
    if [{key:row[key] for key in ('key','capability','parameters','canonical')}
        for row in multiplicity['rows']] != multiplicity_contract.cases():
        raise ValueError('Frozen multiplicity inputs changed.')
    if sha256(Path(multiplicity_contract.__file__)) != multiplicity['reference_code_sha256']:
        raise ValueError('Multiplicity reference code changed.')
    for row,recorded in zip(fresh['rows'],multiplicity['rows'],strict=True):
        key = row['key']
        family = recorded['reference_family']
        name = 'R-4.6.0/'+family
        current.append((key,name,family,native_values(row)))
        saved[(key,name)] = native_values(recorded)
        name = 'exact-rational-closed-testing-and-polynomial-benchmark'
        current.append((key,name,'analytic-complete-adjustment-and-rejection-arrays',multiplicity_contract.reference(row)))
        saved[(key,name)] = recorded['exact_benchmark']
        ours[key] = multiplicity_contract.production(row)
    from reproducibility import fdr_family_contract
    fdr_family = json.loads(fdr_family_contract.FIXTURE.read_text(encoding='utf-8'))
    fresh = fdr_family_contract.execute(output/'native-r-fdr-family')
    if fresh['wasm_sha256'] != fdr_family['wasm_sha256'] or fresh['R'] != fdr_family['R']:
        raise ValueError('Native family-correction reference runtime changed.')
    if [{key:row[key] for key in ('key','capability','parameters','canonical')}
        for row in fdr_family['rows']] != fdr_family_contract.cases():
        raise ValueError('Frozen family-correction inputs changed.')
    if (sha256(Path(fdr_family_contract.__file__)) != fdr_family['reference_code_sha256']
            or sha256(Path(multiplicity_contract.__file__)) != fdr_family['multiplicity_code_sha256']):
        raise ValueError('Family-correction reference definitions changed.')
    for row,recorded in zip(fresh['rows'],fdr_family['rows'],strict=True):
        key = row['key']
        name = 'R-4.6.0/native-family-corrections'
        current.append((key,name,'native-p.adjust-and-published-formulas/complete-table',native_values(row)))
        saved[(key,name)] = native_values(recorded)
        name = 'exact-rational-family-correction-benchmark'
        current.append((key,name,'analytic-complete-labelled-correction-table',fdr_family_contract.mathematical(row)))
        saved[(key,name)] = native_values({'values':recorded['mathematical_values'],
                                         'nonfinite':recorded['mathematical_nonfinite']})
        ours[key] = fdr_family_contract.production(row)
    from reproducibility import circular_contract
    circular = json.loads(circular_contract.FIXTURE.read_text(encoding='utf-8'))
    if sha256(Path(circular_contract.__file__)) != circular['adapter_sha256']:
        raise ValueError('Frozen circular reference adapter changed.')
    if [{k: row[k] for k in ('key', 'capability', 'parameters')} for row in circular['rows']] != circular_contract.cases():
        raise ValueError('Frozen circular reference inputs changed.')
    fresh = circular_contract.execute(output/'native-r-circular')
    if any(fresh[key] != circular['native_runtime'][key] for key in ('wasm_sha256', 'R')):
        raise ValueError('Frozen circular native reference runtime changed.')
    circular_pairs = []
    for row, recorded in zip(fresh['rows'], circular['rows'], strict=True):
        key = row['key']
        period = row['parameters']['period']
        actual = circular_contract.production(row)
        ours[key] = circular_contract.coordinates(actual, period)
        circular_pairs.append({'key': key, 'capability': row['capability'], 'parameters': row['parameters'],
            'fields': circular['fields'], 'production': actual, 'native_R': row,
            'astropy': row['astropy_values'], 'mathematical': circular_contract.mathematical(row)})
        for name, family, answer in (
                ('native-R', 'published-circular-kernel/native-R-descriptives', native_values(row)),
                ('astropy', 'separate-Astropy-circular-implementation', row['astropy_values']),
                ('mathematical', '80-digit-complete-circular-formula', circular_contract.mathematical(row))):
            current.append((key, name, family, circular_contract.coordinates(answer, period)))
            saved[(key, name)] = circular_contract.coordinates(native_values(recorded['references'][name]), period)
    write_json(output/'circular-paired-data.json', {'convention': circular['convention'],
        'nonfinite_representation': 'null means undefined circular output; input infinities are omitted',
        'runtime': circular['native_runtime'], 'rows': circular_pairs})
    from reproducibility import circular_linear_contract
    circular_linear = json.loads(circular_linear_contract.FIXTURE.read_text(encoding='utf-8'))
    if sha256(Path(circular_linear_contract.__file__)) != circular_linear['reference_code_sha256']:
        raise ValueError('Frozen circular-linear reference adapter changed.')
    if [{k:row[k] for k in ('key','capability','parameters')} for row in circular_linear['rows']] != circular_linear_contract.cases():
        raise ValueError('Frozen circular-linear reference inputs changed.')
    from importlib.metadata import distribution
    reference_source = distribution('statsmodels').locate_file('statsmodels/regression/linear_model.py')
    if (version('statsmodels') != circular_linear['versions']['statsmodels']
            or sha256(reference_source) != circular_linear['sources']['statsmodels.regression.linear_model.py']):
        raise ValueError('Pinned circular-linear Statsmodels source changed.')
    fresh = circular_linear_contract.execute(output/'native-r-circular-linear')
    if any(fresh[key] != circular_linear['runtime'][key] for key in ('wasm_sha256','R')):
        raise ValueError('Pinned circular-linear native runtime changed.')
    linear_pairs = []
    for row,recorded in zip(fresh['rows'],circular_linear['rows'],strict=True):
        key = row['key']
        ours[key] = circular_linear_contract.production(row)
        answers = {'native-R':native_values(row),
                   'statsmodels':circular_linear_contract.statsmodels_reference(row),
                   'mathematical':circular_linear_contract.mathematical(row)}
        families = {'native-R':'native-R-lm-estimator-and-F-tail',
                    'statsmodels':'separate-least-squares-estimator/shared-SciPy-tail',
                    'mathematical':'80-digit-least-squares-and-independent-F-tail'}
        for name,answer in answers.items():
            current.append((key,name,families[name],answer))
            saved[(key,name)] = native_values(recorded['references'][name])
        linear_pairs.append({'key':key,'parameters':row['parameters'],
                             'production':ours[key],'references':answers})
    write_json(output/'circular-linear-paired-data.json', {
        'convention':circular_linear['convention'],'fields':circular_linear['fields'],'rows':linear_pairs})
    from reproducibility import watson_williams_contract
    watson = json.loads(watson_williams_contract.FIXTURE.read_text(encoding='utf-8'))
    if sha256(Path(watson_williams_contract.__file__)) != watson['reference_code_sha256']:
        raise ValueError('Frozen Watson-Williams adapter changed.')
    if [{k:row[k] for k in ('key','capability','parameters')} for row in watson['rows']] != watson_williams_contract.cases():
        raise ValueError('Frozen Watson-Williams input identity changed.')
    if version('pycircstat2') != watson['versions']['pycircstat2'] or any(
            sha256(distribution('pycircstat2').locate_file(name)) != identity
            for name,identity in watson['sources'].items()):
        raise ValueError('Pinned PyCircStat2 reference source changed.')
    fresh = watson_williams_contract.execute(output/'native-r-watson-williams')
    if any(fresh[k] != watson['runtime'][k] for k in ('wasm_sha256','R')):
        raise ValueError('Pinned Watson-Williams native runtime changed.')
    watson_pairs,reference_diagnostics = [],[]
    for row,recorded in zip(fresh['rows'],watson['rows'],strict=True):
        key = row['key']
        ours[key] = watson_williams_contract.production(row)
        answers = {'native-R':native_values(row),'mathematical':watson_williams_contract.mathematical(row)}
        accepted = watson_williams_contract.pycircstat_reference(row)
        if recorded['pycircstat2_agrees']:
            answers['pycircstat2'] = accepted
        else:
            # An old explanation is not permission to ignore a new result.
            # Verify the retained artifact, including its infinity sign.
            np.testing.assert_allclose(accepted,native_values(recorded['pycircstat2']),
                                       rtol=RTOL,atol=ATOL,equal_nan=True,err_msg=key)
            reference_diagnostics.append({'contract':key,'reference':'pycircstat2',
                'family':'accepted-package/verified-degenerate-roundoff-artifact',
                'status':'explained-reference-artifact'})
        for name,answer in answers.items():
            family = {'native-R':'native-R-published-within-concentration-formula-and-F-tail',
                      'mathematical':'80-digit-complete-circular-group-benchmark',
                      'pycircstat2':'accepted-CircStat-family/shared-SciPy-tail'}[name]
            current.append((key,name,family,answer))
            saved[(key,name)] = native_values(recorded['pycircstat2'] if name=='pycircstat2'
                                              else recorded['references'][name])
        watson_pairs.append({'key':key,'parameters':row['parameters'],'production':pack_numerical_values(ours[key]),
            'references':{name:pack_numerical_values(answer) for name,answer in answers.items()},
            'raw_pycircstat2':pack_numerical_values(accepted),'pycircstat2_scope':recorded['pycircstat2_scope'],
            'frozen_pooled_convention':recorded['pooled_convention']})
    write_json(output/'watson-williams-paired-data.json',{'fields':watson['fields'],
        'convention':watson['convention'],'rows':watson_pairs,
        'nonfinite_representation':'Each null has a parallel explicit nonfinite classification.'})
    from reproducibility import dispersion_contract, dispersion_decimal
    dispersion = json.loads(dispersion_contract.FIXTURE.read_text(encoding='utf-8'))
    if (sha256(Path(dispersion_contract.__file__)) != dispersion['reference_code_sha256']
            or sha256(Path(dispersion_decimal.__file__)) != dispersion['decimal_code_sha256']):
        raise ValueError('Frozen circular-spread reference code changed.')
    if [{k:row[k] for k in ('key','capability','parameters')} for row in dispersion['rows']] != dispersion_contract.cases():
        raise ValueError('Frozen circular-spread inputs changed.')
    if {name:hashlib.sha256(source.encode()).hexdigest()
            for name,source in dispersion_contract.published_sources().items()} != dispersion['sources']:
        raise ValueError('Pinned published circular-spread source changed.')
    fresh = dispersion_contract.execute(output/'native-r-dispersion')
    if any(fresh[k] != dispersion['runtime'][k] for k in ('wasm_sha256','R')):
        raise ValueError('Pinned circular-spread runtime changed.')
    from reproducibility.reference_runtime import execute_queries
    published = execute_queries([{**row,'code':dispersion_contract.published_query(row)}
        for row in dispersion_contract.cases()],output/'native-r-dispersion',name='published-R-wallraff-kernels')
    spread_pairs = []
    for row,recorded,raw in zip(fresh['rows'],dispersion['rows'],published['rows'],strict=True):
        key = row['key']
        ours[key] = dispersion_contract.production(row)
        answers = {'decimal-native-R':native_values(row),'mathematical':dispersion_contract.mathematical(row)}
        accepted = native_values(raw)
        if recorded['published_R_agrees']:
            answers['published-R'] = accepted
        else:
            np.testing.assert_allclose(accepted,native_values(recorded['published-R']),
                                       rtol=RTOL,atol=ATOL,equal_nan=True,err_msg=key)
            reference_diagnostics.append({'contract':key,'reference':'published-R',
                'family':'published-kernels/precision-sensitive-rank-diagnostic',
                'status':'explained-reference-artifact'})
        for name,answer in answers.items():
            family = {'decimal-native-R':'independent-decimal-Taylor-geometry/native-R-ranks-and-tail',
                      'mathematical':'80-digit-geometry/exact-ranks-and-independent-gamma-tail',
                      'published-R':'unchanged-published-R-kernels/documented-native-mean-port'}[name]
            current.append((key,name,family,answer))
            saved[(key,name)] = native_values(recorded['published-R'] if name=='published-R'
                                              else recorded['references'][name])
        spread_pairs.append({'key':key,'parameters':row['parameters'],
            'production':pack_numerical_values(ours[key]),
            'references':{name:pack_numerical_values(answer) for name,answer in answers.items()},
            'raw_published_R':raw,'published_R_scope':recorded['published_R_scope']})
    write_json(output/'dispersion-paired-data.json',{'convention':dispersion['convention'],'rows':spread_pairs})
    from reproducibility import growth_selected_contract, growth_stationary_reference
    growth = json.loads(growth_selected_contract.FIXTURE.read_text(encoding='utf-8'))
    if sha256(Path(growth_stationary_reference.__file__)) != growth['reference_code_sha256']:
        raise ValueError('Frozen nonlinear growth benchmark source changed.')
    if [{key: row[key] for key in ('key', 'capability', 'parameters')}
            for row in growth['rows']] != growth_selected_contract.cases():
        raise ValueError('Frozen selected growth inputs changed.')
    import mpmath
    if mpmath.__version__ != growth['mpmath']:
        raise ValueError('Selected growth mathematical reference runtime changed.')
    native_growth = execute_queries([{**row, 'code':row['native_R_code']}
        for row in growth['rows']], output/'native-r-selected-growth', name='symbolic-stationarity')
    if any(native_growth[key] != growth['runtime'][key] for key in ('R', 'wasm_sha256')):
        raise ValueError('Selected growth native reference runtime changed.')
    mathematical_answers = {}
    growth_pairs = []
    for recorded, native in zip(growth['rows'], native_growth['rows'], strict=True):
        key = recorded['key']
        assert native['key'] == key
        identity = growth_selected_contract.normalised_identity(recorded)
        if identity != recorded['normalised_input_sha256']:
            raise ValueError('Selected growth normalised input identity changed.')
        if identity not in mathematical_answers:
            mathematical_answers[identity] = growth_stationary_reference.reference(recorded)
        ours[key] = growth_selected_contract.production(recorded)
        answers = {'native-R-symbolic-stationarity': native_values(native),
                   '60-digit-objective-stationarity': mathematical_answers[identity]}
        for name, answer in answers.items():
            family = ('independent-native-R-symbolic-Hessian-and-covariance' if name.startswith('native')
                      else 'independent-mpmath-numerical-derivatives-and-covariance')
            current.append((key, name, family, answer))
            saved[(key, name)] = recorded['native_R_expected'] if name.startswith('native') else recorded['expected']
        growth_pairs.append({'key': key, 'parameters': recorded['parameters'],
            'production': ours[key], 'references': answers, 'normalised_input_sha256': identity})
    write_json(output/'growth-selected-paired-data.json', {'scope':growth['scope'],
        'independence':growth['independence'], 'rows':growth_pairs,
        'native_unpolished_scope':growth['native_unpolished_scope']})
    for contract,reference,family,values in current:
        actual = np.asarray(ours[contract],float)
        reference_array = np.asarray(values,float)
        frozen = np.asarray([np.nan if x is None else x for x in saved[(contract,reference)]],float)
        shapes_equal = actual.shape == reference_array.shape == frozen.shape
        agree = shapes_equal and np.allclose(actual,reference_array,rtol=RTOL,atol=ATOL,equal_nan=True)
        fixture_agree = shapes_equal and np.allclose(reference_array,frozen,rtol=RTOL,atol=ATOL,equal_nan=True)
        if shapes_equal and contract.startswith('group-rhythm.'):
            # Positive tail probabilities must retain relative agreement even
            # below the ordinary absolute tolerance for coefficients/geometry.
            if np.isfinite(reference_array[1]) and reference_array[1]>0:
                agree = agree and bool(np.isclose(actual[1],reference_array[1],rtol=RTOL,atol=0.))
            if np.isfinite(frozen[1]) and frozen[1]>0:
                fixture_agree = fixture_agree and bool(np.isclose(reference_array[1],frozen[1],rtol=RTOL,atol=0.))
        if shapes_equal and contract.startswith(('population-rhythm.', 'mixed-rhythm.', 'mixed-small-variance.')):
            if np.isfinite(reference_array[5]) and reference_array[5]>0:
                agree = agree and bool(np.isclose(actual[5],reference_array[5],rtol=RTOL,atol=0.))
            if np.isfinite(frozen[5]) and frozen[5]>0:
                fixture_agree = fixture_agree and bool(np.isclose(reference_array[5],frozen[5],rtol=RTOL,atol=0.))
        missing_equal = shapes_equal and np.array_equal(np.isnan(actual),np.isnan(reference_array))
        finite = np.isfinite(actual)&np.isfinite(reference_array) if shapes_equal else np.array([],bool)
        error = float(np.max(np.abs(actual[finite]-reference_array[finite]))) if finite.any() else 0.0
        if shapes_equal and not np.array_equal(np.isfinite(actual), np.isfinite(reference_array)):
            error = float("inf")
        rows.append({"contract":contract,"reference":reference,"family":family,
                     "status":"agree" if agree and fixture_agree and missing_equal else "disagree",
                     "shape":str(actual.shape),"missingness_equal":missing_equal,
                     "max_absolute_error":error,"rtol":RTOL,"atol":ATOL,
                     "pyflash_nonfinite":json.dumps({"nan":np.flatnonzero(np.isnan(actual)).tolist(),
                         "positive_infinity":np.flatnonzero(np.isposinf(actual)).tolist(),
                         "negative_infinity":np.flatnonzero(np.isneginf(actual)).tolist()}),
                     "frozen_reference_agrees":fixture_agree,
                     "pyflash_values":json.dumps(json_clean(actual.tolist())),
                     "reference_values":json.dumps(json_clean(reference_array.tolist()))})
    from reproducibility import correction_report_contract
    report_fixture=json.loads(correction_report_contract.FIXTURE.read_text(encoding='utf-8'))
    report_cases=report_fixture['rows']
    report_native={row['key']:row for row in correction_report_contract.execute(output/'native-r')['rows']}
    report_pairs=[]
    for recorded in report_cases:
        actual=correction_report_contract.production(recorded,all_rows=report_cases)
        answers={'exact-mathematical-complete-report':correction_report_contract.reference(recorded,all_rows=report_cases),
                 'native-R-complete-report':correction_report_contract.native_result(report_native[recorded['key']])}
        frozen=correction_report_contract.decoded(recorded['expected'])
        report_pairs.append({'key':recorded['key'],'parameters':recorded['parameters'],
            'production':correction_report_contract.packed(actual),
            'references':{name:correction_report_contract.packed(answer) for name,answer in answers.items()}})
        for name,answer in answers.items():
            errors=[]
            for label,left,right in [('production',actual,answer),('frozen-reference',answer,frozen)]:
                try:correction_report_contract.complete_equal(left,right)
                except AssertionError as exc:errors.append(label+': '+str(exc))
            rows.append({'contract':recorded['key'],'reference':name,
                'family':'independent-complete-correction-report-and-composed-frozen-null-inputs',
                'status':'disagree' if errors else 'agree','shape':'full-labelled-report',
                'missingness_equal':not errors,'max_absolute_error':'','rtol':RTOL,'atol':ATOL,
                'pyflash_nonfinite':'{}','frozen_reference_agrees':not any(error.startswith('frozen-reference:') for error in errors),
                'pyflash_values':json.dumps(correction_report_contract.packed(actual)),
                'reference_values':json.dumps(correction_report_contract.packed(answer))})
            if errors:report_pairs[-1].setdefault('errors',{})[name]=errors
    write_json(output/'correction-report-paired-data.json',{'scope':report_fixture['scope'],'rows':report_pairs})
    # Relational selection has exact labels, counts and types as well as floating
    # measurements. Keep the complete structured result; a numeric projection
    # would conceal dropped rows, changed indices or metadata.
    from reproducibility import iteration_contract
    iteration = json.loads(iteration_contract.FIXTURE.read_text(encoding='utf-8'))
    if sha256(Path(iteration_contract.__file__)) != iteration['reference_code_sha256']:
        raise ValueError('Frozen relational selection adapter changed.')
    if [{k: row[k] for k in ('key','capability','method','state')}
            for row in iteration['rows']] != iteration_contract.cases():
        raise ValueError('Frozen relational selection inputs changed.')
    selection_pairs = []
    for recorded in iteration['rows']:
        actual = iteration_contract.production(recorded)
        answers = {'SQLite-and-literal-metadata': iteration_contract.reference(recorded)}
        if 'exact_arithmetic' in recorded:
            answers['exact-fraction-means'] = iteration_contract.exact_subject_means(recorded)
        selection_pairs.append({**recorded, 'production': actual, 'references': answers})
        for name, answer in answers.items():
            frozen = recorded['exact_arithmetic'] if name == 'exact-fraction-means' else recorded['expected']
            errors = []
            for label, left, right in [('production', actual, answer), ('frozen-reference', answer, frozen)]:
                try:
                    iteration_contract.assert_contract_equal(left, right)
                except AssertionError as error:
                    errors.append(label+': '+str(error))
            rows.append({'contract': recorded['key'], 'reference': name,
                         'family': 'independent-relational-selection-and-functional-metadata',
                         'status': 'disagree' if errors else 'agree', 'shape': 'full-labelled-structure',
                         'missingness_equal': not errors, 'max_absolute_error': '',
                         'rtol': iteration['rtol'], 'atol': iteration['atol'],
                         'pyflash_nonfinite': '{}',
                         'frozen_reference_agrees': not any(e.startswith('frozen-reference:') for e in errors),
                         'pyflash_values': json.dumps(actual), 'reference_values': json.dumps(answer)})
            if errors:
                selection_pairs[-1].setdefault('errors', {})[name] = errors
    from reproducibility import iteration_run_contract
    orchestration = json.loads(iteration_run_contract.FIXTURE.read_text(encoding='utf-8'))
    if (sha256(Path(iteration_run_contract.__file__)) != orchestration['reference_code_sha256']
            or sha256(Path(iteration_contract.__file__)) != orchestration['input_adapter_sha256']):
        raise ValueError('Frozen nested-action reference source changed.')
    if [{k:row[k] for k in ('key','capability','parameters')}
            for row in orchestration['rows']] != iteration_run_contract.cases():
        raise ValueError('Frozen nested-action input settings changed.')
    for recorded in orchestration['rows']:
        actual = iteration_run_contract.production(recorded)
        answer = iteration_run_contract.reference(recorded)
        errors = []
        for label,left,right in [('production',actual,answer),('frozen-reference',answer,recorded['expected'])]:
            try:
                iteration_contract.assert_contract_equal(left,right)
            except AssertionError as error:
                errors.append(label+': '+str(error))
        selection_pairs.append({**recorded,'production':actual,'reference':answer,'errors':errors})
        rows.append({'contract':recorded['key'],'reference':'database-and-independent-event-traces',
            'family':'independent-functional-nested-action-contract',
            'status':'disagree' if errors else 'agree','shape':'full-labelled-event-trace',
            'missingness_equal':not errors,'max_absolute_error':'',
            'rtol':iteration['rtol'],'atol':iteration['atol'],'pyflash_nonfinite':'{}',
            'frozen_reference_agrees':not any(e.startswith('frozen-reference:') for e in errors),
            'pyflash_values':json.dumps(actual),'reference_values':json.dumps(answer)})
    from reproducibility import conditions_contract
    designs = json.loads(conditions_contract.FIXTURE.read_text(encoding='utf-8'))
    if sha256(Path(conditions_contract.__file__)) != designs['reference_code_sha256']:
        raise ValueError('Frozen group-design reference source changed.')
    if [{k:row[k] for k in ('key','capability','capabilities','parameters')}
            for row in designs['rows']] != conditions_contract.cases():
        raise ValueError('Frozen group-design inputs or covered operations changed.')
    design_pairs = []
    for recorded in designs['rows']:
        actual,answer = conditions_contract.production(recorded),conditions_contract.reference(recorded)
        errors = []
        for label,left,right in [('production',actual,answer),('frozen-reference',answer,recorded['expected'])]:
            try:
                iteration_contract.assert_contract_equal(left,right)
            except AssertionError as error:
                errors.append(label+': '+str(error))
        design_pairs.append({**recorded,'production':actual,'reference':answer,'errors':errors})
        rows.append({'contract':recorded['key'],'reference':'literal-design-and-Cartesian-pairs',
            'family':'independent-functional-group-design-contract',
            'status':'disagree' if errors else 'agree','shape':'full-design-metadata-and-comparisons',
            'missingness_equal':not errors,'max_absolute_error':'',
            'rtol':iteration['rtol'],'atol':iteration['atol'],'pyflash_nonfinite':'{}',
            'frozen_reference_agrees':not any(e.startswith('frozen-reference:') for e in errors),
            'pyflash_values':json.dumps(actual),'reference_values':json.dumps(answer)})
    write_json(output/'conditions-paired-data.json',{'rows':design_pairs,'scope':designs['scope']})
    from reproducibility import image_io_contract
    image_fixture=image_io_contract.check_identity();image_pairs=[]
    for case in image_io_contract.cases():
        actual=image_io_contract.production(case);answer=image_io_contract.expected(case)
        agrees=actual==answer
        image_pairs.append({'case':case,'production':actual,'reference':answer,'agrees':agrees})
        rows.append({'contract':case['key'],'reference':'frozen-literal-pixels-native-file-metadata-and-control-events',
            'family':'complete-functional-image-input/no-independent-decoder-kernel-vote',
            'status':'agree' if agrees else 'disagree','shape':'full-pixels-geometry-dtype-and-input-events',
            'missingness_equal':agrees,'max_absolute_error':'','rtol':0.,'atol':0.,
            'pyflash_nonfinite':'{}','frozen_reference_agrees':True,
            'pyflash_values':json.dumps(actual),'reference_values':json.dumps(answer)})
    write_json(output/'image-io-paired-data.json',{'rows':image_pairs,
        'input_manifest':image_fixture['input_manifest'],
        'reference_rule':'Literal encoded samples, native TIFF header metadata and declared resource/event controls; shared decoder and interpolation kernels supply no additional scientific implementation vote.'})
    from reproducibility import bootstrap_options_contract
    bootstrap_fixture=bootstrap_options_contract.check_identity();bootstrap_pairs=[]
    for case in bootstrap_options_contract.cases():
        actual=bootstrap_options_contract.production(case)
        answer=bootstrap_options_contract.independently_recalculate(case)
        expected=bootstrap_options_contract.expected(case)
        unchanged=bootstrap_options_contract.equal(answer,expected)
        agrees=unchanged and bootstrap_options_contract.equal(actual,answer)
        bootstrap_pairs.append({'case':case,'production':actual,'reference':answer,
                                'frozen_reference':expected,'agrees':agrees})
        rows.append({'contract':case['key'],'reference':'independent-pair-variance-and-two-sample-BCa-equations',
            'family':'independent-bootstrap-inference/common-recorded-random-arrangements',
            'status':'agree' if agrees else 'disagree','shape':'both-confidence-endpoints-and-undefinedness',
            'missingness_equal':agrees,'max_absolute_error':'','rtol':RTOL,'atol':ATOL,
            'pyflash_nonfinite':'explicit-null-endpoints','frozen_reference_agrees':unchanged,
            'pyflash_values':json.dumps(actual),'reference_values':json.dumps(answer)})
    write_json(output/'bootstrap-options-paired-data.json',{'rows':bootstrap_pairs,
        'scope':bootstrap_fixture['scope'],'reference_rule':bootstrap_fixture['reference']})
    from reproducibility.validation_registry import validate_all as validate_full_reports
    family_error = None
    try:
        rows.extend(validate_full_reports(output))
    except Exception as error:
        if not hasattr(error, 'partial_rows'):
            raise
        rows.extend(error.partial_rows)
        family_error = error
    write_json(output/'iteration-paired-data.json', {'rows': selection_pairs,
        'identity_rule': iteration['identity_rule'], 'reference_versions': iteration['versions']})
    from reproducibility import cosinor_table_contract
    table_fixture,table_queries=cosinor_table_contract.check_identity()
    native_table=cosinor_table_contract.execute(output/'native-r-cosinor-table')
    table_pairs=[]
    for recorded,native in zip(table_fixture['rows'],native_table['rows'],strict=True):
        case=recorded['case'];key=case['key'];actual=cosinor_table_contract.production(case)
        expected=cosinor_table_contract.expected(case)
        reference_unchanged=cosinor_table_contract.packed(expected)==recorded['expected']
        agrees=reference_unchanged and cosinor_table_contract.equal(actual,expected)
        rows.append({'contract':key,'reference':'identity-checked-existing-independent-rhythm-answers',
            'family':'composed-full-public-table-contract/no-additional-child-reference-family',
            'status':'agree' if agrees else 'disagree','shape':'complete-schema-ordered-rows-identities-and-numerical-fields',
            'missingness_equal':agrees,'max_absolute_error':'','rtol':RTOL,'atol':ATOL,
            'pyflash_nonfinite':'explicit-in-packed-rows','frozen_reference_agrees':reference_unchanged,
            'pyflash_values':json.dumps(cosinor_table_contract.packed(actual)),
            'reference_values':json.dumps(cosinor_table_contract.packed(expected))})
        raw=cosinor_table_contract.preprocessing_answer(case)
        raw_agrees=np.array_equal(np.asarray(native_values(native)),np.asarray(raw),equal_nan=True)
        rows.append({'contract':key+'.raw-inputs','reference':'native-R-independent-raw-time-value-and-identity-preparation',
            'family':'independent-functional-preparation/no-additional-scientific-fit-vote',
            'status':'agree' if raw_agrees else 'disagree','shape':'all-retained-ordered-inputs',
            'missingness_equal':raw_agrees,'max_absolute_error':'','rtol':0.,'atol':0.,
            'pyflash_nonfinite':'{}','frozen_reference_agrees':raw_agrees,
            'pyflash_values':json.dumps(raw),'reference_values':json.dumps(native_values(native))})
        table_pairs.append({'case':case,'production':cosinor_table_contract.packed(actual),
                            'composed_reference':cosinor_table_contract.packed(expected),
                            'independent_native_preprocessing':native,'agrees':agrees and raw_agrees})
    write_json(output/'cosinor-table-paired-data.json',{'scope':table_fixture['scope'],'rows':table_pairs})
    from fractions import Fraction
    import pandas as pd
    from PyFLASH.stats_extra import _mixed_cosinor, cosinor_table
    zero_pairs=[]
    for case in mixed_rhythm_contract.zero_noise_cases():
        residuals=[Fraction(str(y))-(Fraction(2+2*int(a.rsplit(' ',1)[-1]))+Fraction(c)+Fraction(s,2))
                   for t,y,a,c,s in case['parameters']['records']]
        exact_zero=sum(v*v for v in residuals)==0
        native_witness=mixed_native[case['key']]
        native_diverges=bool(np.all(np.diff(native_values(native_witness))>0))
        frame=pd.DataFrame([r[:3] for r in case['parameters']['records']],columns=['_t','_v','animal'])
        error_type=None;error_text=None
        try:_mixed_cosinor(frame,'animal',case['parameters']['period'])
        except ValueError as exc:error_type=type(exc).__name__;error_text=str(exc)
        actual_table=cosinor_table(frame,'_t','_v',animal_col='animal',method='mixed',period=case['parameters']['period'])
        actual={'columns':list(actual_table.columns),'records':actual_table.to_dict(orient='records')}
        record={key:np.nan for key in cosinor_table_contract.FIELDS}
        record.update(group='all',n=len(frame),method='mixed',period=float(case['parameters']['period']),
                      error='mixed cosinor needs positive residual variance for a finite ML fit.')
        expected={'columns':cosinor_table_contract.FIELDS,'records':[record]}
        agrees=exact_zero and native_diverges and error_type=='ValueError' and cosinor_table_contract.equal(actual,expected)
        rows.append({'contract':case['key']+'.no-finite-fit','reference':'exact-zero-noise-likelihood-divergence-and-public-error-contract',
            'family':'exact-rational-design/native-R-likelihood-witness/full-functional-failure-row',
            'status':'agree' if agrees else 'disagree','shape':'complete-public-error-row-and-private-exception',
            'missingness_equal':agrees,'max_absolute_error':'','rtol':RTOL,'atol':ATOL,
            'pyflash_nonfinite':'explicit-in-packed-rows','frozen_reference_agrees':exact_zero and native_diverges,
            'pyflash_values':json.dumps(cosinor_table_contract.packed(actual)),
            'reference_values':json.dumps(cosinor_table_contract.packed(expected))})
        zero_pairs.append({'case':case,'production':cosinor_table_contract.packed(actual),
                           'exact_zero_noise':exact_zero,'native_witness':native_witness,
                           'private_error_type':error_type,'private_error':error_text,'agrees':agrees})
    write_json(output/'mixed-no-finite-fit-paired-data.json',{'rows':zero_pairs})
    from reproducibility.correlation_pipeline_contract import check as check_correlation_pipeline
    rows.extend(check_correlation_pipeline(output / "correlation-pipeline"))
    from reproducibility.adjusted_correlation_pipeline_contract import check as check_adjusted_correlation_pipeline
    rows.extend(check_adjusted_correlation_pipeline(output / "adjusted-correlation-pipeline"))
    from reproducibility.category_counts_contract import check as check_category_counts
    rows.extend(check_category_counts(output / "category-counts"))
    from reproducibility.rhythm_pipeline_contract import validate as check_rhythm_pipeline
    rows.extend(check_rhythm_pipeline(output / "rhythm-pipeline"))
    from reproducibility.iterative_best_fit_contract import validate as check_iterative_best_fit
    rows.extend(check_iterative_best_fit(output / "iterative-best-fit"))
    write_csv(output/"comparisons.csv",rows)
    write_json(output/"paired-data.json",{"inputs":inputs(),"pyflash":ours,"references":current})
    # Exact cell data are retained as CSV; a scientific plot is not required to
    # understand agreement and unexecuted coverage.
    grid = [{k:row[k] for k in ("contract","reference","family","status")} for row in rows]
    grid.extend(reference_diagnostics)
    capabilities = inventory([row["contract"] for row in rows if row["status"] == "agree"])
    grid.extend({"contract":row["capability"],"reference":"complete method/option/plot contract",
                 "family":"coverage", "status":row['status'] if row['status'] == 'validated-complete-contract'
                 else 'unexecuted-complete-contract'} for row in capabilities)
    write_csv(output/"outcome-grid.csv",grid)
    write_csv(output/"capabilities.csv",capabilities)
    if family_error is not None:
        raise family_error
    return rows,capabilities


def _stage_log_excerpt(path,limit=4096):
    with Path(path).open('rb') as stream:
        stream.seek(0,os.SEEK_END)
        size=stream.tell()
        stream.seek(max(0,size-limit))
        text=stream.read().decode('utf-8',errors='replace')
    lines=text.splitlines()[-5:]
    return '\n'.join(line[:400] for line in lines)


def _command_stage(output,name,args,stages,env=None,timeout=None):
    started = time.perf_counter()
    record = {"name":name,"command":args,"status":"running","log":name+".log"}
    stages.append(record)
    write_json(output/"progress.json",stages)
    try:
        with (output/record["log"]).open("w",encoding="utf-8") as stream:
            finished = subprocess.run(args,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,env=env,timeout=timeout)
        record.update(exit_code=finished.returncode,status="pass" if finished.returncode == 0 else "fail")
        log_path=output/record['log']
        if finished.returncode==0:
            record.update(log_sha256=sha256(log_path),log_excerpt=_stage_log_excerpt(log_path),
                          log_retained=False)
            log_path.unlink()
            record['log']=None
        else:
            record['log_retained']=True
    except Exception as exc:
        record.update(status="execution-failure",error=str(exc),log_retained=True)
    record["elapsed_seconds"] = round(time.perf_counter()-started,3)
    write_json(output/"progress.json",stages)
    print(f"{name}: {record['status']} ({record['elapsed_seconds']} s)",flush=True)
    return record


def command_stage(output, name, args, stages, env=None, timeout=None):
    from reproducibility.workflow import command_stage as scoped_command
    return scoped_command(output, name, args, stages, env, timeout)


def development_check(output,stages,env=None):
    """Measure the documented cold command, preserving both correctness and time."""
    record=command_stage(output,'development-loop',python_command()+[
        '-m','pytest','--disable-plugin-autoload','-m','not slow','-q',
        '--durations=10','--junitxml',str(output/'development-tests.xml')],
        stages,env,timeout=150)
    record['budget_seconds']=30.
    record['budget_passed']=record['status']=='pass' and record['elapsed_seconds']<=30.
    if record['status']=='pass' and not record['budget_passed']:
        record['status']='fail'
        record['reason']='Development command exceeded its 30-second budget'
    write_json(output/'progress.json',stages)
    return record


def run_space_requirement(sources, *, full=False, browser_only=False, ui_only=False,
                          real_data=None):
    """Reserve source copies and native outputs before the test scratch gate.

    A retained current run wrote about 1 GiB before testing. Reserve 2 GiB
    for native-reference outputs, in addition to the existing 8 GiB test
    requirement and the exact immutable-source snapshot size. A real-data UI
    trial separately needs max(2 GiB, five times its input size). Browser-only
    and numerical-only commands also execute native references.
    """
    snapshot_bytes = sum(path.stat().st_size for path in sources)
    native_bytes = 100 * 1024**2 if ui_only else 2 * 1024**3
    scratch_bytes = 8 * 1024**3 if full else 0
    real_data_bytes = 0
    if real_data is not None:
        real_data_path = Path(real_data)
        if real_data_path.is_file():
            real_data_bytes = max(2 * 1024**3, real_data_path.stat().st_size * 5)
    finalization_bytes = FINALIZATION_RESERVE_BYTES
    return dict(source_snapshot_bytes=snapshot_bytes,
                reference_output_reserve_bytes=native_bytes,
                test_scratch_reserve_bytes=scratch_bytes,
                real_data_scratch_reserve_bytes=real_data_bytes,
                finalization_reserve_bytes=finalization_bytes,
                total_bytes=snapshot_bytes + native_bytes + scratch_bytes + real_data_bytes + finalization_bytes)


def full_test_environment(output,env):
    """Own test scratch and keep nested replays on this run's source tree."""
    import tempfile
    scratch=Path(tempfile.mkdtemp(prefix='pyflash-test-'))
    if shutil.disk_usage(scratch).free < 8*1024**3:
        shutil.rmtree(scratch)
        write_json(output/'test-scratch.json',{
            'directory':str(scratch),'status':'failed-before-start',
            'directory_absent':True,
            'error':'Test scratch needs an estimated 8 GB free space.'})
        raise RuntimeError('Test scratch needs an estimated 8 GB free space.')
    temporary=scratch/'framework-temporary';temporary.mkdir()
    pytest_scratch=scratch/'pytest'
    pytest_scratch.mkdir()
    write_json(output/'test-scratch.json',{
        'directory':str(scratch),'framework_temporary':str(temporary),
        'pytest_basetemp':str(pytest_scratch),
        'source_root':str(ROOT),
        'purpose':'owned test directories; preserve failure outputs',
        'status':'running','cleanup':'awaiting-test-result'})
    child_env=dict(env,TEMP=str(temporary),TMP=str(temporary),TMPDIR=str(temporary))
    # sys.path changes in check_bootstrap are process-local. Generated replays
    # start Python in temporary directories and otherwise find the editable
    # install, even when this job runs an immutable SOURCE snapshot. Propagate
    # only to the test stage; built-distribution checks own their import paths.
    inherited=child_env.get('PYTHONPATH')
    child_env['PYTHONPATH']=str(ROOT)+(os.pathsep+inherited if inherited else '')
    return pytest_scratch,child_env


def finalize_full_test_scratch(output,scratch,passed):
    """Remove this run's isolated test tree on pass and retain it on failure."""
    import tempfile
    scratch=Path(scratch).resolve()
    owner=scratch.parent
    temp_root=Path(tempfile.gettempdir()).resolve()
    if (scratch.name!='pytest' or not owner.name.startswith('pyflash-test-')
            or owner.parent!=temp_root):
        raise RuntimeError(f'Refusing to clean unowned test scratch: {scratch}')
    receipt_path=Path(output)/'test-scratch.json'
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    if Path(receipt['directory']).resolve()!=owner:
        raise RuntimeError('Test scratch receipt does not match the owned directory.')
    receipt['status']='pass' if passed else 'fail'
    if passed:
        shutil.rmtree(owner)
        receipt.update(cleanup='removed-after-success',directory_absent=not owner.exists())
    else:
        receipt.update(cleanup='preserved-after-failure',directory_absent=False)
    write_json(receipt_path,receipt)
    return receipt


def retire_successful_stage_output(output,relative_path,record,stages):
    """Delete one run-owned stage directory after its final successful consumer."""
    if record.get('status')!='pass':
        return False
    output=Path(output).resolve()
    target=output/relative_path
    resolved=target.resolve()
    try:
        resolved.relative_to(output)
    except ValueError as error:
        raise RuntimeError(f'Refusing to retire output outside this run: {target}') from error
    if target.is_symlink():
        raise RuntimeError(f'Refusing to retire a symlinked stage output: {target}')
    if target.is_dir():
        shutil.rmtree(target)
    cleanups=record.setdefault('scratch_cleanup',[])
    cleanups.append({'path':str(relative_path),'status':'removed',
                     'directory_absent':not target.exists()})
    write_json(output/'progress.json',stages)
    return True


def full_checks(output,stages,port,real_data=None):
    py = python_command(native_metadata=True)
    product_py = python_command()
    env = dict(os.environ,MPLBACKEND="Agg",PYTHONIOENCODING="utf-8")
    development_check(output,stages,env)
    command_stage(output,"demo",py+["demo/run_demo.py","--output",str(output/"demo")],stages,env)
    command_stage(output,"readme-example",py+["-m","reproducibility.verify_example"],stages,env)
    command_stage(output,"fresh-ui-replay",py+["-m","reproducibility.replay","--output",str(output/"replay")],stages,env)
    # Windows path shortening can change exported filenames inside an already
    # long receipt path. Own a short unique scratch directory; retain its exact
    # path so failed outputs remain inspectable beside this receipt.
    scratch,test_env=full_test_environment(output,env)
    try:
        test_record=command_stage(output,"full-tests",py+["-m","reproducibility.run_pytest_shards",
            "--output",str(output),"--basetemp",str(scratch),"--workers","3"],stages,test_env)
    except BaseException:
        finalize_full_test_scratch(output,scratch,False)
        raise
    finalize_full_test_scratch(output,scratch,test_record.get('status')=='pass')
    docs_record=command_stage(output,"docs",py+["-m","mkdocs","build","--strict","--site-dir",str(output/"site")],stages,env)
    retire_successful_stage_output(output,'site',docs_record,stages)
    # Store Python's activation alias can hang inside build-created venvs.
    # uv owns an isolated build environment without changing the interpreter
    # or dependency set used for the scientific checks above.
    uv = shutil.which("uv")
    store_python = os.name == "nt" and "WindowsApps" in str(sys.prefix)
    build = ([uv,"build","--python",f"{sys.version_info.major}.{sys.version_info.minor}",
              "--no-python-downloads",
              "--out-dir",str(output/"dist")] if store_python and uv else
             py+["-m","build","--outdir",str(output/"dist")])
    command_stage(output,"build",build,stages,env)
    command_stage(output,"distribution-reproduction-resources",py+[
        'scripts/check_reproducibility_distribution.py','--dist-dir',str(output/'dist')],stages,env)
    consumer_record=command_stage(output,'built-distribution-consumers',py+[
        'scripts/check_distribution_consumers.py','--dist-dir',str(output/'dist'),
        '--output',str(output/'built-consumers')],stages,env,timeout=1200)
    build_record=next((record for record in stages if record['name']=='build'),{})
    resource_record=next((record for record in stages if record['name']=='distribution-reproduction-resources'),{})
    if all(record.get('status')=='pass' for record in (build_record,resource_record,consumer_record)):
        retire_successful_stage_output(output,'dist',consumer_record,stages)
        retire_successful_stage_output(output,'built-consumers',consumer_record,stages)
    browser_start=len(stages)
    browser_checks(output,stages,port)
    browser_stages=stages[browser_start:]
    if browser_stages and all(record.get('status')=='pass' for record in browser_stages):
        browser_record=browser_stages[-1]
        retire_successful_stage_output(output,'browser-local',browser_record,stages)
    if real_data is not None:
        real_record=command_stage(output,'real-data-interaction-budgets',product_py+['-m','scripts.check_ui_real_data',
            '--source',str(real_data.resolve()),'--output',str(output/'real-data-browser'),
            '--port',str(port)],stages,env)
        retire_successful_stage_output(output,'real-data-browser',real_record,stages)
    repair_record=command_stage(output,'isolated-dependency-repair',product_py+['-m','scripts.check_dependency_repair',
        '--isolated','--output',str(output/'dependency-repair'),'--port',str(port)],stages,env)
    retire_successful_stage_output(output,'dependency-repair',repair_record,stages)


def browser_checks(output,stages,port):
    py = python_command()
    env = dict(os.environ,MPLBACKEND="Agg",PYTHONIOENCODING="utf-8")
    # Each check owns its server/recovery directory; never change the user's
    # active session or ongoing scientific workers.
    browser_env = dict(env,LOCALAPPDATA=str(output/"browser-local"))
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    import socket
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"Browser check port {port} is occupied; refuse to inspect another server.")
    with (output/"server.log").open("w",encoding="utf-8") as server_log:
        # Own the actual server process, not the console launcher's parent.
        # These are the ordinary pyflash-ui launcher's documented settings.
        server = subprocess.Popen(py+["-m","streamlit","run","PyFLASH/ui/app.py",
            f"--server.port={port}","--server.address=127.0.0.1",
            "--server.headless=true","--server.fileWatcherType=none",
            "--runner.postScriptGC=false",
            "--browser.gatherUsageStats=false","--","--demo"],cwd=ROOT,
            stdout=server_log,stderr=subprocess.STDOUT,env=browser_env,creationflags=flags)
        try:
            url = f"http://127.0.0.1:{port}"
            from scripts.ui_readiness import wait_for_server
            readiness = wait_for_server(url,process=server)
            write_json(output/"browser-server.json", {"pid":server.pid,"port":port,
                "address":"127.0.0.1","launch":"ordinary analysis settings; source watcher disabled",
                "workspace":browser_env["LOCALAPPDATA"],"readiness":readiness})
            command_stage(output,"browser",py+["scripts/check_ui_workflow.py","--url",url,"--output",str(output/"browser")],stages,browser_env)
            browser_report = output/"browser"/"browser-checks.json"
            if browser_report.exists():
                measured = json.loads(browser_report.read_text(encoding="utf-8"))
                budgets = {"first_plots_seconds":5.0,"subject_switch_seconds":0.5}
                budget_check = {"name":"interaction-budgets","budgets_seconds":budgets,
                                "measured_seconds":{name:measured.get(name) for name in budgets}}
                budget_check["status"] = "pass" if all(
                    isinstance(measured.get(name),(float,int)) and measured[name] <= budget
                    for name,budget in budgets.items()) else "fail"
                stages.append(budget_check)
                write_json(output/"interaction-budgets.json",budget_check)
                write_json(output/"progress.json",stages)
                print(f"interaction-budgets: {budget_check['status']}",flush=True)
            command_stage(output,'appearance-browser',py+['-m','scripts.check_ui_appearance',
                '--url',url,'--output',str(output/'appearance-browser')],stages,browser_env)
            skill = Path.home()/".claude"/"skills"/"software-development"/"scripts"
            if (skill/"layout-audit.py").exists():
                tool = skill/'layout-audit.py'
                tool_snapshot = output/'tool-sources'/'layout-audit.py'
                tool_snapshot.parent.mkdir()
                shutil.copyfile(tool,tool_snapshot)
                write_json(output/'layout-tool.json', {'path':str(tool), 'sha256':sha256(tool),
                    'snapshot':str(tool_snapshot.relative_to(output))})
                command_stage(output,'layout-text-contract',py+['-m','scripts.check_layout_text',
                    '--audit',str(tool_snapshot),'--output',str(output/'layout-text-contract')],stages,browser_env)
                for size in ("1440x900","800x900"):
                    command_stage(output,"layout-"+size,py+[str(skill/"layout-audit.py"),"measure",url,
                        "--size",size,"--views",'[data-testid="stVegaLiteChart"] svg',"--wait","12000",
                        "--out",str(output/("layout-"+size))],stages,browser_env)
            else:
                stages.append({"name":"layout","status":"unavailable","reason":"skill layout-audit.py not installed"})
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            write_json(output/"browser-server-closed.json", {"pid":server.pid,"returncode":server.returncode})
    command_stage(output,'comparison-browser',py+['-m','scripts.check_ui_comparisons',
        '--output',str(output/'comparison-browser')],stages,browser_env)


def differences(output,rows,capabilities,stages,error=None):
    agreed = sum(r["status"] == "agree" for r in rows)
    failed = [r for r in rows if r["status"] != "agree"]
    gaps = sum(row['status']!='validated-complete-contract' for row in capabilities)
    complete = bool(capabilities) and not gaps and bool(rows) and not failed and not error
    coverage_message = ('The complete scientific-validation gate passes for the declared inventory.' if complete else
        'The complete scientific-validation gate remains failing: matching subroutines do not validate every parent plot, pipeline, or option.')
    lines = ["# Reproducibility differences", "",f"{agreed} executed reference comparisons agree within declared tolerances.",
        coverage_message,"",
        "## Numerical results", "", f"Relative tolerance {RTOL}; absolute tolerance {ATOL}. All paired arrays, shapes, missingness and exact values are in [comparisons.csv](comparisons.csv) and [paired-data.json](paired-data.json)."]
    if not failed:
        lines += ["", "No numerical disagreements within the executed scope."]
    for r in failed:
        lines += ["",f"- **{r['contract']} / {r['reference']}**: maximum absolute error {r['max_absolute_error']}; ours `{r['pyflash_values']}`, reference `{r['reference_values']}`. Cause unresolved: inspect the same frozen method definition before changing production code."]
    lines += ["","## Independence and coverage","",
        "SciPy t-test comparisons are shared-upstream integration checks. Statsmodels uses a separately implemented estimator but a shared SciPy tail; the high-precision mpmath formula uses an independent tail. Pingouin effect estimation and pair-enumeration/formula checks are labelled separately. Initial cosinor integration checks share LAPACK and SciPy distributions. The later complete cosinor contract adds 47 independent 70-digit cases and 40 native-R equivalents, including all uncertainty fields and held-out predictions. Free-period native references use an independent base-R solver, not a published free-period package. Exact/undefined native artifacts are retained without agreement votes.",
        "", "Extended comparisons include high-precision correlation differences/intervals, Cauchy combinations, variance effects, intraclass correlation, independent order-statistic outlier checks, descriptive circular estimates and complete linear-fit predictions/uncertainties. Linear fitting has both Statsmodels and a separate 50-digit scalar solver. Complete circular-statistics comparisons independently check all five fields including Rayleigh significance over 180 input/period/method cases against the published native R kernel, Astropy and an 80-digit benchmark. Complete circular-linear correlation compares all four fields over 48 cases against native R, Statsmodels and independent high-precision least squares. Its two-predictor F probability differs from Pingouin's chi-square definition. These bounded contracts do not certify other circular inference or their parent plots. References, raw circular outputs and identical synthetic settings are retained in the fixtures and source snapshots.",
        "", "Native R 4.6.0 and exact mathematical references also compare complete time-course integration tables, multiplicity adjustment/rejection arrays and labelled within-family correction tables at the requested alpha. Six multiplicity methods use R stats::p.adjust; five use explicitly labelled native R published formulas. Missing family names form one correction family. The GBS probability-0.1 boundary uses verified integer-first algebra; the initial one-ulp native discrepancy is retained in the fixture's recorded prior round. Independent-t power uses both noncentral-t rejection tails and a separately implemented high-precision Gaussian/gamma integral; any reused integral is guarded by exact input, code, settings and runtime identities.",
        "", "Watson-Williams compares every statistic and mean-direction coordinate on 60 cases using native R and an 80-digit benchmark; 54 cases also agree with pinned PyCircStat2. Six degenerate PyCircStat2 results are retained as explained reference artifacts, not agreements: uniform groups amplify floating-point residue and identical constant groups yield negative infinity. The R circular pooled-concentration convention differs from the declared CircStat within-group convention and remains a diagnostic. Squared-distance evaluation removes cancellation for identical means; zero within-group variance preserves group means and the documented infinite/undefined statistic. Prior failures and the immutable fixture retain before/after evidence.",
        "", "Circular dispersion compares every returned field on 51 cases against separately calculated decimal Taylor geometry with native R inference and an 80-digit benchmark. The latter shares mpmath geometry with production but implements ranks and the gamma tail separately; the decimal/native-R reference supplies independent geometry and inference. Forty-one cases also agree with unchanged published R Wallraff/range kernels plus a documented port of their compiled mean calculation. Ten precision-sensitive native rank artifacts remain raw diagnostics, not agreement votes. Original comparisons are retained under .runtime/circular-dispersion-first-round and the immutable fixture. Uniform groups have undefined mean-direction inference. Higher working precision resolves finite input ordering before ranks enter the ordinary-precision inference engine, without relaxing the comparison tolerance. See [dispersion-paired-data.json](dispersion-paired-data.json).",
        "", "Relational selectors and nested actions are functional contracts, not additional statistical algorithms. Full selected rows, column/index labels, dtypes, metadata, iteration positions and every callback/result event compare against independently executed SQLite queries and literal traces; subject averages also have exact-fraction benchmarks. The fixed inputs include missing identifiers and decimal measurements, alternative summaries, nested/repeated levels, label overrides, skipping and hooks. See [iteration-paired-data.json](iteration-paired-data.json). Invalid plans are checked before callbacks or temporary filtering can start.",
        "", "Complete group-design definitions use literal input metadata and independently enumerated Cartesian products/comparison pairs across 54 cases. Every group description, component, factor order, deduplicated level and comparison index is retained in [conditions-paired-data.json](conditions-paired-data.json). These are functional construction contracts, not statistical inference algorithms. Crossed descriptions preserve source designs, compound explanations agree with their components, and ambiguous or unknown control/factor names fail explicitly before a partial design is returned. Their original 20 contract failures and six adversarial failures remain under .runtime/conditions-contract-before.xml and .runtime/condition-design-before.xml.",
        "", "One-based pair extraction has complete literal/SQLite functional references. Scalar magnitude labels have independent decimal boundary cases and unchanged published effectsize 1.0.0 classifiers; these conventions do not certify their parent inference. Rank-null distributions and attainable floors compare all probabilities, pair positions and mode/count metadata on 34 exact/sampled/tied designs against unchanged published PMCMRplus kernels and exact-fraction/70-digit inference. Sampled arrangements share a recorded NumPy random stream; no independent random-generator vote is claimed. All-tied p-values are undefined. Frozen before/after failures remain under .runtime/permutation-contract-before.xml.",
        "", "Supplied minP correction and pair alignment have 84 cases each against exact event unions and native R predicates; sampled runs include the observed arrangement. Value-based Fisher-LSD nulls compare every probability and metadata field over 29 cases against native R pooled t tests and rational/70-digit tails on common recorded arrangements. Complete ladder/audit/verdict and rank/value adjustment wrappers have 577 native-R and exact-mathematical report cases, including reordered/subset comparisons. Every returned key, list, missing value, mode/count field and verdict is retained in correction-report-paired-data.json. Composed independently frozen null inputs do not establish another independent generator or validate sampling assumptions. Exact half-rank residual variance removes a false positive support boundary without rounding p-values or relaxing tolerances. Original reports and domain failures remain retained.",
        "",f"{sum(row['status'] != 'validated-complete-contract' for row in capabilities)} complete callable/plot contracts are not fully independently validated. Every declared signature option and executed partial contract is retained in [capabilities.csv](capabilities.csv); [outcome-grid.csv](outcome-grid.csv) includes unexecuted contracts. Scientific coordinates, annotations, confidence bands and all pipeline stages need their own complete references. The inventory includes public plots lacking a registry alias. No public real-data comparison is claimed.",
        "","## Executed workflow checks",""]
    lines += [f"- {r['name']}: **{r['status']}**"+(f" ({r.get('elapsed_seconds')} s); [{r['log']}]({r['log']})" if r.get("log") else "") for r in stages]
    if error:
        lines += ["", "## Execution failure", "",error]
    lines += ["","## Next investigation","",
        "Extend independent adapters and frozen fixtures to the uncovered full contracts; resolve failing functional/layout stages without loosening the comparison tolerances or declaring unchecked options complete. Preserve this pass alongside later corrections."]
    (output/"DIFFERENCES.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def differences_with_failure_fallback(output, rows, capabilities, stages, error=None):
    """Keep a terminal failure report writable when the full report hits an IO error."""
    try:
        differences(output, rows, capabilities, stages, error)
        return error, False
    except Exception as failure:
        detail = "Final reproducibility report generation failed:\n" + traceback.format_exc()
        combined = (error + "\n\n" if error else "") + detail
        release_finalization_reserve(output)
        grid = Path(output) / "outcome-grid-finalization-fallback.csv"
        try:
            write_failure_outcome_grid(grid, rows, capabilities, str(failure))
        except OSError:
            combined += "\n\nFailure outcome-grid fallback also failed:\n" + traceback.format_exc()
        fallback = Path(output) / "DIFFERENCES.md"
        try:
            fallback.write_text(
                "# Reproducibility differences\n\n"
                "The final report could not be generated. The run is incomplete and "
                "must not be treated as a passing certification. See the "
                "[finalization-fallback grid](outcome-grid-finalization-fallback.csv) "
                "for executed outcomes and pending capability scopes where available.\n\n"
                f"{type(failure).__name__}: {failure}\n",
                encoding="utf-8")
        except OSError as fallback_failure:
            combined += "\n\nFailure-report fallback also failed:\n" + traceback.format_exc()
        return combined, True


def write_failure_outcome_grid(path, rows, capabilities, reason):
    """Write a small per-reference outcome index without copying paired arrays."""
    path = Path(path)
    contract_owner = {}
    for capability in capabilities:
        name = capability.get("capability", "unmapped")
        for contract in str(capability.get("executed_subcontracts", "")).split(";"):
            if contract:
                contract_owner[contract] = name
    grouped = {}
    for row in rows:
        contract = str(row.get("contract", ""))
        capability = contract_owner.get(contract, "unmapped")
        reference = str(row.get("reference", "unavailable"))
        outcome = str(row.get("status", "unavailable"))
        key = (capability, reference, outcome)
        entry = grouped.setdefault(key, {"count": 0, "contracts": set()})
        entry["count"] += 1
        entry["contracts"].add(contract or "unidentified-contract")
    records = []
    for (capability, reference, outcome), entry in sorted(grouped.items()):
        records.append((capability, reference, outcome, entry["count"],
                        ";".join(sorted(entry["contracts"])), reason))
    for capability in capabilities:
        if capability.get("status") != "validated-complete-contract":
            records.append((capability.get("capability", "unmapped"),
                            "required-but-unexecuted", "pending", 0,
                            str(capability.get("executed_subcontracts", "")),
                            "Capability inventory remained incomplete when finalization failed."))
    if not records:
        records.append(("run", "unavailable", "pending", 0, "", reason))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("capability", "reference", "outcome", "comparison_count",
                         "executed_contracts", "reason"))
        writer.writerows(records)


def verification_sources(root=None):
    """One inventory for the starting snapshot and added/deleted-file guard."""
    root = ROOT if root is None else Path(root)
    sources = (list((root/'PyFLASH').rglob('*.py'))+list((root/'tests').glob('*.py'))
        +list((root/'scripts').glob('*.py'))
        +list((root/'reproducibility').glob('*.py'))+list((root/'reproducibility').glob('*.txt'))
        +list((root/'reproducibility').glob('*.mjs'))
        +list((root/'reproducibility').glob('*.json'))
        +list((root/'reproducibility').glob('*.R'))
        +[p for p in (root/'reproducibility/reference-sources').rglob('*') if p.is_file()]
        +list((root/'reproducibility/fixtures').glob('*.json'))
        +[p for p in (root/'reproducibility/fixtures/image-inputs').rglob('*') if p.is_file()]
        +list((root/'docs').rglob('*.md'))
        +list((root/'.github/workflows').glob('*.yml'))
        +[root/name for name in ('pyproject.toml','README.md','MANIFEST.in','mkdocs.yml',
            'architecture.yaml','architecture.lock.json','architecture.schema.json',
            'scripts/contracts-requirements.txt',
            'README_AI.md','pyflash_context.json','demo/run_demo.py','demo/expected_result.json',
            'PyFLASH/README_AI.md','PyFLASH/pyflash_context.json','PyFLASH/ui/data/summary.csv',
            'demo/data/summary.csv','.streamlit/config.toml','reproducibility/package.json',
            'reproducibility/package-lock.json')])
    return sorted(set(sources))


def verification_source_changes(sources,snapshots, *, ui_only=False):
    current = set(verification_sources())
    if ui_only:
        current = {p for p in current if 'reference-sources' not in p.parts and 'fixtures' not in p.parts}
    changed = set(sources)^current
    changed.update(p for p in sources if not p.is_file() or sha256(p)!=sha256(snapshots/p.relative_to(ROOT)))
    return sorted(str(p.relative_to(ROOT)) for p in changed)


def execute_requested_checks(output, stages, *, full=False, browser_only=False, port=8581, real_data=None, ui_only=False):
    """Finish independent workflow gates even if reference execution fails."""
    rows,capabilities,errors = [],[],[]
    if ui_only:
        try:
            browser_checks(output, stages, port)
        except Exception:
            errors.append('Requested interface checks:\n' + traceback.format_exc())
        return rows, capabilities, '\n\n'.join(errors) or None
    try:
        rows,capabilities = numerical_pass(output)
        print(f"Reference comparisons: {len(rows)}; full contracts inventoried: {len(capabilities)}",flush=True)
    except Exception as failure:
        errors.append('Independent reference checks:\n'+traceback.format_exc())
        rows = getattr(failure, 'partial_rows', [])
        capabilities = getattr(failure, 'partial_capabilities', None)
        if capabilities is None:
            capabilities = inventory()
        write_json(output/'numerical-execution-error.json', {'passed':False, 'error':errors[-1],
            'comparisons_retained':len(rows), 'numerical_gate':False, 'scientific_completeness_gate':False})
    try:
        if full:
            full_checks(output,stages,port,real_data)
        elif browser_only:
            browser_checks(output,stages,port)
    except Exception:
        errors.append('Requested workflow checks:\n'+traceback.format_exc())
    return rows,capabilities,'\n\n'.join(errors) or None


def output_manifest(output):
    """Retain readable output hashes and fail closed without losing the receipt."""
    output = Path(output)
    artifacts, errors = [], []
    for path in sorted(output.rglob('*')):
        if path == output / 'run.json' or any(part in path.parts for part in
                ('sources', 'pytest-temp', 'site', 'browser-local')) or path.name == FINALIZATION_RESERVE_NAME:
            continue
        try:
            if path.is_file():
                artifacts.append({'path': str(path.relative_to(output)), 'sha256': sha256(path)})
        except OSError as failure:
            errors.append({'path': str(path.relative_to(output)),
                           'error': type(failure).__name__ + ': ' + str(failure)})
    return artifacts, errors


SOURCE_EVIDENCE_STORE = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'PyFLASH-evidence'


def cleanup_verified_source_snapshot(output,snapshots,changed,source_records=None):
    """Retain and restore-test producing code before retiring duplicate names."""
    output=Path(output).resolve()
    snapshots=Path(snapshots)
    if snapshots.is_symlink():
        raise RuntimeError(f'Refusing to clean an unowned source snapshot: {snapshots}')
    snapshots=snapshots.resolve()
    snapshots.relative_to(output)
    if snapshots.name!='sources':
        raise RuntimeError(f'Refusing to clean an unowned source snapshot: {snapshots}')
    if changed:
        return {'status':'preserved-after-source-change','directory_absent':not snapshots.exists()}
    if snapshots.exists():
        if source_records is None:
            raise RuntimeError('Source manifest is required before deleting a source snapshot')
        from reproducibility.source_retention import preserve_and_retire
        from reproducibility.compact_evidence import ResourcePause, available_ram, RAM_FLOOR
        pauses = 0
        while True:
            try:
                result=preserve_and_retire(output,snapshots,source_records,SOURCE_EVIDENCE_STORE)
                break
            except ResourcePause as error:
                pauses += 1
                write_json(output/'source-cleanup-progress.json', {
                    'status': 'waiting-for-resources', 'pauses': pauses,
                    'reason': str(error), 'minimum_free_ram_bytes': RAM_FLOOR,
                    'available_ram_bytes': available_ram(),
                    'original_sources_preserved_or_checkpointed': True,
                })
                time.sleep(2)
        if pauses:
            write_json(output/'source-cleanup-progress.json', {
                'status': 'completed', 'pauses': pauses, 'cleanup': result,
                'minimum_free_ram_bytes': RAM_FLOOR,
            })
    else:
        result={'status':'already-absent','directory_absent':True}
    progress=output/'snapshot-progress.json'
    progress.unlink(missing_ok=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full",action="store_true",help="Also execute demo, README, all tests, docs, build and actual browser checks.")
    parser.add_argument("--browser-only",action="store_true",help="Run numerical references and real UI checks while investigating a browser failure.")
    parser.add_argument('--ui-only', action='store_true', help='Real UI checks without numerical references; focused evidence only.')
    parser.add_argument('--resume-from', type=Path, help='Reuse verified passing reference-family stages from this previous run.')
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=1, help='Isolated reference-family processes; default serial.')
    parser.add_argument('--snapshot-workers', type=int, choices=range(1, 9), default=4,
                        help='Bounded workers for immutable source snapshots; default 4.')
    parser.add_argument('--fresh-references', action='store_true', help='Force fresh independent native/reference calculations.')
    parser.add_argument("--extended",action="store_true",help="All available reference families are already run by default.")
    parser.add_argument("--require-complete",action="store_true",help="Fail unless every full scientific contract has independent coverage.")
    parser.add_argument("--output",type=Path,default=ROOT/"reproducibility"/"results")
    parser.add_argument("--port",type=int,default=8527)
    parser.add_argument('--real-data',type=Path,help='Also measure cold startup and idle/busy selection on this trusted saved analysis during --full.')
    parser.add_argument("--freeze-reference-fixture",action="store_true")
    parser.add_argument("--reason",default="")
    args = parser.parse_args()
    if args.ui_only and (args.full or args.browser_only or args.require_complete):
        parser.error('--ui-only cannot claim full or complete scientific certification')
    if args.real_data is not None and not args.full:
        parser.error('--real-data requires --full')
    if args.freeze_reference_fixture:
        freeze_references(args.reason)
        return
    output = args.output.resolve()/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True,exist_ok=False)
    free = shutil.disk_usage(output).free
    sources = verification_sources()
    if args.ui_only:
        sources = [p for p in sources if 'reference-sources' not in p.parts and 'fixtures' not in p.parts]
    real_data_error = None
    if args.real_data is not None and not args.real_data.is_file():
        real_data_error = f'Real-data input does not exist or is not a file: {args.real_data}'
    space_requirement = run_space_requirement(sources, full=args.full, browser_only=args.browser_only,
                                              ui_only=args.ui_only, real_data=args.real_data)
    estimated_peak = space_requirement["total_bytes"]
    commit = subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,capture_output=True,text=True).stdout.strip()
    dirty = subprocess.run(["git","status","--porcelain"],cwd=ROOT,capture_output=True,text=True).stdout
    working_tree_lines=dirty.splitlines()
    expected_source_paths=sorted(str(path.relative_to(ROOT)).replace('\\','/') for path in sources)
    snapshots = output/"sources"
    receipt = {"schema_version":1,"commit":commit,"working_tree_dirty":bool(dirty),
               "working_tree_status_entries":len(working_tree_lines),
               "working_tree_status_sha256":hashlib.sha256(dirty.encode('utf-8')).hexdigest(),
               "versions":versions(),"python_command":python_command(),"parameters":vars(args)|{"output":str(args.output)},
               "free_bytes_at_start":free,"estimated_peak_bytes":estimated_peak,
               "space_requirement":space_requirement,
               "snapshot_sources_expected_count":len(expected_source_paths),
               "snapshot_sources_expected_sha256":hashlib.sha256('\n'.join(expected_source_paths).encode('utf-8')).hexdigest(),
               "sources":[],
               "status":"running","passed":False,"owner_pid":os.getpid(),
               "started_at":datetime.now(timezone.utc).isoformat(),
               "numerical_gate":False,"scientific_completeness_gate":False,
               "workflow_gate":False if args.full or args.browser_only else None}
    # Preserve a receipt before the long copy, so a snapshot interruption is visible.
    write_json(output/"run-started.json",receipt)
    write_json(output/"run.json",receipt)
    if real_data_error is not None:
        receipt.update(status="failed-before-start", passed=False, stage="real-data-input-preflight",
                       failed_at=datetime.now(timezone.utc).isoformat(), error=real_data_error,
                       workflow_stages_started=False)
        write_json(output / "run.json", receipt)
        raise SystemExit(1)
    if free < estimated_peak:
        message = f"Needs estimated {estimated_peak} free bytes; only {free} available."
        receipt.update(status="failed-before-start", passed=False, stage="disk-admission",
                       failed_at=datetime.now(timezone.utc).isoformat(), error=message,
                       workflow_stages_started=False)
        write_json(output / "run.json", receipt)
        raise SystemExit(1)
    try:
        create_finalization_reserve(output)
    except OSError as failure:
        receipt.update(status="failed-before-start", passed=False, stage="finalization-reserve",
                       failed_at=datetime.now(timezone.utc).isoformat(),
                       numerical_gate=False, scientific_completeness_gate=False,
                       workflow_gate=False if receipt.get("workflow_gate") is not None else None,
                       error="".join(traceback.format_exception(type(failure), failure, failure.__traceback__)),
                       workflow_stages_started=False)
        write_json(output / "run.json", receipt)
        raise SystemExit(1) from failure
    progress_path = output / "snapshot-progress.json"
    try:
        copied = snapshot_sources(sources, snapshots, workers=args.snapshot_workers,
                                  progress_path=progress_path)
    except Exception as failure:
        release_finalization_reserve(output)
        record_snapshot_failure(output, receipt, failure, stage="source-snapshot",
                                progress_path=progress_path)
        raise SystemExit(1) from failure
    receipt["sources"] = [{"path": str(source.relative_to(ROOT)),
                           "sha256": record["sha256"]}
                          for source, record in zip(sources, copied)]
    write_json(output/"run-started.json",receipt)
    write_json(output/"run.json",receipt)
    rows,capabilities,stages,error = [],[],[],None
    token = None
    request_state = None
    try:
        from reproducibility.workflow import configure, _REQUEST
        request_state = _REQUEST
        token = configure(output, receipt, previous=args.resume_from,
                          workers=args.workers, fresh=args.fresh_references)
        options = dict(full=args.full, browser_only=args.browser_only, port=args.port, real_data=args.real_data)
        if args.ui_only:
            options['ui_only'] = True
        rows,capabilities,error = execute_requested_checks(output,stages,**options)
    except Exception:
        error = traceback.format_exc()
    finally:
        error, finalization_report_failed = differences_with_failure_fallback(
            output, rows, capabilities, stages, error)
        try:
            changed = verification_source_changes(sources,snapshots, ui_only=True) if args.ui_only else verification_source_changes(sources,snapshots)
        except Exception:
            changed = ['source-identity-check-failed']
            error = (error + '\n\n' if error else '') + 'Final source identity check failed:\n' + traceback.format_exc()
        try:
            snapshot_cleanup = cleanup_verified_source_snapshot(output,snapshots,changed,receipt['sources'])
        except Exception:
            snapshot_cleanup = {'status':'cleanup-failed','directory_absent':False}
            error = (error + '\n\n' if error else '') + 'Source snapshot cleanup failed:\n' + traceback.format_exc()
        try:
            artifacts, artifact_errors = output_manifest(output)
        except Exception:
            detail = "Output manifest generation failed:\n" + traceback.format_exc()
            error = (error + "\n\n" if error else "") + detail
            artifacts, artifact_errors = [], [{"path": ".", "error": detail}]
        if artifact_errors:
            detail = 'Output authentication failed:\n' + json.dumps(artifact_errors, indent=2)
            error = (error + '\n\n' if error else '') + detail
            if not finalization_report_failed:
                try:
                    write_json(output / 'output-authentication-errors.json', artifact_errors)
                    differences_path = output / 'DIFFERENCES.md'
                    with differences_path.open('a', encoding='utf-8') as stream:
                        stream.write('\n\n## Output authentication failures\n\n' + detail + '\n')
                    artifacts = [row for row in artifacts if row['path'] != 'DIFFERENCES.md']
                    artifacts.extend({'path': name, 'sha256': sha256(output / name)} for name in
                                     ('DIFFERENCES.md', 'output-authentication-errors.json'))
                except OSError:
                    error += '\n\nCould not write the output-authentication detail files:\n' + traceback.format_exc()
        gaps = sum(row["status"] != "validated-complete-contract" for row in capabilities)
        numerical_gate = bool(rows) and all(r["status"] == "agree" for r in rows) and not (output/"numerical-execution-error.json").exists()
        workflow_requested = args.full or args.browser_only or args.ui_only
        release_finalization_reserve(output)
        receipt.update(comparisons=len(rows),numerical_gate=numerical_gate,
            scientific_completeness_gate=bool(capabilities) and gaps == 0 and numerical_gate and not error and not changed,
            workflow_requested=workflow_requested,
            workflow_gate=(not error and not changed and bool(stages) and all(r["status"] == "pass" for r in stages)) if workflow_requested else None,
            source_changes_during_run=changed, source_snapshot_cleanup=snapshot_cleanup,
            finalization_report_failed=finalization_report_failed,
            coverage_gaps=gaps,stages=stages,error=error,
            output_authentication_errors=artifact_errors, outputs=artifacts)
        receipt.update(status="finished",finished_at=datetime.now(timezone.utc).isoformat(),
            scope='focused-interface' if args.ui_only else 'complete-workflow' if args.full else 'numerical',
            passed=not error and not changed and (numerical_gate or args.ui_only)
                and (not workflow_requested or receipt["workflow_gate"])
                and (not args.require_complete or receipt["scientific_completeness_gate"]))
        write_json(output/"run.json",receipt)
        if request_state is not None and token is not None:
            request_state.reset(token)
        print(f"Receipt: {output / 'run.json'}",flush=True)
    if not receipt["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
