"""Run the real API with isolated fixtures for the Android UI test."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from app.api.deps import get_meal_plan_generation_provider
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.integrations.meal_plan_generation import MealPlanProviderResult
from app.schemas.auth import UserRegister
from app.services.auth import AuthService
from tests.test_recipe_nutrition_totals_api import create_test_ingredient

ACCOUNT = {
    "email": "android-qa@example.com",
    "password": "Mealio-Android-QA-123",
}


class FixtureMealPlanProvider:
    model = "android-qa-fixture"

    async def select_meals(self, *, context_json: str) -> MealPlanProviderResult:
        context = json.loads(context_json)
        items = []
        for slot in context["meal_types"]:
            candidate = next(
                row for row in context["candidates"] if slot in row["allowed_slots"]
            )
            items.append(
                {
                    "meal_type": slot,
                    "candidate_number": candidate["candidate_number"],
                    "serving_hundredths": 100,
                }
            )
        return MealPlanProviderResult({"items": items})


async def seed_account_and_recipes(app: FastAPI) -> None:
    async with get_sessionmaker()() as db:
        registration = await AuthService(db).register_user(
            UserRegister(full_name="Android QA", **ACCOUNT)
        )
        registration.user.email_verified_at = datetime.now(UTC)
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        login = await client.post("/api/v1/auth/login", json=ACCOUNT)
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        ingredient = await create_test_ingredient(
            client,
            headers=headers,
            name="Android QA ingredient",
            nutrition_value={
                "portion_g": "100",
                "calories": "165",
                "protein_g": "31",
                "carbs_g": "0",
                "fat_g": "3.6",
            },
        )
        for meal_type, title, servings, quantity_g in (
            ("lunch", "QA Lunch Bowl", 4, "200"),
            ("dinner", "QA Dinner Bowl", 2, "250"),
        ):
            recipe = await client.post(
                "/api/v1/recipes",
                headers=headers,
                json={
                    "title": title,
                    "instructions": "Mix and serve.",
                    "meal_type": meal_type,
                    "servings": servings,
                    "ingredients": [
                        {"ingredient_id": ingredient["id"], "quantity_g": quantity_g}
                    ],
                },
            )
            recipe.raise_for_status()


def create_app() -> FastAPI:
    database = make_url(get_settings().database_url)
    if (
        database.drivername != "postgresql+asyncpg"
        or database.host != "127.0.0.1"
        or database.database != "mealio_android_qa"
    ):
        raise RuntimeError(
            "Android QA requires a fresh local mealio_android_qa database"
        )

    from app.main import app

    app.dependency_overrides[get_meal_plan_generation_provider] = (
        FixtureMealPlanProvider
    )
    api_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with api_lifespan(app):
            await seed_account_and_recipes(app)
            yield

    app.router.lifespan_context = lifespan
    return app
