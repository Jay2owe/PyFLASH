"""One inexpensive declaration of classifier families, grids and dependencies."""
from importlib import import_module
from itertools import product
from PyFLASH._optional import require

PRESETS=('ultra_compact','compact','full')

def _entry(key,label,estimator,parameters,grids,name,*,fixed=None,seeded=False,per_preset=None,dependency=None,extra=None):
    return {'key':key,'label':label,'help':f'Compare {label.lower()} over the declared parameter grid.',
            'estimator':estimator,'parameters':parameters,'grids':dict(zip(PRESETS,grids)),
            'name':name,'fixed':fixed or {},'seeded':seeded,'per_preset':per_preset or {},
            'dependency':dependency,'extra':extra}

CLASSIFIER_FAMILIES={row['key']:row for row in (
    _entry('ridge_multinomial_logistic','Ridge multinomial logistic regression',
        'sklearn.linear_model.LogisticRegression',('C',),
        ([{'C':1.}], [{'C':v} for v in (.1,1.)], [{'C':v} for v in (.03,.1,.3,1.,3.)]),
        'ridge_C={C:g}',fixed={'penalty':'l2','solver':'lbfgs','max_iter':50000},seeded=True),
    _entry('elastic_net_multinomial_logistic','Elastic net multinomial logistic regression',
        'sklearn.linear_model.LogisticRegression',('C','l1_ratio'),
        ([{'C':.1,'l1_ratio':.5}], [{'C':v,'l1_ratio':.5} for v in (.1,1.)],
         [{'C':c,'l1_ratio':r} for c,r in product((.1,.3,1.),(.1,.5,.9))]),
        'elastic_C={C:g}_l1={l1_ratio:g}',fixed={'penalty':'elasticnet','solver':'saga','max_iter':50000},seeded=True),
    _entry('ordinal_logistic','Ordinal logistic regression',
        'PyFLASH.modelling._PyFLASHOrdinalLogistic',('alpha',),
        ([{'alpha':1.}], [{'alpha':v} for v in (1.,10.)], [{'alpha':v} for v in (.1,1.,10.,100.)]),
        'ordinal_alpha={alpha:g}',fixed={'max_iter':50000},dependency='mord',extra='classification'),
    _entry('shrinkage_lda','Shrinkage linear discriminant analysis',
        'sklearn.discriminant_analysis.LinearDiscriminantAnalysis',('shrinkage',),
        ([{'shrinkage':'auto'}],[{'shrinkage':'auto'}],[{'shrinkage':v} for v in ('auto',.1,.5,.9)]),
        'lda_shrinkage={shrinkage}',fixed={'solver':'lsqr'}),
    _entry('regularised_qda','Regularised quadratic discriminant analysis',
        'sklearn.discriminant_analysis.QuadraticDiscriminantAnalysis',('reg_param',),
        ([{'reg_param':.7}],[{'reg_param':v} for v in (.5,.9)],[{'reg_param':v} for v in (.1,.3,.5,.7,.9)]),
        'qda_reg={reg_param:g}'),
    _entry('polynomial_svm','Polynomial support vector classifier',
        'sklearn.svm.SVC',('C','degree','coef0'),
        ([{'C':1.,'coef0':1.}],[{'C':1.,'coef0':1.}],[{'C':c,'coef0':v} for c,v in product((.1,1.,10.),(0.,1.))]),
        'poly_svm_C={C:g}_coef0={coef0:g}',fixed={'kernel':'poly','degree':2},seeded=True,
        per_preset={'ultra_compact':{'probability':False},'compact':{'probability':True},'full':{'probability':True}}),
    _entry('shallow_random_forest','Shallow random forest',
        'sklearn.ensemble.RandomForestClassifier',('max_depth','min_samples_leaf','max_features','n_estimators'),
        ([{'max_depth':2,'min_samples_leaf':2,'max_features':'sqrt','n_estimators':50}],
         [{'max_depth':2,'min_samples_leaf':2,'max_features':'sqrt','n_estimators':200}],
         [{'max_depth':d,'min_samples_leaf':l,'max_features':f,'n_estimators':200} for d,l,f in product((1,2),(2,4),('sqrt',.5))]),
        'rf_depth={max_depth}_leaf={min_samples_leaf}_mf={max_features}',fixed={'n_jobs':1},seeded=True),
    _entry('shallow_gradient_boosting','Shallow gradient boosting',
        'sklearn.ensemble.GradientBoostingClassifier',('n_estimators','learning_rate','max_depth','min_samples_leaf'),
        ([{'n_estimators':10,'learning_rate':.1,'max_depth':1,'min_samples_leaf':2}],
         [{'n_estimators':25,'learning_rate':.1,'max_depth':1,'min_samples_leaf':2}],
         [{'n_estimators':n,'learning_rate':r,'max_depth':d,'min_samples_leaf':2} for n,r,d in product((10,25),(.03,.1),(1,2))]),
        'gb_n={n_estimators}_lr={learning_rate:g}_depth={max_depth}',seeded=True),
)}

def build_configs(preset,model_families,random_state):
    preset=str(preset).strip().lower()
    if preset not in PRESETS:
        raise ValueError('Unknown model_preset. Valid: '+', '.join(PRESETS))
    wanted=selected_families(model_families)
    # Check every selected dependency before constructing any estimator.
    for key,row in CLASSIFIER_FAMILIES.items():
        if key in wanted and row['dependency']:
            require(row['dependency'],feature=row['label'],extra=row['extra'])
    configs=[]
    for key,row in CLASSIFIER_FAMILIES.items():
        if key not in wanted:continue
        module,attr=row['estimator'].rsplit('.',1)
        estimator=getattr(import_module(module),attr)
        for values in row['grids'][preset]:
            kwargs={**row['fixed'],**row['per_preset'].get(preset,{}),**values}
            if row['seeded']:kwargs['random_state']=random_state
            configs.append({'family':key,'name':row['name'].format(**kwargs),
                'estimator':estimator(**kwargs),'params':{name:kwargs[name] for name in row['parameters']}})
    return configs


def selected_families(model_families):
    if isinstance(model_families,str):model_families=[model_families]
    wanted=set(CLASSIFIER_FAMILIES) if model_families is None else {str(name).strip().lower() for name in model_families if str(name).strip()}
    unknown=wanted-set(CLASSIFIER_FAMILIES)
    if unknown:
        raise ValueError('Unknown classifier families: '+', '.join(sorted(unknown))+'. Valid: '+', '.join(CLASSIFIER_FAMILIES))
    if not wanted:raise ValueError('No classifier families selected. Valid: '+', '.join(CLASSIFIER_FAMILIES))
    return wanted

def dependency_groups(model_families=None):
    wanted=selected_families(model_families)
    return tuple(dict.fromkeys(row['extra'] for key,row in CLASSIFIER_FAMILIES.items()
        if key in wanted and row['dependency']))
