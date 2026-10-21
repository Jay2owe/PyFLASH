"""
Data marker classes — Attribute, Antibody, cellMarker, objectMarker.

These represent individual staining channels or attributes within an experiment.
"""

import re
import numpy as np
import pandas as pd
from collections import defaultdict
_TREE_PENDING = object()
cKDTree = _TREE_PENDING

from PyFLASH.config import Config
from PyFLASH._logging import logger as _log
from PyFLASH.utils import (
    clean_column_name, add_suffix, get_columns,
    convert_microns_to_pixels, convert_pixels_to_microns, trace_downward_nearest,
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

    m = re.match(rf"^{re.escape(marker_s)}_Coloc(?P<target>(?!Count)[^_].*)$", col_s)
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
            return (numeric.notna() & numeric.ne(0.0)).fillna(False).astype(bool)
        return numeric.gt(float(threshold)).fillna(False).astype(bool)

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
            self.addColocData(getattr(self, 'threshold', Config.THRESHOLD))
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
            self.df['Condition'] = pd.Series([
                ''.join(filter(str.isalpha, n)) for n in self.df['AnimalName']
            ], index=self.df.index, dtype=object)
        else:
            # Object/cell marker data
            protected_cols = ['Region', 'Hemisphere', 'ROI', 'Animal Name', 'Count']
            self.df['Count'] = np.where(
                (self.df['Volume (micron^3)'] > 0).fillna(False).to_numpy(dtype=bool), 1, 0
            )
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
            self.df['Condition'] = pd.Series([
                ''.join(filter(str.isalpha, n)) for n in self.df['AnimalName']
            ], index=self.df.index, dtype=object)
            self.df[f'{self.name}_SAtoVolumeRatio'] = (
                self.df[f'{self.name}_Surface'] / self.df[f'{self.name}_Volume']
            )
        return self.df

    def _adjust_coordinates(self):
        name = self.name
        scales = self._source_coordinate_scales(self.df)
        if scales is None:
            # Validate the same physical domain as the public unit converter
            # before inserting either output column. Keep the existing pandas
            # division below so accepted column storage remains unchanged.
            axes = [f'{name}_XM', f'{name}_YM']
            if f'{name}_ZM' in self.df.columns:
                axes.append(f'{name}_ZM')
            acquired = self._real_coordinate_values(self.df, axes)
            planar = acquired[:, :2]
            convert_pixels_to_microns(planar[np.isfinite(planar)])
            self.df[f'{name}_RawYM'] = self.df[f'{name}_YM'] / Config.PIXEL_SIZE
            self.df[f'{name}_RawXM'] = self.df[f'{name}_XM'] / Config.PIXEL_SIZE
        else:
            # FLASH exports voxel coordinates and their individual axis pitches.
            # Preserve acquired ZM and retain a separate physical depth column.
            acquired = self._real_coordinate_values(self.df, [f'{name}_{axis}M' for axis in ('X', 'Y', 'Z')])
            with np.errstate(over='ignore', under='ignore', invalid='ignore'):
                physical = acquired * scales
            if (np.isfinite(acquired) & ~np.isfinite(physical)).any():
                raise ValueError('Source calibration coordinates exceed the finite micrometre range.')
            self.df[f'{name}_RawYM'] = physical[:, 1]
            self.df[f'{name}_RawXM'] = physical[:, 0]
            self.df[f'{name}_RawZM'] = physical[:, 2]
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

    def _source_coordinate_scales(self, frame):
        """Return declared row-wise micrometres per voxel, or legacy absence."""
        name = self.name
        columns = [f'{name}_SourcePixel{axis}' for axis in ('Width', 'Height', 'Depth')]
        if not any(column in frame.columns for column in columns):
            return None
        if not all(column in frame.columns for column in columns):
            raise ValueError('Source calibration requires width, height and depth together.')
        scales = self._real_coordinate_values(frame, columns).copy()
        count_column = f'{name}_Count'
        measured = (frame[count_column].to_numpy() > 0 if count_column in frame.columns
                    else np.ones(len(frame), dtype=bool))
        if not np.isfinite(scales[measured]).all() or (scales[measured] <= 0).any():
            raise ValueError('Source calibration pitches must be positive and finite.')
        units = {
            'micron': 1., 'microns': 1., 'micrometre': 1., 'micrometres': 1.,
            'micrometer': 1., 'micrometers': 1., 'um': 1., 'µm': 1., 'μm': 1.,
            'nm': .001, 'nanometre': .001, 'nanometer': .001,
            'mm': 1000., 'millimetre': 1000., 'millimeter': 1000.,
        }
        for axis, letter in enumerate(('X', 'Y', 'Z')):
            column = f'{name}_SourcePixel{letter}Unit'
            if column not in frame.columns:
                column = f'{name}_SourcePixelUnit'
            if column not in frame.columns:
                raise ValueError('Source calibration requires physical axis units.')
            factors = frame[column].map(lambda value: units.get(str(value).strip().lower(), np.nan)).to_numpy(dtype=float)
            if not np.isfinite(factors[measured]).all():
                raise ValueError('Source calibration units must identify micrometres, nanometres or millimetres.')
            with np.errstate(over='ignore', under='ignore', invalid='ignore'):
                scales[:, axis] *= factors
        if not np.isfinite(scales[measured]).all() or (scales[measured] <= 0).any():
            raise ValueError('Source calibration cannot be represented in micrometres.')
        return scales

    def _spatial_coordinate_data(self, frame):
        name = self.name
        calibrated = f'{name}_RawZM' in frame.columns
        depth = f'{name}_RawZM' if calibrated else f'{name}_ZM'
        coords = self._real_coordinate_values(frame, [f'{name}_RawXM', f'{name}_RawYM', depth])
        valid = np.isfinite(coords).all(axis=1)
        if not calibrated:
            valid &= coords[:, 2] != 0
        if f'{name}_Count' in frame.columns:
            valid &= frame[f'{name}_Count'].to_numpy() > 0
        return coords, valid

    @staticmethod
    def _real_coordinate_values(frame, columns):
        values = frame[columns].to_numpy(copy=False)
        if values.dtype.kind in ('c', 'O'):
            values = values.astype(object, copy=True)
            for position, value in np.ndenumerate(values):
                if value is pd.NA:
                    values[position] = np.nan
                    continue
                if isinstance(value, (complex, np.complexfloating)):
                    if value.imag != 0:
                        raise ValueError('Spatial coordinates and calibration must be real.')
                    values[position] = value.real
        return np.asarray(values, dtype=float)

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
        # Missing labels form a real group (dropna=False). Pandas emits NaN
        # keys whose equality is false, so independently grouped marker frames
        # need the same stable missing-label key before they can be matched.
        return {
            tuple(None if pd.isna(value) else value
                  for value in (key if isinstance(key, tuple) else (key,))):
                np.asarray(pos, dtype=int)
            for key, pos in grouped.items()
        }

    @staticmethod
    def _nearest_neighbor_query(query_coords, reference_coords):
        global cKDTree
        if cKDTree is _TREE_PENDING:
            try:
                from scipy.spatial import cKDTree as tree_type
            except Exception:
                cKDTree = None
            else:
                cKDTree = tree_type
        # Squared distances in the tree can underflow or overflow even though
        # the Euclidean distance itself is representable. Keep normal imaging
        # coordinates on the tree and use bounded robust norms at those limits.
        absolute = np.concatenate((np.abs(query_coords).ravel(), np.abs(reference_coords).ravel()))
        extreme = np.any((absolute > 1e150) | ((absolute > 0) & (absolute < 1e-150)))
        if cKDTree is not None and not extreme:
            tree = cKDTree(reference_coords)
            if len(reference_coords) == 1:
                distances, idx = tree.query(query_coords, k=1)
                distances = np.hypot.reduce(reference_coords[0] - query_coords, axis=1)
                return np.asarray(distances, dtype=float), np.asarray(idx, dtype=int)
            # Counts are attributed to the selected reference row, so equal
            # distances must use the same first-row rule as the bounded
            # fallback. A tree's traversal order is not a scientific tie rule.
            neighbors, indices = tree.query(query_coords, k=2)
            distances = np.asarray(neighbors[:, 0], dtype=float)
            idx = np.asarray(indices[:, 0], dtype=int)
            for position in np.flatnonzero(neighbors[:, 0] == neighbors[:, 1]):
                candidates = sorted(tree.query_ball_point(
                    query_coords[position], np.nextafter(distances[position], np.inf)
                ))
                candidate_distances = np.hypot.reduce(
                    reference_coords[candidates] - query_coords[position], axis=1
                )
                selected = int(np.argmin(candidate_distances))
                distances[position] = candidate_distances[selected]
                idx[position] = candidates[selected]
            # Nearby points at a large common offset can also have a tiny
            # represented separation. Recheck that complete neighbourhood
            # rather than treating a tree-rounded zero as an exact tie.
            tiny = np.flatnonzero(distances < 1e-150)
            if len(tiny):
                distances[tiny], idx[tiny] = Antibody._bounded_nearest_neighbor_query(
                    query_coords[tiny], reference_coords
                )
            return distances, idx

        return Antibody._bounded_nearest_neighbor_query(query_coords, reference_coords)

    @staticmethod
    def _bounded_nearest_neighbor_query(query_coords, reference_coords):
        # Keep the NumPy fallback bounded so large regions do not allocate an
        # all-pairs distance matrix in one shot.
        max_pairs = 2_000_000
        chunk_size = max(1, max_pairs // max(reference_coords.shape[0], 1))
        distances = np.empty(query_coords.shape[0], dtype=float)
        idx = np.empty(query_coords.shape[0], dtype=int)
        for start in range(0, query_coords.shape[0], chunk_size):
            stop = min(start + chunk_size, query_coords.shape[0])
            with np.errstate(over='ignore'):
                delta = query_coords[start:stop, np.newaxis, :] - reference_coords[np.newaxis, :, :]
            dist_chunk = np.hypot.reduce(delta, axis=2)
            idx_chunk = np.argmin(dist_chunk, axis=1)
            distances[start:stop] = dist_chunk[np.arange(stop - start), idx_chunk]
            idx[start:stop] = idx_chunk
        if not np.isfinite(distances).all():
            raise ValueError('Nearest-marker distances exceed the finite coordinate range.')
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
        from PyFLASH.utils import _real_coordinate_array
        x = _real_coordinate_array(roi['x'].squeeze() if hasattr(roi['x'], 'squeeze') else roi['x'], label='ROI', allow_zero_imaginary=True)
        y = _real_coordinate_array(roi['y'].squeeze() if hasattr(roi['y'], 'squeeze') else roi['y'], label='ROI', allow_zero_imaginary=True)
        if x.ndim != 1 or y.ndim != 1 or len(x) != len(y) or len(x) < 2:
            raise ValueError('ROI x/y coordinates must be paired one-dimensional arrays with at least two points.')
        name = roi['name']

        x_path, y_path, idx = trace_downward_nearest(x, y)
        x_s = moving_average(x_path, w=9)
        y_s = moving_average(y_path, w=9)

        points = _real_coordinate_array(points, label='Points', allow_zero_imaginary=True)
        if points.ndim == 1 and points.size == 0:
            points = points.reshape((0, 2))
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Points must be a two-dimensional array with exactly two coordinates per point.')
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
            from matplotlib.ticker import MaxNLocator
            ax.xaxis.set_major_locator(MaxNLocator(nbins='auto', min_n_ticks=1))
            sns.despine(trim=False)
            save_fig(fig, self.experiment.fig_path,
                     f'Ventricle Analysis {name} {self.name}',
                     subfolder='Ventricle Analysis')

        ventricle_line = np.column_stack((x_s, y_s)).astype(float)
        return dists, closest_points, ventricle_line

    def find_distance_to_ventricle(self, rois):
        """Attach per-row ventricle distances in micrometres.

        ROI coordinates are pixels; marker RawXM/RawYM are micrometres.
        Missing/nonfinite marker coordinates or zero depth remain undefined.
        """
        from PyFLASH.utils import convert_pixels_to_microns
        if rois is None:
            rois = self.experiment.data['ROIs'].df
        rois = self._spatial_frame(rois)
        frame = self._spatial_frame(self.df)
        group_cols = ['Region'] + [column for column in self._shared_spatial_columns(frame, rois) if column != 'Region']
        groups = self._group_row_positions(frame, group_cols)
        roi_groups = self._group_row_positions(rois, group_cols)
        distance_out = np.full(len(self.df), np.inf, dtype=float)
        source_scales = self._source_coordinate_scales(frame)
        for key, positions in groups.items():
            roi_positions = roi_groups.get(key)
            if roi_positions is None or roi_positions.size == 0:
                continue
            coordinates, valid = self._spatial_coordinate_data(frame.iloc[positions])
            if not valid.any():
                continue
            roi_df = rois.iloc[roi_positions]
            if source_scales is not None:
                scales = source_scales[positions][valid]
                points = coordinates[valid, :2]
                if roi_df['x'].isna().any():
                    distances = 1024 * scales[:, 0] - points[:, 0]
                else:
                    # Preserve the declared pixel-space tracing/smoothing path,
                    # then measure each row against its physically scaled line.
                    _, _, line = self.analyse_roi(roi_df, np.empty((0, 2)), visualise=False)
                    distances = np.asarray([
                        points_to_polyline_distance([point[0]], [point[1]],
                            line[:, 0] * scale[0], line[:, 1] * scale[1])[0][0]
                        for point, scale in zip(points, scales, strict=True)
                    ])
                distance_out[positions[valid]] = distances
                continue
            points = np.column_stack((
                convert_microns_to_pixels(coordinates[valid, 0]),
                convert_microns_to_pixels(coordinates[valid, 1]),
            ))
            if roi_df['x'].isna().any():
                # Historical fallback: horizontal distance to the 1024-pixel
                # right image edge. Keep the subtraction in pixel units.
                distances = 1024 - points[:, 0]
            else:
                distances, _, _ = self.analyse_roi(roi_df, points, visualise=False)
            distance_out[positions[valid]] = convert_pixels_to_microns(distances)
        self.df[f'{self.name}_DistToVentricle'] = distance_out

    def find_closest_distances_between_markers(self, other_marker):
        threshold = getattr(self, 'threshold', Config.THRESHOLD)
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

            self_coords, self_valid = self._spatial_coordinate_data(self_group)
            other_coords, other_valid = other_marker._spatial_coordinate_data(other_group)

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
