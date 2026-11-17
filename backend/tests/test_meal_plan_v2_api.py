"""PostgreSQL roundtrips for canonical writes and legacy plan compatibility."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.test_meal_plans_api import (
    MEAL_PLANS_URL,
    create_authenticated_user,
    create_test_meal_plan,
    create_test_recipe,
)

V2_URL = "/api/v2/meal-plans"


def item_payload(recipe_id, meal_type="lunch", planned_date="2026-05-18"):
    return {
        "recipe_id": recipe_id,
        "planned_date": planned_date,
        "meal_type": meal_type,
    }


def plan_payload(items):
    return {
        "title": "Canonical slots",
        "start_date": "2026-05-18",
        "end_date": "2026-05-24",
        "items": items,
    }


async def read_plan(client, headers, plan_id):
    response = await client.get(f"{MEAL_PLANS_URL}/{plan_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_v2_plan_create_roundtrips_all_slots_through_existing_reads(client):
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=headers)
    canonical = ["breakfast", "lunch", "dinner", "snack"]
    response = await client.post(
        V2_URL,
        headers=headers,
        json=plan_payload(
            [item_payload(recipe_id, f" {s.upper()} ") for s in canonical]
        ),
    )
    assert response.status_code == 201
    plan = response.json()
    assert sorted(item["meal_type"] for item in plan["items"]) == sorted(canonical)
    assert all(item["planned_servings"] is None for item in plan["items"])
    v1_plan = {
        **plan,
        "items": [
            {key: value for key, value in item.items() if key != "planned_servings"}
            for item in plan["items"]
        ],
    }
    assert await read_plan(client, headers, plan["id"]) == v1_plan
    response = await client.get(MEAL_PLANS_URL, headers=headers)
    assert response.status_code == 200
    assert response.json() == [v1_plan]
    response = await client.get(f"{V2_URL}/{plan['id']}", headers=headers)
    assert response.status_code == 200 and response.json() == plan
    response = await client.get(V2_URL, headers=headers)
    assert response.status_code == 200 and response.json() == [plan]
    response = await client.get(
        "/api/v1/meal-plan-items",
        headers=headers,
        params={
            "from_date": "2026-05-18",
            "to_date": "2026-05-24",
            "meal_type": "LUNCH",
        },
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["meal_type"] == "lunch"


async def test_v2_rejects_custom_writes_atomically_and_preserves_v1_labels(client):
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=headers)
    replacement_id = await create_test_recipe(
        client, headers=headers, title="Replacement"
    )
    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json=plan_payload([item_payload(recipe_id, "  BrUnCh ")]),
    )
    assert response.status_code == 201
    original = response.json()
    assert original["items"][0]["meal_type"] == "brunch"
    item_id = original["items"][0]["id"]
    v2_items_url = f"{V2_URL}/{original['id']}/items"
    v2_item_url = f"{v2_items_url}/{item_id}"
    # A valid earlier item must not survive a later invalid item in a create body.
    response = await client.post(
        V2_URL,
        headers=headers,
        json=plan_payload([item_payload(recipe_id), item_payload(recipe_id, "brunch")]),
    )
    assert response.status_code == 422
    response = await client.get(MEAL_PLANS_URL, headers=headers)
    assert response.status_code == 200
    assert response.json() == [original]
    response = await client.post(
        v2_items_url, headers=headers, json=item_payload(recipe_id, "brunch")
    )
    assert response.status_code == 422
    for invalid in ["brunch", None, "", "  ", True, 1, []]:
        response = await client.patch(
            v2_item_url,
            headers=headers,
            json=item_payload(replacement_id, invalid, "2026-05-19"),
        )
        assert response.status_code == 422
        assert await read_plan(client, headers, original["id"]) == original
    # Date/recipe-only writes and empty PATCH keep a legacy label as-is.
    for patch in [{}, {"recipe_id": replacement_id, "planned_date": "2026-05-19"}]:
        response = await client.patch(v2_item_url, headers=headers, json=patch)
        assert response.status_code == 200
        assert response.json()["meal_type"] == "brunch"
    response = await client.patch(
        v2_item_url, headers=headers, json={"meal_type": " SnAcK "}
    )
    assert response.status_code == 200
    assert response.json()["meal_type"] == "snack"
    assert response.json()["recipe_id"] == replacement_id
    assert response.json()["planned_date"] == "2026-05-19"
    # V1 is still an unrestricted legacy writer, even after v2 adopts the item.
    response = await client.patch(
        f"{MEAL_PLANS_URL}/{original['id']}/items/{item_id}",
        headers=headers,
        json={"meal_type": "brunch"},
    )
    assert response.status_code == 200
    assert response.json()["meal_type"] == "brunch"
    assert (await read_plan(client, headers, original["id"]))["items"] == [
        response.json()
    ]


async def test_v2_duplicate_slots_dates_and_failed_updates_leave_plan_unchanged(client):
    _, headers = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=headers)
    for items, expected in [
        ([item_payload(recipe_id, "Lunch"), item_payload(recipe_id, " lunch ")], 409),
        ([item_payload(recipe_id, planned_date="2026-05-17")], 422),
        ([item_payload(recipe_id, planned_date="2026-05-25")], 422),
    ]:
        response = await client.post(V2_URL, headers=headers, json=plan_payload(items))
        assert response.status_code == expected
    response = await client.post(
        V2_URL,
        headers=headers,
        json={**plan_payload([]), "end_date": "2026-05-17"},
    )
    assert response.status_code == 422
    response = await client.get(MEAL_PLANS_URL, headers=headers)
    assert response.status_code == 200
    assert response.json() == []
    # A legacy v1 item also occupies its slot for v2 requests.
    response = await client.post(
        MEAL_PLANS_URL, headers=headers, json=plan_payload([item_payload(recipe_id)])
    )
    assert response.status_code == 201
    plan = response.json()
    items_url = f"{V2_URL}/{plan['id']}/items"
    for payload, expected in [
        (item_payload(recipe_id, " LUNCH "), 409),
        (item_payload(recipe_id, "dinner", "2026-05-25"), 422),
    ]:
        response = await client.post(items_url, headers=headers, json=payload)
        assert response.status_code == expected
        assert await read_plan(client, headers, plan["id"]) == plan
    response = await client.post(
        items_url, headers=headers, json=item_payload(recipe_id, "DINNER")
    )
    assert response.status_code == 201
    item_url = f"{items_url}/{response.json()['id']}"
    before = await read_plan(client, headers, plan["id"])
    for patch, expected in [
        ({"meal_type": "Lunch"}, 409),
        ({"planned_date": "2026-05-17"}, 422),
        ({"planned_date": "2026-05-25"}, 422),
    ]:
        response = await client.patch(item_url, headers=headers, json=patch)
        assert response.status_code == expected
        assert await read_plan(client, headers, plan["id"]) == before
    # The same type on another day is a different slot.
    response = await client.patch(
        item_url,
        headers=headers,
        json={"meal_type": " Lunch ", "planned_date": "2026-05-19"},
    )
    assert response.status_code == 200
    assert response.json()["meal_type"] == "lunch"


async def test_v2_preserves_plan_item_and_recipe_ownership(client):
    _, owner = await create_authenticated_user(client)
    _, other = await create_authenticated_user(client)
    recipe_id = await create_test_recipe(client, headers=owner)
    foreign_recipe = await create_test_recipe(client, headers=other)
    plan = await create_test_meal_plan(client, owner)
    other_plan = await create_test_meal_plan(client, owner, title="Another owner plan")
    response = await client.post(
        f"{V2_URL}/{plan['id']}/items", headers=owner, json=item_payload(recipe_id)
    )
    assert response.status_code == 201
    item = response.json()
    before = await read_plan(client, owner, plan["id"])
    cases = [
        ("post", V2_URL, owner, plan_payload([item_payload(foreign_recipe)])),
        ("post", f"{V2_URL}/{plan['id']}/items", other, item_payload(foreign_recipe)),
        ("post", f"{V2_URL}/{plan['id']}/items", owner, item_payload(foreign_recipe)),
        (
            "patch",
            f"{V2_URL}/{plan['id']}/items/{item['id']}",
            other,
            {"meal_type": "dinner"},
        ),
        (
            "patch",
            f"{V2_URL}/{other_plan['id']}/items/{item['id']}",
            owner,
            {"meal_type": "dinner"},
        ),
        (
            "patch",
            f"{V2_URL}/{plan['id']}/items/{item['id']}",
            owner,
            {"recipe_id": foreign_recipe},
        ),
    ]
    for method, url, headers, payload in cases:
        response = await client.request(method, url, headers=headers, json=payload)
        assert response.status_code == 404
        assert await read_plan(client, owner, plan["id"]) == before
    response = await client.get(MEAL_PLANS_URL, headers=owner)
    assert response.status_code == 200
    assert {p["id"] for p in response.json()} == {plan["id"], other_plan["id"]}
    assert (await read_plan(client, owner, other_plan["id"]))["items"] == []


@pytest.mark.parametrize(
    "method, path, payload",
    [
        ("post", "", plan_payload([])),
        ("post", f"/{uuid4()}/items", item_payload(str(uuid4()))),
        ("patch", f"/{uuid4()}/items/{uuid4()}", {"meal_type": "dinner"}),
    ],
)
async def test_v2_writes_require_authentication(method, path, payload):
    # Authentication rejects the request before a DB connection is needed.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.request(method, f"{V2_URL}{path}", json=payload)
    assert response.status_code == 401
