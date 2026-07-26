from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_recipe_generation_provider
from app.main import app
from app.models.ingredient import Ingredient
from app.models.recipe import Recipe, RecipeIngredient
from app.schemas.ai_recipe import (
    AIRecipeProviderRequest,
    GeneratedRecipeData,
    GeneratedRecipeIngredient,
)

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
INGREDIENTS_URL = "/api/v1/ingredients"
GENERATE_URL = "/api/v1/recipes/ai/generate-preview"
MATCH_URL = "/api/v1/recipes/ai/ingredient-match-suggestions"
SAVE_URL = "/api/v1/recipes/ai/save-preview"


class FakeRecipeGenerationProvider:
    def __init__(self, *, ingredient_name: str) -> None:
        self.calls: list[AIRecipeProviderRequest] = []
        self.result = GeneratedRecipeData(
            title="Chicken Rice Bowl",
            description="A practical dinner.",
            servings=2,
            prep_time_minutes=30,
            diet_type="balanced",
            ingredients=[
                GeneratedRecipeIngredient(
                    name=ingredient_name,
                    quantity_g="200.25",
                )
            ],
            instructions=[
                "Cook the chicken.",
                "Serve the chicken.",
            ],
        )

    async def generate_recipe(
        self,
        *,
        provider_request: AIRecipeProviderRequest,
    ) -> GeneratedRecipeData:
        self.calls.append(provider_request)
        return self.result


async def create_authenticated_user(client: AsyncClient) -> dict[str, str]:
    email = f"ai-quantity-flow-{uuid4()}@example.com"
    password = "Mealio-password-123"
    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "AI Quantity Flow User",
            "password": password,
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        LOGIN_URL,
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


async def create_ingredient(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str,
) -> dict:
    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json={
            "name": name,
            "category": "protein",
            "nutrition_value": {
                "calories": "165",
                "protein_g": "31",
                "carbs_g": "0",
                "fat_g": "3.6",
                "portion_g": "100",
            },
        },
    )
    assert response.status_code == 201
    return response.json()


async def count_rows(db_session: AsyncSession, model) -> int:
    return (
        await db_session.execute(select(func.count()).select_from(model))
    ).scalar_one()


@pytest.mark.asyncio
async def test_generated_quantity_g_flows_through_explicit_match_and_save(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    headers = await create_authenticated_user(client)
    ingredient_name = f"Flow Chicken {uuid4()}"
    ingredient = await create_ingredient(
        client,
        headers=headers,
        name=ingredient_name,
    )
    provider = FakeRecipeGenerationProvider(ingredient_name=ingredient_name)
    app.dependency_overrides[get_recipe_generation_provider] = lambda: provider
    recipe_count_before = await count_rows(db_session, Recipe)
    ingredient_count_before = await count_rows(db_session, Ingredient)

    try:
        generate_response = await client.post(
            GENERATE_URL,
            headers=headers,
            json={
                "meal_type": "dinner",
                "servings": 2,
                "max_prep_time_minutes": 45,
                "use_only_pantry": False,
            },
        )
        assert generate_response.status_code == 200
        generated = generate_response.json()
        generated_ingredient = generated["ingredients"][0]
        assert set(generated_ingredient) == {"name", "quantity_g"}
        assert await count_rows(db_session, Recipe) == recipe_count_before
        assert await count_rows(db_session, Ingredient) == ingredient_count_before
        assert len(provider.calls) == 1

        match_response = await client.post(
            MATCH_URL,
            headers=headers,
            json={"ingredient_names": [generated_ingredient["name"]]},
        )
        assert match_response.status_code == 200
        exact_match = match_response.json()["results"][0]["exact_match"]
        assert exact_match is not None
        assert exact_match["ingredient_id"] == ingredient["id"]
        assert await count_rows(db_session, Recipe) == recipe_count_before
        assert len(provider.calls) == 1

        save_response = await client.post(
            SAVE_URL,
            headers=headers,
            json={
                "title": generated["title"],
                "description": generated["description"],
                "diet_type": generated["diet_type"],
                "instructions": generated["instructions"],
                "ingredients": [
                    {
                        "ingredient_id": exact_match["ingredient_id"],
                        "quantity_g": generated_ingredient["quantity_g"],
                    }
                ],
            },
        )
        assert save_response.status_code == 201
        saved = save_response.json()
        assert len(provider.calls) == 1
        assert await count_rows(db_session, Recipe) == recipe_count_before + 1
        assert await count_rows(db_session, Ingredient) == ingredient_count_before

        recipe_ingredient = (
            await db_session.execute(
                select(RecipeIngredient).where(
                    RecipeIngredient.recipe_id == UUID(saved["id"]),
                    RecipeIngredient.ingredient_id == UUID(ingredient["id"]),
                )
            )
        ).scalar_one()
        assert Decimal(str(recipe_ingredient.quantity_g)) == Decimal("200.25")
        quantity_g = Decimal(str(generated_ingredient["quantity_g"]))
        nutrition_factor = quantity_g / Decimal("100")

        assert Decimal(str(saved["total_calories"])) == (
            Decimal("165") * nutrition_factor
        )
        assert Decimal(str(saved["total_protein_g"])) == (
            Decimal("31") * nutrition_factor
        )
        assert Decimal(str(saved["total_carbs_g"])) == (Decimal("0") * nutrition_factor)
        assert Decimal(str(saved["total_fat_g"])) == (Decimal("3.6") * nutrition_factor)
    finally:
        app.dependency_overrides.pop(get_recipe_generation_provider, None)
