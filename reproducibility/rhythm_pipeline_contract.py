"""Independent table witnesses through the public rhythm pipeline wrapper."""
from __future__ import annotations

import json
from pathlib import Path

from reproducibility import cosinor_table_contract as table_contract
from reproducibility import circular_contract
from reproducibility import dispersion_contract
from reproducibility import watson_williams_contract


CAPABILITY_PREFIXES = {
    "PyFLASH.pipeline.rhythm": ("rhythm-pipeline.cosinor.", "rhythm-pipeline.parameter."),
    "rhythm_pipeline": ("rhythm-pipeline.cosinor.", "rhythm-pipeline.parameter."),
}

PARAMETER_REQUIRED_KEYS = (
    "rhythm-pipeline.parameter.single-wraparound",
    "rhythm-pipeline.parameter.grouped-circular-tests",
    "rhythm-pipeline.parameter.two-group-welch",
    "rhythm-pipeline.parameter.three-group-kruskal",
    "rhythm-pipeline.parameter.panel-fdr",
    "rhythm-pipeline.parameter.named-family-fdr",
    "rhythm-pipeline.parameter.raw-p-gate",
    "rhythm-pipeline.parameter.fdr-gate",
    "rhythm-pipeline.parameter.radius-figure-route",
    "rhythm-pipeline.parameter.group-and-subject-aliases",
    "rhythm-pipeline.parameter.saved-run-manifest-and-reuse",
)


def cases():
    """Return accepted table cases the public pipeline can express directly."""
    table_contract.check_identity()
    return [
        {"key": "rhythm-pipeline.cosinor." + row["key"], "table_case": row}
        for row in table_contract.cases()
        if "time_map" not in row["parameters"]
    ]


def required_keys():
    return [row["key"] for row in cases()] + list(PARAMETER_REQUIRED_KEYS)


def _parameter_frame():
    """Deterministic subject-level inputs with wraparound and ordered groups."""
    import pandas as pd

    phase = {
        "A": [23.0, 23.4, 0.0, 0.4, 0.8],
        "B": [1.0, 1.4, 2.0, 2.4, 2.8],
        "C": [7.0, 7.4, 8.0, 8.4, 8.8],
    }
    scalar = {
        "A": ([1, 2, 3, 4, 5], [9, 8, 8, 7, 6]),
        "B": ([4, 5, 6, 8, 9], [7, 6, 5, 5, 4]),
        "C": ([10, 11, 12, 13, 15], [4, 3, 3, 2, 1]),
    }
    rows = []
    for group, phases in phase.items():
        for index, value in enumerate(phases):
            first, second = scalar[group]
            rows.append({"group": group, "phase": value,
                         "subject": f"{group}{index}",
                         "measure_a": first[index], "measure_b": second[index],
                         "radius": index + 1})
    return pd.DataFrame(rows)


def _groups_frame(groups):
    import pandas as pd
    return pd.DataFrame([{"group": f"G{index}", "phase": value}
                         for index, values in enumerate(groups)
                         for value in values])


def _clean(value):
    import math
    import numpy as np

    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Inf" if value > 0 else "-Inf")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _parameter_row(key, reference, actual, expected, agrees):
    return {
        "contract": key,
        "reference": reference,
        "family": "public-rhythm-parameter-mode-independent-witness",
        "status": "agree" if agrees else "disagree",
        "shape": "parameter-mode-table-fields-and-control-result",
        "missingness_equal": bool(agrees),
        "max_absolute_error": "",
        "rtol": 1e-9,
        "atol": 1e-12,
        "pyflash_nonfinite": "explicit-string-in-packed-json",
        "frozen_reference_agrees": bool(agrees),
        "pyflash_values": json.dumps(_clean(actual), sort_keys=True),
        "reference_values": json.dumps(_clean(expected), sort_keys=True),
    }


def _same_number(actual, expected, *, atol=1e-10, rtol=1e-9):
    import math
    try:
        a, b = float(actual), float(expected)
    except (TypeError, ValueError):
        return actual == expected
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    if math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) <= atol + rtol * abs(b)


def _records_agree(actual, expected):
    return set(actual) == set(expected) and all(
        _same_number(actual[key], expected[key]) if isinstance(expected[key], (int, float))
        else actual[key] == expected[key]
        for key in expected)


def _student_two_tail(statistic, degrees):
    import mpmath as mp
    with mp.workdps(70):
        t, df = mp.mpf(str(abs(statistic))), mp.mpf(str(degrees))
        x = df / (df + t*t)
        return float(mp.betainc(df/2, mp.mpf("0.5"), 0, x, regularized=True))


