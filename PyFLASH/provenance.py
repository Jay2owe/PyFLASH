"""Figure provenance: what call produced each saved figure.

Every PyFLASH figure is written through :func:`PyFLASH.utils.save_fig`. This
module registers a ``save_fig`` observer that appends one entry per saved file to
``figures.json`` in that file's own folder, so a figure found months later names
the function and arguments that drew it without anyone having recorded it.

Arguments are summarised, never serialised: a DataFrame is recorded as its shape
and column names, not its contents, so the manifest stays small beside the
figure. Nothing here may raise - it runs inside the save path of every plot.

Exact arguments are used when a caller arms a request with :func:`arm` (the
runner does this). Otherwise the calling PyFLASH frame is inspected, so a plot
made directly in a notebook is recorded too.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime

MANIFEST_NAME = "figures.json"
SCHEMA_VERSION = 1
MAX_ITEMS = 12
MAX_STRING = 200
MAX_COLUMNS = 20
MAX_EMBEDDED_HEADLINES = 12
MAX_RAW_STATS_BYTES = 32 * 1024

# Modules that sit between a plot function and the observer; never the producer.
_TRANSPARENT = {
    "PyFLASH.utils",
    "PyFLASH.provenance",
    "PyFLASH.pipeline_montage",
    "PyFLASH.report",
}

# Plumbing a plot needs but nobody reading the manifest wants: the canvas, and
# where it was written. The analysis arguments are what make a figure redrawable.
_PLUMBING = {
    "figure", "fig", "ax", "axes", "canvas",
    "save_path", "savepath", "path", "out", "outdir", "output_dir",
    "name", "image_name", "filename", "subfolder", "verbose",
}

_STATE: dict = {
    "active": False,
    "request": None,
    "batch": None,
    "run_id": None,
    "reproduction_script": None,
    "sources": [],
    "project_root": None,
    "random_seed": None,
}

# Described once before the write so the copy embedded in the SVG and the copy in
# figures.json can never disagree, then consumed by the post-write observer.
_PENDING: dict = {}


def is_active() -> bool:
    """True when a caller has armed an exact request for the plots it is about to make."""
    return bool(_STATE["active"])


def arm(
    request=None,
    *,
    batch=None,
    run_id=None,
    reproduction_script=None,
    sources=None,
    project_root=None,
    random_seed=None,
) -> None:
    """Record ``request`` as the exact producer of every figure saved until :func:`disarm`."""
    _STATE.update(
        {
            "active": True,
            "request": request,
            "batch": batch,
            "run_id": run_id,
            "reproduction_script": reproduction_script,
            "sources": list(sources or []),
            "project_root": project_root,
            "random_seed": random_seed,
        }
    )


def disarm() -> None:
    """Stop attributing saved figures to an armed request."""
    _STATE.update(
        {
            "active": False,
            "request": None,
            "batch": None,
            "run_id": None,
            "reproduction_script": None,
            "sources": [],
            "project_root": None,
            "random_seed": None,
        }
    )


@contextmanager
def armed(request=None, **kwargs):
    """Scope exact runner context to one plotting run."""
    arm(request, **kwargs)
    try:
        yield
    finally:
        disarm()


_VERSION_CACHE: list = []


def _version() -> str:
    """The installed distribution version; the package exposes no ``__version__``."""
    if _VERSION_CACHE:
        return _VERSION_CACHE[0]
    found = "unknown"
    try:
        import PyFLASH

        found = str(getattr(PyFLASH, "__version__", "") or "")
        if not found:
            from importlib.metadata import version

            found = str(version("PyFLASH-analysis"))
    except Exception:
        found = found or "unknown"
    _VERSION_CACHE.append(found or "unknown")
    return _VERSION_CACHE[0]


def summarise(value):
    """A short, JSON-safe description of one argument. Never the data itself."""
    try:
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value if abs(value) < 1e15 else repr(value)
        if isinstance(value, str):
            return value if len(value) <= MAX_STRING else value[:MAX_STRING] + "..."
        cls = type(value).__name__
        shape = getattr(value, "shape", None)
        if cls == "DataFrame":
            text = "DataFrame({}x{})".format(shape[0], shape[1]) if shape else "DataFrame"
            columns = list(getattr(value, "columns", []))
            if columns and len(columns) <= MAX_COLUMNS:
                return "{} columns={}".format(text, [str(column) for column in columns])
            return text
        if cls == "Series":
            return "Series({})".format(shape[0]) if shape else "Series"
        if cls == "ndarray":
            if shape:
                return "ndarray({}, {})".format(tuple(shape), getattr(value, "dtype", "?"))
            return "ndarray"
        if cls in {"Figure", "Axes", "AxesSubplot"}:
            return cls
        if isinstance(value, dict):
            keys = list(value)[:MAX_ITEMS]
            out = {str(key): summarise(value[key]) for key in keys}
            if len(value) > MAX_ITEMS:
                out["..."] = "{} more".format(len(value) - MAX_ITEMS)
            return out
        if isinstance(value, (list, tuple, set, frozenset)):
            items = list(value)
            if len(items) > MAX_ITEMS:
                return "{}[{}]".format(cls, len(items))
            return [summarise(item) for item in items]
        if hasattr(value, "__fspath__"):
            return str(value)
        return cls
    except Exception:
        return "?"


def describe_caller():
    """The outermost public PyFLASH frame below the save call, with its arguments.

    Outermost, because ``plot_marker_counts`` calling ``_draw_panel`` calling
    ``save_fig`` should be recorded as the plot the user asked for, not the
    private helper that happened to hold the pen.
    """
    best = None
    try:
        frame = sys._getframe(1)
        while frame is not None:
            module = frame.f_globals.get("__name__", "")
            function = frame.f_code.co_name
            if (
                module.startswith("PyFLASH")
                and module not in _TRANSPARENT
                and not function.startswith("_")
            ):
                code = frame.f_code
                count = code.co_argcount + code.co_kwonlyargcount
                args = {}
                for variable in code.co_varnames[:count]:
                    if variable in ("self", "cls") or variable in _PLUMBING:
                        continue
                    if variable not in frame.f_locals:
                        continue
                    value = frame.f_locals[variable]
                    # A parameter left at its default is not a choice anyone made;
                    # recording every unset option would bury the ones that were.
                    if value is None:
                        continue
                    args[variable] = summarise(value)
                best = {"function": "{}.{}".format(module, function), "args": args}
            frame = frame.f_back
    except Exception:
        pass
    return best


def _sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write(manifest_path, payload) -> None:
    """Replace the manifest atomically so a crash mid-write cannot truncate it."""
    directory = os.path.dirname(manifest_path)
    handle, temporary = tempfile.mkstemp(dir=directory, prefix=".figures.", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, manifest_path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def read_manifest(directory):
    """The ``figures.json`` mapping for one folder, or an empty dict."""
    path = os.path.join(str(directory), MANIFEST_NAME)
    try:
        with open(path, encoding="utf-8") as stream:
            payload = json.load(stream)
        figures = payload.get("figures")
        return figures if isinstance(figures, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def record_for(figure_path):
    """The recorded producer of one figure, or ``None``."""
    directory, filename = os.path.split(str(figure_path))
    return read_manifest(directory).get(filename)


def record(
    full_path,
    *,
    function=None,
    args=None,
    batch=None,
    stats=None,
    figure_record=None,
) -> None:
    """Add or replace this figure's entry in the ``figures.json`` beside it."""
    try:
        full_path = str(full_path)
        if not os.path.isfile(full_path):
            return
        directory, filename = os.path.split(full_path)
        manifest_path = os.path.join(directory, MANIFEST_NAME)
        payload = {"schema_version": SCHEMA_VERSION, "figures": {}}
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, encoding="utf-8") as stream:
                    existing = json.load(stream)
                if isinstance(existing, dict) and isinstance(existing.get("figures"), dict):
                    payload = existing
                    payload.setdefault("schema_version", SCHEMA_VERSION)
            except (OSError, ValueError):
                pass
        entry = {
            "saved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "pyflash_version": _version(),
            "sha256": _sha256(full_path),
        }
        public_record = bool(
            figure_record is not None
            and figure_record.distribution_profile != "master"
        )
        if function:
            entry["function"] = function
        if args and not public_record:
            entry["args"] = args
        if batch is not None and not public_record:
            entry["batch"] = summarise(batch)
        if stats:
            entry["stats"] = headlines(stats)
        if figure_record is not None:
            entry.update(
                {
                    "figure_id": figure_record.figure_id,
                    "figure_schema": figure_record.schema,
                    "distribution_profile": figure_record.distribution_profile,
                    "created_at": figure_record.created_at,
                    "data_status": figure_record.data_status,
                    "statistics_status": figure_record.statistics_status,
                    "data_tables": [
                        {
                            "name": table.name,
                            "rows": table.row_count,
                            "columns": table.column_count,
                            "sha256": table.sha256,
                        }
                        for table in figure_record.data_tables
                    ],
                    "source_fingerprints": [
                        source.sha256 for source in figure_record.sources if source.sha256
                    ],
                }
            )
        if (
            not public_record
            and _STATE["active"]
            and _STATE["request"] is not None
        ):
            entry["request"] = summarise(_STATE["request"])
        payload["written_by"] = "PyFLASH {} provenance".format(_version())
        payload["figures"][filename] = entry
        _write(manifest_path, payload)
    except Exception:
        pass


