"""One registry for independent full-report validators and focused replay."""
from importlib import import_module

FAMILIES={
    'batch-excel-summary-lifecycle':'reproducibility.excel_summary_lifecycle_contract',
    'batch-excel-filter-controls':'reproducibility.excel_filter_controls_contract',
    'public-condition-key':'reproducibility.condition_key_contract',
    'dataframe-whole-client':'reproducibility.dataframe_whole_contract',
    'dataframe-comparison-requests':'reproducibility.dataframe_comparison_contract',
    'dataframe-metadata-ownership':'reproducibility.dataframe_metadata_contract',
    'dataframe-condition-recoding':'reproducibility.dataframe_recoding_contract',
    'whole-batch-excel-routing':'reproducibility.excel_orchestration_contract',
    'batch-excel-workbook-schemas':'reproducibility.excel_workbook_schema_contract',
    'batch-excel-literal-cells':'reproducibility.excel_literal_cell_contract',
    'batch-excel-coupled-client':'reproducibility.excel_coupled_contract',
    'batch-excel-direct-destinations':'reproducibility.excel_destination_contract',
    'batch-excel-direct-regions':'reproducibility.excel_region_selection_contract',
    'batch-excel-measurement-maps':'reproducibility.excel_measurement_map_contract',
    'batch-excel-all-mapping-workbooks':'reproducibility.excel_all_mapping_workbook_contract',
    'batch-excel-positive-label-semantics':'reproducibility.excel_positive_label_semantics_contract',
    'batch-excel-mean-wording-semantics':'reproducibility.excel_mean_wording_semantics_contract',
    'batch-excel-distance-presentation':'reproducibility.excel_distance_presentation_contract',
    'public-ecdf':'reproducibility.ecdf_public_contract',
    'public-ecdf-regions':'reproducibility.marker_region_contract',
    'public-ecdf-factor-regions':'reproducibility.marker_factor_region_contract',
    'object-window-means':'reproducibility.object_mean_contract',
    'marker-thresholds':'reproducibility.marker_threshold_contract',
    'whole-colocalisation-annotation':'reproducibility.coloc_annotation_contract',
    'marker-nearest-tables':'reproducibility.marker_nearest_contract',
    'marker-calibration-tables':'reproducibility.marker_calibration_contract',
    'experiment-nearest-tables':'reproducibility.experiment_nearest_contract',
    'ventricle-native-tables':'reproducibility.ventricle_native_contract',
    'summary-area-native-tables':'reproducibility.summary_area_contract',
    'ordinal-binary-glm':'reproducibility.ordinal_binary_glm_contract',
    'ordinal-inputs':'reproducibility.ordinal_input_contract',
    'outlier-requests':'reproducibility.outlier_request_contract',
    'outlier-subject-identity':'reproducibility.outlier_subject_identity_contract',
    'outlier-ledger-source':'reproducibility.outlier_ledger_source_contract',
    'outlier-options':'reproducibility.outlier_options_contract',
    'excel-region':'reproducibility.excel_region_contract',
    'excel-index':'reproducibility.excel_export_contract',
    'dataframe-identifiers':'reproducibility.dataframe_identifier_contract',
    'association-fisher':'reproducibility.association_fisher_contract',
    'csv-export':'reproducibility.csv_export_contract',
    'association-intervals':'reproducibility.association_interval_contract',
    'experiment-metadata':'reproducibility.experiment_metadata_contract',
    'inherited-mini-metadata':'reproducibility.inherited_mini_metadata_contract',
    'whole-region-assignment':'reproducibility.region_assignment_contract',
    'surface-volume-unit-semantics':'reproducibility.surface_volume_unit_contract',
    'inherited-mini-csv':'reproducibility.inherited_mini_csv_contract',
    'inherited-spatial-consumers':'reproducibility.inherited_spatial_contract',
    'inherited-roi-consumers':'reproducibility.inherited_roi_contract',
    'direct-scientific-utilities':'reproducibility.scientific_utility_contract',
    'dataframe-lifecycle':'reproducibility.dataframe_lifecycle_contract',
    'scientific-geometry-primitives':'reproducibility.scientific_geometry_contract',
    'experiment-folder-discovery':'reproducibility.experiment_path_contract',
    'normality-and-requests':'reproducibility.normality_association_validation',
    'pooled-normality-reports':'reproducibility.normality_parent_validation',
    'group-normality-boundaries':'reproducibility.group_normality_boundary_contract',
    'group-comparison-inference':'reproducibility.comparison_parent_inference_contract',
    'group-comparison-routing':'reproducibility.comparison_parent_routing_contract',
    'group-comparison-model-scope':'reproducibility.comparison_parent_model_scope_contract',
    'group-comparison-auto-scope':'reproducibility.comparison_parent_auto_scope_contract',
    'group-comparison-point-effects':'reproducibility.comparison_parent_effect_contract',
    'group-comparison-intervals':'reproducibility.parent_interval_contract',
    'group-comparison-design-cache':'reproducibility.comparison_parent_cache_contract',
    'group-comparison-model-records':'reproducibility.comparison_parent_record_contract',
    'comparison-drawing':'reproducibility.comparison_geometry_contract',
    'public-mean-bars':'reproducibility.mean_bars_contract',
    'group-descriptions':'reproducibility.group_description_contract',
    'group-comparison-records':'reproducibility.comparison_record_contract',
    'group-comparison-record-audits':'reproducibility.comparison_record_audit_contract',
    'regression-records':'reproducibility.regression_record_contract',
    'report-serialization':'reproducibility.report_serialization_contract',
    'record-digests':'reproducibility.record_digest_contract',
    'report-collection':'reproducibility.collector_contract',
    'ordinal-parameters':'reproducibility.ordinal_parameter_contract',
    'ordinal-zero-controls':'reproducibility.ordinal_zero_contract',
    'ordinal-native-fitting':'reproducibility.ordinal_fitting_contract',
    'ordinal-response-controls':'reproducibility.ordinal_response_contract',
    'ordinal-constant-controls':'reproducibility.ordinal_constant_contract',
    'growth':'reproducibility.growth_full_validation',
    'outliers':'reproducibility.outlier_validation',
    'effect-reports':'reproducibility.effect_report_validation',
    'effect-interval-scales':'reproducibility.scale_interval_contract',
    'control-and-units':'reproducibility.dunnett_validation',
    'effect-inputs':'reproducibility.scalar_input_contract',
    'presentation-and-cache':'reproducibility.presentation_cache_contract',
    'variance-and-student':'reproducibility.variance_student_validation',
    'mann-whitney':'reproducibility.mann_whitney_validation',
    'report-presentation':'reproducibility.print_export_contract',
    'one-way-reports':'reproducibility.one_way_validation',
    'unequal-variance-anova':'reproducibility.welch_one_way_validation',
    'finite-inference':'reproducibility.extreme_inference_contract',
    'rank-reports':'reproducibility.rank_validation',
    'two-factor-reports':'reproducibility.two_way_validation',
    'rank-correction-reports':'reproducibility.audit_parent_contract',
    'linear-model-reports':'reproducibility.linear_model_validation',
    'public-linear-parent-science':'reproducibility.linear_parent_contract',
    'public-linear-coefficient-drawing':'reproducibility.linear_forest_contract',
    'scalar-corrections':'reproducibility.scalar_multiplicity_contract',
    'slope-comparisons':'reproducibility.interaction_slope_validation',
    'manual-exclusions':'reproducibility.manual_exclusion_contract',
    'mini-scientific-tables':'reproducibility.mini_scientific_contract',
    'mini-summary-exclusions-and-scores':'reproducibility.mini_summary_routes_contract',
    'mini-flat-csv-lifecycle':'reproducibility.mini_lifecycle_contract',
    'whole-mini-summary':'reproducibility.mini_summary_whole_contract',
    'mini-acquired-image-conditions':'reproducibility.mini_image_condition_contract',
    'literal-factors-and-table-ownership':'reproducibility.parent_ownership_contract',
    'mini-flat-csv-refresh':'reproducibility.mini_csv_refresh_contract',
    'empty-parent-tables':'reproducibility.empty_parent_contract',
    'marker-table-assignment':'reproducibility.marker_assignment_contract',
    'display-summary-functional':'reproducibility.display_summary_contract',
    'whole-roi-analysis':'reproducibility.roi_analysis_contract',
    'mixed-mean-fidelity':'reproducibility.mixed_mean_fidelity_contract',
    'whole-parent-conditions':'reproducibility.whole_condition_contract',
    'whole-mini-conditions':'reproducibility.mini_condition_whole_contract',
    'whole-image-tables':'reproducibility.image_table_contract',
    'whole-image-import':'reproducibility.image_import_whole_contract',
    'whole-marker-cleaning-options':'reproducibility.marker_cleaning_options_contract',
    'whole-marker-cleaning-edges':'reproducibility.marker_cleaning_edges_contract',
    'whole-marker-cleaning':'reproducibility.marker_cleaning_whole_contract',
    'whole-axis-bound-policy':'reproducibility.axis_bound_contract',
    'whole-trace-policy':'reproducibility.trace_policy_contract',
    'whole-window-carriers':'reproducibility.window_carrier_contract',
}

