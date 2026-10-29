# NeuroSign architecture

NeuroSign is a Windows desktop demo composed of an Electron application, a
local browser-style renderer, and a Python Flask service. It is not a
clinically validated medical product.

## Components

| Component | Location | Responsibility |
|---|---|---|
| Electron main process | `electron/main.js` | Starts Python, polls the health endpoint, opens the app window, and stops the backend on exit. |
| Preload bridge | `electron/preload.js` | Exposes the local API URL to the isolated renderer. |
| Renderer | `renderer/` | Displays screens, records microphone audio, captures pointer traces, and calls the API. |
| Flask app | `backend/app.py` | Registers authentication routes and the assessment, step, report, and chat blueprints. |
| Analysis | `backend/analysis/` | Extracts features, computes provisional scores, and builds assessment summaries. |
| Persistence | `backend/db.py`, `backend/schema.sql` | Initializes SQLite, migrates relevant schema, and encrypts the database file on Windows using DPAPI. |
| PDF report | `backend/routes/report.py` | Renders assessment results, charts, and general exercise cards with ReportLab. |
| Optional chat | `backend/routes/neuro.py` | Calls Gemini when configured, otherwise uses offline keyword matching. |

## Process and request flow

1. Electron selects `backend/venv/Scripts/python.exe` on Windows and launches
   `app.py` with the backend directory as its working directory.
2. Electron polls `http://127.0.0.1:5057/api/health`.
3. After a successful health response, Electron loads `renderer/index.html`.
4. The renderer sends HTTP requests to the local Flask service.
5. Voice and movement routes validate inputs, extract features, and persist
   results. The browser does not connect to SQLite directly.
6. The finalization route reads assessment data, refreshes comparisons, and
   builds a summary. The PDF route uses the summary to produce a report.

The Electron renderer enables context isolation and disables Node integration.
The preload script shares a narrow bridge rather than giving the renderer direct
access to Node APIs.

## Assessment data flow

An assessment contains eight steps:

- Steps 1–3 record voice baselines; step 4 is the voice detection recording.
- Steps 5–7 capture spiral, wave, and free-shape movement baselines.
- Step 8 repeats a selected movement task.

The renderer records microphone input as mono PCM WAV and submits it to the
voice route. The backend extracts fundamental frequency, jitter, shimmer, and
harmonic-to-noise ratio using parselmouth/Praat. Temporary audio is removed
after analysis; the schema stores extracted features, not the WAV itself.

Movement capture produces timestamped `(time, x, y)` pointer samples. The
backend sorts and deduplicates samples, splits at long pauses, resamples the
longest continuous stroke, filters coordinates, calculates spectral and
smoothness features, and compares guided traces with the guide at corresponding
path progress. The compressed pointer trace is retained in `raw_signals` so
guided scores can be refreshed.

The rule-based scores and flags in `backend/analysis/scoring.py` use provisional
values. An optional Random Forest probability may be saved if
`backend/ml/models/voice_rf.joblib` exists. The optional probability is not
currently part of the final rule-based verdict.

## Storage and security boundaries

The SQLite schema is in `backend/schema.sql`. It includes accounts and tokens,
subject profiles, assessment sessions, voice results, movement results, and
compressed raw movement traces.

On Windows, `backend/db.py` serializes SQLite data and encrypts the database
file with Windows DPAPI. The encrypted data is tied to the Windows user context.
This protects a copied database file from other users more than plaintext
storage would, but it does not protect against a process or malware running as
the same user while the app is open. Backups and recovery should be treated as
sensitive.

If `GEMINI_API_KEY` is configured and Gemini is reachable, chat messages and
recent conversation history leave the device and are sent to Google's service.
Voice and movement analysis are local. Keep secrets in an ignored `.env`.

The Flask backend is designed for local app communication, not public network
deployment. The current DPAPI implementation means the full application does
not support macOS or Linux.

## Model-training caveats

`backend/ml/train_voice_rf.py` reads `backend/parkinsons.data`, trains a
Random Forest over ten acoustic features, evaluates with stratified grouped
cross-validation by subject, and writes a joblib model. The dataset and model
are excluded from the repository. The training dataset's MDVP measures and
live Praat-derived measures are similar but not numerically identical; the code
itself warns that model outputs are indicative, not clinically validated.

[Back to README](../README.md)
