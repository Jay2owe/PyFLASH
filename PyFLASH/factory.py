"""
Factory function for creating batches with minimal boilerplate.
"""

import os

from PyFLASH.config import Config, check_directory
from PyFLASH.experiment import Experiment
from PyFLASH.batch import Batch
from PyFLASH.serialization import save_state, load_state
from PyFLASH.utils import ProgressTracker, generate_aliases


def _copy_representative_metadata(dst_obj, src_obj):
    from PyFLASH.plotting import (
        _normalize_representative_image_table,
        _representative_marker_list,
    )

    copied = 0
    src_table = _normalize_representative_image_table(
        getattr(src_obj, "representative_images", None)
    )
    if not src_table.empty:
        dst_obj.representative_images = src_table.copy()
        copied = int(len(src_table))

    src_markers = _representative_marker_list(
        markers=getattr(src_obj, "representative_image_markers", None)
    )
    if len(src_markers) > 0:
        dst_obj.representative_image_markers = src_markers
    return copied


def _copy_saved_image_edit_metadata(dst_obj, src_obj):
    from PyFLASH.plotting import _normalize_saved_image_edit_table

    src_table = _normalize_saved_image_edit_table(
        getattr(src_obj, "saved_image_edits", None)
    )
    if src_table.empty:
        return 0
    dst_obj.saved_image_edits = src_table.copy()
    return int(len(src_table))


def _carry_over_representatives(new_batch, previous_batch):
    from PyFLASH.plotting import _normalize_representative_image_table

    copied_total = _copy_representative_metadata(new_batch, previous_batch)
    copied_experiments = 0
    batch_rep_table = _normalize_representative_image_table(
        getattr(previous_batch, "representative_images", None)
    )

    previous_by_name = {
        str(getattr(exp, "name", "")).strip(): exp
        for exp in getattr(previous_batch, "experiment_list", [])
    }
    for exp in getattr(new_batch, "experiment_list", []):
        exp_name = str(getattr(exp, "name", "")).strip()
        prev_exp = previous_by_name.get(exp_name)
        copied_rows = 0
        if prev_exp is not None:
            copied_rows = _copy_representative_metadata(exp, prev_exp)
        if copied_rows == 0 and not batch_rep_table.empty and "Experiment" in batch_rep_table.columns:
            exp_table = _normalize_representative_image_table(
                batch_rep_table[batch_rep_table["Experiment"].astype(str) == exp_name].copy()
            )
            if not exp_table.empty:
                exp.representative_images = exp_table
                copied_rows = int(len(exp_table))
        if copied_rows > 0:
            copied_experiments += 1

    return copied_total, copied_experiments


def _carry_over_saved_image_edits(new_batch, previous_batch):
    copied_total = _copy_saved_image_edit_metadata(new_batch, previous_batch)
    copied_experiments = 0

    previous_by_name = {
        str(getattr(exp, "name", "")).strip(): exp
        for exp in getattr(previous_batch, "experiment_list", [])
    }
    for exp in getattr(new_batch, "experiment_list", []):
        exp_name = str(getattr(exp, "name", "")).strip()
        prev_exp = previous_by_name.get(exp_name)
        if prev_exp is None:
            continue
        copied_rows = _copy_saved_image_edit_metadata(exp, prev_exp)
        if copied_rows > 0:
            copied_experiments += 1

    return copied_total, copied_experiments


