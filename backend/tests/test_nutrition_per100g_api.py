"""DB/API regressions: require separate authorization for destructive fixtures."""

from contextlib import contextmanager
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import event, func, select

from app.api.deps import get_recipe_generation_provider
from app.main import app
from app.models.ingredient import NutritionValue
from app.models.recipe import Recipe
from app.repositories.ingredients import IngredientsRepository
from app.repositories.pantry import PantryRepository
from app.schemas.ingredient import IngredientRead
from app.schemas.pantry import PantryItemRead
from app.services.gram_nutrition import NUTRIENTS, TOTALS
from tests.test_ai_recipe_save_api import (
    AI_RECIPE_SAVE_URL,
    INGREDIENTS_URL,
    PANTRY_URL,
    RECIPES_URL,
    create_authenticated_user,
    create_ingredient,
    save_payload,
)
from tests.test_meal_plan_summary_api import create_test_meal_plan, add_meal_plan_item


@contextmanager
def statements(engine):
    captured = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        captured.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        yield captured
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)


@pytest.mark.parametrize(
    "values,expected",
    [
        (
            {
                "calories": "100",
                "protein_g": "2",
                "carbs_g": "3",
                "fat_g": "4",
                "portion_g": "50",
            },
            ["200.00", "4.00", "6.00", "8.00"],
        ),
        ({"calories": "0"}, ["0.00"] * 4),
        ({"calories": "0.01", "portion_g": "999999.99"}, ["0.00"] * 4),
        (
            {**dict.fromkeys(NUTRIENTS, "999999.99"), "portion_g": "0.01"},
            ["9999999900.00"] * 4,
        ),
    ],
)
async def test_all_ingredient_and_pantry_responses_preserve_sources(
    client, async_session_maker, values, expected
):
    _, headers = await create_authenticated_user(client)
    created = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json={
            "name": "Projection contract",
            "extra_ignored": True,
            "nutrition_value": {**values, "per_100g": {"calories": "123.45"}},
        },
    )
    assert created.status_code == 201
    ingredient = created.json()
    ingredient_id = ingredient["id"]
    expected_nutrition = ingredient["nutrition_value"]
    assert expected_nutrition["per_100g"] == dict(zip(NUTRIENTS, expected, strict=True))
    for field in (*NUTRIENTS, "portion_g"):
        assert isinstance(expected_nutrition[field], str)
        assert Decimal(expected_nutrition[field]) == Decimal(
            values.get(field, "100" if field == "portion_g" else "0")
        )

    detail = await client.get(f"{INGREDIENTS_URL}/{ingredient_id}")
    listing = await client.get(INGREDIENTS_URL)
    patched = await client.patch(
        f"{INGREDIENTS_URL}/{ingredient_id}",
        headers=headers,
        json={"category": "Projection"},
    )
    assert detail.status_code == listing.status_code == patched.status_code == 200
    for response in (detail.json(), listing.json()[0], patched.json()):
        assert response["nutrition_value"] == expected_nutrition
    added = await client.post(
        PANTRY_URL,
        headers=headers,
        json={"ingredient_id": ingredient_id, "quantity_g": "125"},
    )
    assert added.status_code == 201
    pantry_id = added.json()["id"]
    listing = await client.get(PANTRY_URL, headers=headers)
    patched = await client.patch(
        f"{PANTRY_URL}/{pantry_id}", headers=headers, json={"quantity_g": "126"}
    )
    assert listing.status_code == patched.status_code == 200
    for response in (added.json(), listing.json()[0], patched.json()):
        assert response["ingredient"]["nutrition_value"] == expected_nutrition

    # A new session rules out an in-memory-only assertion after serialization.
    async with async_session_maker() as db:
        source = await db.scalar(
            select(NutritionValue).where(
                NutritionValue.ingredient_id == UUID(ingredient_id)
            )
        )
        assert str(source.id) == expected_nutrition["id"]
        for field in (*NUTRIENTS, "portion_g"):
            assert getattr(source, field) == Decimal(expected_nutrition[field])


