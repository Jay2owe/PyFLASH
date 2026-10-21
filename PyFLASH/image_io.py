"""
Shared image loading helpers for import and plotting.
"""

import importlib
import os
import contextlib

import numpy as np
from PIL import Image, UnidentifiedImageError


TIFF_EXTENSIONS = {".tif", ".tiff"}
RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}
_OPTIONAL_MODULES = {}
_READ_OBSERVERS = []


@contextlib.contextmanager
def observe_image_reads(observer):
    """Observe actual header/pixel inputs, including background image loaders."""
    _READ_OBSERVERS.append(observer)
    try:
        yield
    finally:
        _READ_OBSERVERS.remove(observer)


def _observe_read(path):
    for observer in tuple(_READ_OBSERVERS):
        observer(os.fspath(path))


def get_image_shape(image_path):
    # Reading the image header is cheap; a path-only cache hides replaced images.
    _observe_read(image_path)
    try:
        with Image.open(os.fspath(image_path)) as img:
            width, height = img.size
    except UnidentifiedImageError:
        if os.path.splitext(str(image_path))[1].lower() not in TIFF_EXTENSIONS:
            raise
        tifffile = _optional_import("tifffile")
        if tifffile is None:
            raise
        with tifffile.TiffFile(image_path) as handle:
            page = handle.pages[0]
            height, width = page.imagelength, page.imagewidth
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

    # Preserve the two spatial axes, including one-row/one-column images.

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


def _display_image_mode(mode):
    if mode in {"P", "PA", "RGB", "RGBA", "CMYK", "YCbCr", "LAB", "HSV", "LA"}:
        return "RGBA" if "A" in mode or mode in {"P", "PA"} else "RGB"
    return "L" if mode == "1" else None


def _read_image_with_pil(image_path, preview_max_dim=None):
    with Image.open(os.fspath(image_path)) as img:
        if int(getattr(img, "tag_v2", {}).get(32997, 1)) > 1:
            # Pillow chooses the final strip plane for a single-page volume.
            # Delegate to the metadata-aware decoder instead of changing slices.
            return _read_image_with_tifffile(image_path, preview_max_dim=preview_max_dim)
        max_dim = _normalize_preview_max_dim(preview_max_dim)
        if max_dim is not None:
            try:
                img.draft(None, (max_dim, max_dim))
            except Exception:
                pass
        mode = str(getattr(img, "mode", "") or "")
        display_mode = _display_image_mode(mode)
        img = img.convert(display_mode) if display_mode is not None else img.copy()

        if max_dim is not None:
            img.thumbnail((max_dim, max_dim), Image.Resampling.BILINEAR)
        return _normalize_image_array(img)


def _tiff_display_plane(array, axes):
    """Choose the first non-spatial plane; S denotes samples, never Z depth."""
    array = np.asarray(array)
    if len(axes) != array.ndim or "Y" not in axes or "X" not in axes:
        raise ValueError("TIFF axes do not identify the two spatial dimensions.")
    for index in range(len(axes) - 1, -1, -1):
        if axes[index] not in "YXS":
            array = np.take(array, 0, axis=index)
            axes = axes[:index] + axes[index + 1:]
    if "S" in axes and array.shape[axes.index("S")] == 1:
        index = axes.index("S")
        array = np.take(array, 0, axis=index)
        axes = axes[:index] + axes[index + 1:]
    order = [axes.index("Y"), axes.index("X")]
    if "S" in axes:
        order.append(axes.index("S"))
    return np.transpose(array, order)


def _tiff_display_colours(array, photometric, bits, colormap=None):
    """Interpret photometric metadata after selecting a spatial plane."""
    photometric = int(photometric)
    bits = bits[0] if isinstance(bits, (tuple, list)) else bits
    if photometric == 0 and array.dtype == np.bool_:
        return np.logical_not(array).astype(np.uint8) * 255
    if photometric == 0 and array.dtype == np.uint8:
        return np.asarray((2 ** int(bits) - 1) - array, dtype=array.dtype)
    if photometric == 3:
        if colormap is None:
            raise ValueError("Palette TIFF has no colour map.")
        colours = (np.asarray(colormap) >> 8).astype(np.uint8)
        rgb = np.moveaxis(colours[:, array], 0, -1)
        return np.concatenate([rgb, np.full((*rgb.shape[:2], 1), 255, dtype=np.uint8)], axis=-1)
    if photometric == 5:
        if array.dtype != np.uint8:
            raise ValueError("CMYK TIFF conversion requires 8-bit colour samples.")
        return np.asarray(Image.fromarray(array, mode="CMYK").convert(_display_image_mode("CMYK")))
    if array.dtype == np.bool_:
        return array.astype(np.uint8) * 255
    if photometric == 1 and array.ndim == 3 and array.shape[-1] == 2:
        return np.concatenate([np.repeat(array[..., :1], 3, axis=-1), array[..., 1:]], axis=-1)
    return array


