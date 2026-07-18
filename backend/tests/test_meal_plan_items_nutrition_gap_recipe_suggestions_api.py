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
RECIPE_SUGGESTIONS_URL = (
    "/api/v1/meal-plan-items/calendar/nutrition-gaps/recipe-suggestions"
)


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"nutrition-gap-recipe-suggestions-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Nutrition Gap Recipe Suggestions User",
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
        "Authorization": f"Bearer {login_response.json()['access_token']}",
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
    diet_type: str = "balanced",
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
            "diet_type": diet_type,
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
    start_date: str,
    end_date: str | None,
    title: str | None = None,
) -> dict:
    payload = {
        "title": title or f"Nutrition Gap Suggestions Plan {uuid4()}",
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
    meal_type: str = "dinner",
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


async def create_gap_day(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    meal_plan_id: str,
    planned_date: str,
    calories: str,
    protein_g: str,
    carbs_g: str,
    fat_g: str,
) -> dict:
    recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title=f"Gap Day {planned_date} {uuid4()}",
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan_id,
        recipe_id=recipe["id"],
        planned_date=planned_date,
    )

    return recipe


def assert_decimal(value, expected: str) -> None:
    assert Decimal(str(value)) == Decimal(expected)


def suggestion_ids(data: dict) -> list[str]:
    return [suggestion["recipe_id"] for suggestion in data["suggestions"]]


@pytest.mark.asyncio
async def test_recipe_suggestions_require_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-12",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_recipe_suggestions_use_only_current_user_recipes_and_gaps(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-gap-suggestions-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-gap-suggestions-{uuid4()}@example.com",
    )

    for headers in (first_headers, second_headers):
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

    first_plan = await create_test_meal_plan(
        client,
        headers=first_headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )
    second_plan = await create_test_meal_plan(
        client,
        headers=second_headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )

    await create_gap_day(
        client,
        headers=first_headers,
        meal_plan_id=first_plan["id"],
        planned_date="2026-07-06",
        calories="10",
        protein_g="10",
        carbs_g="10",
        fat_g="10",
    )
    await create_gap_day(
        client,
        headers=second_headers,
        meal_plan_id=second_plan["id"],
        planned_date="2026-07-06",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )

    first_candidate = await create_test_recipe_with_totals(
        client,
        headers=first_headers,
        title="First User Candidate",
        calories="100",
        protein_g="100",
        carbs_g="100",
        fat_g="100",
    )
    second_candidate = await create_test_recipe_with_totals(
        client,
        headers=second_headers,
        title="Second User Candidate",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=second_headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
        },
    )

    assert response.status_code == 200

    data = response.json()
    ids = suggestion_ids(data)
    protein_recommendation = next(
        item
        for item in data["recommendations_used"]
        if item["action"] == "increase_protein"
    )

    assert ids == [second_candidate["id"]]
    assert first_candidate["id"] not in ids
    assert_decimal(protein_recommendation["average_adjustment"], "50")


@pytest.mark.asyncio
async def test_recipe_suggestions_use_default_current_week_range(
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
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date=today.isoformat(),
        end_date=today.isoformat(),
    )

    await create_gap_day(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        planned_date=today.isoformat(),
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title=f"Default Week Candidate {uuid4()}",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )

    response = await client.get(RECIPE_SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert data["start_date"] == week_start.isoformat()
    assert data["end_date"] == week_end.isoformat()
    assert suggestion_ids(data) == [candidate["id"]]


@pytest.mark.asyncio
async def test_recipe_suggestions_respect_custom_date_filtering(
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

    inside_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )
    outside_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-13",
        end_date="2026-07-13",
    )

    await create_gap_day(
        client,
        headers=headers,
        meal_plan_id=inside_plan["id"],
        planned_date="2026-07-06",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    outside_used_candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Used Outside Selected Range",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=outside_plan["id"],
        recipe_id=outside_used_candidate["id"],
        planned_date="2026-07-13",
    )

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["start_date"] == "2026-07-06"
    assert data["end_date"] == "2026-07-06"
    assert outside_used_candidate["id"] in suggestion_ids(data)


@pytest.mark.asyncio
async def test_recipe_suggestions_sort_by_score_title_and_id_deterministically(
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
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )
    await create_gap_day(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        planned_date="2026-07-06",
        calories="0",
        protein_g="0",
        carbs_g="0",
        fat_g="0",
    )

    highest = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Zulu Highest Score",
        calories="100",
        protein_g="100",
        carbs_g="100",
        fat_g="100",
    )
    alpha = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Alpha Equal Score",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    bravo = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Bravo Equal Score",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    same_title_first = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Same Equal Score",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    same_title_second = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Same Equal Score",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
        },
    )

    assert response.status_code == 200

    data = response.json()
    same_title_ids = sorted(
        [same_title_first["id"], same_title_second["id"]],
    )

    assert suggestion_ids(data) == [
        highest["id"],
        alpha["id"],
        bravo["id"],
        *same_title_ids,
    ]
    assert_decimal(data["suggestions"][0]["score"], "100")
    assert all(
        Decimal(str(item["score"])) == Decimal("50") for item in data["suggestions"][1:]
    )