@pytest.mark.parametrize("create_values", [{}, {"nutrition_value": None}])
async def test_missing_nutrition_and_patch_replacement_defaults(
    client, async_session_maker, create_values
):
    _, headers = await create_authenticated_user(client)
    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json={"name": "Missing nutrition", **create_values},
    )
    assert response.status_code == 201
    ingredient_id = response.json()["id"]
    url = f"{INGREDIENTS_URL}/{ingredient_id}"
    assert response.json()["nutrition_value"] is None
    assert (await client.get(url)).json()["nutrition_value"] is None
    assert (await client.get(INGREDIENTS_URL)).json()[0]["nutrition_value"] is None
    pantry = await client.post(
        PANTRY_URL,
        headers=headers,
        json={"ingredient_id": ingredient_id, "quantity_g": "1"},
    )
    assert pantry.status_code == 201
    pantry_id = pantry.json()["id"]
    assert pantry.json()["ingredient"]["nutrition_value"] is None
    for payload in ({"category": "unchanged"}, {"nutrition_value": None}):
        response = await client.patch(url, headers=headers, json=payload)
        assert response.status_code == 200
        assert response.json()["nutrition_value"] is None
    pantry_list = await client.get(PANTRY_URL, headers=headers)
    pantry_patch = await client.patch(
        f"{PANTRY_URL}/{pantry_id}", headers=headers, json={"quantity_g": "2"}
    )
    assert pantry_list.status_code == pantry_patch.status_code == 200
    assert pantry_list.json()[0]["ingredient"]["nutrition_value"] is None
    assert pantry_patch.json()["ingredient"]["nutrition_value"] is None
    async with async_session_maker() as db:
        assert await db.scalar(select(func.count()).select_from(NutritionValue)) == 0

    response = await client.patch(
        url,
        headers=headers,
        json={
            "nutrition_value": {
                "calories": "100",
                "protein_g": "2",
                "carbs_g": "3",
                "fat_g": "4",
                "portion_g": "50",
                "per_100g": {"calories": "999"},
            }
        },
    )
    assert response.status_code == 200
    original = response.json()["nutrition_value"]
    assert original["per_100g"]["calories"] == "200.00"
    for payload in ({"category": "unchanged"}, {"nutrition_value": None}):
        response = await client.patch(url, headers=headers, json=payload)
        assert response.status_code == 200
        assert response.json()["nutrition_value"] == original
    response = await client.patch(
        url,
        headers=headers,
        json={
            "nutrition_value": {
                "calories": "7",
                "per_100g": "ignored",
            }
        },
    )
    assert response.status_code == 200
    replaced = response.json()["nutrition_value"]
    assert replaced["id"] == original["id"]
    assert replaced["per_100g"] == {
        "calories": "7.00",
        "protein_g": "0.00",
        "carbs_g": "0.00",
        "fat_g": "0.00",
    }
    async with async_session_maker() as db:
        source = await db.scalar(select(NutritionValue))
        assert source.calories == 7 and source.portion_g == 100
        assert source.protein_g == source.carbs_g == source.fat_g == 0


@pytest.mark.parametrize("count", [1, 4])
async def test_eager_reads_have_constant_queries_and_serialization_never_queries(
    client, test_engine, async_session_maker, count
):
    user, headers = await create_authenticated_user(client)
    for index in range(count):
        ingredient_id = await create_ingredient(
            client, headers=headers, name=f"Query count {index}", portion_g="50"
        )
        response = await client.post(
            PANTRY_URL,
            headers=headers,
            json={"ingredient_id": ingredient_id, "quantity_g": "1"},
        )
        assert response.status_code == 201

    async with async_session_maker() as db:
        with statements(test_engine) as queries:
            ingredients = await IngredientsRepository(db).list()
        assert len(queries) == 2  # ingredient batch + nutrition batch
        with statements(test_engine) as queries:
            pantry = await PantryRepository(db).list_user_pantry(UUID(user["id"]))
        assert len(queries) == 3  # pantry + ingredient batch + nutrition batch
        with statements(test_engine) as queries:
            for row in ingredients:
                assert (
                    IngredientRead.model_validate(row).model_dump(mode="json")[
                        "nutrition_value"
                    ]["per_100g"]["calories"]
                    == "330.00"
                )
            for row in pantry:
                assert (
                    PantryItemRead.model_validate(row).model_dump(mode="json")[
                        "ingredient"
                    ]["nutrition_value"]["per_100g"]["calories"]
                    == "330.00"
                )
        assert queries == []
        assert not db.dirty and not db.new and not db.deleted
        # Detached serialization also fails if a new lazy relationship is used.
        db.expunge_all()
        assert (
            len(
                [
                    IngredientRead.model_validate(row).model_dump_json()
                    for row in ingredients
                ]
            )
            == count
        )
        assert (
            len(
                [PantryItemRead.model_validate(row).model_dump_json() for row in pantry]
            )
            == count
        )

    with statements(test_engine) as queries:
        response = await client.get(INGREDIENTS_URL)
    assert response.status_code == 200 and len(response.json()) == count
    assert len(queries) == 2
    with statements(test_engine) as queries:
        response = await client.get(PANTRY_URL, headers=headers)
    assert response.status_code == 200 and len(response.json()) == count
    assert len(queries) == 5  # auth + ensure-user + three batch reads


