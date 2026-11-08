"""HTTP/PostgreSQL regressions for #219, intended to fail on the unfixed base.

Pause real request sessions after flush, before commit. Witness the competing
backend waiting on the holder, rather than treating a pending task as overlap.
Only the first request must reach the barrier: a fixed second request may reject
after its lock wait without ever writing or committing. No application locks,
queries, exceptions or HTTP outcomes are replaced by this test harness.
"""

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.db.session import get_db
from app.main import app
from app.models.meal_plan import MealPlan, MealPlanItem
from app.models.recipe import Recipe
from tests.test_meal_plans_api import (
    MEAL_PLANS_URL,
    create_authenticated_user,
    create_test_recipe,
)


REQUEST = ContextVar("recipe_plan_delete_request", default=None)
PATHS = ("create_plan", "add_item", "replace_recipe")
START = "2026-05-18"
NEXT_DAY = "2026-05-19"
END = "2026-05-24"
PLAN_TITLE = "219 concurrent plan"
RECIPES_URL = "/api/v1/recipes"


@dataclass
class Scenario:
    owner_id: str
    headers: dict[str, str]
    target: str
    previous: str
    control: str
    plan_id: str
    item_id: str


async def scenario(client):
    user, headers = await create_authenticated_user(client)
    recipes = [
        await create_test_recipe(client, headers=headers, title=f"219 {name}")
        for name in ("target", "previous", "control")
    ]
    response = await client.post(
        MEAL_PLANS_URL,
        headers=headers,
        json={
            "title": "219 existing plan",
            "start_date": START,
            "end_date": END,
            "items": [
                {
                    "recipe_id": recipes[1],
                    "planned_date": START,
                    "meal_type": "breakfast",
                }
            ],
        },
    )
    assert response.status_code == 201
    plan = response.json()
    return Scenario(user["id"], headers, *recipes, plan["id"], plan["items"][0]["id"])


def attachment(client, case, path, recipe_id=None, *, payload=None):
    recipe_id = recipe_id or case.target
    item = {"recipe_id": recipe_id, "planned_date": START, "meal_type": "lunch"}
    if path == "create_plan":
        return client.post(
            MEAL_PLANS_URL,
            headers=case.headers,
            json=payload
            or {
                "title": PLAN_TITLE,
                "start_date": START,
                "end_date": END,
                "items": [
                    {
                        "recipe_id": case.previous,
                        "planned_date": START,
                        "meal_type": "breakfast",
                    },
                    item,
                ],
            },
        )
    if path == "add_item":
        return client.post(
            f"{MEAL_PLANS_URL}/{case.plan_id}/items",
            headers=case.headers,
            json=payload or item,
        )
    assert path == "replace_recipe"
    return client.patch(
        f"{MEAL_PLANS_URL}/{case.plan_id}/items/{case.item_id}",
        headers=case.headers,
        json=payload
        or {
            "recipe_id": recipe_id,
            "planned_date": NEXT_DAY,
            "meal_type": "dinner",
        },
    )


async def snapshot(maker):
    # Scalar values from a fresh session also catch partial plans and stale ORM state.
    async with maker() as db:
        result = {}
        for table, columns in (
            ("recipes", (Recipe.id, Recipe.created_by_user_id, Recipe.title)),
            (
                "plans",
                (
                    MealPlan.id,
                    MealPlan.user_id,
                    MealPlan.title,
                    MealPlan.start_date,
                    MealPlan.end_date,
                ),
            ),
            (
                "items",
                (
                    MealPlanItem.id,
                    MealPlanItem.meal_plan_id,
                    MealPlanItem.recipe_id,
                    MealPlanItem.planned_date,
                    MealPlanItem.meal_type,
                ),
            ),
        ):
            rows = (await db.execute(select(*columns))).all()
            result[table] = {
                str(row[0]): tuple(
                    str(value) if isinstance(value, (UUID, date)) else value
                    for value in row[1:]
                )
                for row in rows
            }
        return result


def attached_state(before, case, path, response, recipe_id):
    assert response.status_code == (200 if path == "replace_recipe" else 201)
    expected = {table: rows.copy() for table, rows in before.items()}
    body = response.json()
    if path == "create_plan":
        expected["plans"][body["id"]] = (case.owner_id, PLAN_TITLE, START, END)
        assert len(body["items"]) == 2
        items = {item["meal_type"]: item["id"] for item in body["items"]}
        for meal_type, target in (("breakfast", case.previous), ("lunch", recipe_id)):
            expected["items"][items[meal_type]] = (body["id"], target, START, meal_type)
    elif path == "add_item":
        expected["items"][body["id"]] = (case.plan_id, recipe_id, START, "lunch")
    else:
        assert body["id"] == case.item_id
        expected["items"][case.item_id] = (case.plan_id, recipe_id, NEXT_DAY, "dinner")
    return expected


