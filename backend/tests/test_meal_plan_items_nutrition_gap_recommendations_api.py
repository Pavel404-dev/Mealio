from datetime import date, timedelta
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
NUTRITION_GAP_RECOMMENDATIONS_URL = (
    "/api/v1/meal-plan-items/calendar/nutrition-gaps/recommendations"
)


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"nutrition-gap-recommendations-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Nutrition Gap Recommendations User",
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
    title: str = "Nutrition Gap Recommendations Plan",
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


def assert_macro_recommendation(
    recommendation: dict,
    *,
    action: str,
    macro: str,
    direction: str,
    priority: str,
    affected_days: int,
    average_adjustment: str,
) -> None:
    assert recommendation["action"] == action
    assert recommendation["macro"] == macro
    assert recommendation["direction"] == direction
    assert recommendation["priority"] == priority
    assert recommendation["affected_days"] == affected_days
    assert_decimal(recommendation["average_adjustment"], average_adjustment)
    assert recommendation["missing_targets"] == []


@pytest.mark.asyncio
async def test_recommendations_aggregate_average_prioritize_and_sort_stably(
    client: AsyncClient,
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

    daily_totals = [
        ("Day One", "50", "50", "90", "110"),
        ("Day Two", "70", "80", "100", "120"),
        ("Day Three", "100", "90", "100", "100"),
        ("Day Four", "100", "130", "100", "100"),
        ("Day Five", "100", "100", "100", "100"),
    ]
    recipes = []

    for title, calories, protein_g, carbs_g, fat_g in daily_totals:
        recipes.append(
            await create_test_recipe_with_totals(
                client,
                headers=headers,
                title=f"Recommendations {title}",
                calories=calories,
                protein_g=protein_g,
                carbs_g=carbs_g,
                fat_g=fat_g,
            )
        )

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-06-22",
        end_date="2026-06-26",
    )

    for index, recipe in enumerate(recipes):
        planned_date = date(2026, 6, 22) + timedelta(days=index)
        await add_meal_plan_item(
            client,
            headers=headers,
            meal_plan_id=meal_plan["id"],
            recipe_id=recipe["id"],
            planned_date=planned_date.isoformat(),
            meal_type="dinner",
        )

    response = await client.get(
        NUTRITION_GAP_RECOMMENDATIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-26",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["start_date"] == "2026-06-22"
    assert data["end_date"] == "2026-06-26"
    assert data["days_count"] == 5

    recommendations = data["recommendations"]

    assert [item["action"] for item in recommendations] == [
        "increase_protein",
        "increase_calories",
        "decrease_fat",
        "decrease_protein",
        "increase_carbs",
    ]

    assert_macro_recommendation(
        recommendations[0],
        action="increase_protein",
        macro="protein",
        direction="increase",
        priority="high",
        affected_days=3,
        average_adjustment="26.67",
    )
    assert_macro_recommendation(
        recommendations[1],
        action="increase_calories",
        macro="calories",
        direction="increase",
        priority="medium",
        affected_days=2,
        average_adjustment="40",
    )
    assert_macro_recommendation(
        recommendations[2],
        action="decrease_fat",
        macro="fat",
        direction="decrease",
        priority="medium",
        affected_days=2,
        average_adjustment="15",
    )
    assert_macro_recommendation(
        recommendations[3],
        action="decrease_protein",
        macro="protein",
        direction="decrease",
        priority="low",
        affected_days=1,
        average_adjustment="30",
    )
    assert_macro_recommendation(
        recommendations[4],
        action="increase_carbs",
        macro="carbs",
        direction="increase",
        priority="low",
        affected_days=1,
        average_adjustment="10",
    )


@pytest.mark.asyncio
async def test_recommendations_put_missing_targets_first_and_skip_unknown_macros(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await patch_nutrition_profile(
        client,
        headers=headers,
        payload={
            "daily_calories_target": 100,
            "daily_protein_target_g": 100,
        },
    )

    first_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Missing Targets First Day",
        calories="100",
        protein_g="50",
        carbs_g="30",
        fat_g="20",
    )
    second_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Missing Targets Second Day",
        calories="130",
        protein_g="100",
        carbs_g="40",
        fat_g="30",
    )
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-06-22",
        end_date="2026-06-23",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=first_recipe["id"],
        planned_date="2026-06-22",
        meal_type="breakfast",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=second_recipe["id"],
        planned_date="2026-06-23",
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAP_RECOMMENDATIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-23",
        },
    )

    assert response.status_code == 200

    data = response.json()
    recommendations = data["recommendations"]

    assert data["days_count"] == 2
    assert [item["action"] for item in recommendations] == [
        "set_missing_targets",
        "increase_protein",
        "decrease_calories",
    ]

    missing_targets_recommendation = recommendations[0]

    assert missing_targets_recommendation == {
        "action": "set_missing_targets",
        "macro": None,
        "direction": None,
        "priority": "high",
        "affected_days": 2,
        "average_adjustment": None,
        "missing_targets": [
            "daily_carbs_target_g",
            "daily_fat_target_g",
        ],
    }

    assert_macro_recommendation(
        recommendations[1],
        action="increase_protein",
        macro="protein",
        direction="increase",
        priority="high",
        affected_days=1,
        average_adjustment="50",
    )
    assert_macro_recommendation(
        recommendations[2],
        action="decrease_calories",
        macro="calories",
        direction="decrease",
        priority="high",
        affected_days=1,
        average_adjustment="30",
    )

    assert all(item["macro"] not in {"carbs", "fat"} for item in recommendations)


