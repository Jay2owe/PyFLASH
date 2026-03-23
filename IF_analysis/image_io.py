"""
Shared image loading helpers for import and plotting.
"""

import importlib
import os
from functools import lru_cache

import numpy as np
from PIL import Image


TIFF_EXTENSIONS = {".tif", ".tiff"}
RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}
_OPTIONAL_MODULES = {}


@lru_cache(maxsize=4096)
def get_image_shape(image_path):
    with Image.open(os.fspath(image_path)) as img:
        width, height = img.size
    return int(height), int(width)


def _optional_import(module_name):
    cached = _OPTIONAL_MODULES.get(module_name, None)
    if module_name in _OPTIONAL_MODULES:
        return cached
    try:
        module = importlib.import_module(module_name)
    except Exception:
        module = None
    _OPTIONAL_MODULES[module_name] = module
    return module


def available_image_backends():
    return {
        "tifffile": _optional_import("tifffile") is not None,
        "cv2": _optional_import("cv2") is not None,
        "imageio": _optional_import("imageio.v3") is not None,
        "pil": True,
    }


def summarize_image_backend(backend="auto"):
    backend_name = "auto" if backend is None else str(backend).strip().lower()
    if backend_name != "auto":
        available = available_image_backends()
        lookup_name = "imageio" if backend_name == "imageio" else backend_name
        if backend_name == "pil":
            return "pil"
        if not available.get(lookup_name, False):
            return f"{backend_name} unavailable -> pil"
        return f"{backend_name} -> pil"

    available = available_image_backends()
    ordered = []
    for name in ["tifffile", "cv2", "imageio", "pil"]:
        if available.get(name, False):
            ordered.append(name)
    return "auto[" + " -> ".join(ordered) + "]"


def resolve_image_worker_count(image_workers=None, task_count=0, preload=True):
    task_count = max(0, int(task_count))
    if (not preload) or task_count <= 1:
        return 1

    if image_workers in [None, "auto"]:
        cpu_count = os.cpu_count() or 1
        return max(1, min(task_count, cpu_count, 8))

    return max(1, min(task_count, int(image_workers)))


def _normalize_image_array(array):
    arr = np.asarray(array)
    if arr.ndim == 0:
        raise ValueError("Image data could not be interpreted as an array")

    arr = np.squeeze(arr)

    # Keep plotting-friendly outputs: grayscale 2D or color HxWx3/4.
    while arr.ndim > 3:
        arr = arr[0]

    if arr.ndim == 3:
        if arr.shape[-1] in {3, 4}:
            return np.ascontiguousarray(arr)
        if arr.shape[0] in {3, 4} and arr.shape[-1] not in {3, 4}:
            return np.ascontiguousarray(np.moveaxis(arr, 0, -1))
        if arr.shape[-1] == 1:
            return np.ascontiguousarray(arr[..., 0])
        return np.ascontiguousarray(arr[0])

    return np.ascontiguousarray(arr)


def _normalize_preview_max_dim(preview_max_dim):
    if preview_max_dim in [None, False]:
        return None
    value = int(preview_max_dim)
    if value <= 0:
        return None
    return value


def _downsample_image_array(array, preview_max_dim=None):
    arr = _normalize_image_array(array)
    max_dim = _normalize_preview_max_dim(preview_max_dim)
    if max_dim is None:
        return arr

    if arr.ndim < 2:
        return arr

    height, width = arr.shape[:2]
    current_max_dim = max(height, width)
    if current_max_dim <= max_dim:
        return arr

    scale = float(max_dim) / float(current_max_dim)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))

    cv2 = _optional_import("cv2")
    if cv2 is not None:
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        resized = cv2.resize(arr, (new_width, new_height), interpolation=interpolation)
        return _normalize_image_array(resized)

    pil_mode = None
    if arr.ndim == 2:
        pil_mode = None
    elif arr.ndim == 3 and arr.shape[2] == 3:
        pil_mode = "RGB"
    elif arr.ndim == 3 and arr.shape[2] == 4:
        pil_mode = "RGBA"

    image = Image.fromarray(arr, mode=pil_mode) if pil_mode is not None else Image.fromarray(arr)
    resized = image.resize((new_width, new_height), Image.Resampling.BILINEAR)
    return _normalize_image_array(np.asarray(resized))


