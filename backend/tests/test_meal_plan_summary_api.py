from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
MEAL_PLANS_URL = "/api/v1/meal-plans"
INGREDIENTS_URL = "/api/v1/ingredients"

MEAL_PLAN_SUMMARY_PATHS = (
    "summary",
    "daily-summary",
)


def meal_plan_summary_url(meal_plan_id: str) -> str:
    return f"{MEAL_PLANS_URL}/{meal_plan_id}/summary"


def meal_plan_daily_summary_url(meal_plan_id: str) -> str:
    return f"{MEAL_PLANS_URL}/{meal_plan_id}/daily-summary"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"test-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Test User",
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

    access_token = login_response.json()["access_token"]

    return register_response.json(), {
        "Authorization": f"Bearer {access_token}",
    }


async def create_test_recipe(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    title: str,
    total_calories: str | None = "500.00",
    total_protein_g: str | None = "30.00",
    total_carbs_g: str | None = "50.00",
    total_fat_g: str | None = "15.00",
) -> str:
    payload: dict[str, Any] = {
        "title": title,
        "instructions": "Cook and serve.",
        "diet_type": "balanced",
    }

    if (
        total_calories is not None
        and total_protein_g is not None
        and total_carbs_g is not None
        and total_fat_g is not None
    ):
        ingredient_response = await client.post(
            INGREDIENTS_URL,
            json={
                "name": f"{title} Ingredient {uuid4()}",
                "category": "test",
                "nutrition_value": {
                    "calories": total_calories,
                    "protein_g": total_protein_g,
                    "carbs_g": total_carbs_g,
                    "fat_g": total_fat_g,
                    "portion_g": "100",
                },
            },
        )

        assert ingredient_response.status_code == 201

        ingredient_id = ingredient_response.json()["id"]

        payload["ingredients"] = [
            {
                "ingredient_id": ingredient_id,
                "quantity_g": "100",
            }
        ]

    response = await client.post(
        "/api/v1/recipes",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 201

    return response.json()["id"]


async def create_test_meal_plan(
    client: AsyncClient,
    *,
    headers: dict[str, str],
) -> dict:
    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json={
            "title": "Weekly Meal Plan",
            "start_date": "2026-05-18",
            "end_date": "2026-05-24",
        },
    )

    assert response.status_code == 201

    return response.json()


