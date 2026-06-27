from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recipe import Recipe

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
INGREDIENTS_URL = "/api/v1/ingredients"
RECIPES_URL = "/api/v1/recipes"
MEAL_PLANS_URL = "/api/v1/meal-plans"
NUTRITION_PROFILE_URL = "/api/v1/user-preferences/nutrition"
NUTRITION_GAPS_URL = "/api/v1/meal-plan-items/calendar/nutrition-gaps"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"nutrition-gaps-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Nutrition Gaps User",
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


async def patch_nutrition_profile(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    payload: dict,
) -> dict:
    response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers=headers,
        json=payload,
    )

    assert response.status_code == 200

    return response.json()


async def create_test_ingredient(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    name: str,
    calories: str,
    protein_g: str,
    carbs_g: str,
    fat_g: str,
) -> dict:
    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json={
            "name": name,
            "category": "test",
            "nutrition_value": {
                "calories": calories,
                "protein_g": protein_g,
                "carbs_g": carbs_g,
                "fat_g": fat_g,
                "portion_g": "100",
            },
        },
    )

    assert response.status_code == 201

    return response.json()


async def create_test_recipe_with_totals(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    title: str,
    calories: str,
    protein_g: str,
    carbs_g: str,
    fat_g: str,
) -> dict:
    ingredient = await create_test_ingredient(
        client,
        headers=headers,
        name=f"{title} Ingredient {uuid4()}",
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
    )

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": title,
            "instructions": "Cook and serve.",
            "diet_type": "balanced",
            "ingredients": [
                {
                    "ingredient_id": ingredient["id"],
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert response.status_code == 201

    return response.json()


async def create_test_meal_plan(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    title: str = "Nutrition Gaps Plan",
    start_date: str = "2026-06-27",
    end_date: str | None = "2026-06-30",
) -> dict:
    payload = {
        "title": title,
        "start_date": start_date,
    }

    if end_date is not None:
        payload["end_date"] = end_date

    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json=payload,
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


def assert_decimal(value, expected: str) -> None:
    assert Decimal(str(value)) == Decimal(expected)


@pytest.mark.asyncio
async def test_nutrition_gaps_groups_by_date_and_calculates_statuses(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await patch_nutrition_profile(
        client,
        headers=headers,
        payload={
            "goal": "maintain",
            "diet_type": "balanced",
            "daily_calories_target": 2500,
            "daily_protein_target_g": 140,
            "daily_carbs_target_g": 300,
            "daily_fat_target_g": 80,
            "preferred_meals_per_day": 3,
        },
    )

    breakfast_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Breakfast Bowl",
        calories="500",
        protein_g="30",
        carbs_g="60",
        fat_g="10",
    )
    lunch_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Chicken Rice",
        calories="1600",
        protein_g="90",
        carbs_g="180",
        fat_g="80",
    )
    exact_target_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Exact Target Day",
        calories="2500",
        protein_g="140",
        carbs_g="300",
        fat_g="80",
    )

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-06-27",
        end_date="2026-06-28",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=breakfast_recipe["id"],
        planned_date="2026-06-27",
        meal_type="breakfast",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=lunch_recipe["id"],
        planned_date="2026-06-27",
        meal_type="lunch",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=exact_target_recipe["id"],
        planned_date="2026-06-28",
        meal_type="dinner",
    )

    response = await client.get(
        NUTRITION_GAPS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-27",
            "end_date": "2026-06-28",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert [item["date"] for item in data] == [
        "2026-06-27",
        "2026-06-28",
    ]

    first_day = data[0]

    assert_decimal(first_day["total_calories"], "2100")
    assert first_day["daily_calories_target"] == 2500
    assert_decimal(first_day["calories_gap"], "400")
    assert first_day["calories_status"] == "under"

    assert_decimal(first_day["total_protein_g"], "120")
    assert first_day["daily_protein_target_g"] == 140
    assert_decimal(first_day["protein_gap_g"], "20")
    assert first_day["protein_status"] == "under"

    assert_decimal(first_day["total_carbs_g"], "240")
    assert first_day["daily_carbs_target_g"] == 300
    assert_decimal(first_day["carbs_gap_g"], "60")
    assert first_day["carbs_status"] == "under"

    assert_decimal(first_day["total_fat_g"], "90")
    assert first_day["daily_fat_target_g"] == 80
    assert_decimal(first_day["fat_gap_g"], "-10")
    assert first_day["fat_status"] == "over"

    assert first_day["overall_status"] == "needs_attention"
    assert first_day["missing_targets"] == []

    second_day = data[1]

    assert_decimal(second_day["calories_gap"], "0")
    assert second_day["calories_status"] == "met"
    assert_decimal(second_day["protein_gap_g"], "0")
    assert second_day["protein_status"] == "met"
    assert_decimal(second_day["carbs_gap_g"], "0")
    assert second_day["carbs_status"] == "met"
    assert_decimal(second_day["fat_gap_g"], "0")
    assert second_day["fat_status"] == "met"
    assert second_day["overall_status"] == "on_track"
    assert second_day["missing_targets"] == []


@pytest.mark.asyncio
async def test_nutrition_gaps_filters_by_start_and_end_date(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Daily Recipe",
        calories="100",
        protein_g="10",
        carbs_g="20",
        fat_g="5",
    )
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-06-27",
        end_date="2026-06-29",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-06-27",
        meal_type="breakfast",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-06-28",
        meal_type="lunch",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-06-29",
        meal_type="dinner",
    )

    start_date_response = await client.get(
        NUTRITION_GAPS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-28",
        },
    )

    assert start_date_response.status_code == 200
    assert [item["date"] for item in start_date_response.json()] == [
        "2026-06-28",
        "2026-06-29",
    ]

    end_date_response = await client.get(
        NUTRITION_GAPS_URL,
        headers=headers,
        params={
            "end_date": "2026-06-28",
        },
    )

    assert end_date_response.status_code == 200
    assert [item["date"] for item in end_date_response.json()] == [
        "2026-06-27",
        "2026-06-28",
    ]


