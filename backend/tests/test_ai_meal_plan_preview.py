import asyncio
import json
import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.dialects import postgresql

from app.api.deps import get_current_user, get_meal_plan_generation_provider
from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.meal_plan_generation import (
    MealPlanProviderResult,
    MealPlanProviderTimeout,
    MealPlanProviderTransientError,
    MealPlanProviderUnavailable,
)
from app.main import app
from app.repositories.ai_meal_plan_preview_limits import (
    AIMealPlanPreviewLimitsRepository,
)
from app.schemas.user_nutrition_profile import UserNutritionProfileRead

URL = "/api/v2/meal-plans/ai/generate-preview"
REQUEST = {
    "planned_date": "2026-12-07",
    "locale": "ru",
    "meal_types": ["lunch", "dinner"],
}


def recipe(
    *,
    meal_type=None,
    name="Rice",
    servings=4,
    calories="330",
    macros=("62", "0", "7.20"),
    diet_type="balanced",
    complete=True,
):
    value = SimpleNamespace(
        portion_g=Decimal("100"),
        calories=Decimal("165"),
        protein_g=Decimal("31"),
        carbs_g=Decimal("0"),
        fat_g=Decimal("3.6"),
    )
    return SimpleNamespace(
        id=uuid4(),
        title="private recipe name",
        servings=servings,
        meal_type=meal_type,
        diet_type=diet_type,
        total_calories=Decimal(calories),
        total_protein_g=Decimal(macros[0]),
        total_carbs_g=Decimal(macros[1]),
        total_fat_g=Decimal(macros[2]),
        recipe_ingredients=[
            SimpleNamespace(
                quantity_g=Decimal("200"),
                ingredient=SimpleNamespace(
                    name=name, nutrition_value=value if complete else None
                ),
            )
        ],
    )


def selection(slot="lunch", candidate=1, hundredths=100, **extra):
    return {
        "meal_type": slot,
        "candidate_number": candidate,
        "serving_hundredths": hundredths,
        **extra,
    }


class PreviewSession:
    def __init__(self, user_id):
        self.user_id = user_id
        self.profile = UserNutritionProfileRead(
            daily_calories_target=1400,
            daily_protein_target_g=90,
            liked_ingredients=["Rice"],
            disliked_ingredients=["Exclude me"],
        )
        self.recipes = [recipe(meal_type="lunch"), recipe(meal_type="dinner")]
        self.reads = []
        self.reservations = []
        self.retry_after = None
        self.released = False

    async def execute(self, stmt):
        query = stmt.compile(dialect=postgresql.dialect())
        sql = str(query)
        self.reads.append(sql)
        assert sql.startswith("SELECT ")
        if len(self.reads) == 1:
            assert query.params == {"user_id_1": self.user_id}
            return SimpleNamespace(scalar_one_or_none=lambda: self.profile)
        assert len(self.reads) == 2
        assert "WHERE recipes.created_by_user_id = " in sql
        assert query.params == {"created_by_user_id_1": self.user_id, "param_1": 50}
        return SimpleNamespace(
            unique=lambda: SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: self.recipes),
            )
        )

    async def rollback(self):
        self.released = True

    @asynccontextmanager
    async def begin(self):
        assert self.released
        self.released = False
        try:
            yield
        finally:
            self.released = True


class FakeProvider:
    model = "planner-test"

    def __init__(self, db):
        self.db = db
        self.calls = []
        self.result = {"items": [selection("dinner", 2, 50), selection()]}
        self.failures = []
        self.estimated_cost_usd = None

    async def select_meals(self, *, context_json):
        assert self.db.released
        self.calls.append(json.loads(context_json))
        if self.failures:
            raise self.failures.pop(0)
        return MealPlanProviderResult(
            self.result,
            input_tokens=410,
            output_tokens=34,
            estimated_cost_usd=self.estimated_cost_usd,
        )


