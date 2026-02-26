# Bot Management Dashboard (Railway-ready)

This service adds a secure user interface for:

1. MetaMask sign-up/sign-in (challenge + signature verification).
2. Exchange API key/secret input (encrypted at rest).
3. Strategy configuration with JSON parameters.
4. Bot run/stop control with Telegram integration hooks.
5. A consolidated dashboard overview.

## Security defaults

- Wallet authentication via signed challenge (no password storage).
- JWT-based API sessions.
- Exchange and Telegram secrets encrypted with Fernet before database persistence.
- Rate limiting on auth routes.
- Strict response headers (CSP, HSTS, X-Frame-Options, no-referrer).
- No secret values are returned in API responses (masked only).

## Local run

1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r bot_management_dashboard/requirements.txt`
3. Copy env template:
   - `cp bot_management_dashboard/.env.example .env`
4. Generate a Fernet key:
   - `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
5. Set `DASHBOARD_ENCRYPTION_KEY` and `DASHBOARD_JWT_SECRET` in `.env`.
6. Start server:
   - `uvicorn bot_management_dashboard.main:app --host 0.0.0.0 --port 8000 --reload`

Open `http://localhost:8000`.

## Railway deployment

Yes, you can use Railway for both backend and frontend:

- **Single-service approach (recommended):** deploy this FastAPI service and serve frontend static files from the same Railway service.
- **Split approach:** deploy backend as one Railway service and static frontend (if later separated) as another Railway service, then set `DASHBOARD_CORS_ORIGINS`.

Use `bot_management_dashboard/railway.toml` for deploy defaults.

## Scale guidance

- Use Railway Postgres instead of SQLite (`DASHBOARD_DATABASE_URL`).
- Keep the dashboard API stateless and run multiple replicas.
- For real multi-user bot execution, run isolated workers/containers per user account and use queue-based orchestration.

