"""
Pickle-based save/load for Experiment and Batch objects.
"""

import os
import pickle

import pandas as pd

from IF_analysis.config import check_directory


LEGACY_IMAGE_CACHE_SUFFIX = ".images.pkl"


def _resolve_existing_path(path):
    """Return an existing equivalent path if possible, else the original path."""
    if not isinstance(path, str) or path.strip() == "":
        return path
    if os.path.exists(path):
        return path
    resolved = check_directory(path)
    return resolved if resolved is not None else path


def _normalize_one_object_paths(obj, verbose=False):
    """
    Rebase an object's root path (`filePath`) and regenerate derived save paths.
    Returns True if any path changed.
    """
    changed = False
    old_path = getattr(obj, "filePath", None)
    if isinstance(old_path, str):
        new_path = _resolve_existing_path(old_path)
        if new_path != old_path:
            setattr(obj, "filePath", new_path)
            changed = True
            if verbose:
                print(f"  Rebased {getattr(obj, 'name', type(obj).__name__)}: {old_path} -> {new_path}")

    file_path = getattr(obj, "filePath", None)
    if isinstance(file_path, str) and os.path.exists(file_path) and hasattr(obj, "createSavePaths"):
        try:
            obj.createSavePaths()
        except Exception as exc:
            if verbose:
                print(f"  Warning: could not refresh save paths for {getattr(obj, 'name', type(obj).__name__)} ({exc})")
    return changed


def _normalize_loaded_paths(obj, verbose=False):
    """
    Normalize paths for a loaded Experiment/Batch and nested experiments.
    """
    changed = _normalize_one_object_paths(obj, verbose=verbose)
    if hasattr(obj, "experiment_list"):
        for exp in getattr(obj, "experiment_list", []):
            changed = _normalize_one_object_paths(exp, verbose=verbose) or changed
    return changed


def _strip_legacy_image_arrays(obj):
    """
    Remove legacy inline image arrays from loaded image tables.

    Returns True if any table was changed.
    """
    changed = False
    targets = [obj]
    if hasattr(obj, "experiment_list"):
        targets.extend(list(getattr(obj, "experiment_list", [])))
    for target in targets:
        image_df = getattr(target, "images", None)
        if isinstance(image_df, pd.DataFrame) and "ImageArray" in image_df.columns:
            target.images = image_df.drop(columns=["ImageArray"]).copy()
            changed = True
    return changed


def normalize_paths(obj, verbose=True):
    """
    Public helper: normalize `filePath` + derived save paths in-place.

    Useful if an object is already in memory and not loaded via `load_state`.
    Returns True if any root path was rebased.
    """
    return _normalize_loaded_paths(obj, verbose=verbose)


def save_state(obj, filename=None, verbose=True):
    """
    Save an Experiment or Batch to disk.

    Parameters
    ----------
    obj : Experiment or Batch
    filename : str, optional
        Defaults to '{csv_path}/{name}.pkl'
    """
    if filename is None:
        filename = os.path.join(obj.csv_path, f"{obj.name}.pkl")

    obj._state_path = filename
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'wb') as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)

    legacy_cache = f"{filename}{LEGACY_IMAGE_CACHE_SUFFIX}"
    if os.path.exists(legacy_cache):
        os.remove(legacy_cache)

    size_mb = os.path.getsize(filename) / (1024 * 1024)
    if verbose:
        print(f"Saved '{obj.name}' to {filename} ({size_mb:.1f} MB)")


def load_state(filename, normalize_paths=True, resave_if_rebased=False, verbose=True):
    """
    Load an Experiment or Batch from disk.

    Parameters
    ----------
    filename : str
        Path to .pkl file.
    normalize_paths : bool, default True
        Rebase stale absolute paths (e.g. across different usernames/machines)
        using `check_directory`, then refresh derived save paths.
    resave_if_rebased : bool, default False
        If True, overwrite the pickle after path rebasing.

    Returns
    -------
    Experiment or Batch
    """
    with open(filename, 'rb') as f:
        obj = pickle.load(f)

    obj._state_path = filename
    legacy_arrays_removed = _strip_legacy_image_arrays(obj)
    rebased = False
    if normalize_paths:
        rebased = _normalize_loaded_paths(obj, verbose=verbose)

    legacy_cache = f"{filename}{LEGACY_IMAGE_CACHE_SUFFIX}"
    should_resave = legacy_arrays_removed or os.path.exists(legacy_cache) or (rebased and resave_if_rebased)
    if should_resave:
        save_state(obj, filename, verbose=False)

    if verbose:
        print(f"Loaded '{obj.name}' from {filename}")
        print(f"  Data keys: {list(obj.data.keys())}")
        print(f"  Summary shape: {obj.summary.shape}")
        if hasattr(obj, 'condition_list'):
            print(f"  Conditions: {[c.name for c in obj.condition_list]}")
    return obj