def _stats_enabled() -> bool:
    try:
        from PyFLASH.config import Config

        return bool(getattr(Config, "RECORD_STATS", True))
    except Exception:
        return True


def _arm_stats_collector() -> None:
    """Arm the statistics collector unless something else already did.

    The runner arms it per run and takes the records at the end. Arming here
    when it has not been armed is what lets a plot made in a notebook record its
    own numbers; taking them is never done here, so a run still gets its copy.
    """
    if not _stats_enabled():
        return
    try:
        from PyFLASH import report

        if not report.is_active():
            report.start()
            _STATE["armed_here"] = True
    except Exception:
        pass


def _trim_raw_stats(records):
    """Drop the raw test output from any record too large to sit beside a figure."""
    trimmed = []
    for record in records:
        try:
            if "raw_stats" not in record:
                trimmed.append(record)
                continue
            if len(json.dumps(record, ensure_ascii=False)) <= MAX_RAW_STATS_BYTES:
                trimmed.append(record)
                continue
            reduced = dict(record)
            reduced.pop("raw_stats", None)
            reduced["raw_stats_omitted"] = "exceeded {} bytes".format(MAX_RAW_STATS_BYTES)
            trimmed.append(reduced)
        except Exception:
            trimmed.append(record)
    return trimmed


def take_stats():
    """This figure's statistics: those from plot calls that are still running.

    Records emitted by a call that finished without saving anything belong to no
    figure, so they are dropped rather than inherited by whichever figure saves
    next.
    """
    if not _stats_enabled():
        return []
    try:
        from PyFLASH import report

        watermark = int(_STATE.get("stats_mark") or 0)
        total = report.count()
        if total < watermark:
            watermark = 0
        records = report.records_since(watermark, alive=report.live_frame_ids())
        _STATE["stats_mark"] = total
        # The complete structured results belong in the compressed master SVG.
        # Only the rebuildable folder manifest is summarized; never truncate
        # canonical statistics here.
        return records
    except Exception:
        return []


