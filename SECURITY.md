# Security policy

Saathi serves low-income workers, so it is built to hold as little of their data as possible.

## Design

| Threat | Mitigation |
|---|---|
| Personal data leak | The server is stateless and stores nothing. Profile, earnings, name, phone and worker ID stay in the browser. Complaint letters use placeholders that the browser fills in locally. |
| Personal numbers sent to the AI | Aadhaar, PAN, phone, email, UPI, card and bank numbers are masked before every Gemini call (`app/services/pii.py`). Photos are re-encoded on the phone, which strips EXIF/GPS. |
| Prompt injection | Worker text is wrapped in `<worker_input>` and the model is told to treat it as data; `<` and `>` are neutralised so the tag cannot be closed. Numbers, eligibility and helplines come from code and curated data, not the model. |
| Secret exposure | The Gemini key is read from the environment / Secret Manager only; `.env` is git-ignored; `/api/health` reports only whether AI is on. |
| XSS / clickjacking | Strict CSP (`script-src 'self'`, no inline code, no third-party origins), `textContent` rendering only, `X-Frame-Options: DENY`, `frame-ancestors 'none'`. |
| Abuse / cost attacks | Per-IP rate limit, 8 MB body cap, strict Pydantic bounds with `extra="forbid"`, image magic-byte checks, Gemini timeout and response cache, Cloud Run max-instances cap. |
| Vulnerable dependencies | Pinned versions, `pip-audit` in CI, Dependabot for pip and GitHub Actions. |
| Container breakout impact | Slim image running as an unprivileged user. |

## Reporting a vulnerability

Please open a private security advisory on this repository rather than a public issue. We aim
to acknowledge reports within 3 days.
