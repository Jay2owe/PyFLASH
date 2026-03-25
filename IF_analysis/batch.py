"""
Batch class — combines multiple Experiments under shared conditions.
"""

import os
import re
import pandas as pd
import numpy as np
from functools import reduce
from collections import defaultdict

from IF_analysis.config import check_directory
from IF_analysis.experiment import (
    Experiment, _add_marker_scores,
    _attach_image_metadata, _build_images_dict, _empty_image_table, _sort_image_table,
)
from IF_analysis.markers import objectMarker, cellMarker, Antibody
from IF_analysis.export import _raw_name_cache, write_conditions_table_sheet, convert_raw_name_cached, safe_sheet_name, write_experiment_data_list_sheet, convert_name, BEHAVIOR_NAME_MAP, convert_behavior_name
from IF_analysis.utils import ProgressTracker


NOT_INCLUDED_SENTINEL = "NOT_INCLUDED_IN_EXPERIMENT"
JON = "JON"


class Batch(Experiment):
    """Groups multiple Experiment objects with a shared condition list."""

    def __init__(self, name, experiment_list, cond_list, filePath):
        self.name = name
        self.experiment_list = experiment_list
        self.condition_list = cond_list
        self.filePath = check_directory(filePath) or filePath
        self._current = 0
        self.factorDict = cond_list.factorDict

    def createSavePaths(self):
        results = os.path.join(self.filePath, "Results")
        self.export_path = os.path.join(self.filePath, "Exports")
        self.fig_path = os.path.join(results, "Python Figures")
        self.image_fig_path = os.path.join(self.fig_path, "Images")
        self.representative_path = os.path.join(results, "Representative Images")
        self.legend_path = os.path.join(results, "Legends")
        self.data_path = os.path.join(results, "Data and Stats")
        self.csv_path = os.path.join(results, "Separate CSVs")
        self.column_path = os.path.join(self.csv_path, "Columns")
        self.attribute_path = os.path.join(self.csv_path, "Attributes")

        paths = [results, self.export_path, self.fig_path, self.image_fig_path, self.representative_path, self.legend_path, self.data_path,
                 self.csv_path, self.column_path, self.attribute_path]
        for marker in self.markers:
            paths.append(os.path.join(self.fig_path, marker))
        for p in paths:
            os.makedirs(p, exist_ok=True)

    def processData(self, import_images=True, progress=True):
        tracker = ProgressTracker(
            f"{self.name} processData",
            total=len(self.experiment_list) + 7,
            unit="step",
            enabled=progress,
        )
        for exp in self.experiment_list:
            tracker.start_item(f"Experiment {exp.name}")
            exp.processData(import_images=import_images, progress=progress)
            tracker.finish_item(f"Experiment {exp.name}", detail=getattr(exp, "_last_process_summary", None))
        tracker.start_item("Apply Conditions")
        for exp in self.experiment_list:
            exp.set_condition_list(self.condition_list)
        tracker.finish_item("Apply Conditions", detail=f"{len(self.experiment_list)} experiments updated")
        tracker.start_item("Create Data Dict")
        self._create_data_dict()
        tracker.finish_item("Create Data Dict", detail=f"{len(self.data)} data tables")
        self.markers = reduce(
            lambda a, b: a | b,
            [exp.markers for exp in self.experiment_list]
        )
        tracker.start_item("Create Batch Summary")
        self._create_batch_summary()
        tracker.finish_item("Create Batch Summary", detail=f"{self.summary.shape[0]} animals x {self.summary.shape[1]} columns")
        tracker.start_item("Set Batch Conditions")
        self.set_condition_list(self.condition_list)
        tracker.finish_item("Set Batch Conditions")
        tracker.start_item("Create Save Paths")
        self.createSavePaths()
        tracker.finish_item("Create Save Paths", detail="Results folders ready")
        tracker.start_item("Import Images" if import_images else "Skip Images")
        if import_images:
            self.importImages(progress=progress)
            image_detail = getattr(self, "_last_image_import_summary", None)
        else:
            self.images = None
            self.imagesDict = {}
            image_detail = "Skipped image import"
        tracker.finish_item("Import Images" if import_images else "Skip Images", detail=image_detail)
        tracker.start_item("Assign SCNs")
        self.assign_scn_number()
        tracker.finish_item("Assign SCNs", detail=getattr(self, "_last_scn_summary", None))
        self._last_process_summary = f"{len(self.experiment_list)} experiments | {self.summary.shape[0]} animals"
        tracker.close(self._last_process_summary)

    def importImages(self, progress=True):
        image_tables = []

        tracker = ProgressTracker(
            f"{self.name} importImages",
            total=len(self.experiment_list),
            unit="experiment",
            enabled=progress and len(self.experiment_list) > 0,
        )
        for exp in self.experiment_list:
            tracker.start_item(exp.name)
            exp_images = getattr(exp, "images", None)
            if not isinstance(exp_images, pd.DataFrame):
                exp_images = exp.importImages(progress=progress)
            if not isinstance(exp_images, pd.DataFrame) or exp_images.empty:
                tracker.finish_item(exp.name, detail="No images")
                continue
            exp_table = exp_images.copy()
            exp_table["Experiment"] = exp.name
            image_tables.append(exp_table)
            tracker.finish_item(exp.name, detail=f"{len(exp_images)} images")

        if len(image_tables) == 0:
            self.images = _empty_image_table()
            self.imagesDict = {}
            self._last_image_import_summary = "No Images found across experiments"
            tracker.close(self._last_image_import_summary)
            return self.images

        self.images = (
            _sort_image_table(
                _attach_image_metadata(
                    self,
                    pd.concat(image_tables, ignore_index=True)
                ),
                source=self,
            )
        )
        self.imagesDict = _build_images_dict(self.images)
        markers = self.images["Marker"].dropna().astype(str).unique().tolist()
        animals = self.images["AnimalName"].dropna().astype(str).nunique() if not self.images.empty else 0
        self._last_image_import_summary = f"{len(self.images)} images | {animals} animals | {len(markers)} markers"
        tracker.close(self._last_image_import_summary)
        return self.images

    def getImageTable(self, include_summary=True):
        return super().getImageTable(include_summary=include_summary)

    def _create_data_dict(self):
        result, counts = {}, {}
        for exp in self.experiment_list:
            for k, v in exp.data.items():
                if k not in counts:
                    counts[k] = 0
                    result[k] = v
                else:
                    counts[k] += 1
                    result[f"{k}_{counts[k]}"] = v
        self.data = result

    def _dedup_columns(self, df):
        counts, new_cols = {}, []
        for col in df.columns:
            if col not in counts:
                counts[col] = 0
                new_cols.append(col)
            else:
                counts[col] += 1
                new_cols.append(f"{col}_{counts[col]}")
        df = df.copy()
        df.columns = new_cols
        return df

    def _canonicalize_not_included_cells(self, df, id_cols=None):
        """Normalize any malformed/repeated sentinel strings to one canonical token."""
        out = df.copy()
        id_set = set(id_cols or [])
        for col in out.columns:
            if col in id_set or col == "AnimalName":
                continue
            s = out[col]
            if (
                pd.api.types.is_object_dtype(s)
                or pd.api.types.is_string_dtype(s)
                or pd.api.types.is_categorical_dtype(s)
            ):
                mask = s.astype(str).str.contains(NOT_INCLUDED_SENTINEL, na=False)
                if mask.any():
                    out.loc[mask, col] = NOT_INCLUDED_SENTINEL
        return out

    def _label_duplicate_metric_columns_with_experiment(self, df, id_cols):
        """
        Rename duplicate metric columns by source experiment using `.expN`.

        Uses a dot separator (`.exp1`, `.exp2`) so that the suffix is never
        consumed by underscore-based regex patterns that parse marker names
        (e.g. `<ab>_Coloc<ab2>` where `<ab2>` matches `[A-Za-z0-9_-]+`).

        Temporary merge suffix format is `__exp{idx}` where idx starts at 1
        for the second experiment. The first experiment is treated as exp1.
        Only metric columns are experiment-labeled; ID columns are left as-is.
        """
        cols = list(df.columns)
        parsed = []
        for col in cols:
            m = re.search(r"__exp(\d+)$", str(col))
            if m:
                base = str(col)[:m.start()]
                exp_num = int(m.group(1)) + 1
            else:
                base = str(col)
                exp_num = 1
            parsed.append((base, exp_num))

        base_to_exps = {}
        for base, exp_num in parsed:
            if base in id_cols or base == "AnimalName":
                continue
            base_to_exps.setdefault(base, set()).add(exp_num)
        duplicate_metric_bases = {b for b, exps in base_to_exps.items() if len(exps) > 1}

        used = {}
        new_cols = []
        for base, exp_num in parsed:
            if base in duplicate_metric_bases:
                candidate = f"{base}.exp{exp_num}"
            else:
                candidate = base
            if candidate in used:
                used[candidate] += 1
                candidate = f"{candidate}_{used[candidate]}"
            else:
                used[candidate] = 0
            new_cols.append(candidate)

        out = df.copy()
        out.columns = new_cols
        return out

    def _create_batch_summary(self):
        if len(self.experiment_list) == 0:
            self.summary = pd.DataFrame(columns=["AnimalName"])
            return self.summary

        # Ensure marker score columns exist on every experiment summary before merge.
        for exp in self.experiment_list:
            if hasattr(exp, "summary") and isinstance(exp.summary, pd.DataFrame):
                exp.summary = _add_marker_scores(exp.summary.copy())

        id_cols = {"AnimalName", "Condition", "SCN"}
        # Include factor columns as IDs when available, so only metric columns
        # get the not-included sentinel.
        if hasattr(self, "condition_list") and hasattr(self.condition_list, "factor"):
            try:
                id_cols.update(list(self.condition_list.factor))
            except Exception:
                pass

        # Start from first experiment summary.
        first = self._canonicalize_not_included_cells(
            self.experiment_list[0].summary.copy(),
            id_cols=id_cols,
        )
        summary = first.copy()
        exp_animals = []
        exp_metric_cols = []

        animals0 = set(first["AnimalName"].dropna().astype(str).tolist()) if "AnimalName" in first.columns else set()
        exp_animals.append(animals0)
        exp_metric_cols.append([c for c in first.columns if c not in id_cols])

        # Merge remaining experiments with temporary unique suffixes, so we can
        # track exactly which columns came from which experiment.
        for exp_idx, exp in enumerate(self.experiment_list[1:], start=1):
            right = self._canonicalize_not_included_cells(
                exp.summary.copy(),
                id_cols=id_cols,
            )
            animals = set(right["AnimalName"].dropna().astype(str).tolist()) if "AnimalName" in right.columns else set()
            exp_animals.append(animals)

            rename_map = {
                c: f"{c}__exp{exp_idx}"
                for c in right.columns
                if c != "AnimalName"
            }
            right = right.rename(columns=rename_map)
            summary = pd.merge(summary, right, on="AnimalName", how="outer")

            right_metric_cols = []
            for col in exp.summary.columns:
                if col in id_cols or col == "AnimalName":
                    continue
                right_metric_cols.append(f"{col}__exp{exp_idx}")
            exp_metric_cols.append(right_metric_cols)

        # Mark rows for animals absent from each experiment with sentinel string,
        # but only in that experiment's metric columns.
        animal_series = summary["AnimalName"].astype(str) if "AnimalName" in summary.columns else pd.Series(dtype=str)
        for i, cols in enumerate(exp_metric_cols):
            if len(cols) == 0:
                continue
            absent_mask = ~animal_series.isin(exp_animals[i])
            present_cols = [c for c in cols if c in summary.columns]
            if len(present_cols) == 0:
                continue
            summary.loc[absent_mask, present_cols] = NOT_INCLUDED_SENTINEL

        # Safety pass: collapse any accidental concatenated sentinel strings.
        summary = self._canonicalize_not_included_cells(summary, id_cols=id_cols)

        # Replace generic duplicate numbering with experiment-aware names
        # for repeated metric columns (e.g. CK1d_Count.exp1, CK1d_Count.exp2).
        summary = self._label_duplicate_metric_columns_with_experiment(summary, id_cols=id_cols)
        self.summary = self._dedup_columns(summary)
        return self.summary

    def save_csvs(self):
        for exp in self.experiment_list:
            exp.save_csvs()

    def export_all_excel(self, save_path=None):
        if save_path == None: save_path = self.export_path

        self.export_IF_summary_excel(save_path)
        self.export_behavior_summary_excel(save_path)
        self.export_extended_data_excel(save_path)

        # Alternative optimized version using the cache
    def export_extended_data_excel(self, save_path=None, verbose=True, use_tqdm=False):
        """
        Further optimized version using caching and additional performance improvements.
        
        Args:
            save_path: Path to save the Excel file
            verbose: If True, print progress updates (default: True)
            use_tqdm: If True, use tqdm progress bar instead of print statements (default: False)
        """
        if save_path == None: save_path = self.export_path
        import time
        
        # Try to import tqdm if requested
        if use_tqdm:
            try:
                from tqdm import tqdm
            except ImportError:
                if verbose:
                    print("Warning: tqdm not installed, falling back to print statements")
                use_tqdm = False
        
        used_sheet_names = set()
        _raw_name_cache.clear()  # Clear cache at start
        start_time = time.time()
        
        # Count total sheets
        total_sheets = sum(
            1 for exp in self.experiment_list 
            for obj in exp.data.values() 
            if isinstance(obj, Antibody)
        )
        
        if verbose and not use_tqdm:
            print(f"Starting export to: {save_path}")
            print(f"Processing {len(self.experiment_list)} experiments with {total_sheets} total data sheets...")

        with pd.ExcelWriter(save_path+"/IF_Extended.xlsx", engine="xlsxwriter") as writer:
            if verbose and not use_tqdm:
                print("  ✓ Writing Conditions sheet...")
            write_conditions_table_sheet(writer, self.conditions, sheet_name="Conditions")
            
            wb = writer.book
            header_fmt = wb.add_format({
                "bold": True, "bg_color": "#F2F2F2", "border": 1, 
                "align": "center", "valign": "vcenter"
            })
            cell_fmt = wb.add_format({"border": 1, "valign": "top"})
            wrap_fmt = wb.add_format({"border": 1, "valign": "top", "text_wrap": True})
            
            sheets_processed = 0
            
            # Setup progress tracking
            if use_tqdm:
                exp_iterator = tqdm(enumerate(self.experiment_list, start=1), 
                                total=len(self.experiment_list),
                                desc="Experiments")
            else:
                exp_iterator = enumerate(self.experiment_list, start=1)
            
            for exp_idx, exp in exp_iterator:
                if verbose and not use_tqdm:
                    print(f"\n  Processing Experiment {exp_idx}/{len(self.experiment_list)}...")
                
                cond_map = None
                if "Condition" in exp.summary.columns and "AnimalName" in exp.summary.columns:
                    cond_map = exp.summary[["AnimalName", "Condition"]].drop_duplicates().set_index("AnimalName")["Condition"]
                
                for key, obj in exp.data.items():
                    if not isinstance(obj, Antibody):
                        continue

                    # Preserve ROI designation in sheet name
                    if "_ROI" in key:
                        ab = key.split("_ROI")[0]
                        sheet_suffix = f"{ab} ROI"
                    else:
                        ab = key.split("_ROI")[0]
                        sheet_suffix = ab
                    
                    df = obj.df
                    
                    if "AnimalName" not in df.columns:
                        continue

                    # Column selection
                    id_cols = [c for c in ["Condition", "AnimalName", "SCN"] if c in df.columns]
                    metric_cols = [c for c in df.columns if c.startswith(f"{ab}_")]
                    out = df[id_cols + metric_cols].copy()
                    
                    # Add condition
                    if "Condition" not in out.columns and cond_map is not None:
                        out.insert(0, "Condition", out["AnimalName"].map(cond_map))
                    
                    # Rename operations
                    if "SCN" in out.columns:
                        out.rename(columns={"SCN": "ROI"}, inplace=True)
                    
                    # Use cached version for column renaming
                    rename_dict = {"AnimalName": "Animal ID"}
                    
                    # Start with ID columns that are actually present
                    id_cols_present = [c for c in ["Condition", "AnimalName", "ROI", "SCN"] if c in out.columns]
                    columns_to_keep = id_cols_present.copy()
                    
                    for c in metric_cols:
                        try:
                            new_name, _ = convert_raw_name_cached(c)
                            rename_dict[c] = new_name
                            columns_to_keep.append(c)
                        except KeyError:
                            # Skip columns not in the mapping
                            pass
                    
                    # Filter to only keep mapped columns
                    out = out[columns_to_keep]
                    out.rename(columns=rename_dict, inplace=True)
                    
                    # Check for and handle duplicate column names
                    if out.columns.duplicated().any():
                        # Make column names unique by appending suffixes
                        cols = pd.Series(out.columns)
                        for dup in cols[cols.duplicated()].unique():
                            cols[cols == dup] = [f"{dup}_{i}" if i != 0 else dup 
                                                for i in range(sum(cols == dup))]
                        out.columns = cols
                    
                    out.replace([np.inf, -np.inf], np.nan, inplace=True)
                    
                    # Write to Excel
                    sheet = safe_sheet_name(f"Experiment {exp_idx}_{sheet_suffix}", used_sheet_names)
                    
                    # Sort rows by condition order
                    if "Condition" in out.columns:
                        # Get condition order from condition_list (deduplicate while preserving order)
                        condition_order = []
                        seen = set()
                        for cond in self.condition_list:
                            if cond.name not in seen:
                                condition_order.append(cond.name)
                                seen.add(cond.name)
                        
                        # Separate ID columns from data columns
                        id_column_names = ["Condition", "Animal ID", "ROI"]
                        id_cols_present = [c for c in id_column_names if c in out.columns]
                        data_cols = [c for c in out.columns if c not in id_column_names]
                        
                        # Create a categorical type for Condition with the desired order
                        out["Condition"] = pd.Categorical(out["Condition"], categories=condition_order, ordered=True)
                        
                        # Sort by Condition, then reorder columns: ID cols first, then data cols
                        out = out.sort_values("Condition")
                        out = out[id_cols_present + data_cols]
                        
                        # Convert Condition back to string to avoid fillna issues with Categorical
                        out["Condition"] = out["Condition"].astype(str)
                    
                    out.to_excel(writer, sheet_name=sheet, index=False)
                    ws = writer.sheets[sheet]
                    
                    # Formatting
                    wrap_cols_set = {c for c in out.columns if len(str(c)) > 25}
                    
                    for j, colname in enumerate(out.columns):
                        ws.write(0, j, colname, header_fmt)
                    
                    for j, colname in enumerate(out.columns):
                        fmt = wrap_fmt if colname in wrap_cols_set else cell_fmt
                        col_data = out.iloc[:, j].fillna("").tolist()
                        for i, val in enumerate(col_data, start=1):
                            ws.write(i, j, val, fmt)
                    
                    # Autosize
                    for j, colname in enumerate(out.columns):
                        if len(out) > 0:
                            # Use positional indexing to avoid duplicate column name issues
                            col_str = out.iloc[:, j].astype(str)
                            max_val_len = col_str.str.len().max()
                        else:
                            max_val_len = 0
                        max_len = max(len(str(colname)), max_val_len)
                        ws.set_column(j, j, min(max_len + 2, 60))
                    
                    sheets_processed += 1
                    if verbose and not use_tqdm:
                        print(f"    ✓ Sheet {sheets_processed}/{total_sheets}: '{sheet}' ({len(out)} rows, {len(out.columns)} columns)")
                    elif use_tqdm:
                        exp_iterator.set_postfix({"sheets": f"{sheets_processed}/{total_sheets}"})
        
        if verbose:
            elapsed = time.time() - start_time
            print(f"\n✓ Export complete!")
            print(f"  Total sheets: {sheets_processed}")
            print(f"  Time elapsed: {elapsed:.2f} seconds")
            print(f"  Average: {elapsed/sheets_processed:.3f} sec/sheet" if sheets_processed > 0 else "")
            print(f"  Cache hits: {len(_raw_name_cache)} unique column patterns")
            print(f"  Saved to: {save_path}")
        
        print(f"Exported extended IF data to {save_path+"/IF_Extended.xlsx"}")

    def export_IF_summary_excel(self, save_path=None):
        if save_path == None: save_path = self.export_path
        summary = self.summary
        factors = self.factor
        condition_list = self.condition_list
        columns_to_save = (col for col in summary.columns if col not in ['Condition', 'AnimalName'] + factors and any(data in col for data in self.data.keys())) # Only save relevant columns
        #print([col for col in columns_to_save])

        cols_not_included = []
        with pd.ExcelWriter(save_path+"/IF_Summary.xlsx", engine='xlsxwriter') as writer:
            write_conditions_table_sheet(writer, self.conditions, sheet_name="Experimental Conditions")
            write_experiment_data_list_sheet(writer, self.experiment_list, sheet_name="Data Summary")
            used_sheet_names = set(writer.sheets)
            for col in columns_to_save:
                try:
                    label, desc = convert_name(col, truncate=False)
                    # Avoid reusing the same worksheet when Excel truncates or duplicates labels.
                    sheet_name = safe_sheet_name(label, used_sheet_names)
                    column_data = {cond.name: summary[summary['Condition'] == cond.name][col] for cond in condition_list}
                    column_df = pd.DataFrame(column_data)
                    column_df_cleaned = pd.DataFrame({column: column_df[column].dropna().reset_index(drop=True) for column in column_df.columns})
                    column_df_cleaned.to_excel(writer, sheet_name=sheet_name, index=False)
                    
                    worksheet = writer.sheets[sheet_name]
                    for i, column in enumerate(column_df_cleaned):
                        worksheet.set_column(i, i, len(column) + 4)
                    last_data_row = len(column_df_cleaned) + 1
                    
                    desc_format = writer.book.add_format({
                        "italic": True,
                        "text_wrap": True,
                        "valign": "vcenter"
                    })
                    
                    if desc and len(column_df_cleaned.columns) > 0:
                        worksheet.merge_range(
                            last_data_row + 1, 0,
                            last_data_row + 1, len(column_df_cleaned.columns) - 1,
                            desc,
                            desc_format
                        )

                        desc_row = last_data_row + 1

                        # Estimate row height based on number of lines
                        n_lines = max(desc.count("\n") + 1, len(desc) // 80 + 1)
                        worksheet.set_row(desc_row, 18 * n_lines)

                except KeyError as k:
                    cols_not_included.append(col)
        print(f"Exported IF summary to {save_path+"/IF_Summary.xlsx"}")
        print(cols_not_included)
        

    def export_behavior_summary_excel(self, save_path=None):
        if save_path == None: save_path = self.export_path
        try:
            beh_df = self.data["Behaviour"].df
        except:
            return
        conditions = self.condition_list

        cols_not_included = []

        with pd.ExcelWriter(save_path+"/Behavior_Summary.xlsx", engine="xlsxwriter") as writer:
            write_conditions_table_sheet(writer, self.conditions, sheet_name="Conditions")
            used_sheet_names = set(writer.sheets)
            for col in BEHAVIOR_NAME_MAP.keys():

                if col not in beh_df.columns:
                    cols_not_included.append(col)
                    continue

                try:
                    label, desc = convert_behavior_name(col, truncate=False)
                    # Avoid reusing the same worksheet when Excel truncates or duplicates labels.
                    sheet_name = safe_sheet_name(label, used_sheet_names)

                    # Organize by condition (same pattern as imaging)
                    column_data = {
                        cond.name: beh_df.loc[beh_df["Condition"] == cond.name, col]
                        for cond in conditions
                    }

                    column_df = pd.DataFrame(column_data)
                    column_df_cleaned = pd.DataFrame({
                        c: column_df[c].dropna().reset_index(drop=True)
                        for c in column_df.columns
                    })

                    # Write table
                    column_df_cleaned.to_excel(writer, sheet_name=sheet_name, index=False)

                    worksheet = writer.sheets[sheet_name]

                    # Column widths
                    for i, c in enumerate(column_df_cleaned.columns):
                        worksheet.set_column(i, i, max(len(str(c)) + 4, 14))

                    # ---- Description BELOW the data ----
                    if desc and len(column_df_cleaned.columns) > 0:
                        last_data_row = len(column_df_cleaned) + 1
                        desc_row = last_data_row + 1

                        desc_format = writer.book.add_format({
                            "italic": True,
                            "text_wrap": True,
                            "valign": "vcenter"
                        })

                        worksheet.merge_range(
                            desc_row, 0,
                            desc_row, len(column_df_cleaned.columns) - 1,
                            desc,
                            desc_format
                        )

                        # Row height for multiline text
                        n_lines = max(desc.count("\n") + 1, len(desc) // 80 + 1)
                        worksheet.set_row(desc_row, 18 * n_lines)

                except Exception as e:
                    cols_not_included.append(col)
                    print(f"Behavior export failed for {col}: {e}")

        print(f"Exported Behavior summary to {save_path+"/Behavior_Summary.xlsx"}")
        print("Behavior columns not included:", cols_not_included)

    # ── Iteration ──────────────────────────────────────────────────────

    def __iter__(self):
        return iter(self.experiment_list)

    def __repr__(self):
        return f"Batch('{self.name}', experiments={[e.name for e in self.experiment_list]})"

    # ── Serialization ──────────────────────────────────────────────────

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop('imagesDict', None)
        state.pop('images', None)
        state.pop('image_root', None)
        state.pop('var_name', None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.imagesDict = _build_images_dict(getattr(self, "images", None))
        for exp in self.experiment_list:
            for obj in exp.data.values():
                if hasattr(obj, 'experiment'):
                    obj.experiment = exp
        for obj in self.data.values():
            if hasattr(obj, 'experiment'):
                obj.experiment = self
