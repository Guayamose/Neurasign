# Fatigue evaluation: why published percentages are not interchangeable

Reviewed alongside experiments 014–018. This note does not introduce another trained model or reuse a completed test set.

The June 2026 version of [Enhancing Fatigue Detection through Heterogeneous Multi-Source Data Integration and Cross-Domain Modality Imputation](https://arxiv.org/html/2507.16859v5) reports strong results for combining MEFAR, FatigueSet and VPFD. Its methods explicitly fit scaling across each full dataset. Each participant/label block contributes its middle 80% to training and its outer 20% to testing; validation windows also come from the training blocks. The VPFD target dataset has four people.

That evaluation measures recognition of other portions of already represented people and labeled recording blocks. It does not hold out new people. Full-dataset scaling also exposes preprocessing to test-distribution information. Its reported accuracy therefore cannot be substituted for NEURASIGN's reserved-person results or establish transfer to a new employee or wearable.

Our new experiments keep people separate, fit preprocessing inside training folds and score a frozen selection once. Higher accuracy under a different split would be a different claim, not evidence that these models became more reliable in deployment.
