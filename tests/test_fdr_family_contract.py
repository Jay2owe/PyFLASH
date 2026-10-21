"""Every returned family-correction value and decision against independent tables."""
import hashlib
import json
import numpy as np
import pytest
from reproducibility import fdr_family_contract as contract
from reproducibility.reference_runtime import values

REFERENCE = json.loads(contract.FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('row',REFERENCE['rows'],ids=lambda row:row['key'])
@pytest.mark.parametrize('reference',['native','mathematical'])
def test_complete_family_correction_table(row,reference):
    expected = values(row) if reference=='native' else values({
        'values':row['mathematical_values'],'nonfinite':row['mathematical_nonfinite']})
    np.testing.assert_allclose(contract.production(row),expected,rtol=1e-9,atol=1e-12,equal_nan=True)


def test_family_reference_sources_and_inputs_remain_frozen():
    from reproducibility import multiplicity_contract
    assert hashlib.sha256(open(contract.__file__,'rb').read()).hexdigest() == REFERENCE['reference_code_sha256']
    assert hashlib.sha256(open(multiplicity_contract.__file__,'rb').read()).hexdigest() == REFERENCE['multiplicity_code_sha256']
    assert [{key:row[key] for key in ('key','capability','canonical','parameters')}
            for row in REFERENCE['rows']] == contract.cases()


@pytest.mark.parametrize('alpha',[-.1,1.1,np.nan,np.inf,True,'0.05'])
@pytest.mark.parametrize('pvalues',[[],[.02,.3]])
def test_invalid_alpha_is_rejected_before_any_correction(alpha,pvalues):
    from PyFLASH.stats_extra import apply_fdr
    with pytest.raises(ValueError,match='alpha'):
        apply_fdr(pvalues,alpha=alpha)


def test_empty_collection_still_validates_method():
    from PyFLASH.stats_extra import apply_fdr
    with pytest.raises(ValueError):
        apply_fdr([],method='unknown')


@pytest.mark.parametrize('representation',['list','dict','series','series-override'])
def test_default_and_overridden_label_forms_keep_the_frozen_numeric_table(representation):
    import pandas as pd
    from PyFLASH.stats_extra import apply_fdr
    row = next(row for row in REFERENCE['rows'] if row['canonical']=='fdr_bh'
               and row['parameters']['alpha']==.1 and row['parameters']['families'] is None
               and row['parameters']['representation']=='list' and row['parameters']['pvalues'][0]==.001)
    raw = row['parameters']['pvalues']
    names = row['parameters']['labels']
    source = dict(zip(names,raw)) if representation=='dict' else (
        pd.Series(raw,index=names) if representation.startswith('series') else raw)
    chosen = list(reversed(names)) if representation=='series-override' else None
    table = apply_fdr(source,labels=chosen,alpha=.1)
    assert table['label'].tolist()==(chosen if chosen else list(range(len(raw))) if representation=='list' else names)
    expected = np.asarray(values(row)[2:]).reshape(-1,5)
    np.testing.assert_allclose(table[['p_value','p_adjusted','reject']].to_numpy(float),
                               expected[:,2:],rtol=1e-9,atol=1e-12)


def test_missing_family_spellings_group_together_and_missing_probabilities_are_omitted():
    import pandas as pd
    from PyFLASH.stats_extra import apply_fdr
    table = apply_fdr([.01,.02,None,pd.NA],families=[None,np.nan,pd.NA,None],method='bonferroni')
    np.testing.assert_allclose(table['p_adjusted'],[.02,.04,np.nan,np.nan],equal_nan=True)
    assert table['reject'].tolist()==[True,True,False,False]


@pytest.mark.parametrize('parameters',[{'labels':['a']},{'families':['a']}])
def test_wrong_label_or_family_count_is_rejected(parameters):
    from PyFLASH.stats_extra import apply_fdr
    with pytest.raises(ValueError,match='one label and one family'):
        apply_fdr([.01,.3],**parameters)
