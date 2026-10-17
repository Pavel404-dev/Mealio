"""HTTP/PostgreSQL witnesses; this exact module also runs on the F4 baseline.

Pause the first request after its reads, before its repository mutation. The
second either reaches that boundary (the old race) or waits in PostgreSQL. Never
require both serialized requests to reach a post-read barrier simultaneously.
"""

import asyncio
from contextvars import ContextVar
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import event, select, text

from app.db.session import get_db
from app.main import app
from app.models.ingredient import UserIngredient
from app.repositories.pantry import PantryRepository
from app.repositories.shopping_list import ShoppingListRepository
from tests.test_shopping_list_add_missing_to_pantry_api import (
    ADD_MISSING_TO_PANTRY_URL,
    PANTRY_URL,
    SHOPPING_LIST_URL,
    add_meal_plan_item,
    add_pantry_item,
    create_authenticated_user,
    create_test_ingredient,
    create_test_meal_plan,
    create_test_recipe,
)


REQUEST = ContextVar("pantry_test_request", default=None)
DATES = {"from_date": "2026-05-18", "to_date": "2026-05-18"}


async def scenario(client, *, initial=None, count=1, ingredients=None):
    user, headers = await create_authenticated_user(client)
    if ingredients is None:
        ingredients = [
            await create_test_ingredient(
                client, headers=headers, name=f"F4 {user['id']} {i}"
            )
            for i in range(count)
        ]
    plan = await create_test_meal_plan(client, headers=headers)
    for meal_type, quantity in (("lunch", "100"), ("dinner", "50")):
        recipe = await create_test_recipe(
            client,
            headers=headers,
            title=f"F4 {meal_type}",
            ingredients=[
                {"ingredient_id": item["id"], "quantity_g": quantity}
                for item in ingredients
            ],
        )
        await add_meal_plan_item(
            client,
            headers=headers,
            meal_plan_id=plan["id"],
            recipe_id=recipe["id"],
            planned_date="2026-05-18",
            meal_type=meal_type,
        )
    pantry = []
    if initial is not None:
        for item in ingredients:
            pantry.append(
                await add_pantry_item(
                    client,
                    headers=headers,
                    ingredient_id=item["id"],
                    quantity_g=str(initial),
                )
            )
    return UUID(user["id"]), headers, ingredients, pantry


async def snapshot(maker, user_id):
    async with maker() as db:
        rows = await db.execute(
            select(
                UserIngredient.ingredient_id,
                UserIngredient.quantity_g,
                UserIngredient.expires_at,
                UserIngredient.created_at,
                UserIngredient.updated_at,
            )
            .where(UserIngredient.user_id == user_id)
            .order_by(UserIngredient.ingredient_id)
        )
        return rows.all()


def refill(client, headers, meal_type="  LuNcH  ", **dates):
    params = {**DATES, **dates}
    if meal_type is not None:
        params["meal_type"] = meal_type
    return client.post(ADD_MISSING_TO_PANTRY_URL, headers=headers, params=params)


def assert_refill(response, *, added=0, updated=0, skipped=0, delta=None, stock=None):
    assert response.status_code == 200
    body = response.json()
    assert (
        body["added_items_count"],
        body["updated_items_count"],
        body["skipped_items_count"],
    ) == (added, updated, skipped)
    assert len(body["items"]) == added + updated
    for item in body["items"]:
        assert Decimal(item["added_quantity_g"]) == Decimal(str(delta))
        assert Decimal(item["new_pantry_quantity_g"]) == Decimal(str(stock))


class Interleaving:
    def __init__(self, maker):
        self.maker = maker
        self.ready = {name: asyncio.Event() for name in ("first", "second")}
        self.release = {name: asyncio.Event() for name in ("first", "second")}
        self.pids = {}
        self.ended = {}
        self.preload_owner = None
        self.retained = {}
        self.observed_wait = False

    async def request(self, name, awaitable):
        token = REQUEST.set(name)
        try:
            return await awaitable
        finally:
            REQUEST.reset(token)

    async def boundary(self):
        name = REQUEST.get()
        if name in self.ready:
            self.ready[name].set()
            await asyncio.wait_for(self.release[name].wait(), 15)

    async def pair(self, first, second, while_held=None):
        tasks = []
        # Factories avoid leaking an unawaited HTTP coroutine if setup fails.
        try:
            async with asyncio.timeout(15):
                tasks.append(asyncio.create_task(self.request("first", first())))
                await self.ready["first"].wait()
                tasks.append(asyncio.create_task(self.request("second", second())))
                async with self.maker() as observer:
                    while not self.ready["second"].is_set():
                        if tasks[1].done():
                            await tasks[1]
                            pytest.fail("Second mutation completed before the first")
                        pid = self.pids.get("second")
                        blockers = await observer.scalar(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": pid or 0}
                        )
                        if self.pids["first"] in blockers:
                            self.observed_wait = True
                            break
                assert self.pids["first"] != self.pids["second"]
                if while_held is not None:
                    await while_held()
                self.release["first"].set()
                first_response = await tasks[0]
                self.release["second"].set()
                second_response = await tasks[1]
                return first_response, second_response
        finally:
            for release in self.release.values():
                release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)


