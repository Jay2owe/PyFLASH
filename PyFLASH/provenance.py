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
from datetime import datetime

MANIFEST_NAME = "figures.json"
SCHEMA_VERSION = 1
MAX_ITEMS = 12
MAX_STRING = 200
MAX_COLUMNS = 20

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

_STATE: dict = {"active": False, "request": None, "batch": None}

# Described once before the write so the copy embedded in the SVG and the copy in
# figures.json can never disagree, then consumed by the post-write observer.
_PENDING: dict = {}


def is_active() -> bool:
    """True when a caller has armed an exact request for the plots it is about to make."""
    return bool(_STATE["active"])


def arm(request=None, *, batch=None) -> None:
    """Record ``request`` as the exact producer of every figure saved until :func:`disarm`."""
    _STATE["active"] = True
    _STATE["request"] = request
    _STATE["batch"] = batch


def disarm() -> None:
    """Stop attributing saved figures to an armed request."""
    _STATE.update({"active": False, "request": None, "batch": None})


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


def record(full_path, *, function=None, args=None, batch=None) -> None:
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
        if function:
            entry["function"] = function
        if args:
            entry["args"] = args
        if batch is not None:
            entry["batch"] = summarise(batch)
        if _STATE["active"] and _STATE["request"] is not None:
            entry["request"] = summarise(_STATE["request"])
        payload["written_by"] = "PyFLASH {} provenance".format(_version())
        payload["figures"][filename] = entry
        _write(manifest_path, payload)
    except Exception:
        pass


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


def embedded_record(svg_path):
    """Read back the producer embedded in an SVG, or ``None``.

    Prefers the embedded copy over ``figures.json`` when a figure has been moved
    or renamed away from the manifest that described it.
    """
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
