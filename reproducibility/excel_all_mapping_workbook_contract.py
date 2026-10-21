"""Actual complete workbooks for all 96 declared maps; supporting transport only."""
import hashlib
import json
from pathlib import Path

from reproducibility import excel_coupled_contract as coupled

ARCHIVE=Path(__file__).with_name('reference-sources')/'excel-all-mapping-workbooks/v6'
MANIFEST_SHA256='268cf8fa21bea053c56769b3f5d40b1715697eb562a0c11d3f69f1e55d410d35'
COMPLETE_CAPABILITIES=frozenset()
CAPABILITY_PREFIXES={capability:('excel-all-mapping-workbook.'+capability.rsplit('.',1)[-1]+'.',)
                     for capability in coupled.CAPABILITY_PREFIXES}

def check_identity():
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(ARCHIVE/'source-manifest.json')!=MANIFEST_SHA256:
        raise ValueError('Original all-mapping workbook manifest changed')
    for name,value in json.loads((ARCHIVE/'source-manifest.json').read_text(encoding='utf-8')).items():
        if sha(ARCHIVE/name)!=value:
            raise ValueError('Original all-mapping workbook evidence changed: '+name)
    return json.loads((ARCHIVE/'client-reference.json').read_text(encoding='utf-8'))

def cases():
    rows=check_identity()['rows']
    for row in rows:
        row['_case_digest']=hashlib.sha256(json.dumps(row,sort_keys=True,allow_nan=False).encode('utf-8')).hexdigest()
    return rows

def required_keys(capability):
    method=capability.rsplit('.',1)[-1]
    return {row['key'] for row in cases() if row['method']==method}

def check_mapping_inventory():
    from reproducibility import excel_measurement_map_contract as display
    display.check_mapping_inventory()
    expected={(row['mapping'],row['pattern']) for row in display.cases()}
    executed={(entry['mapping'],entry['pattern']) for row in cases()
              if row['domain']=='isolated-declared-map' for entry in row['covered_mappings']}
    if expected!=executed:
        raise ValueError('All-mapping workbook contract needs every frozen display mapping')
    return expected

def observe(row,output,*,native_reference_root=None):
    return coupled.observe(row,output,native_reference_root=native_reference_root)

def check_original_failures():
    archive=ARCHIVE.parent/'original-probes/v1'
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    if sha(archive/'source-manifest.json')!='8d7a85799154420bdc981b204cebc53539b3c6471cda575bb88f94dda867094f':
        raise ValueError('Original all-mapping workbook failures manifest changed')
    for name,value in json.loads((archive/'source-manifest.json').read_text(encoding='utf-8')).items():
        if sha(archive/name)!=value:
            raise ValueError('Original all-mapping workbook failure evidence changed: '+name)
    receipt=json.loads((archive/'run.json').read_text(encoding='utf-8'))
    paired=json.loads((archive/'excel-all-mapping-workbook-paired.json').read_text(encoding='utf-8'))['rows']
    assert receipt['comparisons']==len(paired)==102 and receipt['disagreements']==8
    assert receipt['execution_errors']==0 and not receipt['source_changes']
    assert all(row['error'] is None and row['observed']['inputs_unchanged'] and row['observed']['source_macros_unchanged'] for row in paired)
    failed={row['case']['key'] for row in paired if not row['agrees']}
    expected={'excel-all-mapping-workbook.export_IF_summary_excel.'+name
              for name in ('ROI_Thickness','ROI_Volume','ROI_Area','Volume0p1mm3','CountNormFactor')}
    expected.update('excel-all-mapping-workbook.'+name+'.combined-all-mappings'
                    for name in ('export_excel','export_all_excel','export_IF_summary_excel'))
    assert failed==expected
    return receipt

def validate(output,*,native_reference_root=None):
    import traceback
    from PyFLASH._persistence import write_json
    from reproducibility.normality_association_validation import comparison
    fixture=check_identity()
    coupled.check_parameter_inventory(fixture)
    check_mapping_inventory()
    paired=[];comparisons=[]
    for row in cases():
        observed=error=None
        try:observed=observe(row,output,native_reference_root=native_reference_root)
        except Exception:error=traceback.format_exc()
        agrees=error is None and not observed['disagreements']
        paired.append(dict(case=row,observed=observed,error=error,agrees=agrees))
        comparisons.append(comparison(row['key'],'predeclared-accepted-display-maps/native-openpyxl-literal-writer-and-reader',
            'functional-all-mapping-workbook-transport/no-independent-estimator-or-description-semantic-vote',
            dict(all_declared_output_matches=agrees),dict(all_declared_output_matches=True),agrees,True,
            'exact-every-worksheet-cell-label-description-merge-report-returned-path-and-unchanged-input',0.,0.))
    write_json(Path(output)/'excel-all-mapping-workbook-paired.json',
        dict(schema_version=1,complete_contract=False,scope=__doc__,rows=paired))
    return comparisons