def validate_family(name,output):
    import sys
    from PyFLASH import report
    caller_bytecode_policy=sys.dont_write_bytecode
    caller_state=report._STATE
    # Retained executable-cache bytes are evidence, not writable working files.
    # Keep source identity checks strict and prevent imports from regenerating
    # those caches in either serial or resident process-pool execution.
    sys.dont_write_bytecode=True
    report._STATE={"active":False,"records":[],"origins":[]}
    try:
        return import_module(FAMILIES[name]).validate(output)
    finally:
        sys.dont_write_bytecode=caller_bytecode_policy
        report._STATE=caller_state

class ReferenceFamilyFailure(RuntimeError):
    """A failed full pass retains completed comparisons from independent families."""
    def __init__(self, partial_rows, failures):
        self.partial_rows = list(partial_rows)
        self.family_failures = list(failures)
        super().__init__("Independent reference families failed: " +
                         "; ".join(item["name"] + ": " + item["error"] for item in failures))


def validate_all(output):
    import hashlib, os, traceback
    from pathlib import Path
    from PyFLASH._persistence import write_json
    output = Path(output)
    from reproducibility.workflow import request, run_families
    configuration = request(output)
    if configuration:
        return run_families(output, list(FAMILIES), configuration['identity'],
                            previous=configuration['previous'], workers=configuration['workers'],
                            fresh=configuration['fresh'])
    rows, failures, progress = [], [], []
    for name in FAMILIES:
        entry = {"name": name, "module": FAMILIES[name], "status": "running",
                 "owner_pid": os.getpid(), "comparisons": 0}
        progress.append(entry)
        write_json(output / "reference-family-progress.json", progress)
        try:
            # Families may execute the same public case to check different
            # obligations. Each execution owns its files and failure evidence.
            family_output = output / "reference-family-output" / name
            family_output.mkdir(parents=True, exist_ok=False)
            completed = validate_family(name, family_output)
            if not completed:
                raise ValueError("Required reference family produced no comparisons.")
            ledger = output / "reference-family-rows" / (name + ".json")
            write_json(ledger, {"name": name, "rows": completed})
            entry.update(status="completed", comparisons=len(completed),
                         rows_file=str(ledger.relative_to(output)),
                         rows_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest())
            rows.extend(completed)
        except Exception as error:
            entry.update(status="execution-failure", error=type(error).__name__ + ": " + str(error),
                         traceback=traceback.format_exc())
            failures.append(dict(entry))
        write_json(output / "reference-family-progress.json", progress)
    if failures:
        raise ReferenceFamilyFailure(rows, failures)
    return rows