def create_batch(name, conditions, batch_path, experiments=None,
                 threshold=None, pickle_path=None, rerun=False,
                 import_images=True, reimport_images=False,
                 progress=True):
    """
    Create (or load) a Batch from a compact specification.

    Parameters
    ----------
    name : str
        Batch name (also used as pickle filename).
    conditions : conditionList
        The experimental conditions.
    batch_path : str
        Output path for the batch. Also used as experiment discovery
        root if ``experiments`` is None.
    experiments : dict, list, str, or None
        - dict {name: path}: create Experiment objects from paths
        - list: pass pre-built Experiment objects
        - str: path to parent folder for auto-discovery
        - None: auto-discover from batch_path
    threshold : int, optional
        Colocalisation threshold. Defaults to Config.THRESHOLD.
    pickle_path : str, optional
        Directory for pickle files. If set, will load from cache
        if available (unless rerun=True).
    rerun : bool
        Force reprocessing even if a pickle exists.
    import_images : bool
        If True, import experiment image paths/metadata during
        processing. Set False to skip image discovery during batch
        creation and scan on demand later.
    reimport_images : bool
        Only applies when ``rerun=True``. If True, force image path
        import during rerun even when ``import_images`` is False.
    progress : bool
        If True, show progress/timing for batch creation and nested
        experiment processing.

    Returns
    -------
    Batch
    """
    threshold = threshold or Config.THRESHOLD
    tracker = ProgressTracker(
        f"create_batch:{name}",
        total=5,
        unit="step",
        enabled=progress,
    )

    tracker.start_item("Check Pickle Cache")
    if pickle_path is not None:
        pkl_file = os.path.join(pickle_path, f"{name}.pkl")
        if os.path.exists(pkl_file) and not rerun:
            tracker.finish_item("Check Pickle Cache", detail=f"Loaded existing pickle: {pkl_file}")
            tracker.close("Returned cached batch")
            return load_state(pkl_file, verbose=False)
    tracker.finish_item("Check Pickle Cache", detail="Rerun requested" if rerun else "No cached batch returned")

    tracker.start_item("Prepare Experiments")
    if experiments is None:
        experiments = batch_path

    if isinstance(experiments, dict):
        exp_list = [
            Experiment(exp_name, check_directory(exp_path) or exp_path, threshold)
            for exp_name, exp_path in experiments.items()
        ]
    elif isinstance(experiments, str):
        exp_root = check_directory(experiments) or experiments
        exp_list = []
        for subfolder in sorted(os.listdir(exp_root)):
            sub_path = os.path.join(exp_root, subfolder)
            if not os.path.isdir(sub_path):
                continue
            data_path = os.path.join(sub_path, 'Data Analysis')
            if not os.path.isdir(data_path):
                continue
            contents = os.listdir(data_path)
            has_structure = any(
                d in contents for d in ['Objects', 'Attributes', 'ROI Intensities']
            ) or any(f.endswith('.csv') for f in contents)
            if has_structure:
                exp_list.append(Experiment(subfolder, data_path, threshold))
        if not exp_list:
            raise ValueError(f"No experiment folders found in {exp_root}")
    elif isinstance(experiments, list):
        exp_list = experiments
    else:
        raise TypeError(f"experiments must be dict, str, list, or None â€” got {type(experiments)}")

    tracker.finish_item("Prepare Experiments", detail=f"{len(exp_list)} experiments: {[e.name for e in exp_list]}")

    tracker.start_item("Process Batch")
    batch = Batch(name, exp_list, conditions, batch_path)
    effective_import_images = bool(import_images or (rerun and reimport_images))
    batch.processData(import_images=effective_import_images, progress=progress)
    tracker.finish_item("Process Batch", detail=getattr(batch, "_last_process_summary", None))

    # Auto-generate path aliases from condition vocabulary
    vocab = set()
    for f in batch.factor:
        vocab.add(f)
    for cond in conditions.conditions:
        vocab.add(cond.name)
        vocab.add(cond.label)
        vocab.add(getattr(cond, 'factor', ''))
    # Also include factor column values from the summary
    for f in batch.factor:
        if f in batch.summary.columns:
            vocab.update(str(v) for v in batch.summary[f].dropna().unique())
    auto_aliases = generate_aliases(vocab - {None, '', 'None'})
    # Manual overrides from Config take priority
    auto_aliases.update(Config.ALIASES)
    batch.aliases = auto_aliases

    tracker.start_item("Carry Over Representatives")
    rep_detail = "No previous representative selections found"
    if pickle_path is not None and rerun and os.path.exists(pkl_file):
        try:
            previous_batch = load_state(pkl_file, verbose=False)
            copied_rows, copied_experiments = _carry_over_representatives(batch, previous_batch)
            copied_edit_rows, copied_edit_experiments = _carry_over_saved_image_edits(batch, previous_batch)

            detail_parts = []
            if copied_rows > 0:
                detail_parts.append(
                    f"{copied_rows} representative selections restored"
                    + (f" | {copied_experiments} experiments updated" if copied_experiments > 0 else "")
                )
            if copied_edit_rows > 0:
                detail_parts.append(
                    f"{copied_edit_rows} saved image edits restored"
                    + (f" | {copied_edit_experiments} experiments updated" if copied_edit_experiments > 0 else "")
                )
            if len(detail_parts) > 0:
                rep_detail = " ; ".join(detail_parts)
            else:
                rep_detail = "Previous pickle loaded but no representative selections or saved image edits were stored"
        except Exception as exc:
            rep_detail = f"Representative carry-over skipped: {exc}"
    tracker.finish_item("Carry Over Representatives", detail=rep_detail)

    tracker.start_item("Save Pickle" if pickle_path is not None else "Finalize")
    if pickle_path is not None:
        os.makedirs(pickle_path, exist_ok=True)
        save_state(batch, pkl_file, verbose=False)
        final_detail = f"Saved to {pkl_file}"
    else:
        final_detail = "Batch ready"
    tracker.finish_item("Save Pickle" if pickle_path is not None else "Finalize", detail=final_detail)

    tracker.close(f"{len(exp_list)} experiments | {batch.summary.shape[0]} animals")
    return batch