def _average_ranks(values):
    order = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    first = 0
    while first < len(order):
        last = first + 1
        while last < len(order) and values[order[last]] == values[order[first]]:
            last += 1
        average = (first + 1 + last) / 2
        for position in order[first:last]:
            result[position] = average
        first = last
    return result


def _scalar_reference(frame, column, groups):
    """Independent full-record reference for _rhythm_param_tests."""
    import math
    import mpmath as mp
    import numpy as np

    vectors = []
    for group in groups:
        values = frame.loc[frame.group.astype(str) == str(group), column]
        numeric = np.asarray(values, dtype=float)
        vectors.append(numeric[~np.isnan(numeric)])
    present = [(group, values) for group, values in zip(groups, vectors) if len(values) >= 2]
    n = sum(len(values) for values in vectors)
    record = {"parameter": str(column), "n": int(n)}
    record.update({f"mean_{group}": float(np.mean(values)) if len(values) else math.nan
                   for group, values in zip(groups, vectors)})
    if len(present) < 2:
        record.update(test="skipped (n<2 in >=2 groups)", statistic=math.nan,
                      p_value=math.nan, trend_rho=math.nan, trend_p=math.nan)
        return record

    present_groups = [group for group, _ in present]
    arrays = [values for _, values in present]
    if len(arrays) == 2:
        a, b = arrays
        va, vb = np.var(a, ddof=1), np.var(b, ddof=1)
        av, bv = va / len(a), vb / len(b)
        se2 = av + bv
        degrees = se2**2 / (av**2/(len(a)-1) + bv**2/(len(b)-1))
        statistic = (np.mean(a)-np.mean(b)) / math.sqrt(se2)
        p_value = _student_two_tail(statistic, degrees)
        test = "Welch t"
    else:
        pooled = [float(value) for values in arrays for value in values]
        ranks = _average_ranks(pooled)
        sizes = [len(values) for values in arrays]
        n_all = len(pooled)
        offset, rank_sums = 0, []
        for size in sizes:
            rank_sums.append(sum(ranks[offset:offset+size]))
            offset += size
        h0 = 12 * sum(rank_sum**2/size for rank_sum, size in zip(rank_sums, sizes)) / (n_all*(n_all+1)) - 3*(n_all+1)
        tie_sizes = {}
        for value in pooled:
            tie_sizes[value] = tie_sizes.get(value, 0) + 1
        correction = 1 - sum(size**3-size for size in tie_sizes.values())/(n_all**3-n_all)
        statistic = h0/correction if correction else math.nan
        with mp.workdps(70):
            p_value = float(mp.gammainc(mp.mpf(len(arrays)-1)/2,
                                        mp.mpf(str(statistic))/2, mp.inf,
                                        regularized=True))
        test = "Kruskal-Wallis"

    codes = {group: index for index, group in enumerate(groups)}
    trend_codes = [codes[group] for group, values in present for _ in values]
    trend_values = [float(value) for _, values in present for value in values]
    rank_x, rank_y = _average_ranks(trend_codes), _average_ranks(trend_values)
    count = len(rank_x)
    mx, my = sum(rank_x)/count, sum(rank_y)/count
    cov = sum((x-mx)*(y-my) for x, y in zip(rank_x, rank_y))
    sx = math.sqrt(sum((x-mx)**2 for x in rank_x))
    sy = math.sqrt(sum((y-my)**2 for y in rank_y))
    rho = cov/(sx*sy) if sx and sy else math.nan
    if not math.isfinite(rho) or count <= 2:
        trend_p = math.nan
    elif abs(rho) >= 1:
        trend_p = 0.0
    else:
        trend_t = rho * math.sqrt((count-2)/(1-rho*rho))
        trend_p = _student_two_tail(trend_t, count-2)
    record.update(test=test, statistic=float(statistic), p_value=float(p_value),
                  trend_rho=float(rho), trend_p=float(trend_p))
    return record


def _run_parameter(frame, **kwargs):
    import matplotlib
    matplotlib.use("Agg", force=True)
    from PyFLASH.pipeline import rhythm
    return rhythm(frame, phase_col="phase", group_col="group", period=24.0,
                  save=False, write_manifest=False, montage=False,
                  run_label="rhythm-parameter-contract", **kwargs)