@pytest.fixture
async def preview(monkeypatch):
    user_id = uuid4()
    db = PreviewSession(user_id)
    provider = FakeProvider(db)

    async def reserve(repository, *, user_id, limit, window_seconds):
        assert repository.db is db and not db.released
        assert user_id == db.user_id
        db.reservations.append(user_id)
        return db.retry_after

    monkeypatch.setattr(AIMealPlanPreviewLimitsRepository, "reserve", reserve)
    monkeypatch.setitem(
        app.dependency_overrides, get_current_user, lambda: SimpleNamespace(id=user_id)
    )
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: db)
    monkeypatch.setitem(
        app.dependency_overrides, get_meal_plan_generation_provider, lambda: provider
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, db, provider


@pytest.mark.parametrize(
    ("estimated_cost", "logged_cost"),
    [(Decimal("0.000058"), "0.000058"), (None, "unknown"), (Decimal("0"), "0")],
)
async def test_preview_validates_owner_snapshot_and_recalculates_in_request_order(
    preview, caplog, estimated_cost, logged_cost
):
    client, db, provider = preview
    provider.estimated_cost_usd = estimated_cost
    db.recipes.extend(
        [
            recipe(name="Exclude me"),
            recipe(complete=False),
            recipe(calories="NaN"),
        ]
    )
    with caplog.at_level(logging.INFO, logger="uvicorn.error.mealio.ai_meal_plan"):
        response = await client.post(URL, json=REQUEST)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [
        (row["recipe_id"], row["meal_type"], Decimal(row["planned_servings"]))
        for row in body["items"]
    ] == [
        (str(db.recipes[0].id), "lunch", Decimal("1")),
        (str(db.recipes[1].id), "dinner", Decimal("0.5")),
    ]
    assert {row["planned_date"] for row in body["items"]} == {REQUEST["planned_date"]}
    assert body["nutrition"] == {
        "total_calories": "123.75",
        "total_protein_g": "23.25",
        "total_carbs_g": "0.00",
        "total_fat_g": "2.70",
    }
    [context] = provider.calls
    assert context["locale"] == "ru" and context["meal_types"] == REQUEST["meal_types"]
    assert context["preferences"]["daily_targets"]["calories"] == 1400
    assert context["preferences"]["allergies"] == []
    assert [
        (row["candidate_number"], row["allowed_slots"], row["liked_ingredient_count"])
        for row in context["candidates"]
    ] == [
        (1, ["lunch"], 1),
        (2, ["dinner"], 1),
    ]
    for private in (
        str(db.user_id),
        *(str(r.id) for r in db.recipes),
        "private recipe name",
        "Exclude me",
    ):
        assert private not in json.dumps(context) and private not in caplog.text
    assert (
        "outcome=success" in caplog.text
        and f"input_tokens=410 output_tokens=34 cost_usd={logged_cost}\n" in caplog.text
    )


async def test_preview_rounds_once_for_the_entire_day(preview):
    client, db, provider = preview
    db.recipes = [recipe(servings=3, calories="1.00")]
    provider.result = {"items": [selection("lunch"), selection("dinner")]}
    response = await client.post(URL, json=REQUEST)
    assert response.status_code == 200
    assert response.json()["nutrition"]["total_calories"] == "0.67"


async def test_partial_day_preview_only_offers_recipes_matching_diet(preview):
    client, db, provider = preview
    db.profile.diet_type = "vegan"
    matching_lunch = recipe(meal_type="lunch", diet_type=" VEGAN ")
    db.recipes = [
        recipe(meal_type="lunch", diet_type="vegetarian"),
        recipe(meal_type="lunch", diet_type=None),
        matching_lunch,
    ]
    provider.result = {"items": [selection()]}

    response = await client.post(URL, json={**REQUEST, "meal_types": ["lunch"]})

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["recipe_id"] == str(matching_lunch.id)
    [context] = provider.calls
    [candidate] = context["candidates"]
    assert candidate["diet_type"] == " VEGAN "


@pytest.mark.parametrize("diet_type", [None, " ", " BALANCED "])
async def test_unrestricted_diet_allows_labeled_and_unlabeled_recipes(
    preview, diet_type
):
    client, db, provider = preview
    db.profile = UserNutritionProfileRead(diet_type=diet_type)
    db.recipes = [
        recipe(meal_type="lunch", diet_type="vegan"),
        recipe(meal_type="dinner", diet_type=None),
    ]

    response = await client.post(URL, json=REQUEST)

    assert response.status_code == 200, response.text
    assert [item["recipe_id"] for item in response.json()["items"]] == [
        str(recipe.id) for recipe in db.recipes
    ]
    [context] = provider.calls
    assert [candidate["diet_type"] for candidate in context["candidates"]] == [
        "vegan",
        None,
    ]


async def test_full_day_preview_fits_the_recorded_staging_targets(preview):
    client, db, provider = preview
    db.profile = UserNutritionProfileRead(
        daily_calories_target=1800,
        daily_protein_target_g=105,
        daily_carbs_target_g=210,
        daily_fat_target_g=60,
        liked_ingredients=["Favorite lunch"],
        disliked_ingredients=["Exclude me"],
    )
    db.recipes = [
        recipe(
            meal_type="breakfast",
            servings=2,
            calories="792",
            macros=("40", "104", "24"),
        ),
        recipe(
            meal_type="breakfast",
            servings=2,
            calories="904.20",
            macros=("77.40", "88.40", "25.44"),
        ),
        recipe(
            meal_type="lunch",
            name="Favorite lunch",
            calories="2900",
            macros=("180", "320", "100"),
        ),
        recipe(meal_type="lunch", calories="2512", macros=("136", "312", "80")),
        recipe(
            meal_type="dinner", servings=3, calories="1740", macros=("105", "195", "60")
        ),
        recipe(
            meal_type="dinner",
            servings=3,
            calories="1788",
            macros=("158.40", "156", "56.64"),
        ),
        recipe(
            meal_type="lunch",
            name="Exclude me",
            calories="2900",
            macros=("180", "320", "100"),
        ),
    ]
    # The recorded model chose the alternative breakfast and lunch at one serving each.
    provider.result = {
        "items": [
            selection("dinner", 5),
            selection("lunch", 4),
            selection("breakfast", 2),
        ]
    }
    response = await client.post(
        URL, json={**REQUEST, "meal_types": ["breakfast", "lunch", "dinner"]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [
        (item["meal_type"], item["recipe_id"], Decimal(item["planned_servings"]))
        for item in body["items"]
    ] == [
        ("breakfast", str(db.recipes[0].id), Decimal("1.25")),
        ("lunch", str(db.recipes[2].id), Decimal("1")),
        ("dinner", str(db.recipes[4].id), Decimal("1")),
    ]
    assert body["nutrition"] == {
        "total_calories": "1800.00",
        "total_protein_g": "105.00",
        "total_carbs_g": "210.00",
        "total_fat_g": "60.00",
    }
    fit = body["target_fit"]
    assert fit["status"] == "within_tolerance" and fit["reason"] is None
    assert fit["tolerance_percent"] == 10
    assert fit["metrics"] == {
        field: {
            "target": target,
            "actual": body["nutrition"][field],
            "delta": "0.00",
            "delta_percent": "0.00",
            "within_tolerance": True,
        }
        for field, target in zip(body["nutrition"], (1800, 105, 210, 60), strict=True)
    }
    [context] = provider.calls
    assert len(context["candidates"]) == 6


@pytest.mark.parametrize("preferred_meals", [3, None])
async def test_lunch_preview_preserves_provider_portion_for_a_partial_day(
    preview, preferred_meals
):
    client, db, provider = preview
    db.profile = UserNutritionProfileRead(
        daily_calories_target=1800, preferred_meals_per_day=preferred_meals
    )
    db.recipes = [
        recipe(meal_type="lunch", servings=1, calories="500"),
        recipe(meal_type="lunch", servings=1, calories="1800"),
    ]
    provider.result = {"items": [selection(hundredths=113)]}
    response = await client.post(URL, json={**REQUEST, "meal_types": ["lunch"]})
    assert response.status_code == 200, response.text
    body = response.json()
    [lunch] = body["items"]
    assert lunch["recipe_id"] == str(db.recipes[0].id)
    assert Decimal(lunch["planned_servings"]) == Decimal("1.13")
    assert body["nutrition"]["total_calories"] == "565.00"
    fit = body["target_fit"]
    assert fit["status"] == "not_evaluated"
    assert fit["reason"] == (
        "partial_day" if preferred_meals == 3 else "unknown_meal_count"
    )
    assert fit["metrics"]["total_calories"] == {
        "target": 1800,
        "actual": "565.00",
        "delta": "-1235.00",
        "delta_percent": "-68.61",
        "within_tolerance": None,
    }
    assert all(metric["within_tolerance"] is None for metric in fit["metrics"].values())
    assert len(provider.calls) == 1


async def test_unreachable_carb_target_does_not_prevent_closer_calories(preview):
    client, db, provider = preview
    db.profile = UserNutritionProfileRead(
        daily_calories_target=250, daily_carbs_target_g=10, preferred_meals_per_day=2
    )
    db.recipes = [
        recipe(meal_type=slot, servings=1, calories="100")
        for slot in REQUEST["meal_types"]
    ]
    provider.result = {"items": [selection("lunch"), selection("dinner", 2)]}
    response = await client.post(URL, json=REQUEST)
    assert response.status_code == 200, response.text
    assert response.json()["nutrition"] == {
        "total_calories": "250.00",
        "total_protein_g": "155.00",
        "total_carbs_g": "0.00",
        "total_fat_g": "18.00",
    }
    fit = response.json()["target_fit"]
    assert fit["status"] == "outside_tolerance" and fit["reason"] is None
    assert fit["metrics"]["total_calories"]["within_tolerance"] is True
    assert fit["metrics"]["total_carbs_g"] == {
        "target": 10,
        "actual": "0.00",
        "delta": "-10.00",
        "delta_percent": "-100.00",
        "within_tolerance": False,
    }
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    ("alternative_diet", "expected_lunch"), [(" VEGAN ", 2), ("balanced", 0)]
)
async def test_equal_nutrition_favors_liked_recipe_with_preferred_diet(
    preview, alternative_diet, expected_lunch
):
    client, db, provider = preview
    db.profile = UserNutritionProfileRead(
        daily_calories_target=200,
        preferred_meals_per_day=2,
        diet_type="vegan",
        liked_ingredients=["Favorite"],
    )
    db.recipes = [
        recipe(meal_type="lunch", calories="400", diet_type="vegan"),
        recipe(meal_type="dinner", calories="400", diet_type="vegan"),
        recipe(
            meal_type="lunch",
            name="Favorite",
            calories="400",
            diet_type=alternative_diet,
        ),
    ]
    provider.result = {"items": [selection("lunch"), selection("dinner", 2)]}
    response = await client.post(URL, json=REQUEST)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"][0]["recipe_id"] == str(db.recipes[expected_lunch].id)
    assert body["nutrition"]["total_calories"] == "200.00"
    [context] = provider.calls
    assert all(
        candidate["diet_type"].strip().casefold() == "vegan"
        for candidate in context["candidates"]
    )


@pytest.mark.parametrize("calories_target", [180, None])
async def test_keeps_provider_portions_when_plan_fits_or_targets_are_absent(
    preview, calories_target
):
    client, db, provider = preview
    db.profile = UserNutritionProfileRead(
        daily_calories_target=calories_target, preferred_meals_per_day=2
    )
    db.recipes = [
        recipe(meal_type=slot, servings=1, calories="100")
        for slot in REQUEST["meal_types"]
    ]
    provider.result = {
        "items": [selection("lunch", hundredths=113), selection("dinner", 2, 67)]
    }
    response = await client.post(URL, json=REQUEST)
    assert response.status_code == 200, response.text
    assert [Decimal(item["planned_servings"]) for item in response.json()["items"]] == [
        Decimal("1.13"),
        Decimal("0.67"),
    ]
    fit = response.json()["target_fit"]
    assert fit["status"] == (
        "within_tolerance" if calories_target is not None else "not_evaluated"
    )
    assert fit["reason"] == (None if calories_target is not None else "no_targets")
    for field in ("total_protein_g", "total_carbs_g", "total_fat_g"):
        assert fit["metrics"][field] == {
            "target": None,
            "actual": response.json()["nutrition"][field],
            "delta": None,
            "delta_percent": None,
            "within_tolerance": None,
        }


@pytest.mark.parametrize(
    "field", ("total_calories", "total_protein_g", "total_carbs_g", "total_fat_g")
)
@pytest.mark.parametrize(
    ("actual", "delta", "within"),
    [
        ("90.00", "-10.00", True),
        ("110.00", "10.00", True),
        ("89.99", "-10.01", False),
        ("110.01", "10.01", False),
    ],
)
async def test_target_fit_includes_tolerance_boundaries_for_every_nutrient(
    preview, field, actual, delta, within
):
    client, db, provider = preview
    db.profile = UserNutritionProfileRead(
        daily_calories_target=100,
        daily_protein_target_g=100,
        daily_carbs_target_g=100,
        daily_fat_target_g=100,
        preferred_meals_per_day=1,
    )
    candidate = recipe(servings=1, calories="100", macros=("100", "100", "100"))
    setattr(candidate, field, Decimal(actual))
    db.recipes = [candidate]
    provider.result = {"items": [selection()]}

    response = await client.post(URL, json={**REQUEST, "meal_types": ["lunch"]})

    assert response.status_code == 200, response.text
    body = response.json()
    fit = body["target_fit"]
    assert fit["status"] == ("within_tolerance" if within else "outside_tolerance")
    assert fit["reason"] is None and fit["tolerance_percent"] == 10
    assert fit["metrics"][field] == {
        "target": 100,
        "actual": actual,
        "delta": delta,
        "delta_percent": delta,
        "within_tolerance": within,
    }
    assert body["nutrition"][field] == actual
    assert len(provider.calls) == 1 and len(db.reads) == 2 and db.released


async def test_rounded_percentage_does_not_hide_an_outside_target(preview):
    client, db, provider = preview
    db.profile = UserNutritionProfileRead(
        daily_calories_target=1000, preferred_meals_per_day=1
    )
    db.recipes = [recipe(servings=1, calories="1100.01")]
    provider.result = {"items": [selection()]}

    response = await client.post(URL, json={**REQUEST, "meal_types": ["lunch"]})

    assert response.status_code == 200, response.text
    fit = response.json()["target_fit"]
    assert fit["status"] == "outside_tolerance"
    assert fit["metrics"]["total_calories"] == {
        "target": 1000,
        "actual": "1100.01",
        "delta": "100.01",
        "delta_percent": "10.00",
        "within_tolerance": False,
    }


async def test_only_configured_target_is_evaluated(preview):
    client, db, provider = preview
    db.profile = UserNutritionProfileRead(
        daily_protein_target_g=62, preferred_meals_per_day=1
    )
    db.recipes = [recipe(servings=1)]
    provider.result = {"items": [selection()]}

    response = await client.post(URL, json={**REQUEST, "meal_types": ["lunch"]})

    assert response.status_code == 200, response.text
    fit = response.json()["target_fit"]
    assert fit["status"] == "within_tolerance"
    assert fit["metrics"]["total_protein_g"]["within_tolerance"] is True
    for field in ("total_calories", "total_carbs_g", "total_fat_g"):
        assert fit["metrics"][field] == {
            "target": None,
            "actual": response.json()["nutrition"][field],
            "delta": None,
            "delta_percent": None,
            "within_tolerance": None,
        }


async def test_missing_profile_reports_actuals_without_fabricating_targets(preview):
    client, db, provider = preview
    db.profile = None

    response = await client.post(URL, json=REQUEST)

    assert response.status_code == 200, response.text
    fit = response.json()["target_fit"]
    assert fit["status"] == "not_evaluated" and fit["reason"] == "no_targets"
    assert set(fit["metrics"]) == set(response.json()["nutrition"])
    for field, metric in fit["metrics"].items():
        assert metric == {
            "target": None,
            "actual": response.json()["nutrition"][field],
            "delta": None,
            "delta_percent": None,
            "within_tolerance": None,
        }
    assert len(provider.calls) == 1


@pytest.mark.parametrize(
    "items",
    [
        [selection()],
        [selection(), selection(hundredths=50)],
        [selection(), selection("breakfast", 2)],
        [selection(candidate=3), selection("dinner", 2)],
        [selection(candidate=2), selection("dinner", 2)],
        [selection(hundredths=0), selection("dinner", 2)],
        [selection(hundredths=1201), selection("dinner", 2)],
        [selection(hundredths=True), selection("dinner", 2)],
        [selection(hundredths="100"), selection("dinner", 2)],
        [selection(total_calories="82.50"), selection("dinner", 2)],
        [selection(ingredient_ids=["invented"]), selection("dinner", 2)],
    ],
)
async def test_invalid_model_output_is_rejected_whole(preview, items):
    client, db, provider = preview
    db.profile.preferred_meals_per_day = len(REQUEST["meal_types"])
    provider.result = {"items": items}
    response = await client.post(URL, json=REQUEST)
    assert response.status_code == 502
    assert response.json() == {"detail": "AI provider returned an invalid meal plan"}
    assert db.released and len(db.reads) == 2 and len(provider.calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"locale": "xx"},
        {"meal_types": []},
        {"meal_types": ["Lunch", " lunch "]},
        {"allergies": []},
        {"planned_date": "2026-02-30"},
    ],
)
async def test_bad_request_stops_before_database_and_provider(preview, change):
    client, db, provider = preview
    response = await client.post(URL, json={**REQUEST, **change})
    assert response.status_code == 422
    assert not db.reads and not provider.calls


