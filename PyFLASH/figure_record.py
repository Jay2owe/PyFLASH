"""PyFLASH adapter for the package-neutral :mod:`reprofig` schema."""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Mapping, Sequence

from reprofig import (
    DataTable,
    FigureRecord,
    ScientificClaim,
    SourceReference,
    StatisticalSpecification,
    attachment_for,
    build_record,
    source_reference,
    table_from_data,
)
from reprofig.validation import privacy_leaks

_TRANSPARENT_MODULES = {
    "PyFLASH.utils",
    "PyFLASH.provenance",
    "PyFLASH.figure_record",
    "PyFLASH.report",
    "PyFLASH.layout",
    "PyFLASH.aesthetics",
}
_PREFERRED_DATA_NAMES = {
    "plotted_data": 120,
    "plot_data": 115,
    "plot_df": 110,
    "display_df": 105,
    "analysis_data": 100,
    "analysis_df": 100,
    "long_df": 95,
    "table": 90,
    "df": 80,
    "data": 80,
    "subset": 75,
    "sub": 70,
    "scope_df": 70,
    "source_df": 45,
    "summary": 25,
}
_GIT_CONTEXT_CACHE: tuple[str | None, bool | None] | None = None


def _typed_statistical_specifications(
    record: FigureRecord,
) -> list[StatisticalSpecification]:
    """Translate only fully identified PyFLASH comparison tests."""

    if not record.data_tables:
        return []
    table = record.data_tables[0]
    columns = {column.name for column in table.columns}
    if not {"group", "metric", "value"}.issubset(columns):
        return []
    table_id = f"table:{table.sha256}"
    specifications: list[StatisticalSpecification] = []
    for index, statistic in enumerate(record.statistics):
        if statistic.get("kind") != "group_comparison":
            continue
        test = statistic.get("test") or {}
        name = str(test.get("name") or "").casefold()
        algorithm = None
        if "welch" in name and "anova" not in name:
            algorithm = "welch-t/v1"
        elif "student" in name and "t-test" in name:
            algorithm = "student-t/v1"
        elif "mann-whitney" in name or "mann whitney" in name:
            algorithm = "mann-whitney/v1"
        elif "kruskal" in name:
            algorithm = "kruskal-wallis/v1"
        elif "welch" in name and "anova" in name:
            algorithm = "welch-anova/v1"
        elif "one-way" in name and "anova" in name:
            algorithm = "one-way-anova/v1"
        if algorithm is None:
            continue
        group_names = [
            str(group.get("name"))
            for group in statistic.get("groups", [])
            if group.get("name") not in (None, "")
        ]
        if len(group_names) < 2:
            continue
        metric = statistic.get("metric")
        references = [
            {
                "table_id": table_id,
                "column": "value",
                "where": {
                    "group": group,
                    **({"metric": str(metric)} if metric not in (None, "") else {}),
                },
            }
            for group in group_names
        ]
        inputs = (
            {"values_a": references[0], "values_b": references[1]}
            if algorithm in {
                "welch-t/v1", "student-t/v1", "mann-whitney/v1"
            }
            else {"groups": references}
        )
        expected = {
            key: test[source]
            for key, source in (("statistic", "statistic"), ("p_value", "p"))
            if test.get(source) is not None
        }
        if not expected:
            continue
        specifications.append(
            StatisticalSpecification(
                statistic_id=str(
                    statistic.get("test_id") or f"pyflash-test:{index + 1}"
                ),
                algorithm_id=algorithm,
                inputs=inputs,
                parameters={
                    **(
                        {"alternative": "two_sided"}
                        if algorithm
                        in {
                            "welch-t/v1",
                            "student-t/v1",
                            "mann-whitney/v1",
                        }
                        else {}
                    ),
                    **(
                        {"missing_policy": "omit", "confidence_level": 0.95}
                        if algorithm in {"welch-t/v1", "student-t/v1"}
                        else {}
                    ),
                    **(
                        {"method": "auto", "continuity": True}
                        if algorithm == "mann-whitney/v1"
                        else {}
                    ),
                    "producer_implementation": "PyFLASH",
                },
                expected=expected,
                display={"reported_test": test.get("name")},
                tolerances={"*": {"absolute": 1e-10, "relative": 1e-7}},
            )
        )
    return specifications


