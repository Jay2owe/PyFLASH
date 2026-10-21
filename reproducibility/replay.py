"""Fresh-process execution of the actual exported UI script, complete reports.

Inputs: supplied demo copied into a new review directory. Outputs: unchanged
script, full paired tables/reports, log and content-checked replay receipt.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from reproducibility.run import ROOT, python_command, write_json, sha256


def verify(output):
    import pandas as pd
    from PyFLASH import report
    from PyFLASH.ui import workspace
    from PyFLASH.spec import _resolve_func,PLOT_REGISTRY
    output.mkdir(parents=True,exist_ok=False)
    source = output/"subjects.csv"
    shutil.copyfile(ROOT/"demo"/"data"/"summary.csv",source)
    parameters = {"data_cols":["Signal_MeanIntensity","DAPI_MeanIntensity"],
                  "stats_test":"welch","save":False,"dry_run":True,"save_normality":False}
    experiment = workspace.load_table(source,demo=True)
    report.start()
    result = _resolve_func(PLOT_REGISTRY["mean_bars"])(experiment,**parameters)
    records = report.coerce(report.collect())
    result.to_csv(output/"ui-result.csv",index=False)
    write_json(output/"ui-statistics.json",records)
    script = workspace.equivalent_script(source,"mean_bars",parameters,source_kind="csv")
    (output/"ui-export.py").write_text(script,encoding="utf-8")
    # The exported script is executed unchanged. The checking wrapper arms the
    # existing collector and retains every returned/report field afterwards.
    wrapper = """import json, runpy
from pathlib import Path
from PyFLASH import report
report.start()
namespace = runpy.run_path('ui-export.py')
namespace['result'].to_csv('fresh-result.csv',index=False)
Path('fresh-statistics.json').write_text(json.dumps(report.coerce(report.collect()),indent=2),encoding='utf-8')
"""
    (output/"verify-export.py").write_text(wrapper,encoding="utf-8")
    env = dict(os.environ,MPLBACKEND="Agg",PYTHONIOENCODING="utf-8")
    # The unchanged exported script must consume this checked package, including
    # when the workflow owns a frozen checkout rather than the editable install.
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT), *filter(None, [env.get('PYTHONPATH')])])
    completed = subprocess.run(python_command()+[str(output/"verify-export.py")],cwd=output,
                               env=env,capture_output=True,text=True,encoding="utf-8")
    (output/"replay.log").write_text(completed.stdout+completed.stderr,encoding="utf-8")
    error = None
    try:
        if completed.returncode:
            raise AssertionError(f"Exported script failed; see replay.log ({completed.returncode})")
        original = pd.read_csv(output/"ui-result.csv")
        fresh = pd.read_csv(output/"fresh-result.csv")
        pd.testing.assert_frame_equal(original,fresh,check_exact=True)
        fresh_records = json.loads((output/"fresh-statistics.json").read_text(encoding="utf-8"))
        assert records == fresh_records,"Full scientific report changed across identical runs."
        assert len(records) == 2,"Both displayed metric reports must be checked."
    except Exception as exc:
        error = str(exc)
    write_json(output/"replay-report.json",{"passed":error is None,"error":error,
        "parameters":parameters,"input_sha256":sha256(source),"script_sha256":sha256(output/"ui-export.py"),
        "rows":len(result),"report_count":len(records),"checked":"all returned cells and every complete scientific report field"})
    if error:
        raise AssertionError(error)
    print("Unchanged UI-exported script reproduced every result/report field in a fresh process.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    verify(parser.parse_args().output.resolve())
