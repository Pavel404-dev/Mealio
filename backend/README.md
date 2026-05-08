# Mealio Backend

Backend API for the Mealio mobile application.

## Stack

- Python
- FastAPI
- Uvicorn
- PostgreSQL
- SQLAlchemy
- Alembic

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

## Notes

The application loads environment variables from:

```txt
backend/.env
```

Do not commit real `.env` files to the repository.