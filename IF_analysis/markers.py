"""
Data marker classes — Attribute, Antibody, cellMarker, objectMarker.

These represent individual staining channels or attributes within an experiment.
"""

import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from collections import defaultdict

from IF_analysis.config import Config
from IF_analysis._logging import logger as _log
from IF_analysis.utils import (
    clean_column_name, add_suffix, get_columns,
    convert_microns_to_pixels, trace_downward_nearest,
    moving_average, points_to_polyline_distance, save_fig,
)


class Attribute:
    """Generic data attribute — wraps a DataFrame with experiment context."""

    def __init__(self, name, df, experiment):
        self.df = df
        self.experiment = experiment
        self.name = name
        self.df.columns = [clean_column_name(c) for c in self.df.columns]
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
        self.df.set_index('SCN', inplace=True)
        _log.confirm(f'{self.name} data processing complete.')
        return self.df

    def _clean_columns(self):
        _log.status(f"Cleaning {self.name} DataFrame...")
        no_rename = ['SCN', 'Animal Name']
        label_map = None
        if hasattr(self.experiment, 'condition_labels'):
            label_map = dict(zip(
                self.experiment.condition_labels.iloc[:, 0],
                self.experiment.condition_labels.iloc[:, 1],
            ))

        if type(self) is Antibody:
            # ROI intensity data
            self.df.columns = [
                f'{self.name}_{clean_column_name(c)}' if c not in no_rename
                else clean_column_name(c) for c in self.df.columns
            ]
            if label_map:
                self.df['AnimalName'] = self.df['AnimalName'].map(lambda x: label_map.get(x, x))
            self.df['Condition'] = [
                ''.join(filter(str.isalpha, n)) for n in self.df['AnimalName']
            ]
        else:
            # Object/cell marker data
            protected_cols = ['SCN', 'Animal Name', 'Count']
            self.df['Count'] = np.where(self.df['Volume (micron^3)'] > 0, 1, 0)
            no_data_mask = self.df['Count'] == 0
            cols_to_nan = self.df.columns.difference(protected_cols)
            self.df.loc[no_data_mask, cols_to_nan] = np.nan
            self.df.columns = [
                f'{self.name}_{clean_column_name(c)}' if c not in no_rename
                else clean_column_name(c) for c in self.df.columns
            ]
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
            area = self.experiment.data['ROI Properties'].df
            self.df = self.df.merge(area, left_on='SCN', right_on='SCN')
            self.df = self.df.drop(columns=["AnimalName_y"]).rename(
                columns={"AnimalName_x": "AnimalName"}
            )
            self.df['X_factor'] = 500 / 1024
            self.df['Y_factor'] = -800 / 1024
            self.df[f'{name}_XM'] = self.df[f'{name}_XM'] * self.df['X_factor']
            self.df[f'{name}_YM'] = self.df[f'{name}_YM'] * self.df['Y_factor']
            self.df = self.df.drop(columns=['Height', 'Width', 'X_factor', 'Y_factor', 'Area'])
            _log.confirm(f'{name} adjusted coordinates added!')
        except KeyError as k:
            import warnings
            warnings.warn(f'No Area Data provided; coordinates not adjusted {k}', stacklevel=2)
        return self.df

    def set_df(self, new_df):
        self.df = new_df
        return self.df

    def addColocData(self, threshold):
        coloc_cols = get_columns(self.df, regex_string="Coloc")
        for column in coloc_cols:
            coloc_name = column.split('Coloc')[1]
            _log.status(f"Adding {coloc_name} colocalisation data...")
            self.df[f'{self.name}_ColocCount{coloc_name}'] = np.where(
                self.df[f'{self.name}_Coloc{coloc_name}'] > threshold, 1, 0
            )
            self.df[f'{self.name}_NonColocCount{coloc_name}'] = np.where(
                self.df[f'{self.name}_Coloc{coloc_name}'] < threshold, 1, 0
            )
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
        for s in self.df['SCN'].unique():
            SCN_df = self.df[self.df['SCN'] == s]
            roi_df = rois[rois['SCN'] == s]
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
        all_distances, all_colocalised = [], []
        all_coloc_count, all_closest_count = [], []

        for s in set(self.df.index.unique()) | set(other_df.index.unique()):
            self_scn = self.df[self.df.index == s]
            other_scn = other_df[other_df.index == s]

            if self_scn.empty or other_scn.empty or self_scn[f'{self.name}_ZM'].iloc[0] == 0:
                closest_dist = np.full(self_scn.shape[0], np.inf)
                coloc_arr = np.zeros(other_scn.shape[0])
                coloc_count_arr = np.zeros(other_scn.shape[0])
                closest_count_arr = np.zeros(other_scn.shape[0])
            else:
                self_coords = self_scn[[f'{self.name}_RawXM', f'{self.name}_RawYM', f'{self.name}_ZM']].to_numpy()
                other_coords = other_scn[[f'{other_marker.name}_RawXM', f'{other_marker.name}_RawYM', f'{other_marker.name}_ZM']].to_numpy()
                distances = np.linalg.norm(self_coords[:, np.newaxis] - other_coords, axis=2)
                closest_dist = np.min(distances, axis=1)
                closest_idx = np.argmin(distances, axis=1)

                coloc_arr = np.zeros(other_scn.shape[0])
                coloc_count_arr = np.zeros(other_scn.shape[0])
                closest_count_arr = np.zeros(other_scn.shape[0])

                try:
                    if other_scn[f'{other_marker.name}_ZM'].iloc[0] != 0:
                        coloc_bool = (self_scn[f'{self.name}_Coloc{other_marker.name}'].to_numpy() > threshold)
                        np.maximum.at(coloc_arr, closest_idx, 1)
                        np.add.at(coloc_count_arr, closest_idx, coloc_bool.astype(int))
                        np.add.at(coloc_arr, closest_idx, 1)
                except KeyError:
                    val = 1 if other_scn[f'{other_marker.name}_ZM'].iloc[0] != 0 else 0
                    coloc_arr[closest_idx] = val
                    coloc_count_arr[closest_idx] = val
                    closest_count_arr[closest_idx] = val

            all_distances.extend(closest_dist)
            all_colocalised.extend(coloc_arr)
            all_coloc_count.extend(coloc_count_arr)
            all_closest_count.extend(closest_count_arr)

        self.df[f'{self.name}_DistToClosest_{other_marker.name}'] = all_distances
        other_df[f'{other_marker.name}_ClosestTo_{self.name}'] = all_colocalised
        other_df[f'{other_marker.name}_NumColoc_{self.name}'] = all_coloc_count
        other_df[f'{other_marker.name}_Contains_{self.name}'] = np.where(
            other_df[f'{other_marker.name}_NumColoc_{self.name}'] >= 1, 1, 0
        )
        other_df[f'{other_marker.name}_NumClosestTo_{self.name}'] = all_closest_count
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
