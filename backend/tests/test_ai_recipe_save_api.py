from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_recipe_generation_provider
from app.main import app
from app.models.ingredient import Ingredient, UserIngredient
from app.models.meal_plan import MealPlan, MealPlanItem
from app.models.recipe import Recipe, RecipeIngredient

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
INGREDIENTS_URL = "/api/v1/ingredients"
PANTRY_URL = "/api/v1/pantry"
RECIPES_URL = "/api/v1/recipes"
AI_RECIPE_SAVE_URL = "/api/v1/recipes/ai/save-preview"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    email = email or f"ai-save-user-{uuid4()}@example.com"
    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "AI Save User",
            "password": password,
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        LOGIN_URL,
        json={
            "email": email,
            "password": password,
        },
    )
    assert login_response.status_code == 200

    return register_response.json(), {
        "Authorization": f"Bearer {login_response.json()['access_token']}"
    }


async def create_ingredient(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str | None = None,
    calories: str = "165",
    protein_g: str = "31",
    carbs_g: str = "0",
    fat_g: str = "3.6",
    portion_g: str = "100",
) -> str:
    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json={
            "name": name or f"AI save ingredient {uuid4()}",
            "category": "test",
            "nutrition_value": {
                "calories": calories,
                "protein_g": protein_g,
                "carbs_g": carbs_g,
                "fat_g": fat_g,
                "portion_g": portion_g,
            },
        },
    )
    assert response.status_code == 201

    return response.json()["id"]


async def add_pantry_item(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    ingredient_id: str,
    quantity_g: str,
) -> None:
    response = await client.post(
        PANTRY_URL,
        headers=headers,
        json={
            "ingredient_id": ingredient_id,
            "quantity_g": quantity_g,
        },
    )
    assert response.status_code == 201


def save_payload(
    ingredient_id: str,
    **overrides,
) -> dict:
    payload = {
        "title": "Chicken Rice Bowl",
        "description": "Generated recipe",
        "diet_type": "balanced",
        "instructions": [
            "Cook the rice.",
            "Cook the chicken.",
            "Serve together.",
        ],
        "ingredients": [
            {
                "ingredient_id": ingredient_id,
                "quantity_g": "200",
            }
        ],
    }
    payload.update(overrides)
    return payload


