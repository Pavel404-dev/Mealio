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
NUTRITION_GAPS_SUMMARY_URL = "/api/v1/meal-plan-items/calendar/nutrition-gaps/summary"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"nutrition-gaps-summary-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Nutrition Gaps Summary User",
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
    title: str = "Nutrition Gaps Summary Plan",
    start_date: str = "2026-06-22",
    end_date: str | None = "2026-06-28",
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
async def test_nutrition_gaps_summary_aggregates_daily_gaps(
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
        title="Summary Breakfast Bowl",
        calories="500",
        protein_g="30",
        carbs_g="60",
        fat_g="10",
    )
    lunch_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Summary Chicken Rice",
        calories="1600",
        protein_g="90",
        carbs_g="180",
        fat_g="80",
    )
    exact_target_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Summary Exact Target Day",
        calories="2500",
        protein_g="140",
        carbs_g="300",
        fat_g="80",
    )
    over_target_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Summary Over Target Day",
        calories="2600",
        protein_g="140",
        carbs_g="300",
        fat_g="100",
    )

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-06-22",
        end_date="2026-06-28",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=breakfast_recipe["id"],
        planned_date="2026-06-22",
        meal_type="breakfast",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=lunch_recipe["id"],
        planned_date="2026-06-22",
        meal_type="lunch",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=exact_target_recipe["id"],
        planned_date="2026-06-23",
        meal_type="dinner",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=over_target_recipe["id"],
        planned_date="2026-06-24",
        meal_type="dinner",
    )

    response = await client.get(
        NUTRITION_GAPS_SUMMARY_URL,
        headers=headers,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-28",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["start_date"] == "2026-06-22"
    assert data["end_date"] == "2026-06-28"
    assert data["days_count"] == 3

    assert data["overall_status_counts"] == {
        "unknown": 0,
        "needs_attention": 1,
        "over_target": 1,
        "on_track": 1,
    }

    assert data["macro_status_counts"] == {
        "calories": {
            "under": 1,
            "met": 1,
            "over": 1,
            "unknown": 0,
        },
        "protein": {
            "under": 1,
            "met": 2,
            "over": 0,
            "unknown": 0,
        },
        "carbs": {
            "under": 1,
            "met": 2,
            "over": 0,
            "unknown": 0,
        },
        "fat": {
            "under": 0,
            "met": 1,
            "over": 2,
            "unknown": 0,
        },
    }

    assert_decimal(data["average_gaps"]["calories_gap"], "100")
    assert_decimal(data["average_gaps"]["protein_gap_g"], "6.67")
    assert_decimal(data["average_gaps"]["carbs_gap_g"], "20")
    assert_decimal(data["average_gaps"]["fat_gap_g"], "-10")

    assert data["missing_targets"] == []
    assert data["main_issues"] == [
        "fat_over",
        "protein_under",
        "calories_under",
        "calories_over",
        "carbs_under",
    ]


@pytest.mark.asyncio
async def test_nutrition_gaps_summary_works_without_profile(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Summary No Profile Recipe",
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
        planned_date="2026-06-22",
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAPS_SUMMARY_URL,
        headers=headers,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-22",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["days_count"] == 1
    assert data["overall_status_counts"] == {
        "unknown": 1,
        "needs_attention": 0,
        "over_target": 0,
        "on_track": 0,
    }

    assert data["macro_status_counts"] == {
        "calories": {
            "under": 0,
            "met": 0,
            "over": 0,
            "unknown": 1,
        },
        "protein": {
            "under": 0,
            "met": 0,
            "over": 0,
            "unknown": 1,
        },
        "carbs": {
            "under": 0,
            "met": 0,
            "over": 0,
            "unknown": 1,
        },
        "fat": {
            "under": 0,
            "met": 0,
            "over": 0,
            "unknown": 1,
        },
    }

    assert data["average_gaps"] == {
        "calories_gap": None,
        "protein_gap_g": None,
        "carbs_gap_g": None,
        "fat_gap_g": None,
    }
    assert data["missing_targets"] == [
        "daily_calories_target",
        "daily_carbs_target_g",
        "daily_fat_target_g",
        "daily_protein_target_g",
    ]
    assert data["main_issues"] == [
        "missing_targets",
    ]


@pytest.mark.asyncio
async def test_nutrition_gaps_summary_uses_only_current_user_data(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-summary-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-summary-user-{uuid4()}@example.com",
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
        title="First Summary User Recipe",
        calories="900",
        protein_g="70",
        carbs_g="100",
        fat_g="30",
    )
    second_recipe = await create_test_recipe_with_totals(
        client,
        headers=second_headers,
        title="Second Summary User Recipe",
        calories="600",
        protein_g="50",
        carbs_g="80",
        fat_g="20",
    )

    first_meal_plan = await create_test_meal_plan(
        client,
        headers=first_headers,
        title="First Summary User Plan",
    )
    second_meal_plan = await create_test_meal_plan(
        client,
        headers=second_headers,
        title="Second Summary User Plan",
    )

    await add_meal_plan_item(
        client,
        headers=first_headers,
        meal_plan_id=first_meal_plan["id"],
        recipe_id=first_recipe["id"],
        planned_date="2026-06-22",
        meal_type="breakfast",
    )
    await add_meal_plan_item(
        client,
        headers=second_headers,
        meal_plan_id=second_meal_plan["id"],
        recipe_id=second_recipe["id"],
        planned_date="2026-06-22",
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAPS_SUMMARY_URL,
        headers=second_headers,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-22",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["days_count"] == 1
    assert data["overall_status_counts"] == {
        "unknown": 0,
        "needs_attention": 1,
        "over_target": 0,
        "on_track": 0,
    }

    assert data["macro_status_counts"]["calories"] == {
        "under": 1,
        "met": 0,
        "over": 0,
        "unknown": 0,
    }
    assert data["macro_status_counts"]["protein"] == {
        "under": 1,
        "met": 0,
        "over": 0,
        "unknown": 0,
    }
    assert data["macro_status_counts"]["carbs"] == {
        "under": 0,
        "met": 0,
        "over": 0,
        "unknown": 1,
    }
    assert data["macro_status_counts"]["fat"] == {
        "under": 0,
        "met": 0,
        "over": 0,
        "unknown": 1,
    }

    assert_decimal(data["average_gaps"]["calories_gap"], "1400")
    assert_decimal(data["average_gaps"]["protein_gap_g"], "100")
    assert data["average_gaps"]["carbs_gap_g"] is None
    assert data["average_gaps"]["fat_gap_g"] is None

    assert data["missing_targets"] == [
        "daily_carbs_target_g",
        "daily_fat_target_g",
    ]
    assert data["main_issues"] == [
        "missing_targets",
        "protein_under",
        "calories_under",
    ]


@pytest.mark.asyncio
async def test_nutrition_gaps_summary_treats_null_recipe_totals_as_zero(
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
        title="Summary Null Totals Recipe",
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
        planned_date="2026-06-22",
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAPS_SUMMARY_URL,
        headers=headers,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-22",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["days_count"] == 1
    assert data["overall_status_counts"] == {
        "unknown": 0,
        "needs_attention": 1,
        "over_target": 0,
        "on_track": 0,
    }

    assert_decimal(data["average_gaps"]["calories_gap"], "100")
    assert_decimal(data["average_gaps"]["protein_gap_g"], "100")
    assert_decimal(data["average_gaps"]["carbs_gap_g"], "100")
    assert_decimal(data["average_gaps"]["fat_gap_g"], "100")

    assert data["main_issues"] == [
        "protein_under",
        "calories_under",
        "carbs_under",
        "fat_under",
    ]


@pytest.mark.asyncio
async def test_nutrition_gaps_summary_rejects_start_date_greater_than_end_date(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        NUTRITION_GAPS_SUMMARY_URL,
        headers=headers,
        params={
            "start_date": "2026-06-30",
            "end_date": "2026-06-22",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "start_date must be less than or equal to end_date"
    )


@pytest.mark.asyncio
async def test_nutrition_gaps_summary_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(
        NUTRITION_GAPS_SUMMARY_URL,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-22",
        },
    )

    assert response.status_code == 401
