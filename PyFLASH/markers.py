"""
Data marker classes — Attribute, Antibody, cellMarker, objectMarker.

These represent individual staining channels or attributes within an experiment.
"""

import re
import numpy as np
import pandas as pd
from collections import defaultdict
try:
    from scipy.spatial import cKDTree
except Exception:
    cKDTree = None

from PyFLASH.config import Config
from PyFLASH._logging import logger as _log
from PyFLASH.utils import (
    clean_column_name, add_suffix, get_columns,
    convert_microns_to_pixels, trace_downward_nearest,
    moving_average, points_to_polyline_distance, save_fig,
)


COLOC_FAMILY_CONFIGS = {
    "Vol": {
        "raw": "VolColoc",
        "count": "VolColocCount",
        "contains": "VolContains",
        "any": "VolAny",
        "combo": "VolCombo",
        "combo_any": "VolComboAny",
        "numcoloc": "VolNumColoc",
    },
    "CPC": {
        "raw": "CPCColoc",
        "count": "CPCColocCount",
        "contains": "CPCContains",
        "any": "CPCAny",
        "combo": "CPCCombo",
        "combo_any": "CPCComboAny",
        "numcoloc": "CPCNumColoc",
    },
}


def _canonical_raw_coloc_column(marker_name, target_name, family="Vol"):
    family_cfg = COLOC_FAMILY_CONFIGS[str(family)]
    return f"{str(marker_name)}_{family_cfg['raw']}_{str(target_name)}"


def _legacy_raw_coloc_column(marker_name, target_name):
    return f"{str(marker_name)}_Coloc{str(target_name)}"


def _extract_raw_coloc_descriptor(colname, marker_name):
    marker_s = str(marker_name)
    col_s = str(colname)

    for family_name, family_cfg in COLOC_FAMILY_CONFIGS.items():
        m = re.match(
            rf"^{re.escape(marker_s)}_{re.escape(str(family_cfg['raw']))}_(?P<target>.+)$",
            col_s,
        )
        if m is not None:
            return family_name, str(m.group("target"))

    m = re.match(rf"^{re.escape(marker_s)}_Coloc_(?P<target>.+)$", col_s)
    if m is not None:
        return "Vol", str(m.group("target"))

    m = re.match(rf"^{re.escape(marker_s)}_Coloc(?P<target>(?!Count)[^_].+)$", col_s)
    if m is not None:
        return "Vol", str(m.group("target"))

    return None


def _extract_raw_coloc_target(colname, marker_name):
    descriptor = _extract_raw_coloc_descriptor(colname, marker_name)
    if descriptor is None:
        return None
    _, target_name = descriptor
    return target_name


def _canonicalize_raw_coloc_family_columns(df, marker_name):
    rename_map = {}
    for col in df.columns:
        descriptor = _extract_raw_coloc_descriptor(col, marker_name)
        if descriptor is None:
            continue
        family_name, target_name = descriptor
        canonical = _canonical_raw_coloc_column(marker_name, target_name, family=family_name)
        if str(col) != canonical and canonical not in df.columns:
            rename_map[str(col)] = canonical
    if len(rename_map) == 0:
        return df
    return df.rename(columns=rename_map)


def _prefix_cleaned_marker_column(marker_name, colname, protected_cols=None):
    cleaned = clean_column_name(colname)
    if protected_cols is not None and colname in protected_cols:
        return cleaned

    marker_prefix = f"{str(marker_name)}_"
    if cleaned.startswith(marker_prefix):
        return cleaned
    return f"{marker_prefix}{cleaned}"


def _resolve_raw_coloc_column(df, marker_name, target_name, family="Vol"):
    candidates = [_canonical_raw_coloc_column(marker_name, target_name, family=family)]
    if str(family) == "Vol":
        candidates.extend([
            f"{str(marker_name)}_Coloc_{str(target_name)}",
            _legacy_raw_coloc_column(marker_name, target_name),
        ])
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


def _coerce_coloc_positive(series, threshold):
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if len(valid) > 0:
        unique_vals = {float(v) for v in valid.unique().tolist()}
        if unique_vals.issubset({0.0, 1.0}):
            return numeric.fillna(0.0).ne(0.0)
        return numeric > float(threshold)

    text = series.astype(str).str.strip().str.casefold()
    mapped = text.map({
        "1": True, "0": False,
        "true": True, "false": False,
        "yes": True, "no": False,
        "y": True, "n": False,
        "t": True, "f": False,
    })
    fallback = pd.to_numeric(text, errors="coerce").fillna(0).ne(0)
    mapped = mapped.where(mapped.notna(), fallback)
    return mapped.fillna(False).astype(bool)


