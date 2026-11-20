import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest
from sqlalchemy import update

from app.api.deps import get_meal_plan_generation_provider
from app.core.config import get_settings
from app.core.security import create_access_token
from app.integrations.meal_plan_generation import (
    MealPlanProviderResult,
    MealPlanProviderTimeout,
    MealPlanProviderTransientError,
)
from app.main import app
from app.models.ai_meal_plan_preview_idempotency import AIMealPlanPreviewIdempotency
from app.models.ai_meal_plan_preview_limit import AIMealPlanPreviewLimit
from app.models.ingredient import Ingredient, NutritionValue
from app.models.recipe import Recipe, RecipeIngredient
from app.models.user import User
from app.models.user_nutrition_profile import UserNutritionProfile
from app.repositories.ai_meal_plan_preview_idempotency import (
    AIMealPlanPreviewIdempotencyRepository,
    PreviewReservation,
)

URL = "/api/v2/meal-plans/ai/generate-preview"
PAYLOAD = {"planned_date": "2026-12-07", "locale": "en", "meal_types": ["lunch"]}
IDEMPOTENCY_KEY = "client-preview-1"


class PreviewProvider:
    model = "quota-test-model"

    def __init__(self):
        self.calls = 0
        self.release = asyncio.Event()
        self.release.set()
        self.failure = None

    async def select_meals(self, *, context_json):
        self.calls += 1
        await self.release.wait()
        if self.failure:
            raise self.failure
        return MealPlanProviderResult(
            {
                "items": [
                    {
                        "meal_type": "lunch",
                        "candidate_number": 1,
                        "serving_hundredths": 100,
                    }
                ]
            }
        )


@pytest.fixture
def provider(client, monkeypatch):
    fake_provider = PreviewProvider()
    monkeypatch.setitem(
        app.dependency_overrides,
        get_meal_plan_generation_provider,
        lambda: fake_provider,
    )
    return fake_provider


async def seed_account(session, name):
    account = User(email=f"{name}@example.com")
    session.add(account)
    await session.flush()
    nutrition = {
        "calories": Decimal("200"),
        "protein_g": Decimal("10"),
        "carbs_g": Decimal("30"),
        "fat_g": Decimal("4"),
    }
    session.add(
        Recipe(
            created_by_user_id=account.id,
            title="Quota test lunch",
            instructions="Synthetic recipe.",
            meal_type="lunch",
            **{f"total_{key}": value for key, value in nutrition.items()},
            recipe_ingredients=[
                RecipeIngredient(
                    quantity_g=Decimal("100"),
                    ingredient=Ingredient(
                        name=f"Quota account ingredient {name}",
                        nutrition_value=NutritionValue(portion_g=100, **nutrition),
                    ),
                )
            ],
        )
    )
    await session.commit()
    token = create_access_token(str(account.id))
    return account.id, {"Authorization": f"Bearer {token}"}


async def test_concurrent_previews_share_the_last_model_attempt(
    client, db_session, provider, monkeypatch
):
    monkeypatch.setattr(get_settings(), "ai_meal_plan_preview_rate_limit", 2)
    account, headers = await seed_account(db_session, "quota-owner")
    initial = await client.post(URL, json=PAYLOAD, headers=headers)
    assert initial.status_code == 200, initial.text

    provider.release.clear()
    requests = [
        asyncio.create_task(client.post(URL, json=PAYLOAD, headers=headers))
        for _ in range(2)
    ]
    try:
        done, _ = await asyncio.wait(
            requests, timeout=10, return_when=asyncio.FIRST_COMPLETED
        )
        assert len(done) == 1, "The rejected request must finish during the model call"
        denied = done.pop().result()
        assert denied.status_code == 429, denied.text
        assert 1 <= int(denied.headers["Retry-After"]) <= 60
    finally:
        provider.release.set()
        responses = await asyncio.wait_for(asyncio.gather(*requests), timeout=10)

    assert sorted(response.status_code for response in responses) == [200, 429]
    assert provider.calls == 2
    bucket = await db_session.get(AIMealPlanPreviewLimit, account)
    assert bucket.attempts == 2