def _read_image_with_pil(image_path, preview_max_dim=None):
    with Image.open(image_path) as img:
        max_dim = _normalize_preview_max_dim(preview_max_dim)
        if max_dim is not None:
            try:
                img.draft(None, (max_dim, max_dim))
            except Exception:
                pass
        mode = str(getattr(img, "mode", "") or "")
        if mode in {"P", "PA", "RGB", "RGBA", "CMYK", "YCbCr", "LAB", "HSV", "LA"}:
            if "A" in mode or mode in {"P", "PA"}:
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")
        elif mode == "1":
            img = img.convert("L")
        else:
            img = img.copy()

        if max_dim is not None:
            img.thumbnail((max_dim, max_dim), Image.Resampling.BILINEAR)
        return _normalize_image_array(img)


def _read_image_with_tifffile(image_path, preview_max_dim=None):
    tifffile = _optional_import("tifffile")
    if tifffile is None:
        raise ImportError("tifffile is not installed")
    return _downsample_image_array(tifffile.imread(image_path), preview_max_dim=preview_max_dim)


def _read_image_with_cv2(image_path, preview_max_dim=None):
    cv2 = _optional_import("cv2")
    if cv2 is None:
        raise ImportError("cv2 is not installed")

    raw = np.fromfile(image_path, dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"OpenCV could not decode {image_path}")

    if image.ndim == 3:
        if image.shape[2] == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
    return _downsample_image_array(image, preview_max_dim=preview_max_dim)


def _read_image_with_imageio(image_path, preview_max_dim=None):
    imageio = _optional_import("imageio.v3")
    if imageio is None:
        raise ImportError("imageio is not installed")
    return _downsample_image_array(imageio.imread(image_path), preview_max_dim=preview_max_dim)


def image_backend_order(image_path, backend="auto"):
    ext = os.path.splitext(str(image_path))[1].lower()
    backend_name = "auto" if backend is None else str(backend).strip().lower()

    if backend_name not in {"auto", "tifffile", "cv2", "imageio", "pil"}:
        raise ValueError(f"Unknown image backend: {backend}")

    if backend_name != "auto":
        if backend_name == "tifffile":
            return ["tifffile", "pil"] if ext in TIFF_EXTENSIONS else ["pil"]
        if backend_name in {"cv2", "imageio"}:
            return [backend_name, "pil"]
        return ["pil"]

    ordered = []
    available = available_image_backends()

    if ext in TIFF_EXTENSIONS and available["tifffile"]:
        ordered.append("tifffile")
    if ext in RASTER_EXTENSIONS and available["cv2"]:
        ordered.append("cv2")
    if available["imageio"]:
        ordered.append("imageio")
    ordered.append("pil")
    return ordered


def read_image_array(image_path, backend="auto", fast_loading=False, preview_max_dim=None):
    max_dim = _normalize_preview_max_dim(preview_max_dim)
    if fast_loading and max_dim is None:
        max_dim = 1024

    readers = {
        "tifffile": lambda path: _read_image_with_tifffile(path, preview_max_dim=max_dim),
        "cv2": lambda path: _read_image_with_cv2(path, preview_max_dim=max_dim),
        "imageio": lambda path: _read_image_with_imageio(path, preview_max_dim=max_dim),
        "pil": lambda path: _read_image_with_pil(path, preview_max_dim=max_dim),
    }

    last_error = None
    for backend_name in image_backend_order(image_path, backend=backend):
        try:
            return readers[backend_name](image_path)
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Could not load image: {image_path}") from last_error
