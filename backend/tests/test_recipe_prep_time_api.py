"""Duration persistence, unknown values, atomicity and unchanged consumers."""

from decimal import Decimal
from uuid import UUID

import pytest

from app.schemas.recipe import RecipeUpdate
from app.services.recipes import RecipesService
from tests.test_ai_recipe_save_api import (
    AI_RECIPE_SAVE_URL,
    RECIPES_URL,
    create_authenticated_user,
    create_ingredient,
    save_payload,
)


@pytest.mark.parametrize("ai_save", [False, True])
@pytest.mark.parametrize("minutes", ["omitted", None, 1, 45, 480])
async def test_manual_and_ai_save_persist_duration(client, ai_save, minutes):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers)
    payload = save_payload(ingredient, servings=2, meal_type="dinner")
    if minutes != "omitted":
        payload["prep_time_minutes"] = minutes
    if not ai_save:
        payload["instructions"] = "Mix."
    response = await client.post(
        AI_RECIPE_SAVE_URL if ai_save else RECIPES_URL, headers=headers, json=payload
    )
    assert response.status_code == 201
    recipe = response.json()
    assert recipe["prep_time_minutes"] == (None if minutes == "omitted" else minutes)
    assert recipe["servings"] == 2
    assert recipe["meal_type"] == "dinner"
    assert Decimal(recipe["total_calories"]) == Decimal("330.00")
    response = await client.get(f"{RECIPES_URL}/{recipe['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json() == recipe
    response = await client.get(RECIPES_URL, headers=headers)
    assert response.status_code == 200
    assert response.json() == [recipe]


async def test_patch_omission_boundaries_and_explicit_null_clear(client):
    _, headers = await create_authenticated_user(client)
    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={"title": "Before", "instructions": "Mix.", "prep_time_minutes": 45},
    )
    assert response.status_code == 201
    url = f"{RECIPES_URL}/{response.json()['id']}"
    for payload, expected in [
        ({"title": "Renamed"}, 45),
        ({"prep_time_minutes": 1}, 1),
        ({"prep_time_minutes": 480}, 480),
        ({"prep_time_minutes": None}, None),
        ({"title": "Still unknown"}, None),
        ({"prep_time_minutes": 30}, 30),
    ]:
        response = await client.patch(url, headers=headers, json=payload)
        assert response.status_code == 200
        assert response.json()["prep_time_minutes"] == expected
        read = await client.get(url, headers=headers)
        assert read.status_code == 200
        assert read.json() == response.json()


@pytest.mark.parametrize(
    "value", [True, False, "45", "", 45.0, 1.5, 0, -1, 481, [], {}]
)
async def test_invalid_writes_preserve_recipe_and_collection(client, value):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers)
    payload = save_payload(ingredient, prep_time_minutes=45)
    response = await client.post(
        RECIPES_URL, headers=headers, json={**payload, "instructions": "Mix."}
    )
    assert response.status_code == 201
    original = response.json()
    url = f"{RECIPES_URL}/{original['id']}"
    response = await client.patch(
        url,
        headers=headers,
        json={"title": "Must not persist", "prep_time_minutes": value},
    )
    assert response.status_code == 422
    for endpoint in [AI_RECIPE_SAVE_URL, RECIPES_URL]:
        invalid = {**payload, "prep_time_minutes": value}
        if endpoint == RECIPES_URL:
            invalid["instructions"] = "Mix."
        response = await client.post(endpoint, headers=headers, json=invalid)
        assert response.status_code == 422
    response = await client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.json() == original
    response = await client.get(RECIPES_URL, headers=headers)
    assert response.status_code == 200
    assert response.json() == [original]


async def test_duration_changes_remain_owner_scoped_and_rollback_after_flush(
    client, async_session_maker, monkeypatch
):
    user, owner = await create_authenticated_user(client)
    _, other = await create_authenticated_user(client)
    response = await client.post(
        RECIPES_URL,
        headers=owner,
        json={"title": "Private", "instructions": "Mix.", "prep_time_minutes": 45},
    )
    assert response.status_code == 201
    original = response.json()
    url = f"{RECIPES_URL}/{original['id']}"
    for minutes in [480, None]:
        response = await client.patch(
            url, headers=other, json={"prep_time_minutes": minutes}
        )
        assert response.status_code == 404
    response = await client.patch(url, json={"prep_time_minutes": 30})
    assert response.status_code == 401
    response = await client.get(url, headers=other)
    assert response.status_code == 404
    response = await client.get(RECIPES_URL, headers=other)
    assert response.status_code == 200
    assert response.json() == []
    async with async_session_maker() as db:

        async def fail_commit():
            await db.flush()
            raise RuntimeError("injected prep time commit failure")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="injected prep time commit failure"):
            await RecipesService(db).update_recipe(
                user_id=UUID(user["id"]),
                recipe_id=UUID(original["id"]),
                data=RecipeUpdate(prep_time_minutes=None, title="Must roll back"),
            )
    response = await client.get(url, headers=owner)
    assert response.status_code == 200
    assert response.json() == original
    response = await client.patch(url, headers=owner, json={"prep_time_minutes": None})
    assert response.status_code == 200
    assert response.json()["prep_time_minutes"] is None


async def test_duration_changes_leave_recipe_nutrition_and_plan_consumers_intact(
    client,
):
    _, headers = await create_authenticated_user(client)
    ingredient = await create_ingredient(client, headers=headers)
    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            **save_payload(
                ingredient, servings=2, meal_type="dinner", prep_time_minutes=45
            ),
            "instructions": "Mix.",
        },
    )
    assert response.status_code == 201
    recipe = response.json()
    response = await client.post(
        "/api/v1/meal-plans",
        headers=headers,
        json={
            "title": "Whole recipe",
            "start_date": "2026-11-16",
            "end_date": "2026-11-22",
            "items": [
                {
                    "recipe_id": recipe["id"],
                    "planned_date": "2026-11-16",
                    "meal_type": "breakfast",
                }
            ],
        },
    )
    assert response.status_code == 201
    plan_url = f"/api/v1/meal-plans/{response.json()['id']}"
    before = {}
    for path in ["", "/summary", "/daily-summary", "/shopping-list"]:
        response = await client.get(f"{plan_url}{path}", headers=headers)
        assert response.status_code == 200
        before[path] = response.json()
    assert Decimal(before["/summary"]["total_calories"]) == Decimal("330.00")
    assert Decimal(before["/shopping-list"][0]["required_quantity_g"]) == 200
    for minutes in [1, 480, None]:
        response = await client.patch(
            f"{RECIPES_URL}/{recipe['id']}",
            headers=headers,
            json={"prep_time_minutes": minutes},
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["prep_time_minutes"] == minutes
        for field in [
            "servings",
            "meal_type",
            "total_calories",
            "total_protein_g",
            "total_carbs_g",
            "total_fat_g",
            "recipe_ingredients",
        ]:
            assert updated[field] == recipe[field]
        for path, expected in before.items():
            response = await client.get(f"{plan_url}{path}", headers=headers)
            assert response.status_code == 200
            assert response.json() == expected
