"""Pure projection/schema regressions; no database fixtures or connections."""

import json
from datetime import datetime, timezone
from decimal import Decimal, DefaultContext, ROUND_DOWN, getcontext, localcontext
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from app.schemas.ingredient import (
    IngredientCreate,
    IngredientRead,
    IngredientUpdate,
    NutritionValueCreate,
    NutritionValueRead,
)
from app.schemas.pantry import PantryItemRead
from app.services.gram_nutrition import NUTRIENTS
from app.services.pantry_nutrition import PantryNutritionCalculator
from app.services.recipe_nutrition import RecipeNutritionCalculator


def nutrition(**values):
    return NutritionValueRead(id=uuid4(), ingredient_id=uuid4(), **values)


@pytest.mark.parametrize("field", NUTRIENTS)
@pytest.mark.parametrize(
    "value,portion,expected",
    [
        ("100", "50", "200.00"),
        ("1", "3", "33.33"),
        ("2", "3", "66.67"),
        ("0.01", "200", "0.01"),  # exact half-cent
        ("0.01", "200.01", "0.00"),  # just below the tie
        ("0.01", "199.99", "0.01"),  # just above the tie
        ("1", "200.01", "0.50"),
        ("0.01", "999999.99", "0.00"),
        ("0", "0.01", "0.00"),
        ("999999.99", "0.01", "9999999900.00"),
        ("999999.99", "999999.99", "100.00"),
    ],
)
def test_projection_exact_examples_for_each_nutrient(field, value, portion, expected):
    source = nutrition(**{"calories": "0", field: value, "portion_g": portion})
    result = json.loads(source.model_dump_json())
    assert result["per_100g"][field] == expected
    assert getattr(source, field) == Decimal(value)
    assert source.portion_g == Decimal(portion)
    assert set(result["per_100g"]) == set(NUTRIENTS)
    assert all(
        isinstance(value, Decimal) for value in source.per_100g.model_dump().values()
    )


def test_default_portion_macros_and_unrestricted_read_values():
    # Existing reads accept more precision/range than NutrientWrite. Do not
    # introduce its restrictions on either source or projection fields.
    source = nutrition(calories="1000000.1234")
    assert source.model_dump(mode="json")["per_100g"] == {
        "calories": "1000000.12",
        "protein_g": "0.00",
        "carbs_g": "0.00",
        "fat_g": "0.00",
    }
    assert source.calories == Decimal("1000000.1234")
    assert source.portion_g == 100


def context_state(context):
    return (
        context.prec,
        context.rounding,
        context.Emin,
        context.Emax,
        context.capitals,
        context.clamp,
        dict(context.flags),
        dict(context.traps),
    )


@pytest.mark.parametrize("portion", ["0.01", "3", "200", "200.01", "999999.99"])
def test_projection_ignores_and_preserves_decimal_contexts(monkeypatch, portion):
    source = nutrition(
        calories="999999.99",
        protein_g="0.01",
        carbs_g="1",
        fat_g="0",
        portion_g=portion,
    )
    expected = source.model_dump_json()
    before_global = context_state(getcontext())
    for attribute, value in {
        "prec": 1,
        "rounding": ROUND_DOWN,
        "Emin": -1,
        "Emax": 1,
        "clamp": 1,
        "capitals": 0,
    }.items():
        monkeypatch.setattr(DefaultContext, attribute, value)
    for signal in DefaultContext.traps:
        monkeypatch.setitem(DefaultContext.traps, signal, True)
        monkeypatch.setitem(DefaultContext.flags, signal, True)
    before_default = context_state(DefaultContext)
    with localcontext(DefaultContext) as hostile:
        before = context_state(hostile)
        assert source.model_dump_json() == expected
        assert context_state(hostile) == before
    assert context_state(DefaultContext) == before_default
    assert context_state(getcontext()) == before_global


@pytest.mark.parametrize("schema", [IngredientCreate, IngredientUpdate])
@pytest.mark.parametrize("injected", [{"calories": "999"}, None, "untrusted"])
def test_writes_ignore_projection_and_keep_existing_extra_policy(schema, injected):
    source = schema.model_validate(
        {
            "name": "Synthetic ingredient",
            "unrelated_extra": True,
            "nutrition_value": {"calories": "100", "per_100g": injected},
        }
    )
    assert source.nutrition_value.model_dump() == {
        "calories": Decimal("100"),
        "protein_g": Decimal("0"),
        "carbs_g": Decimal("0"),
        "fat_g": Decimal("0"),
        "portion_g": Decimal("100"),
        "source_name": None,
        "source_reference": None,
    }


