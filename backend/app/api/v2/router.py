from fastapi import APIRouter

from app.api.v2.endpoints import meal_plans

api_router = APIRouter(prefix="/api/v2")
api_router.include_router(meal_plans.router)
