from uuid import UUID

from sqlalchemy import select

from app.models.user_nutrition_profile import UserNutritionProfile
from tests.test_user_nutrition_profile_w4_api import patch, profile_count, read
from tests.test_user_preferences_nutrition_api import (
    NUTRITION_PROFILE_URL,
    create_authenticated_user,
)


async def test_likes_roundtrip_clear_omission_owner_and_legacy_preservation(
    client, db_session
):
    user, headers = await create_authenticated_user(client)
    _, other = await create_authenticated_user(client)
    assert (await read(client, headers))["liked_ingredients"] == []
    assert await profile_count(db_session, user["id"]) == 0
    original = {
        "diet_type": "custom diet",
        "allergies": ["peanuts"],
        "disliked_ingredients": ["peanuts"],
        "daily_calories_target": 2400,
        "daily_protein_target_g": 150,
        "daily_carbs_target_g": 300,
        "daily_fat_target_g": 80,
        "preferred_meals_per_day": 4,
        "weekly_food_budget_amount": "50.12",
        "budget_currency": "ZZZ",
    }
    assert (await patch(client, headers, original)).status_code == 200
    row = await db_session.scalar(
        select(UserNutritionProfile).where(
            UserNutritionProfile.user_id == UUID(user["id"])
        )
    )
    row_id = row.id
    values = ["peanuts", "peanuts", *["x" * 101] * 26]
    result = await patch(
        client, headers, {"liked_ingredients": [" peanuts ", "", *values[1:]]}
    )
    assert result.status_code == 200
    assert result.json()["liked_ingredients"] == values
    for key, value in original.items():
        assert result.json()[key] == value
    await db_session.refresh(row)
    assert row.id == row_id
    assert row.liked_ingredients == values
    assert await read(client, headers) == result.json()
    assert (await read(client, other))["liked_ingredients"] == []
    omitted = await patch(client, headers, {"max_cooking_time_minutes": 45})
    assert omitted.json()["liked_ingredients"] == values
    invalid = await patch(client, headers, {"liked_ingredients": None})
    assert invalid.status_code == 422
    assert await read(client, headers) == omitted.json()
    assert (
        await patch(client, other, {"liked_ingredients": ["oats"]})
    ).status_code == 200
    assert (await read(client, headers))["liked_ingredients"] == values
    assert (await patch(client, headers, {"liked_ingredients": []})).json()[
        "liked_ingredients"
    ] == []
    assert (await read(client, headers))["allergies"] == ["peanuts"]


async def test_calculate_read_only_then_apply_shown_snapshot_last_write_wins(client):
    _, headers = await create_authenticated_user(client)
    before = await patch(
        client,
        headers,
        {
            "sex": "male",
            "birth_date": "1996-10-04",
            "height_cm": "180.0",
            "weight_kg": "80.00",
            "activity_level": "moderately_active",
            "goal": "maintain",
            "liked_ingredients": ["peanuts"],
            "allergies": ["peanuts"],
            "daily_calories_target": 2400,
        },
    )
    assert before.status_code == 200
    result = await client.post(
        f"{NUTRITION_PROFILE_URL}/calculate",
        headers=headers,
        json={"calculation_date": "2026-10-04", "rules_version": "mealio-nutrition-v1"},
    )
    assert result.status_code == 200
    assert await read(client, headers) == before.json()
    estimate = result.json()["result"]
    targets = {
        "daily_calories_target": estimate["calories_target_kcal"],
        "daily_protein_target_g": estimate["protein_target_g"],
        "daily_carbs_target_g": estimate["carbs_target_g"],
        "daily_fat_target_g": estimate["fat_target_g"],
    }
    assert list(targets.values()) == [3204, 160, 400, 107]
    # Explicitly document the approved concurrency limit: a shown snapshot may
    # overwrite intervening targets. No ETag/revision or hidden recalculation.
    assert (
        await patch(
            client, headers, {"daily_calories_target": 2500, "weight_kg": "81.00"}
        )
    ).status_code == 200
    applied = await patch(client, headers, targets)
    assert applied.status_code == 200
    for key, value in targets.items():
        assert applied.json()[key] == value
    assert applied.json()["weight_kg"] == "81.00"
    assert applied.json()["liked_ingredients"] == ["peanuts"]
    assert applied.json()["allergies"] == ["peanuts"]
