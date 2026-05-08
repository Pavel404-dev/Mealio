from fastapi import FastAPI

app = FastAPI(
    title="Mealio Backend API",
    description="Backend API for the Mealio mobile application.",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "mealio-backend",
    }