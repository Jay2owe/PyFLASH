"""Focused independent numerical checks; synthetic participants only."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import matplotlib
matplotlib.use('Agg')
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from common import run_output


def module(filename):
    spec = importlib.util.spec_from_file_location(filename.replace('.', '_'), Path(__file__).parent / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


human = module('02_human_associations.py')
panels = module('03_panel_statistics.py')
sensitivity = module('04_human_covariate_sensitivity.py')
grouped = module('05_grouped_associations.py')
annotations = module('06_compare_manuscript_annotations.py')


def fixture():
    rng = np.random.default_rng(941)
    rows = []
    for group_index, group in enumerate(human.GROUPS):
        for i in range(16):
            age = rng.normal(69, 8)
            sex = 'Female' if i % 2 else 'Male'
            volume = 22 - (0.05 + 0.12 * group_index) * (age - 65) + rng.normal(0, 1.7)
            activity = 120 + (3 - group_index * 2) * volume + age + rng.normal(0, 14)
            rows.append({'AnimalName': f'{group}-{i}', 'Diagnosis': group, 'Sex': sex,
                         'Age': age, human.DEFAULT_VOLUME: volume, human.DEFAULT_M10: activity})
    return pd.DataFrame(rows)


class ReproductionChecks(unittest.TestCase):
    def test_coefficient_models_keep_separate_complete_cases_and_match_ols(self):
        frame = fixture()
        frame.loc[0, human.DEFAULT_M10] = np.nan
        coefficients, directional, counts = human.coefficients(frame, bootstrap=100, seed=5)
        self.assertEqual(counts['Age-volume']['Control'], 16)
        self.assertEqual(counts['Volume-M10']['Control'], 15)
        for label, x_column, y_column, covariates in [
                ('Age-volume', 'Age', human.DEFAULT_VOLUME, ['Sex']),
                ('Volume-M10', human.DEFAULT_VOLUME, human.DEFAULT_M10, ['Age', 'Sex'])]:
            cohort = frame[['Diagnosis', x_column, y_column, *covariates]].dropna()
            x = (cohort[x_column] - cohort[x_column].mean()) / cohort[x_column].std(ddof=0)
            y = (cohort[y_column] - cohort[y_column].mean()) / cohort[y_column].std(ddof=0)
            mci = cohort.Diagnosis.eq('MCI').astype(float)
            ad = cohort.Diagnosis.eq('AD').astype(float)
            design = pd.DataFrame({'intercept':1., 'x':x, 'MCI':mci, 'AD':ad,
                                   'xMCI':x*mci, 'xAD':x*ad, 'sex':cohort.Sex.eq('Male').astype(float)})
            if 'Age' in covariates:
                design['age'] = cohort.Age
            fitted = sm.OLS(y, design).fit()
            expected = [fitted.params['x'], fitted.params['x']+fitted.params['xMCI'], fitted.params['x']+fitted.params['xAD']]
            np.testing.assert_allclose(coefficients.loc[coefficients.association.eq(label), 'estimate'], expected, rtol=1e-10)
        self.assertEqual(len(directional), 4)
        np.testing.assert_allclose(directional.p, stats.t.cdf(directional.t, directional.df), rtol=1e-10)

    def test_adjusted_spearman_matches_raw_scale_residuals(self):
        frame = fixture()
        table = human.correlations(frame, activity=[human.DEFAULT_M10], bootstrap=100, seed=5)
        for group in human.GROUPS:
            cohort = frame.loc[frame.Diagnosis.eq(group)]
            design = sm.add_constant(pd.DataFrame({'age':cohort.Age, 'sex':cohort.Sex.eq('Male').astype(float)}))
            x = sm.OLS(cohort[human.DEFAULT_VOLUME], design).fit().resid
            y = sm.OLS(cohort[human.DEFAULT_M10], design).fit().resid
            expected = stats.spearmanr(x, y)
            row = table.loc[table.group.eq(group) & table.adjustment.eq('AgeSexAdjusted')].iloc[0]
            self.assertAlmostEqual(row.estimate, expected.statistic, places=12)
            self.assertAlmostEqual(row.p, expected.pvalue, places=12)

    def test_anova_tukey_matches_independent_statistics(self):
        frame = fixture()
        job = {'panel':'demo', 'column':human.DEFAULT_M10, 'group_column':'Diagnosis',
               'groups':human.GROUPS, 'method':'anova_tukey', 'comparisons':['1-2','1-3','2-3'], 'exclude_subjects':[]}
        results, summary, used = panels.analyze(frame, [job])
        expected = stats.f_oneway(*[frame.loc[frame.Diagnosis.eq(g), human.DEFAULT_M10] for g in human.GROUPS])
        self.assertAlmostEqual(results.iloc[0].p, expected.pvalue, places=12)
        tukey = pairwise_tukeyhsd(frame[human.DEFAULT_M10], frame.Diagnosis)
        a,b = tukey._multicomp.pairindices
        pairs = {frozenset([tukey.groupsunique[i], tukey.groupsunique[j]]):p for i,j,p in zip(a,b,tukey.pvalues)}
        for _, row in results.iloc[1:].iterrows():
            i,j = [int(token)-1 for token in row.comparison.split('-')]
            self.assertAlmostEqual(row.p, pairs[frozenset([human.GROUPS[i], human.GROUPS[j]])], places=12)
        self.assertEqual(summary.n.tolist(), [16]*3)
        self.assertEqual(len(used), 48)
        job['method'] = 'kruskal_dunn'
        with self.assertRaisesRegex(ValueError, 'correction explicitly'):
            panels.analyze(frame, [job])

    def test_duplicate_participants_are_rejected(self):
        frame = fixture()
        job = {'panel':'demo', 'column':human.DEFAULT_M10, 'group_column':'Diagnosis',
               'groups':human.GROUPS, 'method':'anova_tukey', 'comparisons':['1-2'], 'exclude_subjects':[]}
        with self.assertRaisesRegex(ValueError, 'one row per'):
            panels.analyze(pd.concat([frame, frame.iloc[[0]]]), [job])

    def test_grouped_pearson_matches_independent_correlation(self):
        frame = fixture()
        job = {'name':'demo', 'x':'Age', 'y':human.DEFAULT_VOLUME,
               'group_column':'Diagnosis', 'groups':human.GROUPS, 'exclude_subjects':[]}
        result = grouped.analyze(frame, [job])
        for group in human.GROUPS:
            cohort = frame.loc[frame.Diagnosis.eq(group)]
            expected = stats.pearsonr(cohort.Age, cohort[human.DEFAULT_VOLUME])
            row = result['correlations'].loc[lambda df:df.group.eq(group)].iloc[0]
            self.assertAlmostEqual(row.estimate, expected.statistic, places=12)
            self.assertAlmostEqual(row.p, expected.pvalue, places=12)
        self.assertFalse(result['regression_coefficients'].empty)

    def test_submitted_age_model_matches_unadjusted_group_slopes(self):
        frame = fixture()
        result,_,_ = human.coefficients(frame, bootstrap=100, definition='submitted_figure')
        scale = frame.Age.std(ddof=0) / frame[human.DEFAULT_VOLUME].std(ddof=0)
        for group in human.GROUPS:
            cohort = frame.loc[frame.Diagnosis.eq(group)]
            expected = stats.linregress(cohort.Age,cohort[human.DEFAULT_VOLUME]).slope * scale
            row = result.loc[result.association.eq('Age-volume') & result.group.eq(group)].iloc[0]
            self.assertAlmostEqual(row.estimate,expected,places=12)
            self.assertEqual(row.covariates,'')

    def test_annotation_comparison_detects_changed_display(self):
        beta = pd.DataFrame([{'association':'demo','group':'Control','estimate':0.584}])
        rho = pd.DataFrame([{'association':'metric','group':'Control','adjustment':'Raw','estimate':0.713},
                            {'association':'metric','group':'Control','adjustment':'AgeSexAdjusted','estimate':0.8059}])
        reference = {'precision':2, 'coefficients':{'demo':{'Control':0.58}},
                     'spearman':{'metric':{'Control':[0.71,0.81]}}}
        self.assertTrue(annotations.compare(beta,rho,reference).matches_display.all())
        beta.loc[0,'estimate'] = 0.57
        self.assertFalse(annotations.compare(beta,rho,reference).matches_display.all())

    def test_sensitivity_uses_conventional_ols_and_writes_no_figures(self):
        frame = fixture()
        results = sensitivity.analyze(frame, [{'name':'demo', 'outcomes':[human.DEFAULT_M10],
                                               'covariates':['Age','Sex'], 'categorical':['Sex']}])
        self.assertFalse(results['means'].empty)
        self.assertFalse(results['contrasts'].empty)
        self.assertTrue(np.isfinite(results['means'].select_dtypes('number')).all().all())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileExistsError):
                with run_output(directory, inputs=[], parameters={}):
                    self.fail('Existing directory must never be overwritten.')


if __name__ == '__main__':
    unittest.main()
