import asyncio
from contextlib import contextmanager
from datetime import date
from decimal import localcontext, ROUND_DOWN
from uuid import UUID

import pytest
from sqlalchemy import event, select, text

from app.api.deps import get_recipe_generation_provider
from app.integrations.openai_recipe_generation import OpenAIRecipeGenerationProvider
from app.main import app
from app.models.user_nutrition_profile import UserNutritionProfile
from app.repositories.user_nutrition_profiles import UserNutritionProfilesRepository
from app.schemas.nutrition_calculation import NutritionCalculationRequest
from app.services.nutrition_calculation import (
    NutritionCalculationInvariantError,
    NutritionCalculator,
)
from app.services.user_nutrition_profiles import UserNutritionProfilesService
from tests.test_user_preferences_nutrition_api import (
    NUTRITION_PROFILE_URL,
    create_authenticated_user,
)

URL = NUTRITION_PROFILE_URL + "/calculate"
REQUEST = {"calculation_date": "2026-10-04"}
PROFILE = {
    "sex": "male",
    "birth_date": "1996-10-04",
    "height_cm": "180.0",
    "weight_kg": "80.00",
    "activity_level": "moderately_active",
    "goal": "maintain",
}
MANUAL = {
    "daily_calories_target": 1,
    "daily_protein_target_g": 2147483647,
    "daily_fat_target_g": 1,
    "daily_carbs_target_g": 2,
    "diet_type": "vegan",
    "allergies": ["peanuts"],
    "disliked_ingredients": ["celery"],
    "preferred_meals_per_day": 8,
    "max_cooking_time_minutes": 1,
    "weekly_food_budget_amount": "10.00",
    "budget_currency": "EUR",
}


@pytest.fixture(autouse=True)
def forbid_provider(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Nutrition calculation invoked a recipe provider")

    app.dependency_overrides[get_recipe_generation_provider] = fail
    monkeypatch.setattr(OpenAIRecipeGenerationProvider, "generate_recipe", fail)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_recipe_generation_provider, None)


