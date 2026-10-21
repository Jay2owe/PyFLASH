"""Exact selected-source values in outlier ledgers; complete parents stay open."""
import json
from pathlib import Path
from reproducibility.outlier_subject_identity_contract import production

ARCHIVE=Path(__file__).with_name('reference-sources')/'outlier-requests/ledger-source-values-v1'
MANIFEST_SHA256='180c3840baae6db5b53072d4a9742c77031e65e75a87ebd62a560c7fcfac9d05'
COMPLETE_CAPABILITIES=frozenset()
CAPABILITY_PREFIXES={'PyFLASH.exclusions.'+api:('outlier-ledger-source.'+api+'.',)
                    for api in ('mark_outliers','exclude_outliers')}


def cases():
    from reproducibility.compact_evidence import entries,digest
    from reproducibility.evidence_identity import verify_manifest
    verify_manifest(ARCHIVE,'source-manifest.json',MANIFEST_SHA256)
    declaration=json.loads((ARCHIVE/'declaration.json').read_text())
    assert digest(ARCHIVE/declaration['input_path'])==declaration['input_sha256']
    assert digest(ARCHIVE.parent/'whole-v1/reference-producer.py')==declaration['expected_base_producer_sha256']
    return list(entries(ARCHIVE/'cases.jsonl.gz'))


def validate(output):
    import gzip
    import runpy
    from reproducibility.normality_association_validation import comparison
    reference=runpy.run_path(str(ARCHIVE/'reference-producer.py'))['expected']
    rows=[]
    with gzip.open(output/'outlier-ledger-source-paired.jsonl.gz','xt',encoding='utf-8') as out:
        for case in cases():
            actual=production(case,output/'cases'/case['key'])
            answer=reference(case);unchanged=answer==case['expected']
            agrees=unchanged and actual==answer
            rows.append(comparison(case['key'],'literal-selected-source-values/before-operation-snapshot',
                'functional-ledger-source-fidelity/not-whole-parent-approval',actual,answer,agrees,unchanged,
                'all-source-summary-ledger-and-ownership-fields',0.,0.))
            out.write(json.dumps(dict(key=case['key'],actual=actual,expected=answer,agrees=agrees),sort_keys=True)+'\n')
    return rows
