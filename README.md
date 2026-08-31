# NoName

A generic starter/template for a Telegram bot service with optional, configurable external-service integrations. It includes a Telegram bot (aiogram 3), a small web application (aiohttp) with a WebApp frontend, a subscription/balance/user model, and a pluggable VPN-provider interface that ships with a safe offline **mock** provider.

> **Disclaimer**: This project is **not** a ready-to-operate VPN service. It is a code template. You are responsible for legal compliance, infrastructure, security, privacy, hosting, service-provider terms, and all operational decisions. Real provider, payment and server integrations must be implemented, configured, reviewed and maintained by you.

## Features

- Telegram bot: `/start`, referral links, trial activation, subscription activation, admin command set
- WebApp UI (vanilla JS) served at `/` with connect/instructions pages
- REST API: user data, tariffs config, buy subscription, promo codes, payment creation, subscription-to-Clash conversion
- Subscription model: tariffs, balance, promo codes, referrals, trial, expiry notifications
- Pluggable VPN provider:
  - `MockVPNProvider` — offline, safe-by-default, never contacts the network
  - `XuiProvider` — optional adapter for 3x-UI panels (disabled unless configured)
- Optional payment adapters (disabled by default; example Platega adapter included)
- SQLite database via aiosqlite

## Tech stack

