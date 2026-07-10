# Classification

## Summary

PyFLASH classification statistics come from model sweeps that test whether
feature sets can predict labelled groups. The sweep is designed for discovery
and comparison of model families, not for proving a biological mechanism.

## Where PyFLASH Uses It

- [iterative_model_sweep](../functions/iterative_model_sweep.md) runs the model
  search, cross-validation, ranking, permutation testing, and output writing.
- [iterative_best_fit](../functions/iterative_best_fit.md) provides a related
  best-fit workflow.
- [Model sweep outputs](../outputs/model-sweep-outputs.md) describes the output
  folder and saved tables.

## Inputs

Inputs include a class label, candidate feature columns, optional row filters,
model-family choices, search settings, a cross-validation splitter, and a
ranking metric.

Preprocessing is performed inside each training fold. Numeric features are
imputed and scaled. Categorical features are imputed and one-hot encoded. This
fold-local preprocessing helps avoid leaking test-fold information into the
training step.

Supported model families include regularized multinomial logistic regression,
ordinal logistic regression when the optional dependency is available, shrinkage
linear discriminant analysis, regularized quadratic discriminant analysis,
polynomial support vector machines, shallow random forests, and shallow gradient
boosting.

## Outputs

Model-sweep outputs include:

- per-model score tables.
- top-score tables.
- feature recurrence summaries.
- predictions for the top model.
- optional permutation-test results.
- plots summarizing performance and feature recurrence.
- a refitted best estimator trained on all filtered rows after ranking.
- `manifest.json` and a run README.

Metrics can include accuracy, balanced accuracy, macro F1, macro one-vs-rest
AUC, and log loss. For log loss, lower values are better; for the other listed
metrics, higher values are better.

## Interpretation

Cross-validation estimates how well a modelling strategy performs on held-out
folds from the same dataset. Balanced accuracy and macro F1 are often more
informative than plain accuracy when class sizes differ. Macro AUC summarizes
one-vs-rest ranking performance. Log loss rewards calibrated probabilities and
penalizes confident wrong predictions.

Permutation testing compares the observed score with scores after shuffling the
class labels. A low permutation p-value means the observed score is unusual
under that shuffle procedure.

## Limitations

Model sweeps can overfit through repeated feature-set and model-family search,
especially with small sample sizes. Cross-validation folds must contain enough
examples from each class; PyFLASH caps stratified folds based on the smallest
class and rejects splits that are not feasible.

High performance does not identify which biological process caused class
separation. Correlated features, batch effects, and class imbalance can make a
classifier look useful while remaining hard to interpret.

## See Also

- [Effect Sizes](effect-sizes.md)
- [Multiple Testing](multiple-testing.md)
- [iterative_model_sweep](../functions/iterative_model_sweep.md)
- [Model options](../parameters/model-options.md)
