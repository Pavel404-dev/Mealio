# Mealio Backend

Backend API for the Mealio mobile application.

## Stack

- Python
- FastAPI
- Uvicorn
- PostgreSQL
- SQLAlchemy
- Alembic
- OpenAI Python SDK

## Local Development

From the repository root:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

On Linux or macOS, activate the environment and copy the example file with:

```bash
source .venv/bin/activate
cp .env.example .env
```

Health check:

```txt
http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "mealio-backend"
}
```

## AI Recipe Generation

The authenticated preview endpoint is:

```http
POST /api/v1/recipes/ai/generate-preview
```

It generates a structured recipe from the current user's pantry, nutrition
profile, and request preferences. The preview is not persisted in the recipes
or ingredients tables.

Configure the provider in `backend/.env` for manual backend development:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-luna
AI_REQUEST_TIMEOUT_SECONDS=30
```

For Docker Compose, place the same variables in a root `.env` file or export
them in the shell before running `docker compose up --build`. Real API keys
must never be committed or logged.

## Authentication Recovery

Password recovery is available through either a reset link or a six-digit email
OTP. Request responses are intentionally generic for both known and unknown email
addresses. OTP codes are never stored in plaintext; the shared OTP challenge
engine stores a purpose-bound HMAC-SHA256 digest and enforces expiry, resend,
delivery, and failed-attempt limits.

After a successful password reset, every refresh-token session and outstanding
password-reset credential for the user is revoked. Already issued stateless
access JWTs remain valid until their `exp` claim. Immediate access-token
invalidation and the Flutter OTP recovery UI are separate follow-up features.

## Notes

The application loads environment variables from:

```txt
backend/.env
```

Do not commit real `.env` files to the repository.
