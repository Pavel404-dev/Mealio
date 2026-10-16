"""F3 HTTP and fresh-session witnesses, without depending on future fix code."""

from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.exceptions import ResponseValidationError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.models.ingredient import Ingredient, NutritionValue, UserIngredient
from app.models.recipe import Recipe, RecipeIngredient
from tests.test_ingredient_portion_schema import INVALID_PORTIONS, VALID_PORTIONS
from tests.test_ingredients_api import create_authenticated_user

INGREDIENTS = "/api/v1/ingredients"
PANTRY = "/api/v1/pantry"
RECIPES = "/api/v1/recipes"
NUTRIENTS = {"calories": "1", "protein_g": "0.1", "carbs_g": "0.2", "fat_g": "0.03"}


async def request_outcome(client, method, path, **kwargs):
    # Existing client uses raise_app_exceptions=True. Catch only relevant
    # application failures, never turn connection/setup failures into F3 evidence.
    try:
        response = await client.request(method, path, **kwargs)
    except ResponseValidationError as error:
        return {"error": type(error).__name__}, None
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) != "22003":
            raise
        return {"error": type(error).__name__, "sqlstate": "22003"}, None
    return {"status": response.status_code}, response


async def fresh_state(session_maker):
    # Core rows bypass identity maps; each observation has an independent session.
    async with session_maker() as session:
        return {
            model.__tablename__: [
                dict(row)
                for row in (
                    await session.execute(select(model.__table__).order_by(model.id))
                ).mappings()
            ]
            for model in (
                Ingredient,
                NutritionValue,
                Recipe,
                RecipeIngredient,
                UserIngredient,
            )
        }


@pytest.mark.parametrize("portion", INVALID_PORTIONS)
async def test_invalid_post_cannot_poison_catalog(client, async_session_maker, portion):
    _, headers = await create_authenticated_user(client)
    outcome, _ = await request_outcome(
        client,
        "POST",
        INGREDIENTS,
        headers=headers,
        json={
            "name": "F3 invalid POST",
            "nutrition_value": {**NUTRIENTS, "portion_g": portion},
        },
    )
    persisted = await fresh_state(async_session_maker)
    catalog, _ = await request_outcome(client, "GET", INGREDIENTS)
    details = []
    for row in persisted["ingredients"]:
        result, _ = await request_outcome(client, "GET", f"{INGREDIENTS}/{row['id']}")
        details.append(result)
    # Print only synthetic data and HTTP/error classes, never tokens or headers.
    print(
        {"post": outcome, "stored": persisted, "catalog": catalog, "details": details}
    )
    assert (outcome, persisted, catalog) == (
        {"status": 422},
        {table: [] for table in persisted},
        {"status": 200},
    )


async def create_dependencies(client, headers, other_headers):
    response = await client.post(
        INGREDIENTS,
        headers=headers,
        json={
            "name": "F3 original",
            "category": "original",
            "nutrition_value": {**NUTRIENTS, "portion_g": "100"},
        },
    )
    assert response.status_code == 201
    ingredient_id = response.json()["id"]
    response = await client.post(
        RECIPES,
        headers=headers,
        json={
            "title": "F3 recipe",
            "instructions": "Mix.",
            "ingredients": [{"ingredient_id": ingredient_id, "quantity_g": "200"}],
        },
    )
    assert response.status_code == 201
    recipe_id = response.json()["id"]
    for auth, quantity in [(headers, "100"), (other_headers, "300")]:
        response = await client.post(
            PANTRY,
            headers=auth,
            json={
                "ingredient_id": ingredient_id,
                "quantity_g": quantity,
            },
        )
        assert response.status_code == 201
    return ingredient_id, recipe_id


@pytest.mark.parametrize("portion", INVALID_PORTIONS)
async def test_invalid_patch_preserves_all_dependent_state(
    client, async_session_maker, portion
):
    _, headers = await create_authenticated_user(client)
    _, other_headers = await create_authenticated_user(client)
    ingredient_id, recipe_id = await create_dependencies(client, headers, other_headers)
    before = await fresh_state(async_session_maker)
    pantry_before = (await client.get(PANTRY, headers=other_headers)).json()
    outcome, _ = await request_outcome(
        client,
        "PATCH",
        f"{INGREDIENTS}/{ingredient_id}",
        headers=headers,
        json={
            "name": "F3 changed",
            "category": "changed",
            "nutrition_value": {**NUTRIENTS, "calories": "2", "portion_g": portion},
        },
    )
    after = await fresh_state(async_session_maker)
    reads = []
    for path, auth in [
        (INGREDIENTS, {}),
        (f"{INGREDIENTS}/{ingredient_id}", {}),
        (PANTRY, headers),
        (PANTRY, other_headers),
        (f"{RECIPES}/{recipe_id}", headers),
    ]:
        result, _ = await request_outcome(client, "GET", path, headers=auth)
        reads.append(result)
    print({"patch": outcome, "before": before, "after": after, "reads": reads})
    assert (outcome, after, reads) == ({"status": 422}, before, [{"status": 200}] * 5)
    assert (await client.get(PANTRY, headers=other_headers)).json() == pantry_before


