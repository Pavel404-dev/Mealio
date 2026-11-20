import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

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
from app.models.ai_meal_plan_preview_limit import AIMealPlanPreviewLimit
from app.models.ingredient import Ingredient, NutritionValue
from app.models.recipe import Recipe, RecipeIngredient
from app.models.user import User

URL = "/api/v2/meal-plans/ai/generate-preview"
PAYLOAD = {"planned_date": "2026-12-07", "locale": "en", "meal_types": ["lunch"]}


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