@pytest.mark.asyncio
async def test_recommendations_work_without_profile_and_only_set_missing_targets(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Recommendations No Profile Recipe",
        calories="500",
        protein_g="30",
        carbs_g="60",
        fat_g="10",
    )
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-06-22",
        end_date="2026-06-22",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-06-22",
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAP_RECOMMENDATIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-22",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["days_count"] == 1
    assert data["recommendations"] == [
        {
            "action": "set_missing_targets",
            "macro": None,
            "direction": None,
            "priority": "high",
            "affected_days": 1,
            "average_adjustment": None,
            "missing_targets": [
                "daily_calories_target",
                "daily_carbs_target_g",
                "daily_fat_target_g",
                "daily_protein_target_g",
            ],
        }
    ]


@pytest.mark.asyncio
async def test_recommendations_return_empty_list_for_empty_period(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        NUTRITION_GAP_RECOMMENDATIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-28",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "start_date": "2026-06-22",
        "end_date": "2026-06-28",
        "days_count": 0,
        "recommendations": [],
    }


@pytest.mark.asyncio
async def test_recommendations_use_only_current_user_data_and_profile(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-recommendations-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-recommendations-user-{uuid4()}@example.com",
    )

    await patch_nutrition_profile(
        client,
        headers=first_headers,
        payload={
            "daily_calories_target": 1000,
            "daily_protein_target_g": 1000,
            "daily_carbs_target_g": 1000,
            "daily_fat_target_g": 1000,
        },
    )
    await patch_nutrition_profile(
        client,
        headers=second_headers,
        payload={
            "daily_calories_target": 200,
            "daily_protein_target_g": 200,
            "daily_carbs_target_g": 200,
            "daily_fat_target_g": 200,
        },
    )

    first_recipe = await create_test_recipe_with_totals(
        client,
        headers=first_headers,
        title="First User Recommendations Recipe",
        calories="900",
        protein_g="900",
        carbs_g="900",
        fat_g="900",
    )
    second_recipe = await create_test_recipe_with_totals(
        client,
        headers=second_headers,
        title="Second User Recommendations Recipe",
        calories="150",
        protein_g="150",
        carbs_g="150",
        fat_g="150",
    )
    first_meal_plan = await create_test_meal_plan(
        client,
        headers=first_headers,
        title="First User Recommendations Plan",
        start_date="2026-06-22",
        end_date="2026-06-22",
    )
    second_meal_plan = await create_test_meal_plan(
        client,
        headers=second_headers,
        title="Second User Recommendations Plan",
        start_date="2026-06-22",
        end_date="2026-06-22",
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
        NUTRITION_GAP_RECOMMENDATIONS_URL,
        headers=second_headers,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-22",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["days_count"] == 1
    assert [item["action"] for item in data["recommendations"]] == [
        "increase_protein",
        "increase_calories",
        "increase_carbs",
        "increase_fat",
    ]

    for recommendation in data["recommendations"]:
        assert recommendation["affected_days"] == 1
        assert recommendation["priority"] == "high"
        assert_decimal(recommendation["average_adjustment"], "50")


@pytest.mark.asyncio
async def test_recommendations_filter_by_start_date_and_end_date(
    client: AsyncClient,
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
        title="Recommendations Date Filter Recipe",
        calories="90",
        protein_g="90",
        carbs_g="90",
        fat_g="90",
    )
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-06-22",
        end_date="2026-06-24",
    )

    for index in range(3):
        planned_date = date(2026, 6, 22) + timedelta(days=index)
        await add_meal_plan_item(
            client,
            headers=headers,
            meal_plan_id=meal_plan["id"],
            recipe_id=recipe["id"],
            planned_date=planned_date.isoformat(),
            meal_type="dinner",
        )

    start_date_response = await client.get(
        NUTRITION_GAP_RECOMMENDATIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-23",
        },
    )

    assert start_date_response.status_code == 200

    start_date_data = start_date_response.json()

    assert start_date_data["start_date"] == "2026-06-23"
    assert start_date_data["end_date"] is None
    assert start_date_data["days_count"] == 2
    assert all(
        item["affected_days"] == 2 for item in start_date_data["recommendations"]
    )

    end_date_response = await client.get(
        NUTRITION_GAP_RECOMMENDATIONS_URL,
        headers=headers,
        params={
            "end_date": "2026-06-23",
        },
    )

    assert end_date_response.status_code == 200

    end_date_data = end_date_response.json()

    assert end_date_data["start_date"] is None
    assert end_date_data["end_date"] == "2026-06-23"
    assert end_date_data["days_count"] == 2
    assert all(item["affected_days"] == 2 for item in end_date_data["recommendations"])