@pytest.mark.asyncio
async def test_recipe_suggestions_exclude_recipes_used_in_selected_range(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await patch_nutrition_profile(
        client,
        headers=headers,
        payload={
            "daily_calories_target": 300,
            "daily_protein_target_g": 300,
            "daily_carbs_target_g": 300,
            "daily_fat_target_g": 300,
        },
    )
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )
    used_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Already Planned Candidate",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    await add_meal_plan_item(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        recipe_id=used_recipe["id"],
        planned_date="2026-07-06",
    )
    available_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Available Candidate",
        calories="100",
        protein_g="100",
        carbs_g="100",
        fat_g="100",
    )

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
        },
    )

    assert response.status_code == 200

    ids = suggestion_ids(response.json())

    assert ids == [available_recipe["id"]]
    assert used_recipe["id"] not in ids


@pytest.mark.asyncio
async def test_recipe_suggestions_exclude_recipes_without_nutrition_totals(
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
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )
    await create_gap_day(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        planned_date="2026-07-06",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    missing_totals_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Missing Totals Candidate",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    valid_recipe = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Valid Totals Candidate",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )

    await db_session.execute(
        update(Recipe)
        .where(Recipe.id == UUID(missing_totals_recipe["id"]))
        .values(
            total_calories=None,
            total_protein_g=None,
            total_carbs_g=None,
            total_fat_g=None,
        )
    )
    await db_session.commit()

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
        },
    )

    assert response.status_code == 200

    ids = suggestion_ids(response.json())

    assert ids == [valid_recipe["id"]]
    assert missing_totals_recipe["id"] not in ids


@pytest.mark.asyncio
async def test_high_priority_recommendation_has_more_scoring_weight(
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
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-06",
        end_date="2026-07-10",
    )

    for day_offset in range(5):
        await create_gap_day(
            client,
            headers=headers,
            meal_plan_id=meal_plan["id"],
            planned_date=(date(2026, 7, 6) + timedelta(days=day_offset)).isoformat(),
            calories="100",
            protein_g="50",
            carbs_g="50" if day_offset == 0 else "100",
            fat_g="100",
        )

    protein_candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Protein Priority Candidate",
        calories="0",
        protein_g="50",
        carbs_g="0",
        fat_g="0",
    )
    carbs_candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Carbs Priority Candidate",
        calories="0",
        protein_g="0",
        carbs_g="50",
        fat_g="0",
    )

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-10",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert [item["action"] for item in data["recommendations_used"]] == [
        "increase_protein",
        "increase_carbs",
    ]
    assert [item["priority"] for item in data["recommendations_used"]] == [
        "high",
        "low",
    ]
    assert suggestion_ids(data) == [
        protein_candidate["id"],
        carbs_candidate["id"],
    ]
    assert_decimal(data["suggestions"][0]["score"], "75")
    assert_decimal(data["suggestions"][1]["score"], "25")


@pytest.mark.asyncio
async def test_decrease_actions_are_unresolved_and_do_not_add_score(
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
            "daily_fat_target_g": 50,
        },
    )
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )
    await create_gap_day(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        planned_date="2026-07-06",
        calories="100",
        protein_g="50",
        carbs_g="100",
        fat_g="100",
    )
    protein_candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Protein Gap Candidate",
        calories="0",
        protein_g="50",
        carbs_g="0",
        fat_g="100",
    )
    fat_only_candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Fat Only Candidate",
        calories="0",
        protein_g="0",
        carbs_g="0",
        fat_g="100",
    )

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["unresolved_actions"] == ["decrease_fat"]
    assert [item["action"] for item in data["recommendations_used"]] == [
        "increase_protein",
    ]
    assert suggestion_ids(data) == [protein_candidate["id"]]
    assert fat_only_candidate["id"] not in suggestion_ids(data)
    assert data["suggestions"][0]["matched_actions"] == ["increase_protein"]


@pytest.mark.asyncio
async def test_set_missing_targets_is_unresolved_and_not_scored(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await patch_nutrition_profile(
        client,
        headers=headers,
        payload={
            "daily_protein_target_g": 100,
        },
    )
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )
    await create_gap_day(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        planned_date="2026-07-06",
        calories="100",
        protein_g="50",
        carbs_g="100",
        fat_g="50",
    )
    candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Missing Targets Protein Candidate",
        calories="500",
        protein_g="50",
        carbs_g="500",
        fat_g="500",
    )

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["unresolved_actions"] == ["set_missing_targets"]
    assert [item["action"] for item in data["recommendations_used"]] == [
        "increase_protein",
    ]
    assert suggestion_ids(data) == [candidate["id"]]
    assert_decimal(data["suggestions"][0]["score"], "100")