async def add_meal_plan_item(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    meal_plan_id: str,
    recipe_id: str,
    planned_date: str,
    meal_type: str,
) -> dict:
    response = await client.post(
        f"{MEAL_PLANS_URL}/{meal_plan_id}/items",
        headers=headers,
        json={
            "recipe_id": recipe_id,
            "planned_date": planned_date,
            "meal_type": meal_type,
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_get_meal_plan_nutrition_summary_success(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    breakfast_recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Breakfast Bowl",
        total_calories="500.00",
        total_protein_g="30.00",
        total_carbs_g="55.00",
        total_fat_g="12.00",
    )

    lunch_recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Rice",
        total_calories="750.00",
        total_protein_g="45.00",
        total_carbs_g="80.00",
        total_fat_g="20.00",
    )

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=breakfast_recipe_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=lunch_recipe_id,
        planned_date="2026-05-18",
        meal_type="lunch",
    )

    response = await client.get(
        meal_plan_summary_url(meal_plan["id"]),
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["meal_plan_id"] == meal_plan["id"]
    assert data["items_count"] == 2
    assert data["total_calories"] == "1250.00"
    assert data["total_protein_g"] == "75.00"
    assert data["total_carbs_g"] == "135.00"
    assert data["total_fat_g"] == "32.00"


@pytest.mark.asyncio
async def test_get_meal_plan_nutrition_summary_for_empty_meal_plan(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
    )

    response = await client.get(
        meal_plan_summary_url(meal_plan["id"]),
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["meal_plan_id"] == meal_plan["id"]
    assert data["items_count"] == 0
    assert data["total_calories"] == "0.00"
    assert data["total_protein_g"] == "0.00"
    assert data["total_carbs_g"] == "0.00"
    assert data["total_fat_g"] == "0.00"


@pytest.mark.asyncio
async def test_get_meal_plan_nutrition_summary_counts_null_values_as_zero(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    recipe_with_null_values_id = await create_test_recipe(
        client,
        headers=headers,
        title="Recipe Without Nutrition",
        total_calories=None,
        total_protein_g=None,
        total_carbs_g=None,
        total_fat_g=None,
    )

    recipe_with_values_id = await create_test_recipe(
        client,
        headers=headers,
        title="Recipe With Nutrition",
        total_calories="400.00",
        total_protein_g="25.00",
        total_carbs_g="40.00",
        total_fat_g="10.00",
    )

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_with_null_values_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_with_values_id,
        planned_date="2026-05-18",
        meal_type="dinner",
    )

    response = await client.get(
        meal_plan_summary_url(meal_plan["id"]),
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["items_count"] == 2
    assert data["total_calories"] == "400.00"
    assert data["total_protein_g"] == "25.00"
    assert data["total_carbs_g"] == "40.00"
    assert data["total_fat_g"] == "10.00"


@pytest.mark.asyncio
async def test_get_meal_plan_daily_nutrition_summary_success(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    breakfast_recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Breakfast Bowl",
        total_calories="500.00",
        total_protein_g="30.00",
        total_carbs_g="55.00",
        total_fat_g="12.00",
    )

    lunch_recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Chicken Rice",
        total_calories="750.00",
        total_protein_g="45.00",
        total_carbs_g="80.00",
        total_fat_g="20.00",
    )

    dinner_recipe_id = await create_test_recipe(
        client,
        headers=headers,
        title="Salmon Dinner",
        total_calories="600.00",
        total_protein_g="40.00",
        total_carbs_g="35.00",
        total_fat_g="25.00",
    )

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=breakfast_recipe_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=lunch_recipe_id,
        planned_date="2026-05-18",
        meal_type="lunch",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=dinner_recipe_id,
        planned_date="2026-05-19",
        meal_type="dinner",
    )

    response = await client.get(
        meal_plan_daily_summary_url(meal_plan["id"]),
        headers=headers,
    )

    assert response.status_code == 200

    assert response.json() == [
        {
            "date": "2026-05-18",
            "items_count": 2,
            "total_calories": "1250.00",
            "total_protein_g": "75.00",
            "total_carbs_g": "135.00",
            "total_fat_g": "32.00",
        },
        {
            "date": "2026-05-19",
            "items_count": 1,
            "total_calories": "600.00",
            "total_protein_g": "40.00",
            "total_carbs_g": "35.00",
            "total_fat_g": "25.00",
        },
    ]


@pytest.mark.asyncio
async def test_get_meal_plan_daily_nutrition_summary_for_empty_meal_plan(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
    )

    response = await client.get(
        meal_plan_daily_summary_url(meal_plan["id"]),
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_meal_plan_daily_nutrition_summary_counts_null_values_as_zero(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    recipe_with_null_values_id = await create_test_recipe(
        client,
        headers=headers,
        title="Recipe Without Nutrition",
        total_calories=None,
        total_protein_g=None,
        total_carbs_g=None,
        total_fat_g=None,
    )

    recipe_with_values_id = await create_test_recipe(
        client,
        headers=headers,
        title="Recipe With Nutrition",
        total_calories="400.00",
        total_protein_g="25.00",
        total_carbs_g="40.00",
        total_fat_g="10.00",
    )

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_with_null_values_id,
        planned_date="2026-05-18",
        meal_type="breakfast",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe_with_values_id,
        planned_date="2026-05-18",
        meal_type="dinner",
    )

    response = await client.get(
        meal_plan_daily_summary_url(meal_plan["id"]),
        headers=headers,
    )

    assert response.status_code == 200

    assert response.json() == [
        {
            "date": "2026-05-18",
            "items_count": 2,
            "total_calories": "400.00",
            "total_protein_g": "25.00",
            "total_carbs_g": "40.00",
            "total_fat_g": "10.00",
        }
    ]


@pytest.mark.parametrize("path_suffix", MEAL_PLAN_SUMMARY_PATHS)
@pytest.mark.asyncio
async def test_meal_plan_summaries_require_authentication(
    client: AsyncClient,
    path_suffix: str,
) -> None:
    meal_plan_id = uuid4()

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan_id}/{path_suffix}",
    )

    assert response.status_code == 401


@pytest.mark.parametrize("path_suffix", MEAL_PLAN_SUMMARY_PATHS)
@pytest.mark.asyncio
async def test_meal_plan_summaries_reject_invalid_token(
    client: AsyncClient,
    path_suffix: str,
) -> None:
    meal_plan_id = uuid4()

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan_id}/{path_suffix}",
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.parametrize("path_suffix", MEAL_PLAN_SUMMARY_PATHS)
@pytest.mark.asyncio
async def test_get_meal_plan_summary_rejects_missing_meal_plan(
    client: AsyncClient,
    path_suffix: str,
) -> None:
    _, headers = await create_authenticated_user(client)
    missing_meal_plan_id = uuid4()

    response = await client.get(
        f"{MEAL_PLANS_URL}/{missing_meal_plan_id}/{path_suffix}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Meal plan not found"


@pytest.mark.parametrize("path_suffix", MEAL_PLAN_SUMMARY_PATHS)
@pytest.mark.asyncio
async def test_user_cannot_access_another_users_meal_plan_summary(
    client: AsyncClient,
    path_suffix: str,
) -> None:
    first_user, first_headers = await create_authenticated_user(
        client,
        email=f"first-summary-user-{uuid4()}@example.com",
    )
    second_user, second_headers = await create_authenticated_user(
        client,
        email=f"second-summary-user-{uuid4()}@example.com",
    )

    meal_plan = await create_test_meal_plan(
        client,
        headers=first_headers,
    )

    assert meal_plan["user_id"] == first_user["id"]
    assert meal_plan["user_id"] != second_user["id"]

    response = await client.get(
        f"{MEAL_PLANS_URL}/{meal_plan['id']}/{path_suffix}",
        headers=second_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Meal plan not found"
