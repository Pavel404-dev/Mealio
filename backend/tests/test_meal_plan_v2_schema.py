"""Canonical writes without narrowing legacy request or response contracts."""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.main import app
from app.schemas.meal_plan import (
    MealPlanCreate,
    MealPlanItemCreate,
    MealPlanItemRead,
    MealPlanItemUpdate,
)
from app.schemas.meal_plan_v2 import (
    MealPlanItemV2Create,
    MealPlanItemV2Update,
    MealPlanV2Create,
)

WRITE_SCHEMAS = [MealPlanItemV2Create, MealPlanItemV2Update, MealPlanV2Create]


def item_payload(**changes):
    return {
        "recipe_id": uuid4(),
        "planned_date": "2026-11-16",
        "meal_type": "lunch",
        **changes,
    }


def payload_for(schema, value):
    item = item_payload(meal_type=value)
    if schema is MealPlanV2Create:
        return {"title": "Canonical slots", "start_date": "2026-11-16", "items": [item]}
    return item


@pytest.mark.parametrize("schema", WRITE_SCHEMAS)
@pytest.mark.parametrize("meal_type", ["breakfast", "lunch", "dinner", "snack"])
def test_all_canonical_writes_normalize_case_and_whitespace(schema, meal_type):
    request = schema.model_validate(payload_for(schema, f" \t{meal_type.upper()}\n"))
    item = request.items[0] if schema is MealPlanV2Create else request
    assert item.meal_type == meal_type


@pytest.mark.parametrize("schema", WRITE_SCHEMAS)
@pytest.mark.parametrize(
    "value",
    [None, "", " \t\n", "brunch", "завтрак", "snacks", True, 1, 1.5, [], {}, "x" * 51],
)
def test_noncanonical_values_are_rejected_in_every_write(schema, value):
    with pytest.raises(ValidationError):
        schema.model_validate(payload_for(schema, value))


def test_patch_omission_does_not_turn_into_null_or_reclassify_a_legacy_slot():
    request = MealPlanItemV2Update(planned_date="2026-11-17")
    assert request.model_dump(exclude_unset=True) == {
        "planned_date": date(2026, 11, 17)
    }
    assert MealPlanItemV2Update().model_dump(exclude_unset=True) == {}
    for field in ["meal_type", "recipe_id", "planned_date"]:
        with pytest.raises(ValidationError):
            MealPlanItemV2Update.model_validate({field: None})


@pytest.mark.parametrize("schema", WRITE_SCHEMAS)
def test_v2_rejects_unknown_fields_instead_of_silently_ignoring_them(schema):
    payload = payload_for(schema, "lunch")
    with pytest.raises(ValidationError):
        schema.model_validate({**payload, "meal_slot": "dinner"})
    if schema is MealPlanV2Create:
        payload["items"][0]["meal_slot"] = "dinner"
        with pytest.raises(ValidationError):
            schema.model_validate(payload)


def test_v1_custom_requests_and_legacy_reads_remain_valid():
    payload = item_payload(meal_type="brunch")
    assert MealPlanItemCreate.model_validate(payload).meal_type == "brunch"
    assert MealPlanItemUpdate(meal_type="brunch").meal_type == "brunch"
    assert (
        MealPlanCreate(title="Legacy", start_date="2026-11-16", items=[payload])
        .items[0]
        .meal_type
        == "brunch"
    )
    assert (
        MealPlanItemRead.model_validate(
            {**payload, "id": uuid4(), "meal_plan_id": uuid4()}
        ).meal_type
        == "brunch"
    )


def test_openapi_exposes_separate_write_contracts_with_shared_legacy_safe_responses():
    spec = app.openapi()
    paths = [
        ("/meal-plans", "post", "MealPlan"),
        ("/meal-plans/{meal_plan_id}/items", "post", "MealPlanItem"),
        ("/meal-plans/{meal_plan_id}/items/{item_id}", "patch", "MealPlanItem"),
    ]
    for path, method, schema in paths:
        v1 = spec["paths"][f"/api/v1{path}"][method]
        v2 = spec["paths"][f"/api/v2{path}"][method]
        suffix = "Update" if method == "patch" else "Create"
        for operation, version in [(v1, ""), (v2, "V2")]:
            assert operation["requestBody"]["content"]["application/json"][
                "schema"
            ] == {"$ref": f"#/components/schemas/{schema}{version}{suffix}"}
        assert v2["responses"] == v1["responses"]
        assert v2["security"] == v1["security"]
    schemas = spec["components"]["schemas"]
    canonical = ["breakfast", "lunch", "dinner", "snack"]
    assert (
        schemas["MealPlanItemV2Create"]["properties"]["meal_type"]["enum"] == canonical
    )
    assert (
        schemas["MealPlanItemV2Update"]["properties"]["meal_type"]["anyOf"][0]["enum"]
        == canonical
    )
    assert "enum" not in schemas["MealPlanItemCreate"]["properties"]["meal_type"]
    assert "enum" not in schemas["MealPlanItemRead"]["properties"]["meal_type"]