async def test_declared_allergies_stop_before_candidates_or_provider(preview):
    client, db, provider = preview
    db.profile.allergies = ["Test allergy"]
    response = await client.post(URL, json=REQUEST)
    assert response.status_code == 422 and "allergies" in response.json()["detail"]
    assert len(db.reads) == 1 and not provider.calls
    assert not db.reservations


async def test_missing_eligible_slot_stops_before_provider(preview):
    client, db, provider = preview
    db.recipes = [recipe(meal_type="lunch"), recipe(meal_type="dinner", complete=False)]
    response = await client.post(URL, json=REQUEST)
    assert response.status_code == 422
    assert not provider.calls
    assert not db.reservations


@pytest.mark.parametrize("dinner_diet", ["vegetarian", None])
async def test_missing_diet_match_for_slot_stops_before_provider(preview, dinner_diet):
    client, db, provider = preview
    db.profile.diet_type = "vegan"
    db.recipes = [
        recipe(meal_type="lunch", diet_type="vegan"),
        recipe(meal_type="dinner", diet_type=dinner_diet),
    ]

    response = await client.post(URL, json=REQUEST)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Not enough eligible saved recipes for the requested meal slots"
    }
    assert not provider.calls
    assert not db.reservations


async def test_rate_limit_returns_retry_after_before_provider(preview):
    client, db, provider = preview
    db.retry_after = 17

    response = await client.post(URL, json=REQUEST)

    assert response.status_code == 429
    assert response.json() == {"detail": "AI meal plan preview rate limit exceeded"}
    assert response.headers["Retry-After"] == "17"
    assert db.reservations == [db.user_id]
    assert db.released and not provider.calls