@pytest.mark.asyncio
async def test_recommendations_use_default_current_week_range(
    client: AsyncClient,
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

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title=f"Recommendations Default Range Recipe {uuid4()}",
        calories="90",
        protein_g="90",
        carbs_g="90",
        fat_g="90",
    )
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date=today.isoformat(),
        end_date=today.isoformat(),
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date=today.isoformat(),
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAP_RECOMMENDATIONS_URL,
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["start_date"] == week_start.isoformat()
    assert data["end_date"] == week_end.isoformat()
    assert data["days_count"] == 1


@pytest.mark.asyncio
async def test_recommendations_reject_start_date_greater_than_end_date(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        NUTRITION_GAP_RECOMMENDATIONS_URL,
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
async def test_recommendations_treat_null_recipe_totals_as_zero(
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
        title="Recommendations Null Totals Recipe",
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

    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-06-22",
        end_date="2026-06-22",
    )

    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=recipe["id"],
        planned_date="2026-06-22",
        meal_type="breakfast",
    )

    response = await client.get(
        NUTRITION_GAP_RECOMMENDATIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-22",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["days_count"] == 1
    assert [item["action"] for item in data["recommendations"]] == [
        "increase_protein",
        "increase_calories",
        "increase_carbs",
        "increase_fat",
    ]

    for recommendation in data["recommendations"]:
        assert_decimal(recommendation["average_adjustment"], "100")


@pytest.mark.asyncio
async def test_recommendations_require_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(
        NUTRITION_GAP_RECOMMENDATIONS_URL,
        params={
            "start_date": "2026-06-22",
            "end_date": "2026-06-22",
        },
    )

    assert response.status_code == 401
