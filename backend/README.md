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

Create a local environment file:

```bash
cp .env.example .env
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the application from the `backend/` directory:

```bash
uvicorn app.main:app --reload
```

Health check:

```txt
GET /health
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