@pytest.mark.parametrize(
    "error,detail",
    [
        (MealPlanProviderTimeout, "AI meal plan preview timed out"),
        (
            MealPlanProviderUnavailable,
            "AI meal plan preview is temporarily unavailable",
        ),
    ],
)
async def test_provider_errors_are_generic_and_count_as_preview_attempts(
    preview, caplog, error, detail
):
    client, db, provider = preview
    provider.failures.append(error("private provider response"))
    with caplog.at_level(logging.INFO, logger="uvicorn.error.mealio.ai_meal_plan"):
        response = await client.post(URL, json=REQUEST)
    assert response.status_code == 503 and response.json() == {"detail": detail}
    assert db.released and len(db.reads) == 2
    assert db.reservations == [db.user_id]
    assert "input_tokens=None output_tokens=None cost_usd=unknown" in caplog.text
    assert "private provider response" not in caplog.text


@pytest.mark.parametrize(
    ("failed_calls", "status", "last_outcome"),
    [(1, 200, "success"), (2, 503, "unavailable")],
)
async def test_transient_provider_failure_retries_once(
    preview, caplog, failed_calls, status, last_outcome
):
    client, db, provider = preview
    provider.failures = [
        MealPlanProviderTransientError("private provider response")
        for _ in range(failed_calls)
    ]

    with caplog.at_level(logging.INFO, logger="uvicorn.error.mealio.ai_meal_plan"):
        response = await client.post(URL, json=REQUEST)

    assert response.status_code == status
    if status == 503:
        assert response.json() == {
            "detail": "AI meal plan preview is temporarily unavailable"
        }
    assert len(provider.calls) == 2 and provider.calls[0] == provider.calls[1]
    assert db.reservations == [db.user_id, db.user_id]
    assert db.released and len(db.reads) == 2
    attempt_logs = [
        record.getMessage()
        for record in caplog.records
        if record.name == "uvicorn.error.mealio.ai_meal_plan"
    ]
    assert len(attempt_logs) == 2
    assert "outcome=unavailable" in attempt_logs[0]
    assert f"outcome={last_outcome}" in attempt_logs[1]
    assert "private provider response" not in caplog.text


