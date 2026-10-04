from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_nutrition_profile import UserNutritionProfile
from app.repositories.user_nutrition_profiles import UserNutritionProfilesRepository
from app.schemas import user_nutrition_profile as schemas
from tests.test_user_preferences_nutrition_api import (
    NUTRITION_PROFILE_URL,
    assert_default_profile,
    create_authenticated_user,
)

NEW_VALUES = {
    "sex": "female",
    "birth_date": "1990-01-02",
    "height_cm": "170.5",
    "weight_kg": "70.25",
    "activity_level": "moderately_active",
    "max_cooking_time_minutes": 45,
    "weekly_food_budget_amount": "120.50",
    "budget_currency": "EUR",
}


async def profile_count(db_session, user_id):
    return await db_session.scalar(
        select(func.count())
        .select_from(UserNutritionProfile)
        .where(UserNutritionProfile.user_id == UUID(user_id))
    )


async def patch(client, headers, payload):
    return await client.patch(NUTRITION_PROFILE_URL, headers=headers, json=payload)


async def read(client, headers):
    response = await client.get(NUTRITION_PROFILE_URL, headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_get_defaults_does_not_create_profile(client, db_session):
    user, headers = await create_authenticated_user(client)
    result = await read(client, headers)
    assert_default_profile(result)
    assert all(result[field] is None for field in NEW_VALUES)
    assert await profile_count(db_session, user["id"]) == 0


async def test_create_read_partial_update_and_nullable_clearing(client, db_session):
    user, headers = await create_authenticated_user(client)
    initial = await patch(
        client,
        headers,
        {
            **NEW_VALUES,
            "budget_currency": " eur ",
            "daily_calories_target": 2400,
            "allergies": ["peanuts"],
        },
    )
    assert initial.status_code == 200
    for field, value in NEW_VALUES.items():
        assert initial.json()[field] == value
    assert await read(client, headers) == initial.json()
    updated = await patch(client, headers, {"height_cm": "175.0", "weight_kg": "71.50"})
    assert updated.status_code == 200
    result = updated.json()
    assert result["height_cm"] == "175.0"
    assert result["weight_kg"] == "71.50"
    assert result["daily_calories_target"] == 2400
    assert result["allergies"] == ["peanuts"]
    assert result["sex"] == "female"
    cleared = await patch(
        client,
        headers,
        {
            **dict.fromkeys(NEW_VALUES),
            "daily_calories_target": None,
            "diet_type": None,
            "preferred_meals_per_day": None,
            "allergies": [],
            "disliked_ingredients": [],
        },
    )
    assert cleared.status_code == 200
    assert all(cleared.json()[field] is None for field in NEW_VALUES)
    assert cleared.json()["allergies"] == []
    assert cleared.json()["disliked_ingredients"] == []
    assert cleared.json()["daily_calories_target"] is None
    assert await profile_count(db_session, user["id"]) == 1


async def test_empty_patch_creates_defaults_and_preserves_existing_row(
    client, db_session
):
    user, headers = await create_authenticated_user(client)
    created = await patch(client, headers, {})
    assert created.status_code == 200
    assert_default_profile(created.json())
    assert all(created.json()[field] is None for field in NEW_VALUES)
    assert await profile_count(db_session, user["id"]) == 1
    row = await db_session.scalar(
        select(UserNutritionProfile).where(
            UserNutritionProfile.user_id == UUID(user["id"])
        )
    )
    row_id, updated_at = row.id, row.updated_at
    changed = await patch(client, headers, NEW_VALUES)
    assert changed.status_code == 200
    await db_session.refresh(row)
    updated_at = row.updated_at
    empty = await patch(client, headers, {})
    assert empty.status_code == 200
    assert empty.json() == changed.json()
    await db_session.refresh(row)
    assert row.id == row_id
    assert row.updated_at == updated_at


@pytest.mark.parametrize(
    "payload",
    [
        {"sex": "unknown"},
        {"activity_level": "active"},
        {"height_cm": True},
        {"height_cm": "170.01"},
        {"height_cm": "NaN"},
        {"weight_kg": False},
        {"weight_kg": "70.001"},
        {"weight_kg": "Infinity"},
        {"weekly_food_budget_amount": True, "budget_currency": "EUR"},
        {"weekly_food_budget_amount": "0", "budget_currency": "EUR"},
        {"weekly_food_budget_amount": "1.001", "budget_currency": "EUR"},
        {"weekly_food_budget_amount": "Infinity", "budget_currency": "EUR"},
        {"max_cooking_time_minutes": True},
        {"max_cooking_time_minutes": 1.5},
        {"max_cooking_time_minutes": 481},
        {"budget_currency": "E1R"},
        {"goal": None},
        {"allergies": None},
        {"disliked_ingredients": None},
        {"id": "00000000-0000-0000-0000-000000000001"},
        {"user_id": "00000000-0000-0000-0000-000000000001"},
        {"unexpected": 1},
        *[
            {field: 2_147_483_648}
            for field in (
                "daily_calories_target",
                "daily_protein_target_g",
                "daily_carbs_target_g",
                "daily_fat_target_g",
            )
        ],
    ],
)
async def test_invalid_patch_leaves_existing_profile_unchanged(client, payload):
    _, headers = await create_authenticated_user(client)
    initial = await patch(client, headers, {**NEW_VALUES, "allergies": ["peanuts"]})
    assert initial.status_code == 200
    response = await patch(client, headers, {"goal": "gain_weight", **payload})
    assert response.status_code == 422
    assert await read(client, headers) == initial.json()


async def test_birth_date_utc_boundary_and_rejection_without_creation(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(schemas, "utc_today", lambda: date(2000, 1, 2))
    user, headers = await create_authenticated_user(client)
    for value in ("1899-12-31", "2000-01-03", "2000-01-02T00:00:00Z", True):
        response = await patch(client, headers, {"birth_date": value})
        assert response.status_code == 422
        assert await profile_count(db_session, user["id"]) == 0
    for value in ("1900-01-01", "2000-01-02"):
        response = await patch(client, headers, {"birth_date": value})
        assert response.status_code == 200
        assert response.json()["birth_date"] == value
    response = await patch(
        client, headers, {"birth_date": "2000-01-03", "height_cm": "180.0"}
    )
    assert response.status_code == 422
    assert (await read(client, headers))["height_cm"] is None


@pytest.mark.parametrize("initial", [None, NEW_VALUES])
async def test_budget_pair_validates_merged_state_atomically(
    client, db_session, initial
):
    user, headers = await create_authenticated_user(client)
    if initial is not None:
        assert (await patch(client, headers, initial)).status_code == 200
    before = await read(client, headers)
    invalid = (
        ({"weekly_food_budget_amount": "80.25"}, {"budget_currency": "EUR"})
        if initial is None
        else ({"weekly_food_budget_amount": None}, {"budget_currency": None})
    )
    for payload in invalid:
        response = await patch(client, headers, {"goal": "gain_weight", **payload})
        assert response.status_code == 422
        assert await read(client, headers) == before
        assert await profile_count(db_session, user["id"]) == (
            0 if initial is None else 1
        )
    complete = await patch(
        client,
        headers,
        {"weekly_food_budget_amount": "80.25", "budget_currency": "eur"},
    )
    assert complete.status_code == 200
    amount_only = await patch(client, headers, {"weekly_food_budget_amount": "99.99"})
    assert amount_only.status_code == 200
    assert amount_only.json()["budget_currency"] == "EUR"
    currency_only = await patch(client, headers, {"budget_currency": "zzz"})
    assert currency_only.status_code == 200
    assert currency_only.json()["weekly_food_budget_amount"] == "99.99"
    assert currency_only.json()["budget_currency"] == "ZZZ"
    cleared = await patch(
        client, headers, {"weekly_food_budget_amount": None, "budget_currency": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["weekly_food_budget_amount"] is None
    assert cleared.json()["budget_currency"] is None


async def test_new_fields_are_scoped_to_authenticated_owner(client, db_session):
    first_user, first_headers = await create_authenticated_user(client)
    second_user, second_headers = await create_authenticated_user(client)
    initial = await patch(client, first_headers, NEW_VALUES)
    assert initial.status_code == 200
    second_profile = await read(client, second_headers)
    assert all(second_profile[field] is None for field in NEW_VALUES)
    forged = await patch(
        client, second_headers, {"user_id": first_user["id"], "weight_kg": "80.00"}
    )
    assert forged.status_code == 422
    own = await patch(client, second_headers, {"weight_kg": "80.00"})
    assert own.status_code == 200
    assert await read(client, first_headers) == initial.json()
    assert await profile_count(db_session, first_user["id"]) == 1
    assert await profile_count(db_session, second_user["id"]) == 1


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure_point", ["after_flush", "before_commit"])
async def test_failure_before_commit_rolls_back_and_propagates(
    client, db_session, monkeypatch, existing, failure_point
):
    user, headers = await create_authenticated_user(client)
    if existing:
        assert (
            await patch(
                client, headers, {"allergies": ["peanuts"], "height_cm": "170.0"}
            )
        ).status_code == 200
    before = await read(client, headers)
    failed_sessions = []
    with monkeypatch.context() as patcher:
        if failure_point == "after_flush":
            method = "update" if existing else "create"
            original = getattr(UserNutritionProfilesRepository, method)

            async def fail_after_flush(self, **kwargs):
                await original(self, **kwargs)
                failed_sessions.append(self.db)
                raise RuntimeError("synthetic nutrition write failure")

            patcher.setattr(UserNutritionProfilesRepository, method, fail_after_flush)
        else:

            async def fail_before_commit(self):
                failed_sessions.append(self)
                raise RuntimeError("synthetic nutrition write failure")

            patcher.setattr(AsyncSession, "commit", fail_before_commit)
        with pytest.raises(RuntimeError, match="synthetic nutrition write failure"):
            await patch(
                client,
                headers,
                {
                    "height_cm": "180.0",
                    "weekly_food_budget_amount": "100.00",
                    "budget_currency": "EUR",
                },
            )
    assert len(failed_sessions) == 1
    assert not failed_sessions[0].in_transaction()
    assert await read(client, headers) == before
    assert await profile_count(db_session, user["id"]) == int(existing)
    assert (await patch(client, headers, {"height_cm": "180.0"})).status_code == 200


@pytest.mark.parametrize(
    "field", ["height_cm", "weight_kg", "weekly_food_budget_amount"]
)
@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
async def test_raw_non_finite_json_is_422_without_changes(client, field, literal):
    _, headers = await create_authenticated_user(client)
    initial = await patch(client, headers, NEW_VALUES)
    assert initial.status_code == 200
    response = await client.patch(
        NUTRITION_PROFILE_URL,
        headers={**headers, "Content-Type": "application/json"},
        content=f'{{"{field}": {literal}, "goal": "gain_weight"}}',
    )
    assert response.status_code == 422
    assert await read(client, headers) == initial.json()


async def test_json_numeric_inputs_and_postgres_integer_max_are_persisted(client):
    _, headers = await create_authenticated_user(client)
    targets = dict.fromkeys(
        [
            "daily_calories_target",
            "daily_protein_target_g",
            "daily_carbs_target_g",
            "daily_fat_target_g",
        ],
        2_147_483_647,
    )
    response = await patch(
        client,
        headers,
        {
            **targets,
            "height_cm": 170.5,
            "weight_kg": 70.25,
            "weekly_food_budget_amount": 99.5,
            "budget_currency": "eur",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["height_cm"] == "170.5"
    assert result["weight_kg"] == "70.25"
    assert result["weekly_food_budget_amount"] == "99.50"
    assert all(result[field] == value for field, value in targets.items())
    assert await read(client, headers) == result