@pytest.fixture
async def interleaving(client, async_session_maker, monkeypatch):
    harness = Interleaving(async_session_maker)
    previous = app.dependency_overrides[get_db]

    async def sessions():
        async with async_session_maker() as db:
            name = REQUEST.get()
            if name is not None:
                harness.pids[name] = await db.scalar(text("SELECT pg_backend_pid()"))
                await db.execute(text("SET LOCAL statement_timeout = '12000ms'"))
                if name == "second" and harness.preload_owner is not None:
                    harness.retained[name] = list(
                        await db.scalars(
                            select(UserIngredient).where(
                                UserIngredient.user_id == harness.preload_owner
                            )
                        )
                    )
            try:
                yield db
            finally:
                if name is not None:
                    # Check before dependency close can hide an unended transaction.
                    harness.ended[name] = not db.in_transaction()

    def wrap(method):
        async def paused(self, *args, **kwargs):
            await harness.boundary()
            return await method(self, *args, **kwargs)

        return paused

    for repository, name in (
        (ShoppingListRepository, "add_missing_items_to_pantry"),
        (PantryRepository, "create"),
        (PantryRepository, "update"),
        (PantryRepository, "delete"),
    ):
        monkeypatch.setattr(repository, name, wrap(getattr(repository, name)))
    app.dependency_overrides[get_db] = sessions
    try:
        yield harness
    finally:
        app.dependency_overrides[get_db] = previous


@pytest.mark.parametrize("initial", [None, 40], ids=["absent", "existing40"])
async def test_two_refills_use_current_deficit(
    client, async_session_maker, interleaving, initial
):
    owner, headers, ingredients, _ = await scenario(client, initial=initial)
    first, second = await interleaving.pair(
        lambda: refill(client, headers), lambda: refill(client, headers)
    )
    rows = await snapshot(async_session_maker, owner)
    assert len(rows) == 1
    assert rows[0].quantity_g == Decimal("100")
    assert str(rows[0].ingredient_id) == ingredients[0]["id"]
    assert_refill(
        first,
        added=int(initial is None),
        updated=int(initial is not None),
        delta=100 - (initial or 0),
        stock=100,
    )
    assert_refill(second, skipped=1)
    assert interleaving.observed_wait
    assert all(interleaving.ended.values())
    before = await snapshot(async_session_maker, owner)
    assert_refill(await refill(client, headers), skipped=1)
    assert await snapshot(async_session_maker, owner) == before


@pytest.mark.parametrize("broad_first", [False, True])
async def test_overlapping_filters_and_multiple_ingredients(
    client, async_session_maker, interleaving, broad_first
):
    owner, headers, _, _ = await scenario(client, count=2)
    first_filter, second_filter = (None, "lunch") if broad_first else ("lunch", None)
    first, second = await interleaving.pair(
        lambda: refill(client, headers, first_filter),
        lambda: refill(client, headers, second_filter),
    )
    rows = await snapshot(async_session_maker, owner)
    assert len(rows) == 2
    assert all(row.quantity_g == 150 for row in rows)
    assert_refill(
        first,
        added=2,
        delta=150 if broad_first else 100,
        stock=150 if broad_first else 100,
    )
    if broad_first:
        assert_refill(second, skipped=2)
    else:
        assert_refill(second, updated=2, delta=50, stock=150)
    assert interleaving.observed_wait
    assert all(interleaving.ended.values())