@pytest.mark.parametrize(("first_elapsed", "expected_calls"), [(6, 2), (11, 1)])
async def test_retry_shares_the_original_deadline(
    preview, monkeypatch, first_elapsed, expected_calls
):
    client, db, provider = preview
    monkeypatch.setattr(get_settings(), "ai_request_timeout_seconds", 10)
    loop = asyncio.get_running_loop()
    real_time = loop.time
    elapsed = 0
    monkeypatch.setattr(loop, "time", lambda: real_time() + elapsed)

    async def select_meals(*, context_json):
        nonlocal elapsed
        assert db.released
        provider.calls.append(context_json)
        if len(provider.calls) == 1:
            elapsed += first_elapsed
            raise MealPlanProviderTransientError
        elapsed += 5
        await asyncio.sleep(0.01)
        return MealPlanProviderResult(provider.result)

    monkeypatch.setattr(provider, "select_meals", select_meals)
    response = await client.post(URL, json=REQUEST)

    assert response.status_code == 503
    assert response.json() == {"detail": "AI meal plan preview timed out"}
    assert len(provider.calls) == expected_calls
    assert db.reservations == [db.user_id] * expected_calls


@pytest.mark.parametrize("key", ["", "two keys", "two,keys", "x" * 129])
async def test_invalid_idempotency_key_is_rejected_before_preview(preview, key):
    client, db, provider = preview
    response = await client.post(URL, json=REQUEST, headers={"Idempotency-Key": key})

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid Idempotency-Key"}
    assert not db.reads and not db.reservations and not provider.calls


async def test_authentication_precedes_provider_configuration():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(URL, json=REQUEST)
    assert response.status_code == 401


async def test_recipe_model_setting_alone_does_not_enable_plan_generation(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides, get_current_user, lambda: SimpleNamespace(id=uuid4())
    )
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: object())
    monkeypatch.setattr(
        "app.api.deps.get_settings",
        lambda: SimpleNamespace(
            openai_api_key=SecretStr("test-key"),
            openai_model="recipe-model",
            openai_meal_plan_api_key=None,
            openai_meal_plan_model=None,
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(URL, json=REQUEST)
    assert response.status_code == 503
    assert response.json() == {"detail": "AI meal plan preview is not configured"}