class Attribute:
    """Generic data attribute — wraps a DataFrame with experiment context."""

    def __init__(self, name, df, experiment):
        self.df = df
        self.experiment = experiment
        self.name = name
        self.df.columns = [clean_column_name(c) for c in self.df.columns]
        # Ensure Region column exists (ZIP-loaded data may still have SCN)
        if 'SCN' in self.df.columns and 'Region' not in self.df.columns:
            self.df = self.df.rename(columns={'SCN': 'Region'})
        if hasattr(self.experiment, 'condition_labels'):
            label_map = dict(zip(
                self.experiment.condition_labels.iloc[:, 0],
                self.experiment.condition_labels.iloc[:, 1],
            ))
            self.df['AnimalName'] = self.df['AnimalName'].map(lambda x: label_map.get(x, x))
        self.df['Condition'] = [
            ''.join(filter(str.isalpha, n)) for n in self.df['AnimalName']
        ]

    # ── Serialization ──────────────────────────────────────────────────

    def __getstate__(self):
        state = self.__dict__.copy()
        if 'experiment' in state and hasattr(state['experiment'], 'name'):
            state['_experiment_name'] = state['experiment'].name
        state.pop('experiment', None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.experiment = None  # Re-linked by parent


class Antibody(Attribute):
    """Marker with spatial data (coordinates, colocalisation, etc.)."""

    def __init__(self, name, df, experiment, color=None):
        self.df = df
        self.name = name
        self.experiment = experiment
        self.color = color
        self.df = self.clean_df()

    def clean_df(self):
        self._clean_columns()
        if isinstance(self, (cellMarker, objectMarker)):
            self._adjust_coordinates()
        if isinstance(self, objectMarker):
            self.addColocData(Config.THRESHOLD)
        self.df.set_index('Region', inplace=True)
        _log.confirm(f'{self.name} data processing complete.')
        return self.df

    def _clean_columns(self):
        _log.status(f"Cleaning {self.name} DataFrame...")
        no_rename = ['Region', 'Hemisphere', 'ROI', 'Animal Name']
        label_map = None
        if hasattr(self.experiment, 'condition_labels'):
            label_map = dict(zip(
                self.experiment.condition_labels.iloc[:, 0],
                self.experiment.condition_labels.iloc[:, 1],
            ))

        if type(self) is Antibody:
            # ROI intensity data
            self.df.columns = [
                _prefix_cleaned_marker_column(self.name, c, protected_cols=no_rename)
                for c in self.df.columns
            ]
            if label_map:
                self.df['AnimalName'] = self.df['AnimalName'].map(lambda x: label_map.get(x, x))
            self.df['Condition'] = [
                ''.join(filter(str.isalpha, n)) for n in self.df['AnimalName']
            ]
        else:
            # Object/cell marker data
            protected_cols = ['Region', 'Hemisphere', 'ROI', 'Animal Name', 'Count']
            self.df['Count'] = np.where(self.df['Volume (micron^3)'] > 0, 1, 0)
            no_data_mask = self.df['Count'] == 0
            cols_to_nan = self.df.columns.difference(protected_cols)
            self.df.loc[no_data_mask, cols_to_nan] = np.nan
            self.df.columns = [
                _prefix_cleaned_marker_column(self.name, c, protected_cols=no_rename)
                for c in self.df.columns
            ]
            self.df = _canonicalize_raw_coloc_family_columns(self.df, self.name)
            int_den_cols = get_columns(self.df, column_strings=['Mean', 'StdDev', 'Median', 'Min', 'Max'])
            self.df = add_suffix(self.df, int_den_cols, 'IntDen')
            if label_map:
                self.df['AnimalName'] = self.df['AnimalName'].map(lambda x: label_map.get(x, x))
            self.df['Condition'] = [
                ''.join(filter(str.isalpha, n)) for n in self.df['AnimalName']
            ]
            self.df[f'{self.name}_SAtoVolumeRatio'] = (
                self.df[f'{self.name}_Surface'] / self.df[f'{self.name}_Volume']
            )
        return self.df

    def _adjust_coordinates(self):
        name = self.name
        self.df[f'{name}_RawYM'] = self.df[f'{name}_YM'] / Config.PIXEL_SIZE
        self.df[f'{name}_RawXM'] = self.df[f'{name}_XM'] / Config.PIXEL_SIZE
        try:
            _log.status(f"Adjusting coordinates for {name} points...")
            roi_props = self.experiment.data.get('ROI Properties')
            if roi_props is not None:
                area = roi_props.df
            else:
                frames = [
                    value.df
                    for key, value in self.experiment.data.items()
                    if 'ROI Properties' in str(key)
                    and isinstance(getattr(value, 'df', None), pd.DataFrame)
                ]
                if len(frames) == 0:
                    raise KeyError('ROI Properties')
                area = pd.concat(frames, ignore_index=True)
            merge_cols = ['Region']
            if 'AnimalName' in self.df.columns and 'AnimalName' in area.columns:
                merge_cols = ['AnimalName', 'Region']
            area = area[merge_cols].drop_duplicates()
            self.df = self.df.merge(area, on=merge_cols, how='left')
            self.df = self.df.drop(columns=["AnimalName_y"], errors='ignore').rename(
                columns={"AnimalName_x": "AnimalName"}
            )
            self.df['X_factor'] = 500 / 1024
            self.df['Y_factor'] = -800 / 1024
            self.df[f'{name}_XM'] = self.df[f'{name}_XM'] * self.df['X_factor']
            self.df[f'{name}_YM'] = self.df[f'{name}_YM'] * self.df['Y_factor']
            self.df = self.df.drop(
                columns=['X_factor', 'Y_factor'],
                errors='ignore',
            )
            _log.confirm(f'{name} adjusted coordinates added!')
        except KeyError as k:
            import warnings
            warnings.warn(f'No Area Data provided; coordinates not adjusted {k}', stacklevel=2)
        return self.df

    def set_df(self, new_df):
        self.df = new_df
        return self.df

    @staticmethod
    def _spatial_frame(df):
        index_name = getattr(df.index, 'name', None)
        if index_name is not None and index_name not in df.columns:
            return df.reset_index()
        return df

    @staticmethod
    def _shared_spatial_columns(*dfs):
        preferred = ['AnimalName', 'ImageROI', 'Hemisphere', 'Region', 'ROI']
        shared = set(preferred)
        for df in dfs:
            shared &= set(df.columns)
        return [col for col in preferred if col in shared]

    @staticmethod
    def _group_row_positions(df, group_cols):
        if len(group_cols) == 0:
            return {('__all__',): np.arange(len(df), dtype=int)}
        grouped = df.groupby(group_cols, sort=False, dropna=False).indices
        return {
            key if isinstance(key, tuple) else (key,): np.asarray(pos, dtype=int)
            for key, pos in grouped.items()
        }

    @staticmethod
    def _nearest_neighbor_query(query_coords, reference_coords):
        if cKDTree is not None:
            tree = cKDTree(reference_coords)
            distances, idx = tree.query(query_coords, k=1)
            return np.asarray(distances, dtype=float), np.asarray(idx, dtype=int)

        # Keep the NumPy fallback bounded so large regions do not allocate an
        # all-pairs distance matrix in one shot.
        max_pairs = 2_000_000
        chunk_size = max(1, max_pairs // max(reference_coords.shape[0], 1))
        distances = np.empty(query_coords.shape[0], dtype=float)
        idx = np.empty(query_coords.shape[0], dtype=int)
        for start in range(0, query_coords.shape[0], chunk_size):
            stop = min(start + chunk_size, query_coords.shape[0])
            delta = query_coords[start:stop, np.newaxis, :] - reference_coords[np.newaxis, :, :]
            dist_chunk = np.linalg.norm(delta, axis=2)
            idx_chunk = np.argmin(dist_chunk, axis=1)
            distances[start:stop] = dist_chunk[np.arange(stop - start), idx_chunk]
            idx[start:stop] = idx_chunk
        return distances, idx

    def addColocData(self, threshold):
        coloc_cols = []
        for column in self.df.columns:
            descriptor = _extract_raw_coloc_descriptor(column, self.name)
            if descriptor is not None:
                family_name, target_name = descriptor
                coloc_cols.append((str(column), family_name, target_name))

        for raw_col, family_name, coloc_name in coloc_cols:
            family_cfg = COLOC_FAMILY_CONFIGS[family_name]
            _log.status(f"Adding {family_name} {coloc_name} colocalisation data...")
            coloc_positive = _coerce_coloc_positive(self.df[raw_col], threshold)
            self.df[f'{self.name}_{family_cfg["count"]}{coloc_name}'] = coloc_positive.astype(np.int8)
            if family_name == "Vol":
                self.df[f'{self.name}_ColocCount{coloc_name}'] = coloc_positive.astype(np.int8)
                self.df[f'{self.name}_NonColocCount{coloc_name}'] = (~coloc_positive).astype(np.int8)
        return self.df

    def analyse_roi(self, roi, points, visualise=False):
        x = roi['x'].squeeze()
        y = roi['y'].squeeze()
        name = roi['name']

        x_path, y_path, idx = trace_downward_nearest(x, y)
        x_s = moving_average(x_path, w=9)
        y_s = moving_average(y_path, w=9)

        points = np.array(points)
        dists, closest_points = points_to_polyline_distance(
            points[:, 0], points[:, 1], x_s, y_s
        )

        if visualise:
            from matplotlib import pyplot as plt
            import seaborn as sns
            from PyFLASH.config import apply_matplotlib_fast_path
            apply_matplotlib_fast_path()
            fig, ax = plt.subplots(1, 1)
            ax.invert_yaxis()
            ax.plot(x, y, c='yellow', lw=4)
            ax.plot(x_s, y_s, c='g', lw=4)
            ax.plot([points[:, 0]], [points[:, 1]], marker='x', c='yellow', markersize=20)
            ax.plot([closest_points[:, 0]], [closest_points[:, 1]], marker='x', c='r', markersize=20)
            ax.plot([points[:, 0], closest_points[:, 0]],
                    [points[:, 1], closest_points[:, 1]], c='r', lw=4, linestyle='--')
            ax.set_aspect('equal', adjustable='box')
            sns.despine(trim=False)
            save_fig(fig, self.experiment.fig_path,
                     f'Ventricle Analysis {name} {self.name}',
                     subfolder='Ventricle Analysis')

        ventricle_line = np.array(list(zip(x_s, y_s)))
        return dists, closest_points, ventricle_line

    def find_distance_to_ventricle(self, rois):
        rois = self.experiment.data['ROIs'].df
        all_distances = []
        for s in self.df['Region'].unique():
            SCN_df = self.df[self.df['Region'] == s]
            roi_df = rois[rois['Region'] == s]
            if SCN_df.empty or SCN_df[f'{self.name}_ZM'].iloc[0] == 0 or roi_df.empty:
                dists = np.full(SCN_df.shape[0], np.inf)
            elif roi_df.isna()['x'].any():
                dists = np.full(
                    SCN_df.shape[0],
                    convert_microns_to_pixels(1024, pixel_size=Config.PIXEL_SIZE)
                    - SCN_df[f'{self.name}_RawXM']
                )
            else:
                points = np.array(list(zip(
                    convert_microns_to_pixels(SCN_df[f'{self.name}_RawXM']),
                    convert_microns_to_pixels(SCN_df[f'{self.name}_RawYM']),
                )))
                dists, _, _ = self.analyse_roi(roi_df, points, visualise=False)
            all_distances.extend(dists)
        self.df[f'{self.name}_DistToVentricle'] = convert_microns_to_pixels(
            np.array(all_distances), pixel_size=Config.PIXEL_SIZE
        )

    def find_closest_distances_between_markers(self, other_marker):
        threshold = Config.THRESHOLD
        other_df = other_marker.df
        self_frame = self._spatial_frame(self.df)
        other_frame = self._spatial_frame(other_df)
        group_cols = self._shared_spatial_columns(self_frame, other_frame)
        self_groups = self._group_row_positions(self_frame, group_cols)
        other_groups = self._group_row_positions(other_frame, group_cols)
        all_keys = list(dict.fromkeys([*self_groups.keys(), *other_groups.keys()]))

        distance_out = np.full(self.df.shape[0], np.inf, dtype=float)
        closest_flag_out = np.zeros(other_df.shape[0], dtype=float)
        coloc_count_out = np.zeros(other_df.shape[0], dtype=float)
        closest_count_out = np.zeros(other_df.shape[0], dtype=float)

        self_coord_cols = [f'{self.name}_RawXM', f'{self.name}_RawYM', f'{self.name}_ZM']
        other_coord_cols = [
            f'{other_marker.name}_RawXM',
            f'{other_marker.name}_RawYM',
            f'{other_marker.name}_ZM',
        ]

        for key in all_keys:
            self_pos = self_groups.get(key, np.empty(0, dtype=int))
            other_pos = other_groups.get(key, np.empty(0, dtype=int))
            if self_pos.size == 0 or other_pos.size == 0:
                continue

            self_group = self.df.iloc[self_pos]
            other_group = other_df.iloc[other_pos]

            closest_dist = np.full(self_pos.shape[0], np.inf, dtype=float)
            closest_flags = np.zeros(other_pos.shape[0], dtype=float)
            coloc_count_arr = np.zeros(other_pos.shape[0], dtype=float)
            closest_count_arr = np.zeros(other_pos.shape[0], dtype=float)

            self_coords = self_group[self_coord_cols].to_numpy(dtype=float, copy=False)
            other_coords = other_group[other_coord_cols].to_numpy(dtype=float, copy=False)
            self_valid = np.isfinite(self_coords).all(axis=1) & (
                self_group[f'{self.name}_ZM'].to_numpy(dtype=float, copy=False) != 0
            )
            other_valid = np.isfinite(other_coords).all(axis=1) & (
                other_group[f'{other_marker.name}_ZM'].to_numpy(dtype=float, copy=False) != 0
            )

            if self_valid.any() and other_valid.any():
                valid_self_coords = self_coords[self_valid]
                valid_other_coords = other_coords[other_valid]
                valid_dist, valid_idx = self._nearest_neighbor_query(
                    valid_self_coords,
                    valid_other_coords,
                )
                closest_dist[self_valid] = valid_dist

                other_valid_idx = np.flatnonzero(other_valid)
                closest_idx = other_valid_idx[valid_idx]
                np.maximum.at(closest_flags, closest_idx, 1)
                np.add.at(closest_count_arr, closest_idx, 1)

                try:
                    coloc_col = _resolve_raw_coloc_column(
                        self_group,
                        self.name,
                        other_marker.name,
                        family="Vol",
                    )
                    if coloc_col is None:
                        raise KeyError(other_marker.name)
                    coloc_bool = (
                        _coerce_coloc_positive(self_group[coloc_col], threshold)
                        .to_numpy(dtype=bool, copy=False)[self_valid]
                    )
                    np.add.at(coloc_count_arr, closest_idx, coloc_bool.astype(int))
                except KeyError:
                    np.add.at(coloc_count_arr, closest_idx, 1)

            distance_out[self_pos] = closest_dist
            closest_flag_out[other_pos] = closest_flags
            coloc_count_out[other_pos] = coloc_count_arr
            closest_count_out[other_pos] = closest_count_arr

        self.df[f'{self.name}_DistToClosest_{other_marker.name}'] = distance_out
        other_df[f'{other_marker.name}_ClosestTo_{self.name}'] = closest_flag_out
        other_df[f'{other_marker.name}_VolNumColoc_{self.name}'] = coloc_count_out
        other_df[f'{other_marker.name}_VolContains_{self.name}'] = np.where(
            coloc_count_out >= 1, 1, 0
        ).astype(np.int8)
        # Legacy volumetric aliases retained for marker-level plotting helpers.
        other_df[f'{other_marker.name}_NumColoc_{self.name}'] = other_df[f'{other_marker.name}_VolNumColoc_{self.name}']
        other_df[f'{other_marker.name}_Contains_{self.name}'] = other_df[f'{other_marker.name}_VolContains_{self.name}']
        other_df[f'{other_marker.name}_NumClosestTo_{self.name}'] = closest_count_out
        other_marker.set_df(other_df)

        _log.confirm(f"'Closest to {self.name}' column added to {other_marker.name} DataFrame!")
        _log.confirm(f"'Distance to closest {other_marker.name}' column added to {self.name} DataFrame!")
        return self.df


class cellMarker(Antibody):
    """Intracellular marker — no colocalisation data."""

    def __init__(self, name, df, experiment, color):
        self.df = df
        self.experiment = experiment
        self.name = name
        self.color = color
        self.df = super().clean_df()


class objectMarker(Antibody):
    """Intra/extracellular marker with colocalisation data."""

    def __init__(self, name, df, experiment, color, threshold=30):
        self.df = df
        self.experiment = experiment
        self.name = name
        self.color = color
        self.threshold = threshold
        self.df = super().clean_df()


# ── Default stain-to-color mapping ─────────────────────────────────────

stainColors = defaultdict(lambda: 'grey')
stainColors.update({
    'H31L21': 'green', 'DAPI': 'blue', 'GFAP': 'red', 'Iba1': 'cyan',
    'CD68': 'yellow', 'CD11b': 'purple', 'CD45': 'orange',
    'CD3': 'dark_green', 'CD4': 'dark_yellow', 'CD8': 'dark_red',
    'CD20': 'dark_blue', 'CD138': 'dark_cyan', 'CD163': 'grey',
    'CD206': 'black', 'AF(488)': 'green', 'Caspase3': 'green',
    'mCherry': 'red', 'IgG': 'magenta', 'AF546': 'red', 'CK1d': 'cyan'
})