@pytest.mark.parametrize("kind", ["post", "patch", "delete"])
@pytest.mark.parametrize("crud_first", [True, False])
async def test_crud_and_refill_follow_lock_order(
    client, async_session_maker, interleaving, kind, crud_first
):
    owner, headers, ingredients, pantry = await scenario(
        client, initial={"post": None, "patch": 70, "delete": 40}[kind]
    )

    def crud():
        if kind == "post":
            return client.post(
                PANTRY_URL,
                headers=headers,
                json={"ingredient_id": ingredients[0]["id"], "quantity_g": "40"},
            )
        url = f"{PANTRY_URL}/{pantry[0]['id']}"
        if kind == "patch":
            return client.patch(url, headers=headers, json={"quantity_g": "40"})
        return client.delete(url, headers=headers)

    def refill_request():
        return refill(client, headers)

    requests = (crud, refill_request) if crud_first else (refill_request, crud)
    first, second = await interleaving.pair(*requests)
    mutation, fill = (first, second) if crud_first else (second, first)
    assert (
        mutation.status_code
        == {"post": 201 if crud_first else 409, "patch": 200, "delete": 204}[kind]
    )
    rows = await snapshot(async_session_maker, owner)
    if kind == "delete" and not crud_first:
        assert rows == []
    else:
        assert len(rows) == 1
        assert rows[0].quantity_g == (40 if kind == "patch" and not crud_first else 100)
    created = (kind == "post" and not crud_first) or (kind == "delete" and crud_first)
    assert_refill(
        fill,
        added=int(created),
        updated=int(not created),
        delta=100 if created else (30 if kind == "patch" and not crud_first else 60),
        stock=100,
    )
    assert interleaving.observed_wait
    assert all(interleaving.ended.values())


async def test_waiting_patch_refreshes_preloaded_pantry(
    client, async_session_maker, interleaving
):
    owner, headers, _, pantry = await scenario(client, initial=40)
    interleaving.preload_owner = owner
    first, second = await interleaving.pair(
        lambda: refill(client, headers),
        lambda: client.patch(
            f"{PANTRY_URL}/{pantry[0]['id']}",
            headers=headers,
            json={"expires_at": "2030-01-01T00:00:00Z"},
        ),
    )
    assert_refill(first, updated=1, delta=60, stock=100)
    assert second.status_code == 200
    assert Decimal(second.json()["quantity_g"]) == 100
    rows = await snapshot(async_session_maker, owner)
    assert rows[0].quantity_g == 100
    assert rows[0].expires_at.year == 2030
    assert interleaving.observed_wait


async def test_other_owner_and_read_only_get_progress_while_writer_held(
    client, async_session_maker, interleaving
):
    owner, headers, ingredients, _ = await scenario(client)
    other, other_headers, _, _ = await scenario(
        client, initial=20, ingredients=ingredients
    )

    async def independently():
        # This must complete while the first user's transaction still holds its lock.
        assert_refill(
            await refill(client, other_headers), updated=1, delta=80, stock=100
        )
        response = await client.get(
            SHOPPING_LIST_URL,
            headers=headers,
            params={**DATES, "meal_type": "lunch", "subtract_pantry": True},
        )
        assert response.status_code == 200
        assert Decimal(response.json()[0]["pantry_quantity_g"]) == 0

    first, second = await interleaving.pair(
        lambda: refill(client, headers), lambda: refill(client, headers), independently
    )
    assert_refill(first, added=1, delta=100, stock=100)
    assert_refill(second, skipped=1)
    assert (await snapshot(async_session_maker, owner))[0].quantity_g == 100
    assert (await snapshot(async_session_maker, other))[0].quantity_g == 100


