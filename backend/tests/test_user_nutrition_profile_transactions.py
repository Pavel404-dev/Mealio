import asyncio
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models.user import User
from app.models.user_nutrition_profile import UserNutritionProfile
from app.repositories.user_nutrition_profiles import UserNutritionProfilesRepository
from app.schemas.user_nutrition_profile import UserNutritionProfileUpdate
from app.services.user_nutrition_profiles import UserNutritionProfilesService
from tests.test_user_preferences_nutrition_api import create_authenticated_user


@pytest.mark.parametrize("existing", [False, True])
async def test_concurrent_partial_patches_are_serialized(
    client, async_session_maker, monkeypatch, existing
):
    user, _ = await create_authenticated_user(client)
    user_id = UUID(user["id"])
    if existing:
        async with async_session_maker() as setup:
            await UserNutritionProfilesService(
                setup
            ).create_or_update_current_user_profile(
                user_id=user_id, data=UserNutritionProfileUpdate(allergies=["peanuts"])
            )

    first_has_lock = asyncio.Event()
    release_first = asyncio.Event()
    second_about_to_lock = asyncio.Event()
    original_get = UserNutritionProfilesRepository.get_by_user_id
    tasks = []

    async with (
        async_session_maker() as first,
        async_session_maker() as second,
        async_session_maker() as observer,
    ):
        # Reproduce authentication autobegin and assert separate real connections.
        await first.scalar(select(User).where(User.id == user_id))
        await second.scalar(select(User).where(User.id == user_id))
        first_pid = await first.scalar(text("SELECT pg_backend_pid()"))
        second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
        assert first_pid != second_pid
        # A previously loaded row must not hide a concurrent committed update.
        stale_profile = await original_get(
            UserNutritionProfilesRepository(second), user_id
        )

        async def pause_after_owner_lock(self, owner_id):
            assert owner_id == user_id
            if self.db is first:
                first_has_lock.set()
                await release_first.wait()
            return await original_get(self, owner_id)

        monkeypatch.setattr(
            UserNutritionProfilesRepository, "get_by_user_id", pause_after_owner_lock
        )
        second_service = UserNutritionProfilesService(second)
        original_lock = second_service.users_repository.get_by_id_for_update

        async def signal_second_lock(owner_id):
            second_about_to_lock.set()
            return await original_lock(owner_id)

        monkeypatch.setattr(
            second_service.users_repository, "get_by_id_for_update", signal_second_lock
        )
        try:
            async with asyncio.timeout(10):
                tasks.append(
                    asyncio.create_task(
                        UserNutritionProfilesService(
                            first
                        ).create_or_update_current_user_profile(
                            user_id=user_id,
                            data=UserNutritionProfileUpdate(
                                height_cm="180.0",
                                weekly_food_budget_amount="80.50",
                                budget_currency="EUR",
                            ),
                        )
                    )
                )
                await first_has_lock.wait()
                tasks.append(
                    asyncio.create_task(
                        second_service.create_or_update_current_user_profile(
                            user_id=user_id,
                            data=UserNutritionProfileUpdate(
                                weight_kg="75.25", weekly_food_budget_amount="90.25"
                            ),
                        )
                    )
                )
                await second_about_to_lock.wait()
                # Do not release the first writer until PostgreSQL confirms the
                # second connection is blocked by its row lock.
                while True:
                    blockers = await observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": second_pid}
                    )
                    if first_pid in blockers:
                        break
                    await asyncio.sleep(0.01)
                assert not tasks[1].done()
                release_first.set()
                first_result, second_result = await asyncio.gather(*tasks)
        finally:
            release_first.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        assert first_result.height_cm == Decimal("180.0")
        assert second_result.height_cm == Decimal("180.0")
        assert second_result.budget_currency == "EUR"
        assert second_result.weekly_food_budget_amount == Decimal("90.25")
        if existing:
            assert stale_profile is not None
            assert second_result.allergies == ["peanuts"]

    async with async_session_maker() as check:
        profiles = (
            await check.scalars(
                select(UserNutritionProfile).where(
                    UserNutritionProfile.user_id == user_id
                )
            )
        ).all()
        assert len(profiles) == 1
        profile = profiles[0]
        assert profile.height_cm == Decimal("180.0")
        assert profile.weight_kg == Decimal("75.25")
        assert profile.weekly_food_budget_amount == Decimal("90.25")
        assert profile.budget_currency == "EUR"
        assert profile.allergies == (["peanuts"] if existing else [])


@pytest.mark.parametrize(
    "assignment",
    [
        "sex = 'other'",
        "birth_date = DATE '1899-12-31'",
        "birth_date = (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date + 1",
        "height_cm = 49.9",
        "height_cm = 250.1",
        "height_cm = 'NaN'::numeric",
        "weight_kg = 9.99",
        "weight_kg = 500.01",
        "weight_kg = 'Infinity'::numeric",
        "activity_level = 'active'",
        "max_cooking_time_minutes = 0",
        "max_cooking_time_minutes = 481",
        "weekly_food_budget_amount = 0, budget_currency = 'EUR'",
        "weekly_food_budget_amount = 1000000.01, budget_currency = 'EUR'",
        "weekly_food_budget_amount = 'NaN'::numeric, budget_currency = 'EUR'",
        "budget_currency = 'usd', weekly_food_budget_amount = 10",
        "budget_currency = 'E1R', weekly_food_budget_amount = 10",
        "budget_currency = 'EUR'",
        "weekly_food_budget_amount = 10",
    ],
)
async def test_database_checks_reject_invalid_values(client, db_session, assignment):
    user, _ = await create_authenticated_user(client)
    user_id = UUID(user["id"])
    await UserNutritionProfilesService(
        db_session
    ).create_or_update_current_user_profile(
        user_id=user_id, data=UserNutritionProfileUpdate()
    )
    # assignment is a fixed test parametrization, never user input.
    # Constrained Numeric rejects Infinity before CHECK evaluation (22003).
    expected_error = DBAPIError if "Infinity" in assignment else IntegrityError
    expected_sqlstate = "22003" if "Infinity" in assignment else "23514"
    with pytest.raises(expected_error) as caught:
        await db_session.execute(
            text(
                f"UPDATE user_nutrition_profiles SET {assignment} WHERE user_id = :user_id"
            ),
            {"user_id": user_id},
        )
    assert caught.value.orig.sqlstate == expected_sqlstate
    await db_session.rollback()
    result = await UserNutritionProfilesService(db_session).get_current_user_profile(
        user_id
    )
    assert result.sex is None
    assert result.height_cm is None
    assert result.weekly_food_budget_amount is None
    assert result.budget_currency is None


async def test_unexpected_database_failure_is_not_masked(
    client, db_session, monkeypatch
):
    user, _ = await create_authenticated_user(client)
    user_id = UUID(user["id"])
    service = UserNutritionProfilesService(db_session)
    await service.create_or_update_current_user_profile(
        user_id=user_id, data=UserNutritionProfileUpdate(height_cm="170.0")
    )
    original_update = service.repository.update

    async def invalid_database_write(**kwargs):
        profile = await original_update(**kwargs)
        profile.sex = "other"
        await db_session.flush()
        return profile

    monkeypatch.setattr(service.repository, "update", invalid_database_write)
    with pytest.raises(IntegrityError):
        await service.create_or_update_current_user_profile(
            user_id=user_id, data=UserNutritionProfileUpdate(height_cm="180.0")
        )
    assert not db_session.in_transaction()
    result = await service.get_current_user_profile(user_id)
    assert result.height_cm == Decimal("170.0")
    assert result.sex is None
