# Every second matters — the 76-second story

The film is an original animated hospital scenario: one patient, three fictional doctors, and a coordinator who confirms the proposed response. The first 56 seconds retain the hospital story; a 15-second “Beyond hospitals” section and five-second brand ending complete the revision. Eleven narration cues accompany 2,280 frames at 30 fps, matching `src/hospital/HospitalFilm.tsx` and the narration manifest in `public/audio/hospital-narration.json`.

| Scene | Film time | Picture and purpose | English narration |
| --- | --- | --- | --- |
| 1. Hospital | 0–5 s | Hospital exterior and arriving ambulance. “Every second matters.” Establish the setting. | “In an emergency, the right support can change everything.” |
| 2. Arrival | 5–11 s | Sliding doors open. A patient arrives on a stretcher; three responders are present. | “A patient arrives. Three qualified doctors. One decision: who should respond?” |
| 3. Wearable signals | 11–18 s | Omar, Emma and Maya appear with animated, illustrative heart rate, variability and movement. | “Behind each wristband is a different story. Heart rate. Variability. Movement.” |
| 4. Signals to context | 18–26 s | Wearable → phone → NEURASIGN, followed by the four proposed interpretation categories. | “NeuraSign turns those signals into estimates of stress, fatigue, workload and readiness.” |
| 5. Team context | 26–33 s | Three comparison cards combine story availability, skills and illustrative state estimates. | “Omar is already busy. Emma shows elevated fatigue. Maya is available and ready.” |
| 6. Incident | 33–41 s | A request for Trauma bay 02 appears. The film illustrates a comparison and a recommendation prepared for review. | “The incident reaches NeuraSign. It compares the team’s signals, availability and relevant skills.” |
| 7. Recommendation | 41–49 s | Maya's recommendation appears alongside its scripted reasons. The coordinator retains the final decision. | “Maya is the recommended match. You see who, and the reasons behind the recommendation.” |
| 8. Response | 49–56 s | The coordinator confirms, a phone receives the illustrated alert, and Maya approaches the patient. | “The coordinator confirms. Maya gets the alert, and moves straight to the patient.” |
| 9. Beyond hospitals | 56–71 s | The hospital is one example. Original vector scenes broaden the concept to construction sites, industrial operations and control rooms. | Cue 9: “This hospital is just one example.” Cue 10: “NeuraSign is designed for demanding workplaces with real risks. Construction sites. Industrial operations. Control rooms.” |
| 10. Closing | 71–76 s | Official cobalt branding and the closing message. | Cue 11: “NeuraSign. Understand your team. Respond with confidence.” |

The first eight caption windows keep their existing starts: 0.5, 5.2, 11.3, 18.2, 26.2, 33.2, 41.2 and 49.2 seconds. Cue 9 runs at 56.2–60.7 seconds, cue 10 at 61.0–70.8 seconds, and the sign-off at 71.2–75.7 seconds. The stable `hospital-narration.vtt` file contains all eleven cues. Narration uses the spoken spelling “NeuroSign” to guide pronunciation; on-screen text and captions retain **NeuraSign**.

## How to read the numbers

All identities, physiological readings, signal traces and interpretations in this film are fictional scenario values. They are not UNIVERSE recordings, live employee data, or outputs from a model run. The **0–100 scores are illustrative indices, not model accuracy, confidence percentages, or clinical thresholds**.

| Fictional character | Heart rate | HRV | Stress | Fatigue | Workload | Readiness | Story context |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dr. Omar Reed | 104 bpm | 24 ms | 68 | 39 | 88 | 42 | Already with another patient. |
| Dr. Emma Cruz | 88 bpm | 31 ms | 42 | 73 | 48 | 38 | Available; a check-in is suggested in the story. |
| Dr. Maya Chen | 74 bpm | 58 ms | 24 | 18 | 29 | 86 | Available; the proposed match in this scripted scenario. |

The film communicates a proposed product experience. It does not demonstrate a deployed clinical assignment system, validate inference from wearables, or change the existing application. No real recommendation, notification or assignment is sent. The on-screen “Illustrative hospital scenario” label, estimate captions and closing disclosure preserve that distinction.

## Production and editing

Characters, hospital sets, additional workplaces, props and diagrams are original SVG/React artwork. This revision refines the characters’ hands and facial animation while preserving the established palette and story. The full soundtrack combines Gemini 3.8 Flash TTS narration using the Iapetus stock voice with original synthesized music and effects. `HospitalFilm.tsx` plays the 76-second WAV master once, from frame zero; individual stems should not be played simultaneously with that mix.

The player offers chapter shortcuts at **0, 11, 26, 33, 41, 49 and 56 seconds**. These are navigation points; the editable source retains the complete hospital story, workplace extension and final brand scene. Modify artwork, values and timing in `src/hospital/`, then render the 1080p or 4K composition. Existing WAV audio can be rendered locally without credentials or model calls.
