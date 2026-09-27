# Causal engine verification

Verified with recorded inputs; hardware and the production consumer are not validated.

The 180-second UN_101 Lab1 n-back recording produced 13 outputs, first at 60 seconds and then every 10 seconds.
The normalized-sample and existing observation-block CLI paths agreed on all 43 features and every available prediction.

Local extraction plus model compute: median 4.82 ms; observed 95th percentile 12.99 ms across 13 updates. This excludes sensor acquisition, transport and the 60-second evidence window.

23 unit tests pass. They cover future-sample independence, packet-size equivalence, known synthetic pulse recovery, missing/gapped data, motion masking, source binding, duplicate IDs, both API timestamp forms, and individual-window scoring.
Three complete native BVP sequences (one lab, two wild) match their original CSV samples exactly. This is a spot check, not a full acquisition re-audit.

## Interpretation outcome

The final selection chose a learned gradient-boosting head only for mental demand. The other five selected constants. The engine reports those five as `no_predictive_model_selected` without emitting a rating.
The learned selection and the selection procedure have not established a clear advantage over constant references; no calibrated confidence is supplied. A working stream is not evidence of reliable instantaneous state inference.

Detailed machine-readable results: `results/causal-v3/verification.json`, `report.json`, `replay-model.json`, `stream-model-observations.jsonl` and `native-source-check.json`.
