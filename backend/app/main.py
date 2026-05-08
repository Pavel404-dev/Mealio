from fastapi import FastAPI

from app.core.config import get_settings
from app.db.session import check_database_connection

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "mealio-backend",
    }


@app.get("/health/db")
async def database_health_check():
    await check_database_connection()

    return {
        "status": "ok",
        "database": "connected",
    }