@pytest.mark.asyncio
async def test_empty_recommendations_return_empty_suggestions(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Unused Candidate Without Gap Days",
        calories="500",
        protein_g="50",
        carbs_g="50",
        fat_g="20",
    )

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-12",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "start_date": "2026-07-06",
        "end_date": "2026-07-12",
        "recommendations_used": [],
        "unresolved_actions": [],
        "suggestions": [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_limit", [0, 51])
async def test_recipe_suggestions_validate_limit(
    client: AsyncClient,
    invalid_limit: int,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={"limit": invalid_limit},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recipe_suggestions_apply_limit_after_deterministic_sorting(
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
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )
    await create_gap_day(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        planned_date="2026-07-06",
        calories="0",
        protein_g="0",
        carbs_g="0",
        fat_g="0",
    )
    top_candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Top Candidate",
        calories="100",
        protein_g="100",
        carbs_g="100",
        fat_g="100",
    )
    await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Second Candidate",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
            "limit": 1,
        },
    )

    assert response.status_code == 200
    assert suggestion_ids(response.json()) == [top_candidate["id"]]


@pytest.mark.asyncio
async def test_recipe_suggestions_filter_by_non_balanced_diet_preference(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    await patch_nutrition_profile(
        client,
        headers=headers,
        payload={
            "diet_type": "high_protein",
            "daily_calories_target": 100,
            "daily_protein_target_g": 100,
            "daily_carbs_target_g": 100,
            "daily_fat_target_g": 100,
        },
    )
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )
    await create_gap_day(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        planned_date="2026-07-06",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    preferred_candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="High Protein Preferred Candidate",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
        diet_type="high_protein",
    )
    balanced_candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Balanced Non Preferred Candidate",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
        diet_type="balanced",
    )

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
        },
    )

    assert response.status_code == 200

    ids = suggestion_ids(response.json())

    assert ids == [preferred_candidate["id"]]
    assert balanced_candidate["id"] not in ids


@pytest.mark.asyncio
async def test_recipe_suggestions_reuse_allergy_and_disliked_ingredient_filtering(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    allergy_name = f"Gap Allergy {uuid4()}"
    disliked_name = f"Gap Disliked {uuid4()}"

    await patch_nutrition_profile(
        client,
        headers=headers,
        payload={
            "allergies": [allergy_name.upper()],
            "disliked_ingredients": [disliked_name.upper()],
            "daily_calories_target": 100,
            "daily_protein_target_g": 100,
            "daily_carbs_target_g": 100,
            "daily_fat_target_g": 100,
        },
    )
    meal_plan = await create_test_meal_plan(
        client,
        headers=headers,
        start_date="2026-07-06",
        end_date="2026-07-06",
    )
    await create_gap_day(
        client,
        headers=headers,
        meal_plan_id=meal_plan["id"],
        planned_date="2026-07-06",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )

    safe_candidate = await create_test_recipe_with_totals(
        client,
        headers=headers,
        title="Safe Personalized Candidate",
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    allergy_ingredient = await create_test_ingredient(
        client,
        headers=headers,
        name=allergy_name,
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )
    disliked_ingredient = await create_test_ingredient(
        client,
        headers=headers,
        name=disliked_name,
        calories="50",
        protein_g="50",
        carbs_g="50",
        fat_g="50",
    )

    allergy_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Allergy Candidate",
            "instructions": "Cook.",
            "diet_type": "balanced",
            "ingredients": [
                {
                    "ingredient_id": allergy_ingredient["id"],
                    "quantity_g": "100",
                }
            ],
        },
    )
    disliked_response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Disliked Candidate",
            "instructions": "Cook.",
            "diet_type": "balanced",
            "ingredients": [
                {
                    "ingredient_id": disliked_ingredient["id"],
                    "quantity_g": "100",
                }
            ],
        },
    )

    assert allergy_response.status_code == 201
    assert disliked_response.status_code == 201

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-06",
            "end_date": "2026-07-06",
        },
    )

    assert response.status_code == 200

    ids = suggestion_ids(response.json())

    assert ids == [safe_candidate["id"]]
    assert allergy_response.json()["id"] not in ids
    assert disliked_response.json()["id"] not in ids


@pytest.mark.asyncio
async def test_recipe_suggestions_reject_invalid_date_range(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        RECIPE_SUGGESTIONS_URL,
        headers=headers,
        params={
            "start_date": "2026-07-12",
            "end_date": "2026-07-06",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "start_date must be less than or equal to end_date"
    )