@pytest.mark.parametrize("portion", VALID_PORTIONS + [None])
async def test_valid_post_patch_round_trip_and_calculations(
    client, async_session_maker, portion
):
    _, headers = await create_authenticated_user(client)
    expected = Decimal("100") if portion is None else Decimal(str(portion))
    nutrition = dict(NUTRIENTS)
    if portion is not None:
        nutrition["portion_g"] = portion
    response = await client.post(
        INGREDIENTS,
        headers=headers,
        json={
            "name": "F3 valid",
            "nutrition_value": nutrition,
        },
    )
    assert response.status_code == 201
    ingredient_id = response.json()["id"]
    for method in ["POST", "PATCH"]:
        if method == "PATCH":
            # First use a different portion so PATCH must actually replace it.
            changed = await client.patch(
                f"{INGREDIENTS}/{ingredient_id}",
                headers=headers,
                json={"nutrition_value": {**NUTRIENTS, "portion_g": "50"}},
            )
            assert changed.status_code == 200
            response = await client.patch(
                f"{INGREDIENTS}/{ingredient_id}",
                headers=headers,
                json={"nutrition_value": nutrition},
            )
            assert response.status_code == 200
        value = response.json()["nutrition_value"]["portion_g"]
        assert isinstance(value, str)
        assert Decimal(value) == expected
        async with async_session_maker() as session:
            stored = await session.scalar(
                select(NutritionValue.portion_g).where(
                    NutritionValue.ingredient_id == UUID(ingredient_id)
                )
            )
            assert stored == expected
        detail = await client.get(f"{INGREDIENTS}/{ingredient_id}")
        catalog = await client.get(INGREDIENTS)
        assert detail.status_code == catalog.status_code == 200
        for item in (detail.json(), catalog.json()[0]):
            assert isinstance(item["nutrition_value"]["portion_g"], str)
            assert Decimal(item["nutrition_value"]["portion_g"]) == expected

    # Fixed moderate quantity avoids large recipe totals at the minimum portion.
    pantry = await client.post(
        PANTRY,
        headers=headers,
        json={"ingredient_id": ingredient_id, "quantity_g": "0.01"},
    )
    assert pantry.status_code == 201
    pantry_list = await client.get(PANTRY, headers=headers)
    assert pantry_list.status_code == 200
    for item in [pantry.json(), pantry_list.json()[0]]:
        assert Decimal(item["ingredient"]["nutrition_value"]["portion_g"]) == expected
    recipe = await client.post(
        RECIPES,
        headers=headers,
        json={
            "title": "F3 bounded nutrition",
            "instructions": "Mix.",
            "ingredients": [{"ingredient_id": ingredient_id, "quantity_g": "0.01"}],
        },
    )
    assert recipe.status_code == 201
    reloaded = await client.get(f"{RECIPES}/{recipe.json()['id']}", headers=headers)
    summary = await client.get(f"{PANTRY}/summary", headers=headers)
    assert reloaded.status_code == summary.status_code == 200
    for nutrient, amount in NUTRIENTS.items():
        total = Decimal(amount) * (Decimal("0.01") / expected)
        assert Decimal(summary.json()[f"total_{nutrient}"]) == total
        assert Decimal(reloaded.json()[f"total_{nutrient}"]) == total.quantize(
            Decimal("0.01")
        )


@pytest.mark.parametrize("explicit_null", [False, True])
async def test_nutrition_omission_and_null_semantics(
    client, async_session_maker, explicit_null
):
    _, headers = await create_authenticated_user(client)
    fields = {"nutrition_value": None} if explicit_null else {}
    response = await client.post(
        INGREDIENTS, headers=headers, json={"name": "F3 optional", **fields}
    )
    assert response.status_code == 201
    assert response.json()["nutrition_value"] is None
    ingredient_id = response.json()["id"]
    response = await client.patch(
        f"{INGREDIENTS}/{ingredient_id}",
        headers=headers,
        json={"nutrition_value": NUTRIENTS},
    )
    assert response.status_code == 200
    before = await fresh_state(async_session_maker)
    response = await client.patch(
        f"{INGREDIENTS}/{ingredient_id}", headers=headers, json=fields
    )
    assert response.status_code == 200
    assert await fresh_state(async_session_maker) == before
