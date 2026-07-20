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

## Notes

The application loads environment variables from:

```txt
backend/.env
```

Do not commit real `.env` files to the repository.