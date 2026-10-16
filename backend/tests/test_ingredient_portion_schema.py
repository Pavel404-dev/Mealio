"""F3 input/read contract; identical on the tracked-HEAD baseline and fix."""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.ingredient import (
    IngredientCreate,
    IngredientUpdate,
    NutritionValueCreate,
    NutritionValueRead,
)


VALID_PORTIONS = [
    "0.01",
    0.01,
    "999999.99",
    999999.99,
    100,
    100.0,
    "100.00",
    "100.000",
    "0.0100",
    "1e-2",
    "1E+2",
    "123400e-4",
    "999999.9900",
]
INVALID_PORTIONS = [
    "0.001",
    "0.004",
    "0.005",
    "1.234",
    0.001,
    1.234,
    "0",
    "-0.00",
    "-1",
    "1000000",
    "999999.999",
    "1e-100",
    "1e20",
    True,
    False,
    "NaN",
    "sNaN",
    "Infinity",
    "-Infinity",
    "not-a-number",
    "",
    None,
    [],
    {},
    # Context rounding must not erase a significant digit far after scale=2.
    "100.00000000000000000000000000001",
]


@pytest.mark.parametrize("portion", VALID_PORTIONS)
@pytest.mark.parametrize("schema", [NutritionValueCreate, NutritionValueRead])
def test_exact_portion_forms_are_accepted(schema, portion):
    data = schema.model_validate(
        {
            "id": uuid4(),
            "ingredient_id": uuid4(),
            "calories": "1",
            "portion_g": portion,
        }
    )
    assert data.portion_g == Decimal(str(portion))
    assert isinstance(data.model_dump(mode="json")["portion_g"], str)


@pytest.mark.parametrize("portion", INVALID_PORTIONS)
@pytest.mark.parametrize("schema", [IngredientCreate, IngredientUpdate])
def test_invalid_portion_is_rejected_in_both_write_schemas(schema, portion):
    with pytest.raises(ValidationError) as error:
        schema.model_validate(
            {
                "name": "F3 invalid portion",
                "nutrition_value": {"calories": "1", "portion_g": portion},
            }
        )
    assert any(
        e["loc"] == ("nutrition_value", "portion_g") for e in error.value.errors()
    )


@pytest.mark.parametrize("portion", ["0.001", "1.234", "1000000", "NaN"])
def test_read_schema_requires_storable_portion(portion):
    with pytest.raises(ValidationError):
        NutritionValueRead.model_validate(
            {
                "id": uuid4(),
                "ingredient_id": uuid4(),
                "calories": "1",
                "portion_g": portion,
            }
        )


def test_omitted_portion_keeps_default():
    assert NutritionValueCreate(calories=Decimal("1")).portion_g == Decimal("100")


@pytest.mark.parametrize("portion", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_python_numbers_are_rejected(portion):
    with pytest.raises(ValidationError):
        NutritionValueCreate(calories=Decimal("1"), portion_g=portion)


@pytest.mark.parametrize("schema", [IngredientCreate, IngredientUpdate])
def test_omitted_and_null_nutrition_remain_distinct(schema):
    omitted = schema(name="F3 omitted")
    explicit_null = schema(name="F3 null", nutrition_value=None)
    assert omitted.nutrition_value is explicit_null.nutrition_value is None
    assert "nutrition_value" not in omitted.model_fields_set
    assert "nutrition_value" in explicit_null.model_fields_set