def headlines(records):
    """One readable line per result, which is what the on-figure panel prints."""
    lines = []
    for record in records or []:
        try:
            text = record.get("headline")
            if text:
                lines.append(str(text))
        except Exception:
            continue
    if len(lines) > MAX_EMBEDDED_HEADLINES:
        extra = len(lines) - MAX_EMBEDDED_HEADLINES
        lines = lines[:MAX_EMBEDDED_HEADLINES] + ["{} more in {}".format(extra, MANIFEST_NAME)]
    return lines


def describe_save(full_path, image_name=None):
    """Describe the call now, for embedding, and hold it for the manifest.

    Called before the write so the description can go inside the file; the
    post-write observer reuses the same description rather than walking the
    stack a second time and risking a different answer.
    """
    called = describe_caller() or {}
    batch = _STATE["batch"]
    if batch is None:
        batch = (called.get("args") or {}).get("batch")
    described = {
        "function": called.get("function"),
        "args": called.get("args"),
        "batch": batch,
        "stats": take_stats(),
    }
    try:
        _PENDING[os.path.normcase(str(full_path))] = described
    except Exception:
        pass
    return described


def _without_column_names(args):
    """Drop ``columns=[...]`` from a summarised argument.

    Column names are data. ``figures.json`` sits in the analysis folder beside
    the data itself, so listing them there reveals nothing new - but a figure
    travels, and its text is searchable, so the embedded copy carries the shape
    only. It also keeps the file's text to what the picture shows: a test
    asserting a column was not plotted should not be defeated by metadata.
    """
    if not isinstance(args, dict):
        return args
    trimmed = {}
    for key, value in args.items():
        if isinstance(value, str) and " columns=[" in value:
            value = value.split(" columns=[", 1)[0]
        trimmed[key] = value
    return trimmed