async def count_rows(db_session: AsyncSession, model) -> int:
    result = await db_session.execute(select(func.count()).select_from(model))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_success(client: AsyncClient) -> None:
    user, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(ingredient_id),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["created_by_user_id"] == user["id"]
    assert data["title"] == "Chicken Rice Bowl"
    assert data["description"] == "Generated recipe"
    assert data["diet_type"] == "balanced"
    assert data["instructions"] == (
        "1. Cook the rice.\n" "2. Cook the chicken.\n" "3. Serve together."
    )
    assert len(data["recipe_ingredients"]) == 1
    assert data["recipe_ingredients"][0]["ingredient_id"] == ingredient_id
    assert Decimal(str(data["recipe_ingredients"][0]["quantity_g"])) == Decimal("200")


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_requires_authentication(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        json=save_payload(ingredient_id),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_saved_ai_recipe_belongs_only_to_current_user(
    client: AsyncClient,
) -> None:
    first_user, first_headers = await create_authenticated_user(client)
    _, second_headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=first_headers)

    save_response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=first_headers,
        json=save_payload(ingredient_id),
    )
    assert save_response.status_code == 201
    recipe = save_response.json()
    assert recipe["created_by_user_id"] == first_user["id"]

    get_response = await client.get(
        f"{RECIPES_URL}/{recipe['id']}",
        headers=second_headers,
    )
    assert get_response.status_code == 404

    list_response = await client.get(RECIPES_URL, headers=second_headers)
    assert list_response.status_code == 200
    assert recipe["id"] not in {item["id"] for item in list_response.json()}


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_rejects_missing_ingredient_atomically(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe_count_before = await count_rows(db_session, Recipe)
    recipe_ingredient_count_before = await count_rows(db_session, RecipeIngredient)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(str(uuid4())),
    )

    assert response.status_code == 404
    assert "Ingredients not found" in response.json()["detail"]
    assert await count_rows(db_session, Recipe) == recipe_count_before
    assert (
        await count_rows(db_session, RecipeIngredient) == recipe_ingredient_count_before
    )


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_rejects_duplicate_ingredient(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(
            ingredient_id,
            ingredients=[
                {"ingredient_id": ingredient_id, "quantity_g": "100"},
                {"ingredient_id": ingredient_id, "quantity_g": "200"},
            ],
        ),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_rejects_generated_ingredient_fields(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(
            ingredient_id,
            ingredients=[
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": "100",
                    "name": "Chicken breast",
                    "unit": "g",
                },
            ],
        ),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_rejects_invalid_quantity(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(
            ingredient_id,
            ingredients=[
                {"ingredient_id": ingredient_id, "quantity_g": "0"},
            ],
        ),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_rejects_blank_title(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(ingredient_id, title="   "),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_rejects_empty_instruction_list(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(ingredient_id, instructions=[]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_rejects_blank_instruction_step(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(
            ingredient_id,
            instructions=["Cook the chicken.", "   "],
        ),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_calculates_nutrition_totals(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(
        client,
        headers=headers,
        calories="165",
        protein_g="31",
        carbs_g="0",
        fat_g="3.6",
        portion_g="100",
    )

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(
            ingredient_id,
            ingredients=[
                {"ingredient_id": ingredient_id, "quantity_g": "200"},
            ],
        ),
    )

    assert response.status_code == 201
    data = response.json()
    assert Decimal(str(data["total_calories"])) == Decimal("330")
    assert Decimal(str(data["total_protein_g"])) == Decimal("62")
    assert Decimal(str(data["total_carbs_g"])) == Decimal("0")
    assert Decimal(str(data["total_fat_g"])) == Decimal("7.20")


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_does_not_mutate_pantry(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=ingredient_id,
        quantity_g="500",
    )

    user_id = UUID(user["id"])
    ingredient_uuid = UUID(ingredient_id)
    pantry_quantity_stmt = select(UserIngredient.quantity_g).where(
        UserIngredient.user_id == user_id,
        UserIngredient.ingredient_id == ingredient_uuid,
    )
    quantity_before = (await db_session.execute(pantry_quantity_stmt)).scalar_one()
    pantry_count_before = await count_rows(db_session, UserIngredient)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(ingredient_id),
    )

    assert response.status_code == 201
    quantity_after = (await db_session.execute(pantry_quantity_stmt)).scalar_one()
    assert Decimal(str(quantity_after)) == Decimal(str(quantity_before))
    assert await count_rows(db_session, UserIngredient) == pantry_count_before


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_does_not_call_provider(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)
    provider_dependency_calls = 0

    def provider_dependency():
        nonlocal provider_dependency_calls
        provider_dependency_calls += 1
        raise AssertionError("Recipe generation provider must not be resolved")

    app.dependency_overrides[get_recipe_generation_provider] = provider_dependency

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(ingredient_id),
    )

    assert response.status_code == 201
    assert provider_dependency_calls == 0


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_does_not_create_ingredients(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)
    ingredient_count_before = await count_rows(db_session, Ingredient)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(ingredient_id),
    )

    assert response.status_code == 201
    assert await count_rows(db_session, Ingredient) == ingredient_count_before


@pytest.mark.asyncio
async def test_save_ai_recipe_preview_does_not_mutate_meal_plans(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)
    meal_plan_count_before = await count_rows(db_session, MealPlan)
    meal_plan_item_count_before = await count_rows(db_session, MealPlanItem)

    response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=save_payload(ingredient_id),
    )

    assert response.status_code == 201
    assert await count_rows(db_session, MealPlan) == meal_plan_count_before
    assert await count_rows(db_session, MealPlanItem) == meal_plan_item_count_before


@pytest.mark.asyncio
async def test_duplicate_save_requests_create_two_recipes(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(client, headers=headers)
    payload = save_payload(ingredient_id)

    first_response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=payload,
    )
    second_response = await client.post(
        AI_RECIPE_SAVE_URL,
        headers=headers,
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["id"] != second_response.json()["id"]
