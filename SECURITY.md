# Security Policy

## Supported version

Security reports are currently accepted for the latest code on the `main`
branch. NeuroSign is an experimental desktop demo and is not intended for
internet-facing deployment or storage of real patient records.

## Reporting a vulnerability

Please do not report an unpatched vulnerability in a public issue. Use GitHub's
private vulnerability reporting for this repository:

<https://github.com/Luci-XO/neurosign/security/advisories/new>

If private reporting is unavailable, contact the repository owner privately
through their GitHub profile. Include the affected component, impact, and
reproduction details. Do not include real personal health data, passwords, API
keys, or other secrets.

## Data and deployment notes

- Keep `.env` private and never commit API keys.
- The database encryption currently uses Windows DPAPI and is scoped to the
  Windows user account. It does not protect data from processes running as that
  same user while the app is open.
- Configuring Gemini sends chat content to Google's Gemini service.
- Do not expose the local Flask backend to a public network.
- NeuroSign is not clinically validated and should not be used to diagnose or
  rule out a medical condition.