def svg_metadata(full_path, image_name=None):
    """``savefig(metadata=...)`` for an SVG, carrying the producer inside the file.

    The SVG writer accepts only Dublin Core keys, so the producer travels as
    JSON in ``Description``. Embedded rather than only listed in
    ``figures.json`` because a manifest is keyed by filename: renaming a figure,
    or copying it into a slide folder, loses the entry but not the file.

    The figure's own hash is deliberately absent - a file cannot contain its own
    hash. That stays in the manifest.
    """
    try:
        described = describe_save(full_path, image_name)
        payload = {key: value for key, value in described.items() if value}
        if payload.get("args"):
            payload["args"] = _without_column_names(payload["args"])
        if payload.get("stats"):
            payload["stats"] = headlines(payload["stats"])
        if _STATE["active"] and _STATE["request"] is not None:
            payload["request"] = summarise(_STATE["request"])
        payload["pyflash_version"] = _version()
        metadata = {"Creator": "PyFLASH {} provenance".format(_version())}
        if image_name:
            metadata["Title"] = str(image_name)
        metadata["Description"] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return metadata
    except Exception:
        return {}


def _armed_context():
    return {
        "request": _STATE.get("request"),
        "batch": _STATE.get("batch"),
        "run_id": _STATE.get("run_id"),
        "reproduction_script": _STATE.get("reproduction_script"),
        "sources": list(_STATE.get("sources") or []),
        "project_root": _STATE.get("project_root"),
        "random_seed": _STATE.get("random_seed"),
    }


def prepare_figure_record(
    figure,
    full_path,
    image_name=None,
    *,
    figure_profile="master",
    safe_columns=None,
    public_sources=None,
    proof=False,
):
    """Build one complete generic record before any figure carrier is written.

    The returned record is always the master.  ReproFig derives the requested
    distribution profile separately for every carrier, preserving one figure
    identity across SVG, PDF and raster renders.
    """
    from reprofig import derive_profile
    from PyFLASH.figure_record import build_pyflash_record

    described = describe_save(full_path, image_name)
    complete = build_pyflash_record(
        figure,
        full_path=full_path,
        image_name=image_name or os.path.splitext(os.path.basename(str(full_path)))[0],
        described=described,
        context=_armed_context(),
        proof=proof,
    )
    selected = derive_profile(
        complete,
        figure_profile,
        safe_columns=safe_columns,
        public_sources=public_sources,
    )
    if figure_profile == "minimal_public":
        selected._companion_record = derive_profile(
            complete,
            "public",
            safe_columns=safe_columns,
            public_sources=public_sources,
        )
    described["figure_record"] = selected
    try:
        _PENDING[os.path.normcase(str(full_path))] = described
    except Exception:
        pass

    summary = {
        "schema": selected.schema,
        "figure_id": selected.figure_id,
        "distribution_profile": selected.distribution_profile,
        "function": selected.producer.get("function"),
        "pyflash_version": selected.producer.get("package_version"),
        "stats": headlines(selected.statistics),
    }
    if selected.title:
        summary["title"] = selected.title
    metadata = {
        "Creator": "PyFLASH {} + ReproFig provenance".format(_version()),
        "Description": json.dumps(summary, ensure_ascii=False, sort_keys=True),
    }
    if image_name:
        metadata["Title"] = str(image_name)
    return complete, metadata, described


def stage_prepared_save(full_path, described, figure_record) -> None:
    """Give a second carrier the same producer/statistics entry as the first."""

    pending = dict(described or {})
    pending["figure_record"] = figure_record
    _PENDING[os.path.normcase(str(full_path))] = pending


