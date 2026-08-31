# Security Policy

## Reporting a vulnerability

Please report security vulnerabilities **privately**. Do **not** open a public issue for an unpatched vulnerability, and do not discuss exploit details in public before a fix is available.

Send a private report to:

- **Email**: `security@example.com` (placeholder — replace with a real, monitored address before operating a public service)
- For GitHub-hosted projects, you may use the repository's private vulnerability reporting feature (Security → Report a vulnerability) if enabled.

Vulnerabilities include, but are not limited to:

- authentication or authorization bypass;
- injection (SQL, command, HTML/template, SSRF);
- secrets, tokens or user data disclosure;
- payment/balance manipulation or webhook forgery;
- unsafe defaults that expose user data or infrastructure.

## What to include in a vulnerability report

A good report lets maintainers reproduce and fix the issue quickly. Include where possible:

1. Affected version or commit (repository + branch).
2. Component/module and endpoint or handler involved.
3. Step-by-step reproduction (minimal script, curl commands, or request/response pairs).
4. Expected vs actual behavior.
5. Impact assessment (what an attacker can do, what data is exposed).
6. Suggested fix if you have one (optional).

Redact or avoid attaching production data, database dumps, real tokens, or personal data.

## Disclosure expectations

- Maintainers will acknowledge receipt within [e.g., 3 business days — replace me].
- We will work on a fix, release it, and disclose details only after users have a reasonable chance to update.
- Security researchers may publish findings after a coordinated disclosure window agreed with the maintainers (default: e.g., 90 days after the fix is released).

## Supported versions

Only the latest release of the `main` branch is supported for security fixes. Older versions should be upgraded promptly.

## Rule: no secrets in public channels

Never submit secrets, tokens, API keys, database dumps, production logs, `.env` files, VPN credentials, or personal/identifiable user data in issues, pull requests, or any public channel. If you believe such data was exposed (including in Git history), contact the maintainers privately: the content must be purged and the affected credentials rotated.

## Maintainers

Before operating a real public service, replace the placeholder contact (`security@example.com`) with a monitored security address, document supported versions and disclosure windows, and define a responsible-disclosure workflow.