- Python 3.11+ (developed on 3.14)
- [aiogram](https://github.com/aiogram/aiogram) 3.x — Telegram Bot API
- [aiohttp](https://docs.aiohttp.org) — web server, REST API, Telegram webhook
- [aiosqlite](https://github.com/omnilib/aiosqlite) — async SQLite
- [python-dotenv](https://github.com/theskumar/python-dotenv) — environment loading
- No build step: the frontend is static HTML/CSS/JS served by aiohttp

## Project structure

```
app.py                    # entry point: web server, webhook/polling, bot setup
config/settings.py        # all configuration from environment variables
bot/                      # Telegram bot handlers
  handlers.py             #   user-facing commands
  admin_handlers.py       #   admin commands (restricted to TELEGRAM_ADMIN_IDS)
services/
  vpn.py                  # VPN provider interface + mock provider + factory
  xui_api.py              # optional 3x-UI panel adapter (transport layer)
  db.py                   # SQLite access layer
  payment.py              # payment ID helper
  platega.py              # example payment adapter (disabled by default)
  sub_convert.py          # subscription link -> Clash YAML conversion
  notify.py               # subscription-expiry notifications
  auth.py                 # Telegram WebApp initData verification
models/user.py            # user model
web/
  routes.py               # REST API + static serving + payment webhook
  static/                 # frontend (index.html, connect.html, privacy/terms)
data/                     # SQLite database lives here at runtime (gitignored)
```

## Prerequisites

- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- (Optional, only if you use the xui provider) a 3x-UI panel instance you own/operate

## Installation

### 1. Clone and prepare a virtual environment

```bash
git clone <your-repository-url> noname
cd noname
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

- `TELEGRAM_BOT_TOKEN` — your bot token
- `BOT_USERNAME` — your bot username (without `@`)

`TELEGRAM_ADMIN_IDS` is optional for development; admin commands are disabled when no admin IDs are configured.

> Never commit your real `.env`. It is protected by `.gitignore`.

### 3. Run (development, long polling)

```bash
python app.py
```

This starts:

- the Telegram bot with long polling;
- the local web server at http://127.0.0.1:8000 serving the WebApp and REST API.

Open the bot and press start. The default `VPN_PROVIDER=mock` needs no external infrastructure.

### 4. Run with a webhook (production-like)

Set `WEBHOOK_ENABLED=true` and a public HTTPS `BASE_URL`, then:

```bash
python app.py
```

On startup the app calls `setWebhook` with `BASE_URL/telegram-webhook`. Telegram webhooks require a valid public HTTPS endpoint (e.g. reverse proxy or tunnel).

## Environment variables

See `.env.example` for the complete list with comments. The most important ones:

| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Bot token |
| `TELEGRAM_ADMIN_IDS` | empty | Comma-separated admin Telegram user IDs |
| `BASE_URL` | auto from HOST/PORT | Public base URL (WebApp, webhook) |
| `WEBHOOK_ENABLED` | `false` | Enable Telegram webhook mode |
| `DB_URL` | `sqlite+aiosqlite:///./data/noname.db` | Database URL |
| `VPN_PROVIDER` | `mock` | `mock` or `xui` |
| `VPN_API_URL`, `VPN_PASSWORD`, `VPN_INBOUND_IDS` | — | Panel connection (xui) |
| `PAYMENT_PROVIDER` | `none` | Payment adapter; `none` disables payments |
| `TARIFFS` | sample values | `DAYS:PRICE,...` tariff map |
| `SUPPORT_URL` | placeholder | Support link |

## Database

The app uses SQLite by default; the schema (users, payments, promocodes, referrals, notifications) is created automatically on first startup at `./data/noname.db` (`data/` is gitignored). There is no separate migration step for the default setup.

If you switch to PostgreSQL or another backend, update `DB_URL` and adjust `services/db.py` accordingly.

## Custom provider adapters

All VPN backends implement the `VPNProvider` interface in `services/vpn.py`:

```python
class MyProvider(VPNProvider):
    name = "myprovider"

    async def add_client(self, email, days, inbound_id=None): ...
    async def update_client_expiry(self, email, days): ...
    async def remove_client(self, email): ...
    async def build_link_for_email(self, email, inbound_id=None): ...
    async def get_client_activity(self, email): ...
```

Then register it in `get_provider()` and set `VPN_PROVIDER=myprovider` in your `.env`. A `MockVPNProvider` is included as a reference implementation. Keep your adapter backend-agnostic: never hardcode credentials, endpoints or infrastructure assumptions; read them from settings.

Payment adapters follow the same pattern: implement a module exposing `create_transaction(...)`, gate it behind `PAYMENT_PROVIDER` and credential settings, and wire the webhook verification into `web/routes.py`.

## Tests, lint and type checks

This template currently ships **no automated tests and no lint/type-check configuration**. The test command is therefore:

```bash
python -m compileall app.py bot config models services web
```

Consider adding `pytest`, `ruff` and `mypy` before production use, and read `CONTRIBUTING.md`.

## Security notes

- Admin commands only run for user IDs listed in `TELEGRAM_ADMIN_IDS`; with no IDs configured, admin commands are effectively disabled.
- `DEV_MODE` (plain `?userId=` auth) must stay `false` in production.
- Payment webhooks are rate-limited and signature/secret verified when configured; the endpoint returns `404` unless a payment provider is configured.
- The mock provider makes no network requests; external credentials are only read from the environment.
- Enable TLS in production (reverse proxy); never run `USE_HTTPS=false` behind public URLs without a terminating proxy.
- Auth data from the Telegram WebApp is verified with HMAC against the bot token (`services/auth.py`).

## Before production use

- [ ] Create new secrets (bot token, webhook secret, payment keys) and store them securely (e.g. a secrets manager); rotate copied/example credentials
- [ ] Configure your own database and infrastructure (DB backend, backups, TLS, reverse proxy, host/domain)
- [ ] Configure a real provider integration (implement/select a `VPNProvider`; never ship with mock in production)
- [ ] Implement rate limiting and abuse prevention beyond the basic per-IP limits
- [ ] Configure backups for the database; keep them out of the repository
- [ ] Configure privacy-safe logging (no secrets, no personal data in logs)
- [ ] Replace the template privacy policy and terms with documents reviewed by legal counsel for your jurisdiction
- [ ] Remove or replace all placeholder links/contacts (support URL, bot username, `example.invalid` values)
- [ ] Perform an independent security review (dependency audit, configuration scan, penetration test where appropriate)
- [ ] Validate legal requirements in your deployment jurisdiction (data protection, telecom/VPN regulations, payment rules)

## License

This project is licensed under the [MIT License](LICENSE).