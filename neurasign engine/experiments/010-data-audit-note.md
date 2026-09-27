# Experiment 010: label availability and planned context check

Recorded before any experiment 010 model selection or Lab2 predictions.

The original Lab1 questionnaire CSVs contain the `Mental effort level` field for only four of the 19 development participants. Of these, two also have a Lab2 session. The field is absent from the other 15 source CSV headers; this is not a feature-extraction or normalization issue. The primary ordinal-derived binary target therefore permits only two paired people, one with at least two calibration tasks per class. It cannot establish the prespecified research signal requiring at least ten people.

The separately registered `Mental Demand` questionnaire field exists in all 19 Lab1 source files and all 17 available Lab2 source files. Its fixed low/high mapping permits 17 paired people, of whom 12 have at least two Lab1 tasks in each class. This registered secondary target supplies the informative personalization comparison. It is not substituted for missing mental-effort answers. Missing and neutral answers stay excluded, and coverage will be reported.

Both targets and all originally specified arms remain in the experiment. No score or classification threshold is changed. Original held-out participants remain closed, and model selection uses Lab1 only.

A descriptive context check will also score the same saved Lab2 predictions after excluding the `relaxation_video` segment. Segment names are used solely to define this audit subset, never as model inputs or substitute outcome labels. This check asks whether apparent separation persists during active tasks. It will report how many people still have both classes, alongside all-window results; it cannot replace the primary cohort or justify selecting a different model. No new model is fitted for this check.

The two sessions repeat the same families of experimental tasks. Session-separated evaluation therefore does not, by itself, establish transfer to new kinds of workplace activity or continuous live monitoring.
