from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.ai_recipe import GeneratedRecipeIngredient


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1, Decimal("1")),
        ("300", Decimal("300")),
        ("15.75", Decimal("15.75")),
        (Decimal("0.01"), Decimal("0.01")),
    ],
)
def test_generated_recipe_ingredient_accepts_positive_quantity_g(
    value,
    expected: Decimal,
) -> None:
    ingredient = GeneratedRecipeIngredient(name="Rice", quantity_g=value)

    assert ingredient.quantity_g == expected


@pytest.mark.parametrize(
    "value",
    [
        0,
        "0",
        -1,
        "-0.01",
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_generated_recipe_ingredient_rejects_non_positive_or_non_finite_quantity_g(
    value,
) -> None:
    with pytest.raises(ValidationError):
        GeneratedRecipeIngredient(name="Rice", quantity_g=value)


def test_generated_recipe_ingredient_trims_name() -> None:
    ingredient = GeneratedRecipeIngredient(name="  Chicken breast  ", quantity_g="300")

    assert ingredient.name == "Chicken breast"


def test_generated_recipe_ingredient_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        GeneratedRecipeIngredient(name="   ", quantity_g="100")


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Rice", "quantity": "160", "unit": "g"},
        {
            "name": "Rice",
            "quantity_g": "160",
            "quantity": "160",
            "unit": "g",
        },
        {"name": "Rice", "quantity_g": "160", "unexpected": "field"},
    ],
)
def test_generated_recipe_ingredient_rejects_legacy_and_extra_fields(
    payload: dict,
) -> None:
    with pytest.raises(ValidationError):
        GeneratedRecipeIngredient.model_validate(payload)


def test_generated_recipe_ingredient_serializes_only_quantity_g() -> None:
    ingredient = GeneratedRecipeIngredient(name="Rice", quantity_g="160.5")

    assert ingredient.model_dump() == {
        "name": "Rice",
        "quantity_g": Decimal("160.5"),
    }