@pytest.mark.parametrize("kind", ["refill", "post", "patch", "delete"])
async def test_sql_mutation_failure_rolls_back_and_releases_lock(
    client, async_session_maker, test_engine, interleaving, kind
):
    owner, headers, ingredients, pantry = await scenario(
        client, initial=None if kind in ("refill", "post") else 40, count=2
    )
    before = await snapshot(async_session_maker, owner)
    mutations = []

    def fail_after_sql(conn, cursor, statement, parameters, context, executemany):
        sql = statement.lstrip().lower()
        if REQUEST.get() == "failure" and sql.startswith(
            (
                "insert into user_ingredients",
                "update user_ingredients",
                "delete from user_ingredients",
            )
        ):
            mutations.append(sql.split()[0])
            raise RuntimeError("synthetic failure after pantry SQL")

    def operation():
        if kind == "refill":
            return refill(client, headers)
        if kind == "post":
            return client.post(
                PANTRY_URL,
                headers=headers,
                json={"ingredient_id": ingredients[0]["id"], "quantity_g": "40"},
            )
        url = f"{PANTRY_URL}/{pantry[0]['id']}"
        if kind == "patch":
            return client.patch(url, headers=headers, json={"quantity_g": "70"})
        return client.delete(url, headers=headers)

    event.listen(test_engine.sync_engine, "after_cursor_execute", fail_after_sql)
    try:
        with pytest.raises(RuntimeError, match="synthetic failure after pantry SQL"):
            await asyncio.wait_for(interleaving.request("failure", operation()), 10)
    finally:
        event.remove(test_engine.sync_engine, "after_cursor_execute", fail_after_sql)
    assert len(mutations) == 1  # SQL executed successfully before injection.
    assert await snapshot(async_session_maker, owner) == before
    assert interleaving.ended["failure"]  # rollback before dependency cleanup
    response = await asyncio.wait_for(operation(), 10)
    assert (
        response.status_code
        == {"refill": 200, "post": 201, "patch": 200, "delete": 204}[kind]
    )
    if kind == "refill":
        assert_refill(response, added=2, delta=100, stock=100)
        assert len(await snapshot(async_session_maker, owner)) == 2


async def test_noop_empty_expired_and_unrelated_stock(
    client, async_session_maker, interleaving
):
    owner, headers, ingredients, pantry = await scenario(client, initial=180)
    unrelated = await create_test_ingredient(
        client, headers=headers, name=f"F4 unrelated {owner}"
    )
    await add_pantry_item(
        client, headers=headers, ingredient_id=unrelated["id"], quantity_g="17"
    )
    expired = await client.patch(
        f"{PANTRY_URL}/{pantry[0]['id']}",
        headers=headers,
        json={"expires_at": "2020-01-01T00:00:00Z"},
    )
    assert expired.status_code == 200
    before = await snapshot(async_session_maker, owner)
    assert_refill(
        await interleaving.request("noop", refill(client, headers)), skipped=1
    )
    assert_refill(
        await interleaving.request(
            "empty",
            refill(client, headers, from_date="2026-06-01", to_date="2026-06-01"),
        )
    )
    assert await snapshot(async_session_maker, owner) == before
    # Expired stock is still counted; topping it up preserves expires_at/created_at.
    await client.patch(
        f"{PANTRY_URL}/{pantry[0]['id']}", headers=headers, json={"quantity_g": "40"}
    )
    assert_refill(await refill(client, headers), updated=1, delta=60, stock=100)
    after = await snapshot(async_session_maker, owner)
    before_by_id = {str(row.ingredient_id): row for row in before}
    after_by_id = {str(row.ingredient_id): row for row in after}
    selected = ingredients[0]["id"]
    assert after_by_id[selected].expires_at == before_by_id[selected].expires_at
    assert after_by_id[selected].created_at == before_by_id[selected].created_at
    assert after_by_id[unrelated["id"]] == before_by_id[unrelated["id"]]
    assert all(interleaving.ended.values())


@pytest.mark.parametrize(
    "kind", ["duplicate", "foreign_patch", "foreign_delete", "missing_ingredient"]
)
async def test_crud_rejections_end_transaction_and_preserve_owners(
    client, async_session_maker, interleaving, kind
):
    owner, headers, ingredients, pantry = await scenario(client, initial=40)
    other, other_headers, _, _ = await scenario(client, ingredients=ingredients)
    before = await snapshot(async_session_maker, owner)
    if kind == "duplicate":
        request = client.post(
            PANTRY_URL,
            headers=headers,
            json={"ingredient_id": ingredients[0]["id"], "quantity_g": "10"},
        )
        status = 409
    elif kind == "missing_ingredient":
        request = client.post(
            PANTRY_URL,
            headers=headers,
            json={
                "ingredient_id": "00000000-0000-0000-0000-000000000001",
                "quantity_g": "10",
            },
        )
        status = 404
    else:
        url = f"{PANTRY_URL}/{pantry[0]['id']}"
        request = (
            client.patch(url, headers=other_headers, json={"quantity_g": "10"})
            if kind == "foreign_patch"
            else client.delete(url, headers=other_headers)
        )
        status = 404
    response = await interleaving.request("rejected", request)
    assert response.status_code == status
    assert interleaving.ended["rejected"]
    assert await snapshot(async_session_maker, owner) == before
    assert await snapshot(async_session_maker, other) == []
    assert_refill(
        await asyncio.wait_for(refill(client, headers), 10),
        updated=1,
        delta=60,
        stock=100,
    )
