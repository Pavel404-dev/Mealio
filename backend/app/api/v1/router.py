from fastapi import APIRouter

from app.api.v1.endpoints import (
    ingredients,
    meal_plan_summaries,
    meal_plans,
    pantry,
    recipes,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(ingredients.router)
api_router.include_router(pantry.router)
api_router.include_router(recipes.router)
api_router.include_router(meal_plans.router)
api_router.include_router(meal_plan_summaries.router)