def stamp_figure_artifact(
    full_path,
    figure,
    image_name=None,
    *,
    figure_profile=None,
    safe_columns=None,
    public_sources=None,
    write_companion_csv=None,
):
    """Embed a PyFLASH record into an already-rendered supported carrier.

    Altair and Plotly own their rendering APIs, so they cannot call
    ``reprofig.save_figure``.  They leave through this companion choke point:
    the same data/statistics capture, privacy profiles, validation and manifest
    entry as Matplotlib outputs, followed by generic ReproFig embedding.
    """

    from PyFLASH.config import Config
    from PyFLASH.figure_record import build_pyflash_record
    from reprofig import (
        derive_profile,
        embed_file,
        validate_artifact,
        write_companion_tables,
    )

    path = str(full_path)
    name = image_name or os.path.splitext(os.path.basename(path))[0]
    profile = figure_profile or getattr(Config, "FIGURE_PROFILE", "master")
    if safe_columns is None:
        safe_columns = getattr(Config, "FIGURE_SAFE_COLUMNS", None)
    if public_sources is None:
        public_sources = getattr(Config, "FIGURE_PUBLIC_SOURCES", None)
    if write_companion_csv is None:
        write_companion_csv = bool(getattr(Config, "FIGURE_COMPANION_CSV", False))

    described = describe_save(path, name)
    master = build_pyflash_record(
        figure,
        full_path=path,
        image_name=name,
        described=described,
        context=_armed_context(),
    )
    final = derive_profile(
        master,
        profile,
        safe_columns=safe_columns,
        public_sources=public_sources,
    )
    embed_file(path, final)
    validation = validate_artifact(
        path,
        expected_profile=profile,
        public_safety=profile != "master",
    )
    if not validation.valid:
        raise ValueError(
            "; ".join(
                issue.message
                for issue in validation.issues
                if issue.severity == "error"
            )
        )
    if write_companion_csv:
        companion_profile = "public" if profile == "minimal_public" else profile
        companion = derive_profile(
            master,
            companion_profile,
            safe_columns=safe_columns,
            public_sources=public_sources,
        )
        write_companion_tables(companion, path)
    _PENDING.pop(os.path.normcase(path), None)
    record(
        path,
        function=described.get("function"),
        args=described.get("args"),
        batch=described.get("batch"),
        stats=described.get("stats"),
        figure_record=final,
    )
    return final


def embed_figure_record(full_path, figure_record) -> None:
    """Embed the prepared record after PyFLASH finishes normalizing the SVG."""
    from reprofig import embed_record

    embed_record(full_path, figure_record)


def write_companion_csvs(full_path, figure_record):
    """Write optional disposable CSV conveniences beside a master SVG."""
    from reprofig import write_companion_tables

    companion = getattr(figure_record, "_companion_record", figure_record)
    return write_companion_tables(companion, full_path)


def embedded_record(svg_path):
    """Read back the producer embedded in an SVG, or ``None``.

    Prefers the embedded copy over ``figures.json`` when a figure has been moved
    or renamed away from the manifest that described it.
    """
    try:
        from reprofig import extract_record

        complete = extract_record(svg_path)
        payload = complete.to_dict()
        producer = complete.producer
        # Compatibility aliases for callers of the original Dublin Core API.
        payload.setdefault("function", producer.get("function"))
        payload.setdefault("args", _without_column_names(producer.get("arguments") or {}))
        payload.setdefault("batch", producer.get("batch"))
        payload.setdefault("request", producer.get("request"))
        payload.setdefault("pyflash_version", producer.get("package_version"))
        payload.setdefault("stats", headlines(complete.statistics))
        return payload
    except Exception:
        pass
    try:
        with open(str(svg_path), encoding="utf-8") as stream:
            head = stream.read(65536)
        start = head.find("<dc:description>")
        if start < 0:
            return None
        start += len("<dc:description>")
        end = head.find("</dc:description>", start)
        if end < 0:
            return None
        text = head[start:end]
        for entity, literal in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")):
            text = text.replace(entity, literal)
        record = json.loads(text)
        return record if isinstance(record, dict) else None
    except (OSError, ValueError):
        return None


def _observer(full_path, image_name, subfolder, key) -> None:
    """Post-write ``save_fig`` observer: describe the call that produced this file.

    Registered with ``utils.register_fig_saved_observer`` rather than the
    pre-write hook, because the manifest records the written file's hash.
    """
    try:
        described = _PENDING.pop(os.path.normcase(str(full_path)), None)
        if described is None:
            described = describe_save(full_path, image_name)
            _PENDING.pop(os.path.normcase(str(full_path)), None)
        record(
            full_path,
            function=described.get("function"),
            args=described.get("args"),
            batch=described.get("batch"),
            stats=described.get("stats"),
            figure_record=described.get("figure_record"),
        )
    except Exception:
        pass


def enable() -> None:
    """Register the observer. Idempotent; called when PyFLASH is imported."""
    try:
        from PyFLASH import utils

        utils.register_fig_saved_observer(_observer)
    except Exception:
        pass


def disable() -> None:
    """Stop recording provenance for saved figures."""
    try:
        from PyFLASH import utils

        utils.unregister_fig_saved_observer(_observer)
    except Exception:
        pass
