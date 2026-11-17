"""Versioned portions: exact input precision and omission/null semantics."""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.meal_plan import (
    MealPlanItemCreate,
    MealPlanItemRead,
    MealPlanItemUpdate,
)
from app.schemas.meal_plan_v2 import (
    MealPlanItemV2Create,
    MealPlanItemV2Read,
    MealPlanItemV2Update,
    MealPlanV2Create,
)
from tests.test_meal_plan_v2_schema import item_payload

WRITES = [MealPlanItemV2Create, MealPlanItemV2Update, MealPlanV2Create]


def portion_request(schema, value):
    item = item_payload(planned_servings=value)
    payload = (
        {"title": "Portions", "start_date": "2026-11-16", "items": [item]}
        if schema is MealPlanV2Create
        else item
    )
    model = schema.model_validate(payload)
    return model.items[0] if schema is MealPlanV2Create else model


@pytest.mark.parametrize("schema", WRITES)
@pytest.mark.parametrize("value", [None, "0.01", 0.5, 1, "1.2500", Decimal("12.00")])
def test_portions_accept_exact_hundredths_or_whole_recipe(schema, value):
    result = portion_request(schema, value)
    assert result.planned_servings == (None if value is None else Decimal(str(value)))


@pytest.mark.parametrize("schema", WRITES)
@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        0,
        -1,
        "0.001",
        "12.001",
        "1.005",
        13,
        "NaN",
        "Infinity",
        "-Infinity",
        "",
        [],
        {},
    ],
)
def test_portions_reject_invalid_values_without_rounding(schema, value):
    with pytest.raises(ValidationError):
        portion_request(schema, value)


def test_patch_null_is_distinct_from_omission_and_v1_cannot_change_portions():
    assert MealPlanItemV2Create(**item_payload()).planned_servings is None
    assert MealPlanItemV2Update().model_dump(exclude_unset=True) == {}
    assert MealPlanItemV2Update(planned_servings=None).model_dump(
        exclude_unset=True
    ) == {"planned_servings": None}
    assert MealPlanItemUpdate(planned_servings=2).model_dump(exclude_unset=True) == {}
    assert (
        "planned_servings"
        not in MealPlanItemCreate(**item_payload(planned_servings=2)).model_dump()
    )


def test_v2_read_keeps_legacy_labels_and_v1_projection_hides_count():
    payload = {
        **item_payload(meal_type="brunch"),
        "id": uuid4(),
        "meal_plan_id": uuid4(),
        "planned_servings": "0.5",
    }
    result = MealPlanItemV2Read.model_validate(payload)
    assert result.meal_type == "brunch" and result.planned_servings == Decimal("0.5")
    assert (
        "planned_servings" not in MealPlanItemRead.model_validate(payload).model_dump()
    )
