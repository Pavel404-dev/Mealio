import json
import logging
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.dialects import postgresql

from app.api.deps import get_current_user, get_meal_plan_generation_provider
from app.db.session import get_db
from app.integrations.meal_plan_generation import (
    MealPlanProviderResult,
    MealPlanProviderTimeout,
    MealPlanProviderUnavailable,
)
from app.main import app
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


class ReadOnlySession:
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


class FakeProvider:
    model = "planner-test"

    def __init__(self, db):
        self.db = db
        self.calls = []
        self.result = {"items": [selection("dinner", 2, 50), selection()]}
        self.failure = None
        self.estimated_cost_usd = None

    async def select_meals(self, *, context_json):
        assert self.db.released
        self.calls.append(json.loads(context_json))
        if self.failure:
            raise self.failure
        return MealPlanProviderResult(
            self.result,
            input_tokens=410,
            output_tokens=34,
            estimated_cost_usd=self.estimated_cost_usd,
        )


@pytest.fixture
async def preview(monkeypatch):
    user_id = uuid4()
    db = ReadOnlySession(user_id)
    provider = FakeProvider(db)
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


async def test_missing_eligible_slot_stops_before_provider(preview):
    client, db, provider = preview
    db.recipes = [recipe(meal_type="lunch"), recipe(meal_type="dinner", complete=False)]
    response = await client.post(URL, json=REQUEST)
    assert response.status_code == 422
    assert not provider.calls


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
async def test_provider_errors_are_generic_and_preview_reads_only(
    preview, caplog, error, detail
):
    client, db, provider = preview
    provider.failure = error("private provider response")
    with caplog.at_level(logging.INFO, logger="uvicorn.error.mealio.ai_meal_plan"):
        response = await client.post(URL, json=REQUEST)
    assert response.status_code == 503 and response.json() == {"detail": detail}
    assert db.released and len(db.reads) == 2
    assert "input_tokens=None output_tokens=None cost_usd=unknown" in caplog.text
    assert "private provider response" not in caplog.text


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