async def assert_plan_read(client, case, expected, plan_id=None):
    plan_id = plan_id or case.plan_id
    response = await client.get(f"{MEAL_PLANS_URL}/{plan_id}", headers=case.headers)
    assert response.status_code == 200
    assert {
        item["id"]: (
            item["meal_plan_id"],
            item["recipe_id"],
            item["planned_date"],
            item["meal_type"],
        )
        for item in response.json()["items"]
    } == {
        item_id: values
        for item_id, values in expected["items"].items()
        if values[0] == plan_id
    }


class Interleaving:
    def __init__(self, maker):
        self.maker = maker
        self.flushed = {name: asyncio.Event() for name in ("first", "second")}
        self.release = {name: asyncio.Event() for name in ("first", "second")}
        self.sessions = {}
        self.pids = {}
        self.xids = {}
        self.committed = []
        self.witness = None

    async def request(self, name, factory):
        token = REQUEST.set(name)
        try:
            return await factory()
        finally:
            REQUEST.reset(token)

    async def before_commit(self, db, name):
        # The old repositories flush implicitly inside commit. Make that same
        # real flush explicit, retaining FK/row locks while the barrier is held.
        await db.flush()
        self.xids[name] = await db.scalar(
            text("SELECT pg_current_xact_id_if_assigned()::text")
        )
        assert self.xids[name] is not None, "The barrier must follow a SQL write"
        self.flushed[name].set()
        await asyncio.wait_for(self.release[name].wait(), 15)

    async def observe_overlap(self, tasks, *, require_lock_wait):
        async with self.maker() as observer:
            observer_pid = await observer.scalar(text("SELECT pg_backend_pid()"))
            while True:
                if tasks[1].done():
                    await tasks[1]
                    pytest.fail("The second request ended before overlap was observed")
                if "second" not in self.pids:
                    await asyncio.sleep(0.01)
                    continue
                assert self.sessions["first"] is not self.sessions["second"]
                assert len({observer_pid, *self.pids.values()}) == 3
                # pg_stat_activity snapshots otherwise persist in the observer's
                # transaction. pg_blocking_pids itself reports live lock waits.
                await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                rows = (
                    (
                        await observer.execute(
                            text(
                                "SELECT pid, state, wait_event_type, "
                                "xact_start IS NOT NULL AS in_transaction, "
                                "pg_blocking_pids(pid) AS blockers "
                                "FROM pg_stat_activity WHERE pid IN (:first, :second)"
                            ),
                            self.pids,
                        )
                    )
                    .mappings()
                    .all()
                )
                activity = {row["pid"]: row for row in rows}
                assert set(activity) == set(self.pids.values())
                assert all(row["in_transaction"] for row in activity.values())
                if activity[self.pids["first"]]["state"] != "idle in transaction":
                    await asyncio.sleep(0.01)
                    continue
                second = activity[self.pids["second"]]
                if self.pids["first"] in second["blockers"]:
                    assert second["wait_event_type"] == "Lock"
                    self.witness = "lock_wait"
                    return
                if self.flushed["second"].is_set():
                    assert not require_lock_wait, "Same-recipe requests must conflict"
                    assert self.xids["first"] != self.xids["second"]
                    if second["state"] != "idle in transaction":
                        await asyncio.sleep(0.01)
                        continue
                    self.witness = "two_flushed_transactions"
                    return
                await asyncio.sleep(0.01)

    async def pair(self, first, second, *, require_lock_wait=True):
        tasks = []
        barrier = asyncio.create_task(self.flushed["first"].wait())
        try:
            async with asyncio.timeout(15):
                tasks.append(asyncio.create_task(self.request("first", first)))
                done, _ = await asyncio.wait(
                    [tasks[0], barrier], return_when=asyncio.FIRST_COMPLETED
                )
                if tasks[0] in done:
                    response = await tasks[0]
                    pytest.fail(
                        f"First request returned {response.status_code} before flush barrier"
                    )
                tasks.append(asyncio.create_task(self.request("second", second)))
                await self.observe_overlap(tasks, require_lock_wait=require_lock_wait)
                assert not tasks[0].done() and not tasks[1].done()
                self.release["first"].set()
                first_response = await tasks[0]
                # Keep a successful second mutation uncommitted until the first
                # HTTP response (including any post-commit refresh) is complete.
                self.release["second"].set()
                second_response = await tasks[1]
                assert self.committed[0] == "first"
                return first_response, second_response
        finally:
            for release in self.release.values():
                release.set()
            for task in [barrier, *tasks]:
                if not task.done():
                    task.cancel()
            await asyncio.wait_for(
                asyncio.gather(barrier, *tasks, return_exceptions=True), 5
            )


