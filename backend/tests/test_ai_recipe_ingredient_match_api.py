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
AI_INGREDIENT_MATCH_URL = "/api/v1/recipes/ai/ingredient-match-suggestions"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    email = email or f"ai-match-user-{uuid4()}@example.com"
    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "AI Ingredient Match User",
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
    name: str,
    category: str | None = "test",
) -> dict:
    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json={
            "name": name,
            "category": category,
            "nutrition_value": {
                "calories": "100",
                "protein_g": "10",
                "carbs_g": "10",
                "fat_g": "2",
                "portion_g": "100",
            },
        },
    )
    assert response.status_code == 201
    return response.json()


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


async def count_rows(db_session: AsyncSession, model) -> int:
    result = await db_session.execute(select(func.count()).select_from(model))
    return result.scalar_one()


def match_payload(*ingredient_names: str) -> dict:
    return {"ingredient_names": list(ingredient_names)}


@pytest.mark.asyncio
async def test_successful_batch_exact_matching(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)
    chicken = await create_ingredient(
        client,
        headers=headers,
        name="Chicken Breast",
        category="protein",
    )
    rice = await create_ingredient(
        client,
        headers=headers,
        name="Rice",
        category="grain",
    )

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("Chicken Breast", "Rice", "Olive oil"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "generated_name": "Chicken Breast",
                "exact_match": {
                    "ingredient_id": chicken["id"],
                    "name": "Chicken Breast",
                    "category": "protein",
                },
            },
            {
                "generated_name": "Rice",
                "exact_match": {
                    "ingredient_id": rice["id"],
                    "name": "Rice",
                    "category": "grain",
                },
            },
            {
                "generated_name": "Olive oil",
                "exact_match": None,
            },
        ]
    }


@pytest.mark.asyncio
async def test_ingredient_match_suggestions_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        json=match_payload("Rice"),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_exact_matching_is_case_insensitive(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(
        client,
        headers=headers,
        name="Chicken Breast",
        category="protein",
    )

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("cHiCkEn bReAsT"),
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["generated_name"] == "cHiCkEn bReAsT"
    assert result["exact_match"]["ingredient_id"] == ingredient["id"]


@pytest.mark.asyncio
async def test_ingredient_names_are_trimmed(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(
        client,
        headers=headers,
        name="Rice",
        category="grain",
    )

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("   Rice   "),
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["generated_name"] == "Rice"
    assert result["exact_match"]["ingredient_id"] == ingredient["id"]


@pytest.mark.asyncio
async def test_unmatched_ingredient_returns_null(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("Olive oil"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "results": [{"generated_name": "Olive oil", "exact_match": None}]
    }


@pytest.mark.asyncio
async def test_result_order_matches_request_order(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)
    chicken = await create_ingredient(
        client,
        headers=headers,
        name="Chicken Breast",
    )
    rice = await create_ingredient(client, headers=headers, name="Rice")

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("Rice", "Unknown ingredient", "Chicken Breast"),
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["generated_name"] for item in results] == [
        "Rice",
        "Unknown ingredient",
        "Chicken Breast",
    ]
    assert results[0]["exact_match"]["ingredient_id"] == rice["id"]
    assert results[1]["exact_match"] is None
    assert results[2]["exact_match"]["ingredient_id"] == chicken["id"]


@pytest.mark.asyncio
async def test_duplicate_names_after_normalization_return_422(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload(" Rice ", "rICE"),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_blank_name_returns_422(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("Rice", "   "),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_empty_name_list_returns_422(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_more_than_maximum_names_returns_422(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient_names = [f"Ingredient {index}" for index in range(51)]

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json={"ingredient_names": ingredient_names},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_substring_name_is_not_an_exact_match(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(
        client,
        headers=headers,
        name="Chicken Breast",
    )

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("Chicken Breast", "Chicken"),
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["exact_match"]["ingredient_id"] == ingredient["id"]
    assert results[1] == {"generated_name": "Chicken", "exact_match": None}


@pytest.mark.asyncio
async def test_ingredient_match_suggestions_do_not_call_provider(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)
    provider_dependency_calls = 0

    def provider_dependency():
        nonlocal provider_dependency_calls
        provider_dependency_calls += 1
        raise AssertionError("Recipe generation provider must not be resolved")

    app.dependency_overrides[get_recipe_generation_provider] = provider_dependency

    try:
        response = await client.post(
            AI_INGREDIENT_MATCH_URL,
            headers=headers,
            json=match_payload("Rice"),
        )
    finally:
        app.dependency_overrides.pop(get_recipe_generation_provider, None)

    assert response.status_code == 200
    assert provider_dependency_calls == 0


@pytest.mark.asyncio
async def test_ingredient_match_suggestions_do_not_mutate_ingredients(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await create_authenticated_user(client)
    await create_ingredient(
        client,
        headers=headers,
        name="Rice",
        category="grain",
    )
    ingredient_state_stmt = select(
        Ingredient.id,
        Ingredient.name,
        Ingredient.category,
    ).order_by(Ingredient.id)
    state_before = (await db_session.execute(ingredient_state_stmt)).all()

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("Rice", "Olive oil"),
    )

    assert response.status_code == 200
    state_after = (await db_session.execute(ingredient_state_stmt)).all()
    assert state_after == state_before


@pytest.mark.asyncio
async def test_ingredient_match_suggestions_do_not_create_recipes(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await create_authenticated_user(client)
    recipe_count_before = await count_rows(db_session, Recipe)
    recipe_ingredient_count_before = await count_rows(db_session, RecipeIngredient)

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("Rice"),
    )

    assert response.status_code == 200
    assert await count_rows(db_session, Recipe) == recipe_count_before
    assert (
        await count_rows(db_session, RecipeIngredient) == recipe_ingredient_count_before
    )


@pytest.mark.asyncio
async def test_ingredient_match_suggestions_do_not_mutate_pantry(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers, name="Rice")
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=ingredient["id"],
        quantity_g="500",
    )
    pantry_count_before = await count_rows(db_session, UserIngredient)
    pantry_quantity_stmt = select(UserIngredient.quantity_g).where(
        UserIngredient.user_id == UUID(user["id"]),
        UserIngredient.ingredient_id == UUID(ingredient["id"]),
    )
    quantity_before = (await db_session.execute(pantry_quantity_stmt)).scalar_one()

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("Rice"),
    )

    assert response.status_code == 200
    quantity_after = (await db_session.execute(pantry_quantity_stmt)).scalar_one()
    assert Decimal(str(quantity_after)) == Decimal(str(quantity_before))
    assert await count_rows(db_session, UserIngredient) == pantry_count_before


@pytest.mark.asyncio
async def test_ingredient_match_suggestions_do_not_mutate_meal_plans(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await create_authenticated_user(client)
    meal_plan_count_before = await count_rows(db_session, MealPlan)
    meal_plan_item_count_before = await count_rows(db_session, MealPlanItem)

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json=match_payload("Rice"),
    )

    assert response.status_code == 200
    assert await count_rows(db_session, MealPlan) == meal_plan_count_before
    assert await count_rows(db_session, MealPlanItem) == meal_plan_item_count_before


@pytest.mark.asyncio
async def test_extra_request_fields_return_422(client: AsyncClient) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        AI_INGREDIENT_MATCH_URL,
        headers=headers,
        json={
            "ingredient_names": ["Rice"],
            "create_missing": True,
        },
    )

    assert response.status_code == 422