def _validate_parameter(output):
    """Execute the declared parameter-mode requirements against independent references."""
    import math
    from pathlib import Path
    import numpy as np
    from reproducibility import multiplicity_contract

    frame = _parameter_frame()
    rows, retained = [], []

    # Circular summaries are checked against high-precision geometry, while
    # the two group tests use the independent Watson-Williams and Wallraff
    # mathematical witnesses already exercised as public statistics contracts.
    result = _run_parameter(frame)
    circular_actual = result["circular_phase_stats"].set_index("group")
    for group in result["groups"]:
        data = frame.loc[frame.group == group, "phase"].tolist()
        witness = {"parameters": {"values": data, "period": 24.0}}
        expected = circular_contract.mathematical(witness)
        actual = circular_actual.loc[group]
        mean_angle = float(actual["mean_phase"]) * 2 * math.pi / 24
        actual_coords = [int(actual["n"]), math.cos(mean_angle), math.sin(mean_angle),
                         float(actual["resultant_r"]), float(actual["rayleigh_z"]),
                         float(actual["rayleigh_p"])]
        expected_coords = circular_contract.coordinates(expected, 24.0)
        agrees = len(actual_coords) == len(expected_coords) and all(
            _same_number(a, e) for a, e in zip(actual_coords, expected_coords))
        key = "rhythm-pipeline.parameter.single-wraparound"
        actual_record = {"group": group, "values": actual_coords}
        ref_record = {"group": group, "values": expected_coords}
        if group == "A":
            rows.append(_parameter_row(key, "80-digit circular geometry and pinned Astropy/native references",
                                       [actual_record], [ref_record], agrees))
        else:
            rows[-1]["status"] = "agree" if rows[-1]["status"] == "agree" and agrees else "disagree"
            rows[-1]["missingness_equal"] = rows[-1]["status"] == "agree"
            rows[-1]["frozen_reference_agrees"] = rows[-1]["missingness_equal"]
            rows[-1]["pyflash_values"] = json.dumps(_clean(json.loads(rows[-1]["pyflash_values"]) + [actual_record]), sort_keys=True)
            rows[-1]["reference_values"] = json.dumps(_clean(json.loads(rows[-1]["reference_values"]) + [ref_record]), sort_keys=True)

    ww_case = next(case for case in watson_williams_contract.cases()
                   if case["key"] == "watson.williams.separated.24.0")
    ww_expected = watson_williams_contract.mathematical(ww_case)
    ww_frame = _groups_frame(ww_case["parameters"]["groups"])
    ww_run = _run_parameter(ww_frame)
    ww_actual = ww_run["phase_group_test"].set_index("test").loc["Watson-Williams (mean)"]
    ww_fields = ["F", "p", "df1", "df2", "k", "n", "R"]
    ww_values = [ww_actual.get(field, np.nan) for field in ww_fields]
    ww_agrees = all(_same_number(a, e) for a, e in zip(ww_values, ww_expected[:7]))
    dispersion_case = next(case for case in dispersion_contract.cases()
                           if case["key"] == "circular.dispersion.ordinary.24.0")
    dispersion_expected = dispersion_contract.mathematical(dispersion_case)
    dispersion_frame = _groups_frame(dispersion_case["parameters"]["groups"])
    dispersion_run = _run_parameter(dispersion_frame)
    dispersion_actual = dispersion_run["phase_group_test"].set_index("test").loc["Wallraff (dispersion)"]
    dispersion_values = [dispersion_actual["statistic"], dispersion_actual["p"],
                         dispersion_actual["k"], dispersion_actual["n"]]
    dispersion_agrees = all(_same_number(a, e) for a, e in
                            zip(dispersion_values, dispersion_expected[:4]))
    grouped_agrees = ww_agrees and dispersion_agrees
    rows.append(_parameter_row(
        "rhythm-pipeline.parameter.grouped-circular-tests",
        "independent high-precision Watson-Williams and Wallraff witnesses",
        {"watson_williams": ww_values, "dispersion": dispersion_values},
        {"watson_williams": ww_expected[:7], "dispersion": dispersion_expected[:4]},
        grouped_agrees))

    # Reconstruct every scalar output field, including group means, sample
    # counts, trend estimates and probabilities. The t and chi-square tails use
    # high-precision incomplete beta/gamma evaluation, not SciPy's test calls.
    two = _run_parameter(frame[frame.group.isin(["A", "B"])], param_cols=["measure_a"])
    two_row = two["parameter_tests"].iloc[0]
    welch_expected = _scalar_reference(frame[frame.group.isin(["A", "B"])],
                                       "measure_a", two["groups"])
    welch_actual = {key: two_row[key] for key in welch_expected}
    rows.append(_parameter_row("rhythm-pipeline.parameter.two-group-welch",
        "independent complete Welch-Satterthwaite record and high-precision Student-t tail",
        welch_actual, welch_expected,
        _records_agree(welch_actual, welch_expected)))

    three = _run_parameter(frame, param_cols=["measure_a"])
    three_row = three["parameter_tests"].iloc[0]
    kruskal_expected = _scalar_reference(frame, "measure_a", three["groups"])
    kruskal_actual = {key: three_row[key] for key in kruskal_expected}
    rows.append(_parameter_row("rhythm-pipeline.parameter.three-group-kruskal",
        "independent full-table pooled-rank Kruskal-Wallis with tie correction and trend",
        kruskal_actual, kruskal_expected,
        _records_agree(kruskal_actual, kruskal_expected)))

    # BH q-values are recomputed by the rational reference implementation.
    panel = _run_parameter(frame, param_cols=["measure_a", "measure_b"], screen=True)
    panel_table = panel["parameter_tests"].set_index("parameter")
    panel_names = ("measure_a", "measure_b")
    scalar_panel_expected = {name: _scalar_reference(frame, name, panel["groups"])
                             for name in panel_names}
    panel_records_actual = {name: {"parameter": name, **{
        field: panel_table.loc[name, field] for field in scalar_panel_expected[name]
        if field != "parameter"}} for name in panel_names}
    raw = [scalar_panel_expected[name]["p_value"] for name in panel_names]
    panel_case = {"canonical": "fdr_bh", "parameters": {
        "pvalues": raw, "labels": ["measure_a", "measure_b"], "families": None,
        "alpha": 0.05}}
    panel_expected = multiplicity_contract.reference(panel_case)
    panel_q = [float(panel_table.loc[name, "p_adjusted"]) for name in panel_names]
    panel_ref_q = [panel_expected[1 + len(raw)], panel_expected[2 + len(raw)]]
    panel_ok = (all(_records_agree(panel_records_actual[name], scalar_panel_expected[name])
                    for name in panel_names) and
                all(_same_number(a, b) for a, b in zip(panel_q, panel_ref_q)))
    rows.append(_parameter_row("rhythm-pipeline.parameter.panel-fdr",
        "complete independent scalar records and exact-rational Benjamini-Hochberg family",
        {"records": panel_records_actual, "q": panel_q},
        {"records": scalar_panel_expected, "q": panel_ref_q}, panel_ok))

    families = {"measure_a": "phase", "measure_b": "amplitude"}
    named = _run_parameter(frame, param_cols=["measure_a", "measure_b"], screen=True,
                           families=families)
    named_table = named["parameter_tests"].set_index("parameter")
    named_raw = [scalar_panel_expected[name]["p_value"] for name in families]
    named_case = {"canonical": "fdr_bh", "parameters": {
        "pvalues": named_raw, "labels": list(families),
        "families": [families[name] for name in families], "alpha": 0.05}}
    named_q = [float(named_table.loc[name, "p_adjusted"]) for name in families]
    # Each named family has one member here, so the exact BH correction is q=p.
    # Keep this separate from the panel-wide two-member reference above.
    named_ref_q = list(named_raw)
    named_records_actual = {name: {"parameter": name, **{
        field: named_table.loc[name, field] for field in scalar_panel_expected[name]
        if field != "parameter"}} for name in families}
    named_ok = (all(_records_agree(named_records_actual[name], scalar_panel_expected[name])
                    for name in families) and
                all(_same_number(a, b) for a, b in zip(named_q, named_ref_q)))
    rows.append(_parameter_row("rhythm-pipeline.parameter.named-family-fdr",
        "independent full scalar records and exact BH within singleton named families",
        {"families": list(families.values()), "records": named_records_actual, "q": named_q},
        {"families": list(families.values()), "records": scalar_panel_expected, "q": named_ref_q},
        named_ok))

    raw_gate = _run_parameter(frame, param_cols=["measure_a", "measure_b"],
                              screen=True, gate="p", alpha=0.05)
    independent_raw_p = [_scalar_reference(frame, column, raw_gate["groups"])["p_value"]
                         for column in ("measure_a", "measure_b")]
    raw_expected = sum(p < 0.05 for p in independent_raw_p)
    raw_significant = int(raw_gate["n_significant"])
    rows.append(_parameter_row("rhythm-pipeline.parameter.raw-p-gate",
        "declared raw-p gate semantics", raw_gate["n_significant"], raw_expected,
        raw_gate["n_significant"] == raw_significant == raw_expected))

    fdr_gate = _run_parameter(frame, param_cols=["measure_a", "measure_b"],
                              screen=True, gate="fdr", alpha=0.05)
    fdr_significant = int((fdr_gate["parameter_tests"]["p_adjusted"] < 0.05).sum())
    fdr_reference_significant = sum(q < 0.05 for q in panel_ref_q)
    rows.append(_parameter_row("rhythm-pipeline.parameter.fdr-gate",
        "declared FDR gate semantics with duplicate raw-p and q columns",
        {"n_significant": fdr_gate["n_significant"],
         "raw_p_preserved": "p_value" in fdr_gate["parameter_tests"],
         "q_present": "p_adjusted" in fdr_gate["parameter_tests"]},
        {"n_significant": fdr_reference_significant, "raw_p_preserved": True, "q_present": True},
        fdr_gate["n_significant"] == fdr_significant == fdr_reference_significant and
        "p_value" in fdr_gate["parameter_tests"] and
        "p_adjusted" in fdr_gate["parameter_tests"]))

    # Track the real plotting route with save disabled so this verification
    # creates no image artifact.
    from PyFLASH import pipeline
    original_plot = pipeline.plot_acrophase_clock
    radius_calls = []
    def tracked_plot(*args, **kwargs):
        radius_calls.append(kwargs.get("radius_col"))
        return original_plot(*args, **kwargs)
    pipeline.plot_acrophase_clock = tracked_plot
    try:
        radius_result = _run_parameter(frame, radius_col="radius")
    finally:
        pipeline.plot_acrophase_clock = original_plot
    radius_expected = [None, "radius"]
    rows.append(_parameter_row("rhythm-pipeline.parameter.radius-figure-route",
        "public plotting adapter call trace with figures unsaved", radius_calls,
        radius_expected, radius_calls == radius_expected and
        radius_result["mode"] == "parameter"))

    alias_frame = frame.rename(columns={"group": "Diagnosis", "subject": "Animal"})
    alias_result = pipeline.rhythm(alias_frame, phase_col="phase", group_cols=["Diagnosis"],
        subject_col="Animal", period=24.0, save=False, write_manifest=False,
        montage=False, run_label="rhythm-alias-contract")
    rows.append(_parameter_row("rhythm-pipeline.parameter.group-and-subject-aliases",
        "public dataframe group_cols and subject_col aliases",
        {"group_col": alias_result["group_col"], "groups": alias_result["groups"],
         "mode": alias_result["mode"]},
        {"group_col": "Diagnosis", "groups": ["A", "B", "C"], "mode": "parameter"},
        alias_result["group_col"] == "Diagnosis" and
        alias_result["groups"] == ["A", "B", "C"] and
        alias_result["mode"] == "parameter"))

    # Exercise actual manifest creation and skip/reuse while intercepting the
    # plotting writer. The parameter tables and persisted manifest are real.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    root = output / "saved-run-reuse"
    root.mkdir(parents=True, exist_ok=True)
    saved_frame = frame.copy()
    original_plot = pipeline.plot_acrophase_clock
    def no_file_plot(*args, **kwargs):
        kwargs["save"] = False
        return original_plot(*args, **kwargs)
    pipeline.plot_acrophase_clock = no_file_plot
    try:
        first = pipeline.rhythm(saved_frame, phase_col="phase", group_col="group",
            param_cols=["measure_a"], period=24.0, save=True, write_manifest=True,
            montage=False, run_label="persisted-parameter-contract",
            dataframe_kwargs={"fig_path": str(root), "data_path": str(root)})
        manifest_path = Path(first["data_dir"]) / "manifest.json"
        persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
        second = pipeline.rhythm(saved_frame, phase_col="phase", group_col="group",
            param_cols=["measure_a"], period=24.0, save=True, write_manifest=True,
            montage=False, run_label="persisted-parameter-contract", if_exists="skip",
            dataframe_kwargs={"fig_path": str(root), "data_path": str(root)})
        reuse_actual = {"manifest": persisted.get("pipeline"),
                        "reused": second.get("reused"),
                        "run_label": second.get("run_label")}
        reuse_expected = {"manifest": "rhythm", "reused": True,
                          "run_label": "persisted-parameter-contract"}
        reuse_ok = reuse_actual == reuse_expected
    finally:
        pipeline.plot_acrophase_clock = original_plot
    rows.append(_parameter_row("rhythm-pipeline.parameter.saved-run-manifest-and-reuse",
        "saved public manifest and if_exists=skip reuse", reuse_actual,
        reuse_expected, reuse_ok))

    from PyFLASH._persistence import write_json
    write_json(output / "rhythm-parameter-paired-data.json", {
        "scope": "public parameter-mode pipeline outputs and option controls",
        "inputs": frame.to_dict(orient="records"),
        "rows": rows,
        "saved_manifest": persisted,
        "saved_manifest_path": str(manifest_path),
        "saved_run_reuse": reuse_actual,
    })

    return rows