@pytest.fixture
async def interleaving(client, async_session_maker):
    harness = Interleaving(async_session_maker)
    previous = app.dependency_overrides[get_db]

    async def sessions():
        async with async_session_maker() as db:
            name = REQUEST.get()
            if name is not None:
                harness.sessions[name] = db
                harness.pids[name] = await db.scalar(text("SELECT pg_backend_pid()"))
                await db.execute(text("SET LOCAL statement_timeout = '12000ms'"))
                await db.execute(text("SET LOCAL lock_timeout = '8000ms'"))
                commit = db.commit

                async def paused_commit():
                    await harness.before_commit(db, name)
                    await commit()
                    harness.committed.append(name)

                db.commit = paused_commit
            yield db

    app.dependency_overrides[get_db] = sessions
    try:
        yield harness
    finally:
        app.dependency_overrides[get_db] = previous


@pytest.mark.parametrize("path", PATHS)
async def test_attachment_commits_first_preserves_slot_and_rejects_delete(
    client, async_session_maker, interleaving, path
):
    case = await scenario(client)
    before = await snapshot(async_session_maker)
    linked, deleted = await interleaving.pair(
        lambda: attachment(client, case, path),
        lambda: client.delete(f"{RECIPES_URL}/{case.target}", headers=case.headers),
    )
    assert interleaving.witness == "lock_wait"
    expected = attached_state(before, case, path, linked, case.target)
    after = await snapshot(async_session_maker)
    recipe = await client.get(f"{RECIPES_URL}/{case.target}", headers=case.headers)
    # Report the status and persisted cascade damage together on the old base.
    assert (deleted.status_code, recipe.status_code, after) == (409, 200, expected)
    assert (
        deleted.json()["detail"] == "Recipe is used in meal plans and cannot be deleted"
    )
    await assert_plan_read(client, case, expected)
    if path == "create_plan":
        await assert_plan_read(client, case, expected, linked.json()["id"])


@pytest.mark.parametrize("path", PATHS)
async def test_delete_commits_first_rejects_attachment_without_partial_write(
    client, async_session_maker, interleaving, path
):
    case = await scenario(client)
    before = await snapshot(async_session_maker)
    deleted, linked = await interleaving.pair(
        lambda: client.delete(f"{RECIPES_URL}/{case.target}", headers=case.headers),
        lambda: attachment(client, case, path),
    )
    assert interleaving.witness == "lock_wait"
    expected = {table: rows.copy() for table, rows in before.items()}
    del expected["recipes"][case.target]
    after = await snapshot(async_session_maker)
    assert after == expected  # Includes the old PATCH reference/date/meal type.
    await assert_plan_read(client, case, before)
    recipe = await client.get(f"{RECIPES_URL}/{case.target}", headers=case.headers)
    assert (deleted.status_code, linked.status_code, recipe.status_code) == (
        204,
        404,
        404,
    )
    detail = linked.json()["detail"]
    if path == "create_plan":
        assert detail == f"Recipes not found: {case.target}"
    else:
        assert detail == "Recipe not found"


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("first", ["attachment", "delete"])
async def test_other_recipe_attachment_survives_in_both_commit_orders(
    client, async_session_maker, interleaving, path, first
):
    case = await scenario(client)
    before = await snapshot(async_session_maker)

    def attach_control():
        return attachment(client, case, path, case.control)

    def delete_target():
        return client.delete(f"{RECIPES_URL}/{case.target}", headers=case.headers)

    requests = (
        (attach_control, delete_target)
        if first == "attachment"
        else (delete_target, attach_control)
    )
    responses = await interleaving.pair(*requests, require_lock_wait=False)
    linked, deleted = responses if first == "attachment" else responses[::-1]
    assert interleaving.witness in {"lock_wait", "two_flushed_transactions"}
    assert deleted.status_code == 204
    expected = attached_state(before, case, path, linked, case.control)
    del expected["recipes"][case.target]
    assert await snapshot(async_session_maker) == expected
    recipe = await client.get(f"{RECIPES_URL}/{case.control}", headers=case.headers)
    assert recipe.status_code == 200
    await assert_plan_read(client, case, expected)
    if path == "create_plan":
        await assert_plan_read(client, case, expected, linked.json()["id"])