@pytest.mark.asyncio
async def test_nutrition_gaps_rejects_start_date_greater_than_end_date(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        NUTRITION_GAPS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-30",
            "end_date": "2026-06-27",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "start_date must be less than or equal to end_date"
    )


@pytest.mark.asyncio
async def test_nutrition_gaps_is_scoped_to_current_user_items_and_profile(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-gaps-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-gaps-user-{uuid4()}@example.com",
    )

    await patch_nutrition_profile(
        client,
        headers=first_headers,
        payload={
            "daily_calories_target": 1000,
            "daily_protein_target_g": 100,
        },
    )
    await patch_nutrition_profile(
        client,
        headers=second_headers,
        payload={
            "daily_calories_target": 2000,
            "daily_protein_target_g": 150,
        },
    )

    first_recipe = await create_test_recipe_with_totals(
        client,
        headers=first_headers,
        title="First User Recipe",
        calories="900",
        protein_g="70",
        carbs_g="100",
        fat_g="30",
    )
    second_recipe = await create_test_recipe_with_totals(
        client,
        headers=second_headers,
        title="Second User Recipe",
        calories="600",
        protein_g="50",
        carbs_g="80",
        fat_g="20",
    )

    first_meal_plan = await create_test_meal_plan(
        client,
        headers=first_headers,
        title="First User Plan",
    )
    second_meal_plan = await create_test_meal_plan(
        client,
        headers=second_headers,
        title="Second User Plan",
    )

    await add_meal_plan_item(
        client,
        headers=first_headers,
        meal_plan_id=first_meal_plan["id"],
        recipe_id=first_recipe["id"],
        planned_date="2026-06-27",
        meal_type="breakfast",
    )
    await add_meal_plan_item(
        client,
        headers=second_headers,
        meal_plan_id=second_meal_plan["id"],
        recipe_id=second_recipe["id"],
        planned_date="2026-06-27",
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAPS_URL,
        headers=second_headers,
        params={
            "start_date": "2026-06-27",
            "end_date": "2026-06-27",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    day = data[0]

    assert day["date"] == "2026-06-27"
    assert_decimal(day["total_calories"], "600")
    assert day["daily_calories_target"] == 2000
    assert_decimal(day["calories_gap"], "1400")
    assert day["calories_status"] == "under"

    assert_decimal(day["total_protein_g"], "50")
    assert day["daily_protein_target_g"] == 150
    assert_decimal(day["protein_gap_g"], "100")
    assert day["protein_status"] == "under"

    assert day["daily_carbs_target_g"] is None
    assert day["carbs_gap_g"] is None
    assert day["carbs_status"] == "unknown"

    assert day["daily_fat_target_g"] is None
    assert day["fat_gap_g"] is None
    assert day["fat_status"] == "unknown"

    assert day["overall_status"] == "needs_attention"
    assert day["missing_targets"] == [
        "daily_carbs_target_g",
        "daily_fat_target_g",
    ]


@pytest.mark.asyncio
async def test_nutrition_gaps_works_without_profile_and_lists_missing_targets(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="No Profile Recipe",
        calories="500",
        protein_g="30",
        carbs_g="60",
        fat_g="10",
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-06-27",
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAPS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-27",
            "end_date": "2026-06-27",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    day = data[0]

    assert_decimal(day["total_calories"], "500")
    assert day["daily_calories_target"] is None
    assert day["calories_gap"] is None
    assert day["calories_status"] == "unknown"

    assert_decimal(day["total_protein_g"], "30")
    assert day["daily_protein_target_g"] is None
    assert day["protein_gap_g"] is None
    assert day["protein_status"] == "unknown"

    assert_decimal(day["total_carbs_g"], "60")
    assert day["daily_carbs_target_g"] is None
    assert day["carbs_gap_g"] is None
    assert day["carbs_status"] == "unknown"

    assert_decimal(day["total_fat_g"], "10")
    assert day["daily_fat_target_g"] is None
    assert day["fat_gap_g"] is None
    assert day["fat_status"] == "unknown"

    assert day["overall_status"] == "unknown"
    assert day["missing_targets"] == [
        "daily_calories_target",
        "daily_protein_target_g",
        "daily_carbs_target_g",
        "daily_fat_target_g",
    ]


@pytest.mark.asyncio
async def test_nutrition_gaps_treats_null_recipe_totals_as_zero(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    _, headers = await create_authenticated_user(client)

    await patch_nutrition_profile(
        client,
        headers=headers,
        payload={
            "daily_calories_target": 100,
            "daily_protein_target_g": 100,
            "daily_carbs_target_g": 100,
            "daily_fat_target_g": 100,
        },
    )

    recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Null Totals Recipe",
        calories="500",
        protein_g="30",
        carbs_g="60",
        fat_g="10",
    )

    await db_session.execute(
        update(Recipe)
        .where(Recipe.id == UUID(recipe["id"]))
        .values(
            total_calories=None,
            total_protein_g=None,
            total_carbs_g=None,
            total_fat_g=None,
        )
    )
    await db_session.commit()

    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-06-27",
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAPS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-27",
            "end_date": "2026-06-27",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    day = data[0]

    assert_decimal(day["total_calories"], "0")
    assert_decimal(day["calories_gap"], "100")
    assert day["calories_status"] == "under"

    assert_decimal(day["total_protein_g"], "0")
    assert_decimal(day["protein_gap_g"], "100")
    assert day["protein_status"] == "under"

    assert_decimal(day["total_carbs_g"], "0")
    assert_decimal(day["carbs_gap_g"], "100")
    assert day["carbs_status"] == "under"

    assert_decimal(day["total_fat_g"], "0")
    assert_decimal(day["fat_gap_g"], "100")
    assert day["fat_status"] == "under"

    assert day["overall_status"] == "needs_attention"
    assert day["missing_targets"] == []


@pytest.mark.asyncio
async def test_nutrition_gaps_allows_negative_gaps_and_overall_over_target(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await patch_nutrition_profile(
        client,
        headers=headers,
        payload={
            "daily_calories_target": 80,
            "daily_protein_target_g": 70,
            "daily_carbs_target_g": 80,
            "daily_fat_target_g": 30,
        },
    )

    recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Over Target Recipe",
        calories="100",
        protein_g="200",
        carbs_g="160",
        fat_g="45",
    )
    meal_plan = await create_test_meal_plan(client, headers=headers)

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-06-27",
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAPS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-27",
            "end_date": "2026-06-27",
        },
    )

    assert response.status_code == 200

    day = response.json()[0]

    assert_decimal(day["calories_gap"], "-20")
    assert day["calories_status"] == "over"

    assert_decimal(day["protein_gap_g"], "-130")
    assert day["protein_status"] == "over"

    assert_decimal(day["carbs_gap_g"], "-80")
    assert day["carbs_status"] == "over"

    assert_decimal(day["fat_gap_g"], "-15")
    assert day["fat_status"] == "over"

    assert day["overall_status"] == "over_target"
    assert day["missing_targets"] == []


@pytest.mark.asyncio
async def test_nutrition_gaps_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(
        NUTRITION_GAPS_URL,
        params={
            "start_date": "2026-06-27",
            "end_date": "2026-06-27",
        },
    )

    assert response.status_code == 401