def _packed_records(frame):
    return {
        "columns": [column for column in frame.columns if column != "column"],
        "records": frame.drop(columns=["column"]).to_dict(orient="records"),
    }


def compare_case(declared, index=0):
    """Compare one public-pipeline result with its independent table answer."""
    import matplotlib
    matplotlib.use("Agg", force=True)
    import pandas as pd
    from PyFLASH.pipeline import rhythm

    case = declared["table_case"]
    parameters = case["parameters"]
    frame = pd.DataFrame(parameters["records"], columns=parameters["columns"])
    expected = table_contract.expected(case)
    try:
        result = rhythm(
            frame,
            data_cols=[parameters["value_col"]],
            time_col=parameters["time_col"],
            group_col=parameters["group_col"],
            animal_col=parameters["animal_col"],
            period=parameters.get("period", 24.0),
            period_free=parameters.get("period_free", False),
            method=parameters["method"],
            save=False,
            write_manifest=False,
            montage=False,
            run_label=f"rhythm-contract-{index:04d}",
        )
        table = result.get("cosinor_parameters")
        if table is None or "column" not in table.columns:
            raise ValueError("pipeline omitted its cosinor_parameters table")
        actual = _packed_records(table)
        agrees = (
            actual["columns"] == expected["columns"]
            and table_contract.equal(actual["records"], expected["records"])
            and result["mode"] == "cosinor"
            and result["method"] == parameters["method"]
            and result["period"] == float(parameters.get("period", 24.0))
            and result["period_free"] == bool(parameters.get("period_free", False))
        )
    except Exception as error:
        actual = {"error": type(error).__name__ + ": " + str(error)}
        agrees = False
    packed_actual = table_contract.packed(actual)
    packed_expected = table_contract.packed(expected)
    row = {
        "contract": declared["key"],
        "reference": "identity-checked-independent-cosinor-table-answers",
        "family": "public-rhythm-pipeline-composed-native-and-mathematical-table-reference",
        "status": "agree" if agrees else "disagree",
        "shape": "ordered-complete-table-schema-rows-and-manifest-settings",
        "missingness_equal": agrees,
        "max_absolute_error": "",
        "rtol": 1e-9,
        "atol": 1e-12,
        "pyflash_nonfinite": "explicit-in-packed-rows",
        "frozen_reference_agrees": True,
        "pyflash_values": json.dumps(packed_actual, sort_keys=True),
        "reference_values": json.dumps(packed_expected, sort_keys=True),
    }
    retained = {"case": case, "production": packed_actual,
                "reference": packed_expected, "agrees": agrees}
    return row, retained


def validate_cases(output, declared_cases=None):
    """Compare selected public pipeline tables with independent answers."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    table_contract.check_identity()
    declarations = cases() if declared_cases is None else list(declared_cases)
    rows, retained = [], []
    for index, declared in enumerate(declarations):
        row, record = compare_case(declared, index)
        rows.append(row)
        retained.append(record)
    parameter_rows = _validate_parameter(output)
    rows.extend(parameter_rows)
    from PyFLASH._persistence import write_json
    write_json(output / "rhythm-pipeline-paired-data.json", {
        "scope": "cosinor mode, fixed/free periods and pooled/population/mixed methods, plus parameter-mode circular and scalar tests, correction gates, aliases, figure routing and saved-run reuse; time-map inputs are outside this wrapper's public signature",
        "independent_table_fixture": str(table_contract.FIXTURE),
        "rows": retained,
        "parameter_rows": parameter_rows,
    })
    return rows


def validate(output):
    """Compare every pipeline cosinor table with its independent answer."""
    return validate_cases(output)
