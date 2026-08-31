# Contributing

Thanks for considering contributing to NoName.

## Ground rules

- **No secrets.** Never commit real tokens, keys, passwords, `.env` files, database dumps, production logs, user data, VPN credentials, or identifiable infrastructure details (real domains, IPs, server identities). If you accidentally commit something sensitive, stop and ask maintainers for help with removal and rotation.
- **No production configuration.** Configuration must be environment-driven via `.env` / settings; add placeholders to `.env.example` and document new variables.
- **Safe by default.** New features must not trigger network calls, webhooks, payments, or message sends by default in development, and must not weaken default auth (e.g. admin checks).
- **Keep integrations generic.** Provider integrations (VPN, payments) must implement the existing interfaces (see `services/vpn.py`), be disabled by default, and must not hardcode endpoints or credentials.
- **No AI-generated placeholder docs.** If you change behavior, update the README and `.env.example` in the same pull request.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your own development values
python app.py          # dev mode: long polling + local web server
```

## Branch and pull requests

1. Create a feature branch from `main`: `git checkout -b feat/your-change`.
2. Commit focused changes with clear messages.
3. Open a pull request against `main`, describe what and why you changed, and mention affected settings/docs.
4. The template currently has no CI; please verify your changes locally before opening the PR:

```bash
python -m compileall app.py bot config models services web
```

If you add tests/lint/type-check tooling, document the commands in the README and run them.

## Code style

- Python: PEP 8, type hints on public functions, no third-party dependencies without justification, no dead code or comments that repeat the code.
- Keep bot-facing strings consistent with existing copy and the `APP_NAME` setting; avoid hardcoding branding.
- Frontend: plain JS/HTML/CSS like the existing pages; no build step.

## Reporting issues

- **Bugs**: include reproduction steps, expected vs actual behavior, and environment details (OS, Python version).
- **Security issues**: do not file public issues — use the private process in `SECURITY.md`.
- **Feature requests**: describe the use case and how it fits the generic template; prefer configurable/optional features over hardcoded behavior.

## When adding configuration

- Read new values from the environment in `config/settings.py`.
- Add the variable with a safe placeholder and a comment to `.env.example`.
- Document it in the README's environment-variable section.
- Keep defaults non-destructive: disabled providers, no defaults that contact networks, no default admin IDs.