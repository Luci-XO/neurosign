# Development setup

NeuroSign currently requires Windows for normal operation because database
encryption uses Windows DPAPI. The Electron launcher can locate POSIX Python
interpreters, but that does not make the backend database implementation
portable.

## Requirements

- Windows 10 or later.
- Node.js 20 or later with npm.
- Python 3.11.
- A microphone and mouse/pointer device to exercise the app.

## Install

From PowerShell:

```powershell
git clone https://github.com/Luci-XO/neurosign.git
Set-Location neurosign
npm ci

py -3.11 -m venv backend\venv
backend\venv\Scripts\python.exe -m pip install --upgrade pip
backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

Copy-Item .env.example .env
```

The `backend/ml/models/voice_rf.joblib` artifact and `backend/parkinsons.data`
training dataset are not included. The optional voice model will not load unless
you train and supply the model separately. Model training expects the UCI
Parkinson's dataset in `backend/parkinsons.data`; review the dataset's own
license and terms before obtaining or redistributing it.

## Run

From the project root:

```powershell
npm start
```

Electron starts `backend/app.py` from the backend working directory, waits for
the health endpoint on port `5057`, and then opens the renderer. Running
`backend/app.py` manually is generally unnecessary when launching Electron.

## Configuration

Copy `.env.example` to `.env`. The backend reads these variables:

| Name | Default | Notes |
|---|---|---|
| `NEUROSIGN_PORT` | `5057` | Electron and renderer URLs are currently hardcoded to the same port. Avoid changing this setting alone. |
| `NEUROSIGN_DB_PATH` | `neurosign.db` | Database filename under `backend/`. |
| `NEUROSIGN_DEBUG` | `false` | Flask debug mode; keep disabled for ordinary use. |
| `GEMINI_API_KEY` | empty | Optional online chat credential. Blank uses offline fallback. |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Gemini model name used by the optional chat client. |

Never commit `.env`, database files, recordings, or real personal health
information. Gemini chat content is sent externally when the API key is
configured and the service is available.

## Checks

From the project root:

```powershell
npm run lint
```

```powershell
backend\venv\Scripts\python.exe -m ruff check backend
Set-Location backend
.\venv\Scripts\python.exe -m unittest test_movement_features
```

`backend/test_models.py` is an integration script that sends live requests to
Gemini. It is not a routine offline test and may use an API key or incur API
charges.

## Troubleshooting

### Python environment not found

Recreate it at the exact location used by Electron:

```powershell
py -3.11 -m venv backend\venv
backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### Backend does not start

Read the Python output in the terminal. Confirm that dependencies installed and
that port `5057` is free. Electron waits up to 40 seconds for
`http://127.0.0.1:5057/api/health`.

### Database decryption fails

The database is protected using DPAPI for the Windows user context that
encrypted it. Launch NeuroSign as that same Windows user. Do not copy the
database to another device and assume it can be decrypted there.

### No online chat response

The app falls back to the offline keyword library if no key is configured or
Gemini setup/request fails. Check the backend output for the reported chat
service error. Do not publish the API key when asking for help.

[Back to README](../README.md)
