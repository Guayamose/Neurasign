# Acquisition and evaluation amendment

This amendment is recorded before Mobile CogLoad model fitting or held-out scoring.

The CognitiveLoad_Wearables archive provides raw signals and timing sheets but no
task NASA-TLX answers. Its 15 participants remain entirely withheld. It cannot
currently provide a questionnaire prediction test.

Mobile CogLoad adds 36 exported user IDs. A seeded, label-blind split reserved ten
codes before model fitting; the schema example is kept in development. Its thesis
describes a user-entered unique ID, but the article describes 23 participants, so
the export/publication discrepancy remains explicit. These are ten held-out user
codes, not independently verified real-world identities. This limits any claim of
meeting the ten-person gate even if numerical criteria are met.

The thesis (Knez 2019, section 3.4 and figure 4.4a, printed pages 7 and 13)
identifies the NASA-TLX questions and shows 21 slider positions. The development
export spans 0..20. Four demand/effort dimensions are mapped by multiplying by five
for an experimental joint model. This is a linear encoding assumption, not proof
of cross-study psychometric equivalence. Performance direction is not pooled.
UNIVERSE's ordinal mental-effort label has no corresponding Mobile label.

Microsoft's Band SDK documentation defines GSR as resistance in kOhm; it is
converted to conductance using 1000/resistance. Native beat events are used for
interval variability, never the 1-Hz repeated last-value column. Game behavior,
personality, frustration, and composite TLX are excluded.

Development uses five disjoint user folds per source. Both local-source and pooled
models are compared; preprocessing is fitted within each training fold. All
development search results are selection scores. Final configurations and artifact
hashes will be frozen before the ten-code test is scored once. The ±10 point and
three-level gates apply only to 0..100 rating outputs, not ordinal mental effort.

CLACIR (142 recording groups) and CogWear (24 participant namespaces) provide
6,063 nonoverlapping minute windows for unlabeled feature pretraining. Their task
conditions and affective questionnaires are not target labels. The pretraining
holdout measures reconstruction only. MAUS's author-released wrist feature table
is evaluated separately as an N-back protocol classification probe, not a
questionnaire interpretation or MVP acceptance test.

Sources: [Mobile repository](https://gitlab.fri.uni-lj.si/lrk/mobile-cogload-dataset),
[original thesis](https://repozitorij.uni-lj.si/IzpisGradiva.php?id=110571),
[Microsoft-authored SDK manual, mirrored](https://www.scribd.com/document/353279939/Microsoft-Band-Sdk).
