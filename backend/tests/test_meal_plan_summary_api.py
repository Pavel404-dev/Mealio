from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
MEAL_PLANS_URL = "/api/v1/meal-plans"


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
    title: str,
    total_calories: str | None = "500.00",
    total_protein_g: str | None = "30.00",
    total_carbs_g: str | None = "50.00",
    total_fat_g: str | None = "15.00",
) -> str:
    payload = {
        "title": title,
        "instructions": "Cook and serve.",
        "diet_type": "balanced",
        "total_calories": total_calories,
        "total_protein_g": total_protein_g,
        "total_carbs_g": total_carbs_g,
        "total_fat_g": total_fat_g,
    }

    response = await client.post(
        "/api/v1/recipes",
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
    user, headers = await create_authenticated_user(client)

    breakfast_recipe_id = await create_test_recipe(
        client,
        title="Breakfast Bowl",
        total_calories="500.00",
        total_protein_g="30.00",
        total_carbs_g="55.00",
        total_fat_g="12.00",
    )

    lunch_recipe_id = await create_test_recipe(
        client,
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
        f"/api/v1/users/{user['id']}/meal-plans/{meal_plan['id']}/summary"
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
    user, headers = await create_authenticated_user(client)

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
    )

    response = await client.get(
        f"/api/v1/users/{user['id']}/meal-plans/{meal_plan['id']}/summary"
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
    user, headers = await create_authenticated_user(client)

    recipe_with_null_values_id = await create_test_recipe(
        client,
        title="Recipe Without Nutrition",
        total_calories=None,
        total_protein_g=None,
        total_carbs_g=None,
        total_fat_g=None,
    )

    recipe_with_values_id = await create_test_recipe(
        client,
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
        f"/api/v1/users/{user['id']}/meal-plans/{meal_plan['id']}/summary"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["items_count"] == 2
    assert data["total_calories"] == "400.00"
    assert data["total_protein_g"] == "25.00"
    assert data["total_carbs_g"] == "40.00"
    assert data["total_fat_g"] == "10.00"


@pytest.mark.asyncio
async def test_get_meal_plan_nutrition_summary_rejects_missing_user(
    client: AsyncClient,
) -> None:
    missing_user_id = uuid4()
    meal_plan_id = uuid4()

    response = await client.get(
        f"/api/v1/users/{missing_user_id}/meal-plans/{meal_plan_id}/summary"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_get_meal_plan_nutrition_summary_rejects_missing_meal_plan(
    client: AsyncClient,
) -> None:
    user, _ = await create_authenticated_user(client)
    missing_meal_plan_id = uuid4()

    response = await client.get(
        f"/api/v1/users/{user['id']}/meal-plans/{missing_meal_plan_id}/summary"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Meal plan not found"


@pytest.mark.asyncio
async def test_get_meal_plan_daily_nutrition_summary_success(
    client: AsyncClient,
) -> None:
    user, headers = await create_authenticated_user(client)

    breakfast_recipe_id = await create_test_recipe(
        client,
        title="Breakfast Bowl",
        total_calories="500.00",
        total_protein_g="30.00",
        total_carbs_g="55.00",
        total_fat_g="12.00",
    )

    lunch_recipe_id = await create_test_recipe(
        client,
        title="Chicken Rice",
        total_calories="750.00",
        total_protein_g="45.00",
        total_carbs_g="80.00",
        total_fat_g="20.00",
    )

    dinner_recipe_id = await create_test_recipe(
        client,
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
        f"/api/v1/users/{user['id']}/meal-plans/{meal_plan['id']}/daily-summary"
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
    user, headers = await create_authenticated_user(client)

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
    )

    response = await client.get(
        f"/api/v1/users/{user['id']}/meal-plans/{meal_plan['id']}/daily-summary"
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_meal_plan_daily_nutrition_summary_counts_null_values_as_zero(
    client: AsyncClient,
) -> None:
    user, headers = await create_authenticated_user(client)

    recipe_with_null_values_id = await create_test_recipe(
        client,
        title="Recipe Without Nutrition",
        total_calories=None,
        total_protein_g=None,
        total_carbs_g=None,
        total_fat_g=None,
    )

    recipe_with_values_id = await create_test_recipe(
        client,
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
        f"/api/v1/users/{user['id']}/meal-plans/{meal_plan['id']}/daily-summary"
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


@pytest.mark.asyncio
async def test_get_meal_plan_daily_nutrition_summary_rejects_missing_user(
    client: AsyncClient,
) -> None:
    missing_user_id = uuid4()
    meal_plan_id = uuid4()

    response = await client.get(
        f"/api/v1/users/{missing_user_id}/meal-plans/{meal_plan_id}/daily-summary"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_get_meal_plan_daily_nutrition_summary_rejects_missing_meal_plan(
    client: AsyncClient,
) -> None:
    user, _ = await create_authenticated_user(client)
    missing_meal_plan_id = uuid4()

    response = await client.get(
        f"/api/v1/users/{user['id']}/meal-plans/{missing_meal_plan_id}/daily-summary"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Meal plan not found"