async def test_failed_attempt_counts_and_the_expired_window_resets_per_account(
    client, db_session, provider, monkeypatch
):
    monkeypatch.setattr(get_settings(), "ai_meal_plan_preview_rate_limit", 1)
    account, headers = await seed_account(db_session, "quota-first")
    _, other_headers = await seed_account(db_session, "quota-other")
    provider.failure = MealPlanProviderTimeout()

    failure = await client.post(URL, json=PAYLOAD, headers=headers)
    assert failure.status_code == 503
    provider.failure = None
    denied = await client.post(URL, json=PAYLOAD, headers=headers)
    assert denied.status_code == 429
    assert provider.calls == 1

    other = await client.post(URL, json=PAYLOAD, headers=other_headers)
    assert other.status_code == 200, other.text
    await db_session.execute(
        update(AIMealPlanPreviewLimit)
        .where(AIMealPlanPreviewLimit.user_id == account)
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()

    retried = await client.post(URL, json=PAYLOAD, headers=headers)
    assert retried.status_code == 200, retried.text
    assert provider.calls == 3
    bucket = await db_session.get(AIMealPlanPreviewLimit, account)
    assert bucket.attempts == 1 and bucket.expires_at > datetime.now(UTC)


@pytest.mark.parametrize(("limit", "status"), [(1, 429), (2, 503)])
async def test_retry_reserves_a_separate_account_attempt(
    client, db_session, provider, monkeypatch, limit, status
):
    monkeypatch.setattr(get_settings(), "ai_meal_plan_preview_rate_limit", limit)
    account, headers = await seed_account(db_session, "quota-retry")
    provider.failure = MealPlanProviderTransientError()

    response = await client.post(URL, json=PAYLOAD, headers=headers)

    assert response.status_code == status
    if status == 429:
        assert response.json() == {"detail": "AI meal plan preview rate limit exceeded"}
        assert 1 <= int(response.headers["Retry-After"]) <= 60
    assert provider.calls == limit
    bucket = await db_session.get(AIMealPlanPreviewLimit, account)
    assert bucket.attempts == limit


async def test_concurrent_key_generates_once_and_replays_after_quota_is_used(
    client, db_session, provider, monkeypatch
):
    monkeypatch.setattr(get_settings(), "ai_meal_plan_preview_rate_limit", 1)
    account, headers = await seed_account(db_session, "preview-key-concurrent")
    headers["Idempotency-Key"] = IDEMPOTENCY_KEY

    provider.release.clear()
    requests = [
        asyncio.create_task(client.post(URL, json=PAYLOAD, headers=headers))
        for _ in range(2)
    ]
    try:
        done, _ = await asyncio.wait(
            requests, timeout=10, return_when=asyncio.FIRST_COMPLETED
        )
        assert len(done) == 1, "The duplicate should return while generation is running"
        duplicate = done.pop().result()
        assert duplicate.status_code == 409
        assert duplicate.json() == {
            "detail": "AI meal plan preview is already in progress"
        }
        assert duplicate.headers["Retry-After"] == "1"
    finally:
        provider.release.set()
        responses = await asyncio.wait_for(asyncio.gather(*requests), timeout=10)

    [original] = [response for response in responses if response.status_code == 200]
    replay = await client.post(
        URL, json={**PAYLOAD, "meal_types": [" LUNCH "]}, headers=headers
    )
    assert replay.status_code == 200
    assert replay.json() == original.json()
    assert provider.calls == 1
    bucket = await db_session.get(AIMealPlanPreviewLimit, account)
    assert bucket.attempts == 1


async def test_key_is_scoped_to_account_and_preview_input(client, db_session, provider):
    _, first_headers = await seed_account(db_session, "preview-key-first")
    _, second_headers = await seed_account(db_session, "preview-key-second")
    first_headers["Idempotency-Key"] = IDEMPOTENCY_KEY
    second_headers["Idempotency-Key"] = IDEMPOTENCY_KEY
    first = await client.post(URL, json=PAYLOAD, headers=first_headers)

    changed = await client.post(
        URL, json={**PAYLOAD, "planned_date": "2026-12-08"}, headers=first_headers
    )
    assert changed.status_code == 409
    assert "Retry-After" not in changed.headers
    assert changed.json() == {
        "detail": "Idempotency-Key already used with different preview inputs"
    }
    assert provider.calls == 1

    second = await client.post(URL, json=PAYLOAD, headers=second_headers)
    assert first.status_code == second.status_code == 200
    assert (
        first.json()["items"][0]["recipe_id"] != second.json()["items"][0]["recipe_id"]
    )
    assert provider.calls == 2


async def test_replay_checks_current_recipe_and_allergy_inputs(
    client, db_session, provider
):
    account, headers = await seed_account(db_session, "preview-key-recipe")
    headers["Idempotency-Key"] = IDEMPOTENCY_KEY
    original = await client.post(URL, json=PAYLOAD, headers=headers)
    assert original.status_code == 200

    await db_session.execute(
        update(Recipe)
        .where(Recipe.created_by_user_id == account)
        .values(total_calories=Decimal("220"))
    )
    await db_session.commit()
    changed = await client.post(URL, json=PAYLOAD, headers=headers)
    assert changed.status_code == 409

    db_session.add(UserNutritionProfile(user_id=account, allergies=["Soy"]))
    await db_session.commit()
    allergy = await client.post(URL, json=PAYLOAD, headers=headers)
    assert allergy.status_code == 422
    assert provider.calls == 1


async def test_provider_failure_releases_key_for_retry(client, db_session, provider):
    account, headers = await seed_account(db_session, "preview-key-failure")
    headers["Idempotency-Key"] = IDEMPOTENCY_KEY
    provider.failure = MealPlanProviderTimeout()

    failure = await client.post(URL, json=PAYLOAD, headers=headers)
    assert failure.status_code == 503
    assert (
        await db_session.get(
            AIMealPlanPreviewIdempotency,
            (account, sha256(IDEMPOTENCY_KEY.encode()).hexdigest()),
        )
        is None
    )

    provider.failure = None
    retry = await client.post(URL, json=PAYLOAD, headers=headers)
    assert retry.status_code == 200
    assert provider.calls == 2
    bucket = await db_session.get(AIMealPlanPreviewLimit, account)
    assert bucket.attempts == 2


async def test_completed_key_can_be_reused_after_expiry(client, db_session, provider):
    account, headers = await seed_account(db_session, "preview-key-expiry")
    headers["Idempotency-Key"] = IDEMPOTENCY_KEY
    first = await client.post(URL, json=PAYLOAD, headers=headers)
    assert first.status_code == 200

    await db_session.execute(
        update(AIMealPlanPreviewIdempotency)
        .where(AIMealPlanPreviewIdempotency.user_id == account)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()

    new_day = "2026-12-08"
    new_preview = await client.post(
        URL, json={**PAYLOAD, "planned_date": new_day}, headers=headers
    )
    assert new_preview.status_code == 200
    assert new_preview.json()["items"][0]["planned_date"] == new_day
    assert provider.calls == 2


async def test_expired_reservation_cannot_write_or_delete_replacement(db_session):
    account, _ = await seed_account(db_session, "preview-key-replacement")
    repository = AIMealPlanPreviewIdempotencyRepository(db_session)
    key_hash = sha256(IDEMPOTENCY_KEY.encode()).hexdigest()
    expired = PreviewReservation(account, key_hash, uuid.uuid4())
    current = PreviewReservation(account, key_hash, uuid.uuid4())

    async with db_session.begin():
        assert await repository.claim(expired, "a" * 64) is None
        await db_session.execute(
            update(AIMealPlanPreviewIdempotency)
            .where(AIMealPlanPreviewIdempotency.user_id == account)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    async with db_session.begin():
        assert await repository.claim(current, "b" * 64) is None
        assert not await repository.complete(expired, {"items": []})
        await repository.release(expired)

    claim = await db_session.get(AIMealPlanPreviewIdempotency, (account, key_hash))
    assert claim.reservation_id == current.id and claim.preview is None