@contextmanager
def read_only_requests(engine):
    statements = []

    def inspect_sql(conn, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().upper().startswith("SELECT"), "Calculation wrote SQL"
        assert "FOR UPDATE" not in statement.upper()
        statements.append(statement)

    def reject_commit(conn):
        pytest.fail("Calculation committed a transaction")

    event.listen(engine.sync_engine, "before_cursor_execute", inspect_sql)
    event.listen(engine.sync_engine, "commit", reject_commit)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", inspect_sql)
        event.remove(engine.sync_engine, "commit", reject_commit)


async def stored_profiles(session):
    rows = await session.execute(
        select(UserNutritionProfile.__table__).order_by(UserNutritionProfile.id)
    )
    return [dict(row) for row in rows.mappings()]


async def set_profile(client, headers, data):
    response = await client.patch(NUTRITION_PROFILE_URL, headers=headers, json=data)
    assert response.status_code == 200
    return response.json()


async def test_authentication_required(client, test_engine):
    with read_only_requests(test_engine):
        response = await client.post(URL, json=REQUEST)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "profile,status,detail",
    [
        (
            None,
            "incomplete_profile",
            ["sex", "birth_date", "height_cm", "weight_kg", "activity_level"],
        ),
        ({**PROFILE, "weight_kg": None}, "incomplete_profile", ["weight_kg"]),
        (
            {**PROFILE, "birth_date": "2010-10-04"},
            "unsupported_profile",
            ["age_out_of_range"],
        ),
        (
            {**PROFILE, "height_cm": "200.0", "weight_kg": "160.00"},
            "unsupported_profile",
            ["bmi_out_of_range"],
        ),
        (PROFILE, "calculated", None),
    ],
)
async def test_outcome_shape_single_read_no_writes(
    client, db_session, test_engine, profile, status, detail
):
    _, headers = await create_authenticated_user(client)
    if profile is not None:
        await set_profile(client, headers, {**profile, **MANUAL})
    before = await stored_profiles(db_session)
    with read_only_requests(test_engine) as statements:
        response = await client.post(URL, headers=headers, json=REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == status
    assert body["rules_version"] == "mealio-nutrition-v1"
    assert body["calculation_date"] == "2026-10-04"
    assert sum("FROM user_nutrition_profiles" in sql for sql in statements) == 1
    assert (
        await stored_profiles(db_session) == before
    )  # Includes row count and timestamps.
    if detail is not None:
        detail_field = (
            "missing_fields" if status == "incomplete_profile" else "reason_codes"
        )
        assert body == {
            "status": status,
            "rules_version": "mealio-nutrition-v1",
            "calculation_date": "2026-10-04",
            "result": None,
            detail_field: detail,
        }
    else:
        assert set(body) == {"status", "rules_version", "calculation_date", "result"}
        assert body["result"] == {
            "age_years": 30,
            "used_inputs": PROFILE,
            "activity_factor": "1.80",
            "goal_factor": "1.00",
            "ree_kcal": "1780.00",
            "tdee_kcal": "3204.00",
            "calories_target_kcal": 3204,
            "protein_target_g": 160,
            "fat_target_g": 107,
            "carbs_target_g": 400,
            "energy_delta_kcal": -1,
        }


async def test_manual_preferences_do_not_change_estimate(client, db_session):
    _, headers = await create_authenticated_user(client)
    await set_profile(client, headers, PROFILE)
    first = await client.post(URL, headers=headers, json=REQUEST)
    saved = await set_profile(client, headers, MANUAL)
    before = await stored_profiles(db_session)
    second = await client.post(
        URL,
        headers=headers,
        json={**REQUEST, "rules_version": "mealio-nutrition-v1"},
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert await stored_profiles(db_session) == before
    assert (await client.get(NUTRITION_PROFILE_URL, headers=headers)).json() == saved


async def test_ownership_and_concurrent_requests(client, db_session, test_engine):
    _, first = await create_authenticated_user(client)
    _, second = await create_authenticated_user(client)
    female = {
        **PROFILE,
        "sex": "female",
        "height_cm": "165.0",
        "weight_kg": "60.00",
        "activity_level": "sedentary",
        "goal": "lose_weight",
    }
    await set_profile(client, first, PROFILE)
    await set_profile(client, second, female)
    before = await stored_profiles(db_session)

    async def request(headers, precision):
        with localcontext() as context:
            context.prec = precision
            context.rounding = ROUND_DOWN
            response = await client.post(URL, headers=headers, json=REQUEST)
            assert context.prec == precision
            assert response.status_code == 200
            return response.json()["result"]

    with read_only_requests(test_engine):
        results = await asyncio.gather(
            request(first, 1), request(second, 2), request(first, 3)
        )
    assert [r["used_inputs"] for r in results] == [PROFILE, female, PROFILE]
    assert [r["calories_target_kcal"] for r in results] == [3204, 1664, 3204]
    assert await stored_profiles(db_session) == before


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"calculation_date": None},
        *[
            {"calculation_date": value}
            for value in (
                True,
                0,
                1791072000,
                1.5,
                "2026-10-04T00:00:00Z",
                "20261004",
                "2026-1-04",
                "2026-02-29",
            )
        ],
        *[
            {**REQUEST, "rules_version": value}
            for value in (None, 1, True, [], {}, "unknown", "mealio-nutrition-v2")
        ],
        *[
            {**REQUEST, field: "synthetic-forbidden-override"}
            for field in (
                "id",
                "user_id",
                "age",
                "profile",
                "sex",
                "birth_date",
                "height_cm",
                "weight_kg",
                "goal",
                "daily_calories_target",
            )
        ],
    ],
)
async def test_invalid_requests_are_422_without_writes(
    client, db_session, test_engine, payload
):
    _, headers = await create_authenticated_user(client)
    await set_profile(client, headers, PROFILE)
    before = await stored_profiles(db_session)
    with read_only_requests(test_engine):
        response = await client.post(URL, headers=headers, json=payload)
    assert response.status_code == 422
    assert "synthetic-forbidden-override" not in response.text
    assert "result" not in response.json()
    assert await stored_profiles(db_session) == before


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["read", "calculator"])
async def test_unexpected_failure_propagates_without_writes(
    client, db_session, test_engine, monkeypatch, existing, failure
):
    _, headers = await create_authenticated_user(client)
    if existing:
        await set_profile(client, headers, {**PROFILE, **MANUAL})
    before = await stored_profiles(db_session)
    if failure == "read":

        async def broken_read(*args, **kwargs):
            raise RuntimeError("synthetic read failure")

        monkeypatch.setattr(
            UserNutritionProfilesRepository, "get_by_user_id", broken_read
        )
        error = RuntimeError
    else:

        def broken_calculator(*args, **kwargs):
            raise NutritionCalculationInvariantError("synthetic invariant failure")

        monkeypatch.setattr(NutritionCalculator, "calculate", broken_calculator)
        error = NutritionCalculationInvariantError
    with read_only_requests(test_engine), pytest.raises(error, match="synthetic"):
        await client.post(URL, headers=headers, json=REQUEST)
    assert await stored_profiles(db_session) == before