def _read_image_with_tifffile(image_path, preview_max_dim=None):
    tifffile = _optional_import("tifffile")
    if tifffile is None:
        raise ImportError("tifffile is not installed")
    with tifffile.TiffFile(image_path) as handle:
        page = handle.pages[0]
        array = page.asarray()
        array = _tiff_display_plane(array, page.axes)
        array = _tiff_display_colours(array, page.photometric, page.bitspersample, page.colormap)
    return _downsample_image_array(array, preview_max_dim=preview_max_dim)


def _read_image_with_cv2(image_path, preview_max_dim=None):
    cv2 = _optional_import("cv2")
    if cv2 is None:
        raise ImportError("cv2 is not installed")

    if os.path.splitext(str(image_path))[1].lower() in TIFF_EXTENSIONS:
        with Image.open(os.fspath(image_path)) as header:
            if header.mode in {"RGBA", "LA", "PA", "CMYK"}:
                # OpenCV's TIFF codec premultiplies unassociated alpha samples.
                # The existing fallback preserves the declared original pixels.
                return _read_image_with_pil(image_path, preview_max_dim=preview_max_dim)
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
    if os.path.splitext(str(image_path))[1].lower() in TIFF_EXTENSIONS:
        array = imageio.imread(image_path, index=0, page=0)
        metadata = imageio.immeta(image_path, index=0, page=0)
        axes = "ZYX" if metadata.get("ImageDepth", 1) > 1 else "YX"
        if metadata.get("SamplesPerPixel", 1) > 1:
            axes = "S" + axes if metadata.get("PlanarConfiguration") == 2 else axes + "S"
        array = _tiff_display_plane(array, axes)
        array = _tiff_display_colours(array, metadata.get("PhotometricInterpretation", 1),
                                     metadata.get("BitsPerSample", array.dtype.itemsize * 8),
                                     metadata.get("ColorMap"))
    else:
        with Image.open(os.fspath(image_path)) as header:
            display_mode = _display_image_mode(header.mode)
        options = {"mode": display_mode} if display_mode is not None else {}
        array = imageio.imread(image_path, index=0, **options)
    return _downsample_image_array(array, preview_max_dim=preview_max_dim)


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
    """Read display pixels as a contiguous grayscale or RGB/RGBA image.

    Spatial axes remain present for single-row/column images. TIFF metadata
    distinguishes depth from colour samples; stacks/volumes use their first
    spatial plane. Volume TIFFs require the optional metadata-aware decoder.
    Colour modes preserve transparency and use the shared RGB/RGBA conversion.
    A requested decoder falls back to Pillow when unavailable or unable to
    preserve the declared pixels. High-precision grayscale retains stored
    intensities, including photometric-white encodings; byte/bilevel display
    modes interpret their colour metadata. Full-resolution colour reads preserve
    supported floating samples;
    preview sizing uses the selected decoder's recorded resize policy.
    ``fast_loading`` caps an otherwise uncapped preview at 1024 pixels;
    ``preview_max_dim`` supplies an explicit cap, or disables it when nonpositive.
    Invalid settings fail before recording an unread file as an input.
    """
    max_dim = _normalize_preview_max_dim(preview_max_dim)
    backend_order = image_backend_order(image_path, backend=backend)
    _observe_read(image_path)
    if fast_loading and max_dim is None:
        max_dim = 1024

    readers = {
        "tifffile": lambda path: _read_image_with_tifffile(path, preview_max_dim=max_dim),
        "cv2": lambda path: _read_image_with_cv2(path, preview_max_dim=max_dim),
        "imageio": lambda path: _read_image_with_imageio(path, preview_max_dim=max_dim),
        "pil": lambda path: _read_image_with_pil(path, preview_max_dim=max_dim),
    }

    last_error = None
    for backend_name in backend_order:
        try:
            return readers[backend_name](image_path)
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Could not load image: {image_path}") from last_error