@pytest.mark.parametrize(
    "value,portion,quantity,projection,total",
    [("100", "50", "125", "200.00", "250.00"), ("1", "200.01", "1", "0.50", "0.00")],
)
async def test_aggregates_ai_save_and_ownership_use_original_values(
    client,
    async_session_maker,
    monkeypatch,
    value,
    portion,
    quantity,
    projection,
    total,
):
    def no_provider():
        raise AssertionError("AI save must not resolve the provider")

    monkeypatch.setitem(
        app.dependency_overrides, get_recipe_generation_provider, no_provider
    )
    user, headers = await create_authenticated_user(client)
    _, other_headers = await create_authenticated_user(client)
    ingredient_id = await create_ingredient(
        client, headers=headers, portion_g=portion, **dict.fromkeys(NUTRIENTS, value)
    )
    detail = await client.get(f"{INGREDIENTS_URL}/{ingredient_id}")
    assert detail.json()["nutrition_value"]["per_100g"] == dict.fromkeys(
        NUTRIENTS, projection
    )
    pantry = await client.post(
        PANTRY_URL,
        headers=headers,
        json={"ingredient_id": ingredient_id, "quantity_g": quantity},
    )
    assert pantry.status_code == 201
    summary = await client.get(f"{PANTRY_URL}/summary", headers=headers)
    assert summary.status_code == 200
    for field in TOTALS:
        if quantity == "125":
            assert Decimal(summary.json()[field]) == 250
        else:
            assert Decimal("0") < Decimal(summary.json()[field]) < Decimal("0.005")
    assert (await client.get(PANTRY_URL, headers=other_headers)).json() == []
    assert (
        await client.patch(
            f"{PANTRY_URL}/{pantry.json()['id']}",
            headers=other_headers,
            json={"quantity_g": "9"},
        )
    ).status_code == 404

    plan = await create_test_meal_plan(client, headers=headers)
    recipe_ids = []
    for endpoint in (RECIPES_URL, AI_RECIPE_SAVE_URL):
        payload = save_payload(
            ingredient_id,
            ingredients=[
                {
                    "ingredient_id": ingredient_id,
                    "quantity_g": quantity,
                }
            ],
        )
        if endpoint == RECIPES_URL:
            payload["instructions"] = "Mix"
        response = await client.post(endpoint, headers=headers, json=payload)
        assert response.status_code == 201
        recipe = response.json()
        recipe_ids.append(UUID(recipe["id"]))
        assert recipe["created_by_user_id"] == user["id"]
        assert all(recipe[field] == total for field in TOTALS)
        assert (
            await client.get(f"{RECIPES_URL}/{recipe['id']}", headers=other_headers)
        ).status_code == 404
        await add_meal_plan_item(
            client,
            headers=headers,
            meal_plan_id=plan["id"],
            recipe_id=recipe["id"],
            planned_date="2026-05-18",
            meal_type="breakfast" if endpoint == RECIPES_URL else "lunch",
        )
    summary = await client.get(
        f"/api/v1/meal-plans/{plan['id']}/summary", headers=headers
    )
    assert summary.status_code == 200
    assert all(Decimal(summary.json()[field]) == Decimal(total) * 2 for field in TOTALS)
    assert (
        await client.get(
            f"/api/v1/meal-plans/{plan['id']}/summary", headers=other_headers
        )
    ).status_code == 404
    async with async_session_maker() as db:
        source = await db.scalar(select(NutritionValue))
        assert source.portion_g == Decimal(portion)
        assert all(getattr(source, field) == Decimal(value) for field in NUTRIENTS)
        recipes = (
            await db.scalars(select(Recipe).where(Recipe.id.in_(recipe_ids)))
        ).all()
        assert len(recipes) == 2
        assert all(
            getattr(recipe, field) == Decimal(total)
            for recipe in recipes
            for field in TOTALS
        )
