"""DB/API lifecycle and validation regressions; separately authorized runs only."""

import json

import pytest
from sqlalchemy import select

from app.models.ingredient import NutritionValue
from tests.test_ai_recipe_save_api import (
    INGREDIENTS_URL,
    RECIPES_URL,
    create_authenticated_user,
    create_ingredient,
)
from tests.test_nutrition_storage_transactions import snapshot

SOURCE_A = {"source_name": "Synthetic source A", "source_reference": "record:A"}
SOURCE_B = {"source_name": "Synthetic source B", "source_reference": "record:B"}
VALUES = {
    "calories": "100",
    "protein_g": "10",
    "carbs_g": "20",
    "fat_g": "5",
    "portion_g": "50",
}


async def test_nested_replacement_preservation_clearing_and_aggregate_reload(
    client, async_session_maker
):
    _, headers = await create_authenticated_user(client)
    identifier = await create_ingredient(client, headers=headers, **VALUES, **SOURCE_A)
    url = f"{INGREDIENTS_URL}/{identifier}"
    recipe = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Synthetic",
            "instructions": "Mix",
            "ingredients": [{"ingredient_id": identifier, "quantity_g": "125"}],
        },
    )
    assert recipe.status_code == 201
    recipe_url = f"{RECIPES_URL}/{recipe.json()['id']}"
    original = (await client.get(url)).json()["nutrition_value"]
    assert original["per_100g"]["calories"] == "200.00"
    assert recipe.json()["total_calories"] == "250.00"
    for payload in ({"category": "Changed"}, {"nutrition_value": None}):
        response = await client.patch(url, headers=headers, json=payload)
        assert response.status_code == 200
        assert response.json()["nutrition_value"] == original
    for values, metadata, projection, total in [
        (VALUES, {}, "200.00", "250.00"),  # identical numbers still clear source
        (VALUES, SOURCE_A, "200.00", "250.00"),
        (
            {
                "calories": "120",
                "protein_g": "8",
                "carbs_g": "16",
                "fat_g": "4",
                "portion_g": "40",
            },
            {},
            "300.00",
            "375.00",
        ),
        ({"calories": "120"}, SOURCE_B, "120.00", "150.00"),
        ({"calories": "120"}, {}, "120.00", "150.00"),
        (
            VALUES,
            {
                "source_name": "  Synthetic source B\u2003",
                "source_reference": " record:B ",
            },
            "200.00",
            "250.00",
        ),
        (VALUES, {"source_name": None, "source_reference": None}, "200.00", "250.00"),
        (VALUES, {"source_name": "Synthetic source B"}, "200.00", "250.00"),
    ]:
        response = await client.patch(
            url, headers=headers, json={"nutrition_value": {**values, **metadata}}
        )
        assert response.status_code == 200
        nutrition = response.json()["nutrition_value"]
        assert nutrition["id"] == original["id"]
        for field in SOURCE_A:
            raw = metadata.get(field)
            assert nutrition[field] == (raw.strip() if raw else None)
        assert nutrition["per_100g"]["calories"] == projection
        if len(values) == 1:
            assert nutrition["portion_g"] == "100.00"
            assert all(
                nutrition[field] == "0.00"
                for field in ("protein_g", "carbs_g", "fat_g")
            )
        assert (await client.get(url)).json()["nutrition_value"] == nutrition
        assert (await client.get(recipe_url, headers=headers)).json()[
            "total_calories"
        ] == total
        async with async_session_maker() as db:
            row = await db.scalar(select(NutritionValue))
            assert row.source_name == nutrition["source_name"]
            assert row.source_reference == nutrition["source_reference"]


@pytest.mark.parametrize(
    "invalid",
    [
        {"source_name": None, "source_reference": "orphan"},
        {"source_name": "   "},
        {"source_reference": "\t\u2003"},
        {"source_name": "x" * 256},
        {"source_reference": "x" * 1001},
        {"source_name": 42},
        {"source_reference": True},
        {"source_name": []},
        {"source_reference": {}},
        {"source_name": "a\x00b"},
        {"source_reference": "a\x00b"},
        {"source_name": "\ud800"},
        {"source_reference": "\udfff"},
        {"calories": "1.234"},
    ],
)
async def test_validation_is_atomic_for_create_and_patch(
    client, async_session_maker, invalid
):
    _, headers = await create_authenticated_user(client)
    identifier = await create_ingredient(client, headers=headers, **VALUES, **SOURCE_A)
    before = await snapshot(async_session_maker)
    for method, url in [
        (client.post, INGREDIENTS_URL),
        (client.patch, f"{INGREDIENTS_URL}/{identifier}"),
    ]:
        response = await method(
            url,
            headers={**headers, "Content-Type": "application/json"},
            content=json.dumps(
                {
                    "name": "Must not persist",
                    "category": "Changed",
                    "nutrition_value": {**VALUES, **SOURCE_B, **invalid},
                },
                ensure_ascii=True,
            ),
        )
        assert response.status_code == 422
        assert await snapshot(async_session_maker) == before
    response = await client.patch(
        f"{INGREDIENTS_URL}/{identifier}",
        headers=headers,
        json={"nutrition_value": SOURCE_B},
    )
    assert response.status_code == 422
    assert await snapshot(async_session_maker) == before


async def test_public_catalog_reads_authenticated_shared_writes(client):
    _, headers = await create_authenticated_user(client)
    _, other_headers = await create_authenticated_user(client)
    payload = {
        "name": "Synthetic public metadata",
        "nutrition_value": {**VALUES, **SOURCE_A},
    }
    assert (await client.post(INGREDIENTS_URL, json=payload)).status_code == 401
    response = await client.post(INGREDIENTS_URL, headers=headers, json=payload)
    assert response.status_code == 201
    url = f"{INGREDIENTS_URL}/{response.json()['id']}"
    assert (await client.patch(url, json=payload)).status_code == 401
    response = await client.patch(
        url, headers=other_headers, json={"nutrition_value": {**VALUES, **SOURCE_B}}
    )
    assert response.status_code == 200
    assert (await client.get(url)).json()["nutrition_value"][
        "source_reference"
    ] == "record:B"
    assert (await client.get(INGREDIENTS_URL)).json()[0]["nutrition_value"][
        "source_name"
    ] == SOURCE_B["source_name"]