def _pyflash_version() -> str:
    try:
        return version("PyFLASH-analysis")
    except PackageNotFoundError:
        return "unknown"


def _repo_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[1]
    return candidate if (candidate / ".git").exists() else None


def _git_context() -> tuple[str | None, bool | None]:
    global _GIT_CONTEXT_CACHE
    if _GIT_CONTEXT_CACHE is not None:
        return _GIT_CONTEXT_CACHE
    root = _repo_root()
    if root is None:
        return None, None
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        _GIT_CONTEXT_CACHE = (commit or None, bool(status.strip()))
        return _GIT_CONTEXT_CACHE
    except Exception:
        return None, None


def _statistics_not_applicable(function: Any) -> bool:
    """Return whether PyFLASH classifies this plot as intentionally statistics-free."""

    function_name = str(function or "").rsplit(".", 1)[-1]
    try:
        from PyFLASH.spec import DESCRIBE_EXEMPT, PLOT_REGISTRY

        for short_name, registered in PLOT_REGISTRY.items():
            if str(registered).rsplit(".", 1)[-1] == function_name:
                return short_name in DESCRIBE_EXEMPT
    except Exception:
        pass
    return False


def producer_record(
    described: Mapping[str, Any], context: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    context = dict(context or {})
    commit, dirty = _git_context()
    producer: dict[str, Any] = {
        "package": "PyFLASH-analysis",
        "package_version": _pyflash_version(),
        "python_version": sys.version.split()[0],
        "function": described.get("function"),
        "arguments": described.get("args") or {},
        "request": context.get("request"),
        "run_id": context.get("run_id"),
        "git_commit": commit,
        "git_dirty": dirty,
        "batch": context.get("batch") or described.get("batch"),
        "random_seed": context.get("random_seed"),
    }
    return {key: value for key, value in producer.items() if value is not None}


def _candidate_score(name: str, frame_depth: int, frame_public: bool, frame_value: Any) -> int:
    lowered = name.lower()
    score = _PREFERRED_DATA_NAMES.get(lowered, 40)
    for token, value in _PREFERRED_DATA_NAMES.items():
        if token in lowered:
            score = max(score, value - 5)
    if lowered.startswith(("raw", "all_", "batch_")):
        score -= 45
    if lowered in {"coefficients", "stats", "results", "pvalues", "p_values"}:
        score -= 35
    score += 20 if frame_public else 0
    score -= min(frame_depth, 20)
    try:
        cells = int(frame_value.shape[0]) * int(frame_value.shape[1])
        if cells > 5_000_000:
            score -= 50
        elif cells == 0:
            score -= 100
    except Exception:
        pass
    return score


def capture_stack_tables() -> tuple[list[DataTable], dict[str, Any]]:
    """Capture analysis-ready DataFrames still live in the producing plot call.

    Explicit figure attachments always win. This is a compatibility fallback
    for the many established PyFLASH plot functions that already compute an
    exact filtered DataFrame locally before calling ``save_fig``.
    """

    candidates: list[tuple[int, int, str, str, Any]] = []
    seen: set[int] = set()
    frame = inspect.currentframe()
    depth = 0
    try:
        frame = frame.f_back if frame else None
        while frame is not None:
            module = str(frame.f_globals.get("__name__", ""))
            function = frame.f_code.co_name
            if module.startswith("PyFLASH") and module not in _TRANSPARENT_MODULES:
                public = not function.startswith("_")
                for name, value in frame.f_locals.items():
                    if id(value) in seen:
                        continue
                    cls = type(value).__name__
                    if cls != "DataFrame" or not hasattr(value, "to_csv"):
                        continue
                    seen.add(id(value))
                    score = _candidate_score(name, depth, public, value)
                    candidates.append((score, depth, module, name, value))
            frame = frame.f_back
            depth += 1
    finally:
        del frame
    candidates.sort(key=lambda item: (-item[0], item[1], item[3]))
    if not candidates:
        return [], {"capture_method": "none"}
    chosen = candidates[:3]
    tables: list[DataTable] = []
    used_names: set[str] = set()
    omitted_private_columns: dict[str, list[str]] = {}
    for index, (_score, _depth, module, variable, value) in enumerate(chosen):
        name = "plotted_data" if index == 0 else variable
        if name in used_names:
            name = f"{name}_{index + 1}"
        used_names.add(name)
        safe_columns: list[Any] = []
        private_columns: list[str] = []
        for column in value.columns:
            dtype_kind = getattr(value[column].dtype, "kind", None)
            probe = (
                table_from_data(value.loc[:, [column]], name="privacy_probe")
                if dtype_kind in {"O", "U", "S"}
                else None
            )
            if probe is not None and probe.contents and privacy_leaks(probe.contents):
                private_columns.append(str(column))
            else:
                safe_columns.append(column)
        if private_columns:
            omitted_private_columns[variable] = private_columns
        if not safe_columns:
            continue
        safe_value = value.loc[:, safe_columns]
        tables.append(
            table_from_data(
                safe_value,
                name=name,
                purpose="plot_and_statistics" if index == 0 else "supporting_analysis",
                metadata={
                    "capture_method": "live_stack_dataframe",
                    "source_variable": variable,
                    "source_module": module,
                    "omitted_private_columns": private_columns,
                },
            )
        )
    return tables, {
        "capture_method": "live_stack_dataframe",
        "candidate_count": len(candidates),
        "captured_variables": [item[3] for item in chosen],
        "omitted_private_columns": omitted_private_columns,
    }


def _context_sources(context: Mapping[str, Any] | None) -> list[SourceReference]:
    context = dict(context or {})
    root = context.get("project_root")
    references: list[SourceReference] = []
    for item in context.get("sources") or []:
        if isinstance(item, SourceReference):
            references.append(item)
            continue
        if isinstance(item, Mapping):
            references.append(SourceReference.from_dict(item))
            continue
        try:
            references.append(
                source_reference(
                    item,
                    role="batch_pickle" if str(item).lower().endswith(".pkl") else "source",
                    project_root=root,
                )
            )
        except OSError:
            references.append(
                SourceReference(
                    role="batch_pickle" if str(item).lower().endswith(".pkl") else "source",
                    relative_path=Path(item).name,
                )
            )
    return references


def capture_stack_sources() -> list[SourceReference]:
    """Recover declared experiment/batch inputs from the live plotting stack."""
    declared: list[Any] = []
    visited: set[int] = set()

    def visit(value: Any) -> None:
        if id(value) in visited:
            return
        visited.add(id(value))
        for item in getattr(value, "_provenance_sources", []) or []:
            declared.append(item)
        state_path = getattr(value, "_state_path", None)
        if state_path:
            declared.append({"path": state_path, "role": "batch_pickle"})
        for experiment in getattr(value, "experiment_list", []) or []:
            visit(experiment)

    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame else None
        while frame is not None:
            module = str(frame.f_globals.get("__name__", ""))
            if module.startswith("PyFLASH") and module not in _TRANSPARENT_MODULES:
                for value in frame.f_locals.values():
                    if hasattr(value, "_provenance_sources") or hasattr(value, "experiment_list"):
                        visit(value)
            frame = frame.f_back
    finally:
        del frame

    references: list[SourceReference] = []
    for item in declared:
        if isinstance(item, SourceReference):
            references.append(item)
            continue
        if isinstance(item, Mapping):
            if "sha256" in item or "relative_path" in item:
                references.append(SourceReference.from_dict(item))
                continue
            path = item.get("path")
            role = str(item.get("role", "source"))
            uri = item.get("uri")
            project_root = item.get("project_root")
        else:
            path, role, uri, project_root = item, "source", None, None
        if not path:
            continue
        try:
            references.append(
                source_reference(
                    path,
                    role=role,
                    project_root=project_root or Path(path).parent,
                    uri=uri,
                )
            )
        except OSError:
            references.append(
                SourceReference(role=role, relative_path=Path(path).name, uri=uri)
            )
    deduplicated: list[SourceReference] = []
    seen: set[tuple[Any, ...]] = set()
    for source in references:
        key = (source.role, source.relative_path, source.uri, source.sha256)
        if key not in seen:
            seen.add(key)
            deduplicated.append(source)
    return deduplicated


def build_pyflash_record(
    figure: Any,
    *,
    full_path: str | os.PathLike[str],
    image_name: str,
    described: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
    proof: bool = False,
) -> FigureRecord:
    attached = attachment_for(figure)
    attached_tables = attached.get("data_tables")
    plotted_data = attached.get("plotted_data")
    capture: dict[str, Any] = {"capture_method": "explicit_figure_attachment"}
    if plotted_data is None and not attached_tables:
        attached_tables, capture = capture_stack_tables()
    statistics = list(attached.get("statistics") or described.get("stats") or [])
    analysis = dict(attached.get("analysis") or {})
    analysis.update(capture)
    if "independent_unit" not in analysis:
        units = [record.get("unit") for record in statistics if isinstance(record, Mapping)]
        units = [unit for unit in units if unit]
        if units:
            analysis["independent_unit"] = units[0]
    data_status = attached.get("data_status")
    if data_status is None:
        data_status = "complete" if (plotted_data is not None or attached_tables) else "incomplete"
    statistics_status = attached.get("statistics_status")
    if statistics_status is None:
        statistics_status = "complete" if statistics else "incomplete"
    if described.get("statistics_not_applicable") or _statistics_not_applicable(
        described.get("function")
    ):
        statistics_status = "not_applicable"
    context = dict(context or {})
    reproduction = {
        "script": context.get("reproduction_script"),
        "request": context.get("request"),
    }
    reproduction = {key: value for key, value in reproduction.items() if value is not None}
    all_sources = [*_context_sources(context), *capture_stack_sources()]
    for source in attached.get("sources") or []:
        all_sources.append(
            source if isinstance(source, SourceReference) else SourceReference.from_dict(source)
        )
    deduplicated_sources = []
    source_keys = set()
    for source in all_sources:
        key = (source.role, source.relative_path, source.uri, source.sha256)
        if key not in source_keys:
            source_keys.add(key)
            deduplicated_sources.append(source)
    record = build_record(
        title=image_name,
        original_stem=Path(full_path).stem,
        producer=producer_record(described, context),
        analysis=analysis,
        plotted_data=plotted_data,
        data_tables=attached_tables,
        statistics=statistics,
        sources=deduplicated_sources,
        reproduction=reproduction,
        column_classification=attached.get("column_classification"),
        column_roles=attached.get("column_roles"),
        data_status=data_status,
        statistics_status=statistics_status,
        extensions={"pyflash": {"manifest_schema": 1}},
    )
    if proof:
        specifications = _typed_statistical_specifications(record)
        claim_text = analysis.get("claim") or context.get("request")
        claims = []
        if claim_text:
            claims.append(
                ScientificClaim(
                    text=str(claim_text),
                    statistic_ids=[
                        str(specification.statistic_id)
                        for specification in specifications
                    ],
                ).to_dict()
            )
        record.extensions["proof"] = {
            "statistical_specifications": [
                specification.to_dict() for specification in specifications
            ],
            "claims": claims,
            "opaque_statistics": len(record.statistics) - len(specifications),
        }
    return record
