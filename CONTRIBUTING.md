# Contributing to NeuroSign

Thank you for considering a contribution. NeuroSign is an educational screening
demo, not a medical device or a clinically validated diagnostic tool.

## Before you begin

- Search existing issues before opening a new one.
- For a large change, open an issue first to discuss the approach.
- Keep changes focused and explain their user impact.
- Do not submit real patient data, recordings, credentials, or API keys.
- Do not describe experimental scores as diagnoses or validated clinical results.

## Development setup

1. Install Node.js 20 or later and Python 3.11.
2. Install the project dependencies:

   ```powershell
   npm ci
   py -3.11 -m venv backend\venv
   backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
   backend\venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
   ```

3. Copy `.env.example` to `.env` if you need to configure optional settings.
   Never commit `.env` or put secrets in issues or pull requests.
4. Start the desktop app with `npm start`.

The database currently uses Windows DPAPI for encryption, so the complete
application backend is Windows-specific.

## Checks

From the repository root:

```powershell
npm run lint
```

```powershell
Set-Location backend
.\venv\Scripts\python.exe -m ruff check .
.\venv\Scripts\python.exe -m unittest test_movement_features
```

Do not run `test_models.py` as part of routine offline checks: it sends requests
to the configured Gemini service and can incur external API usage.

## Pull requests

- Use a clear title and explain what changed and why.
- Include relevant tests for behavior changes.
- Update documentation when setup, behavior, or configuration changes.
- State which checks you ran and their results.
- Keep unrelated formatting or generated files out of the pull request.

By contributing, you agree to follow the project’s [Code of Conduct](CODE_OF_CONDUCT.md).
