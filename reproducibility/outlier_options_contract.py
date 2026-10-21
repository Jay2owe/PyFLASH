"""Frozen exposed-option and owner-protocol controls for both outlier parents."""
import json
from pathlib import Path
from reproducibility.outlier_subject_identity_contract import production

ARCHIVE=Path(__file__).with_name('reference-sources')/'outlier-requests/options-v1'
MANIFEST_SHA256='ce639757468fecf6860e2769f9f3b8c8f4bef250fd0ba74d29829fff2a0306f2'
COMPLETE_CAPABILITIES=frozenset()
CAPABILITY_PREFIXES={'PyFLASH.exclusions.'+api:('outlier-options.'+api+'.',)
                    for api in ('mark_outliers','exclude_outliers')}


def cases():
    from reproducibility.compact_evidence import entries,digest
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
    for name,sha in json.loads((ARCHIVE/'declaration.json').read_text())['dependencies'].items():
        assert digest(Path(__file__).resolve().parents[1]/name)==sha
    return list(entries(ARCHIVE/'cases.jsonl.gz'))


def validate(output):
    import gzip
    import runpy
    from reproducibility.normality_association_validation import comparison
    reference=runpy.run_path(str(ARCHIVE/'reference-producer.py'))['expected']
    rows=[]
    with gzip.open(output/'outlier-options-paired.jsonl.gz','xt',encoding='utf-8') as out:
        for case in cases():
            actual=production(case,output/'cases'/case['key'])
            answer=reference(case);unchanged=answer==case['expected']
            agrees=unchanged and actual==answer
            rows.append(comparison(case['key'],'accepted-independent-detectors/literal-option-source-and-ledger-rules',
                'outlier-option-and-owner-protocol-composition',actual,answer,agrees,unchanged,
                'all-summary-ledger-saved-csv-request-and-owner-fields',0.,0.))
            out.write(json.dumps(dict(key=case['key'],actual=actual,expected=answer,agrees=agrees),sort_keys=True)+'\n')
    return rows