@pytest.mark.parametrize("path", PATHS)
async def test_attachment_rejects_foreign_recipe_without_mutation(
    client, async_session_maker, path
):
    case = await scenario(client)
    _, foreign_headers = await create_authenticated_user(client)
    foreign = await create_test_recipe(client, headers=foreign_headers)
    before = await snapshot(async_session_maker)
    response = await asyncio.wait_for(attachment(client, case, path, foreign), 10)
    assert response.status_code == 404
    assert response.json()["detail"] == (
        f"Recipes not found: {foreign}" if path == "create_plan" else "Recipe not found"
    )
    assert await snapshot(async_session_maker) == before
    await assert_plan_read(client, case, before)


@pytest.mark.parametrize("path", PATHS)
async def test_genuine_slot_conflict_still_returns_409_without_mutation(
    client, async_session_maker, path
):
    case = await scenario(client)
    if path == "create_plan":
        payload = {
            "title": PLAN_TITLE,
            "start_date": START,
            "end_date": END,
            "items": [
                {"recipe_id": target, "planned_date": START, "meal_type": meal_type}
                for target, meal_type in (
                    (case.previous, "breakfast"),
                    (case.target, " BREAKFAST "),
                )
            ],
        }
    elif path == "add_item":
        payload = {
            "recipe_id": case.target,
            "planned_date": START,
            "meal_type": " BREAKFAST ",
        }
    else:
        payload = {
            "recipe_id": case.target,
            "planned_date": NEXT_DAY,
            "meal_type": " DINNER ",
        }
        occupied = await client.post(
            f"{MEAL_PLANS_URL}/{case.plan_id}/items",
            headers=case.headers,
            json={**payload, "recipe_id": case.control},
        )
        assert occupied.status_code == 201
    before = await snapshot(async_session_maker)
    response = await asyncio.wait_for(
        attachment(client, case, path, payload=payload), 10
    )
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Meal plan cannot contain duplicate meal slots"
        if path == "create_plan"
        else "Meal plan already has an item for this date and meal type"
    )
    assert await snapshot(async_session_maker) == before
    await assert_plan_read(client, case, before)


@pytest.mark.parametrize("path", ["add_item", "replace_recipe"])
async def test_overlapping_slot_writers_keep_genuine_409(
    client, async_session_maker, interleaving, path
):
    case = await scenario(client)
    if path == "replace_recipe":
        occupied = await client.post(
            f"{MEAL_PLANS_URL}/{case.plan_id}/items",
            headers=case.headers,
            json={
                "recipe_id": case.control,
                "planned_date": START,
                "meal_type": "lunch",
            },
        )
        assert occupied.status_code == 201
        other_item_id = occupied.json()["id"]

    def same_slot():
        if path == "add_item":
            return attachment(client, case, path, case.control)
        # A different existing item contends for the first PATCH's new slot.
        # Its old control-recipe link and slot must survive the rejected write.
        return client.patch(
            f"{MEAL_PLANS_URL}/{case.plan_id}/items/{other_item_id}",
            headers=case.headers,
            json={
                "recipe_id": case.control,
                "planned_date": NEXT_DAY,
                "meal_type": "dinner",
            },
        )

    before = await snapshot(async_session_maker)
    linked, rejected = await interleaving.pair(
        lambda: attachment(client, case, path), same_slot
    )
    assert interleaving.witness == "lock_wait"
    expected = attached_state(before, case, path, linked, case.target)
    assert await snapshot(async_session_maker) == expected
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == (
        "Meal plan already has an item for this date and meal type"
    )
    await assert_plan_read(client, case, expected)


@pytest.mark.parametrize("kind", ["missing", "foreign"])
async def test_recipe_delete_preserves_owner_scoping(client, async_session_maker, kind):
    case = await scenario(client)
    if kind == "foreign":
        _, headers = await create_authenticated_user(client)
        recipe_id = await create_test_recipe(client, headers=headers)
    else:
        recipe_id = str(uuid4())
    before = await snapshot(async_session_maker)
    response = await asyncio.wait_for(
        client.delete(f"{RECIPES_URL}/{recipe_id}", headers=case.headers), 10
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Recipe not found"
    assert await snapshot(async_session_maker) == before