def test_read_projection_uses_response_snapshot_and_is_not_cached():
    raw = NS(
        id=uuid4(),
        ingredient_id=uuid4(),
        calories=Decimal("100"),
        protein_g=Decimal("2"),
        carbs_g=Decimal("3"),
        fat_g=Decimal("4"),
        portion_g=Decimal("50"),
        per_100g={"calories": "999"},
    )
    before = vars(raw).copy()
    source = NutritionValueRead.model_validate(raw)
    assert source.model_dump(mode="json")["per_100g"]["calories"] == "200.00"
    assert vars(raw) == before
    raw.calories = Decimal("7")
    assert source.per_100g.calories == Decimal("200.00")
    source.calories = Decimal("50")
    assert source.per_100g.calories == Decimal("100.00")


def test_missing_nutrition_stays_null_in_nested_serialization():
    now = datetime.now(timezone.utc)
    ingredient = IngredientRead(id=uuid4(), name="Missing", created_at=now)
    pantry = PantryItemRead(
        id=uuid4(),
        user_id=uuid4(),
        ingredient_id=ingredient.id,
        quantity_g="1",
        expires_at=None,
        created_at=now,
        updated_at=now,
        ingredient=ingredient,
    )
    assert ingredient.model_dump(mode="json")["nutrition_value"] is None
    assert pantry.model_dump(mode="json")["ingredient"]["nutrition_value"] is None


@pytest.mark.parametrize(
    "value,portion,quantity,projection,total",
    [("100", "50", "125", "200.00", "250.00"), ("1", "200.01", "1", "0.50", "0.00")],
)
def test_rounded_projection_never_drives_aggregates(
    value, portion, quantity, projection, total
):
    source = nutrition(calories=value, portion_g=portion)
    assert source.model_dump(mode="json")["per_100g"]["calories"] == projection
    rows = [NS(quantity_g=Decimal(quantity), ingredient=NS(nutrition_value=source))]
    recipe = RecipeNutritionCalculator().calculate_from_recipe(
        NS(recipe_ingredients=rows)
    )
    assert str(recipe.total_calories) == total
    pantry = PantryNutritionCalculator().calculate_from_pantry_items(rows)
    if quantity == "125":
        assert pantry.total_calories == Decimal("250")
    else:
        assert Decimal("0") < pantry.total_calories < Decimal("0.005")


def test_openapi_uses_read_projection_only():
    # Building OpenAPI is a pure operation: no ASGI requests or DB fixtures.
    from app.main import app

    schema = app.openapi()
    components = schema["components"]["schemas"]
    read = components["NutritionValueRead"]
    assert read["properties"]["per_100g"]["readOnly"] is True
    assert "per_100g" in read["required"]
    assert "per_100g" not in components["NutritionValueCreate"]["properties"]
    for field, limit in [("source_name", 255), ("source_reference", 1000)]:
        write = components["NutritionValueCreate"]["properties"][field]
        assert (
            NutritionValueCreate.model_json_schema()["properties"][field]["default"]
            is None
        )
        assert write["anyOf"] == [
            {"type": "string", "maxLength": limit, "minLength": 1},
            {"type": "null"},
        ]
        assert field not in components["NutritionValueCreate"]["required"]
        assert read["properties"][field]["anyOf"] == [
            {"type": "string"},
            {"type": "null"},
        ]
    assert "per_100g" not in NutritionValueRead.model_json_schema()["properties"]
    for field in NUTRIENTS:
        assert (
            components["NutritionPer100gRead"]["properties"][field]["type"] == "string"
        )
    for name in ("IngredientCreate", "IngredientUpdate"):
        assert components[name]["properties"]["nutrition_value"]["anyOf"][0] == {
            "$ref": "#/components/schemas/NutritionValueCreate"
        }
    assert components["IngredientRead"]["properties"]["nutrition_value"]["anyOf"][
        0
    ] == {"$ref": "#/components/schemas/NutritionValueRead"}
    assert components["PantryItemRead"]["properties"]["ingredient"] == {
        "$ref": "#/components/schemas/IngredientRead"
    }
    for path, method, status, name, is_list in [
        ("/ingredients", "get", "200", "IngredientRead", True),
        ("/ingredients", "post", "201", "IngredientRead", False),
        ("/ingredients/{ingredient_id}", "get", "200", "IngredientRead", False),
        ("/ingredients/{ingredient_id}", "patch", "200", "IngredientRead", False),
        ("/pantry", "get", "200", "PantryItemRead", True),
        ("/pantry", "post", "201", "PantryItemRead", False),
        ("/pantry/{pantry_item_id}", "patch", "200", "PantryItemRead", False),
    ]:
        response = schema["paths"][f"/api/v1{path}"][method]["responses"][status]
        shape = response["content"]["application/json"]["schema"]
        assert (shape["items"] if is_list else shape)[
            "$ref"
        ] == f"#/components/schemas/{name}"