async def test_service_does_not_autoflush_pending_changes(
    client, async_session_maker, test_engine
):
    user, _ = await create_authenticated_user(client)
    async with async_session_maker() as session:
        pending = UserNutritionProfile(user_id=UUID(user["id"]), goal="gain_weight")
        session.add(pending)
        with read_only_requests(test_engine):
            result = await UserNutritionProfilesService(
                session
            ).calculate_current_user_targets(
                user_id=UUID(user["id"]),
                data=NutritionCalculationRequest(calculation_date=date(2026, 10, 4)),
            )
        assert result.status == "incomplete_profile"
        assert "goal" not in result.missing_fields
        assert pending in session.new
        assert pending.id is None


async def test_snapshot_survives_concurrent_patch_in_separate_sessions(
    client, monkeypatch
):
    _, headers = await create_authenticated_user(client)
    await set_profile(client, headers, PROFILE)
    read_done, resume = asyncio.Event(), asyncio.Event()
    original = UserNutritionProfilesRepository.get_by_user_id
    reader_pids, writer_pids = [], []

    async def pause_read(self, user_id):
        row = await original(self, user_id)
        pid = await self.db.scalar(text("SELECT pg_backend_pid()"))
        if asyncio.current_task() is read_task:
            reader_pids.append(pid)
            read_done.set()
            await resume.wait()
        else:
            writer_pids.append(pid)
        return row

    monkeypatch.setattr(UserNutritionProfilesRepository, "get_by_user_id", pause_read)
    read_task = asyncio.create_task(client.post(URL, headers=headers, json=REQUEST))
    changed = {
        **PROFILE,
        "height_cm": "165.0",
        "weight_kg": "60.00",
        "sex": "female",
        "activity_level": "sedentary",
        "goal": "lose_weight",
    }
    try:
        async with asyncio.timeout(10):
            await read_done.wait()
            await set_profile(client, headers, changed)
            resume.set()
            old = await read_task
    finally:
        resume.set()
        if not read_task.done():
            read_task.cancel()
        await asyncio.gather(read_task, return_exceptions=True)
    assert len(reader_pids) == len(writer_pids) == 1
    assert reader_pids[0] != writer_pids[0]
    assert old.status_code == 200
    assert old.json()["result"]["used_inputs"] == PROFILE
    assert old.json()["result"]["calories_target_kcal"] == 3204
    new = await client.post(URL, headers=headers, json=REQUEST)
    assert new.status_code == 200
    assert new.json()["result"]["used_inputs"] == changed
    assert new.json()["result"]["calories_target_kcal"] == 1664
