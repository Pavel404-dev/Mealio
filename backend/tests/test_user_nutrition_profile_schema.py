from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import user_nutrition_profile as schemas
from app.schemas.user_nutrition_profile import (
    UserNutritionProfileCreate,
    UserNutritionProfileRead,
    UserNutritionProfileUpdate,
)

DECIMAL_FIELDS = {
    "height_cm": ("50.0", "250.0", "49.9", "250.1", "170.01", "170.00"),
    "weight_kg": ("10.00", "500.00", "9.99", "500.01", "70.001", "70.000"),
    "weekly_food_budget_amount": (
        "0.01",
        "1000000.00",
        "0.00",
        "1000000.01",
        "25.001",
        "25.000",
    ),
}


@pytest.mark.parametrize(
    "schema", [UserNutritionProfileCreate, UserNutritionProfileUpdate]
)
@pytest.mark.parametrize(
    ("field", "value"),
    [
        (field, value)
        for field, bounds in DECIMAL_FIELDS.items()
        for value in bounds[:2]
    ],
)
def test_decimal_boundaries(schema, field, value):
    assert getattr(schema.model_validate({field: value}), field) == Decimal(value)


@pytest.mark.parametrize(
    "schema", [UserNutritionProfileCreate, UserNutritionProfileUpdate]
)
@pytest.mark.parametrize(
    ("field", "value"),
    [
        (field, value)
        for field, bounds in DECIMAL_FIELDS.items()
        for value in [
            *bounds[2:],
            True,
            False,
            "NaN",
            "sNaN",
            "Infinity",
            "-Infinity",
            float("nan"),
            float("inf"),
        ]
    ],
)
def test_invalid_decimals(schema, field, value):
    with pytest.raises(ValidationError):
        schema.model_validate({field: value})


@pytest.mark.parametrize("value", [1, 480])
def test_cooking_time_boundaries(value):
    assert (
        UserNutritionProfileUpdate(
            max_cooking_time_minutes=value
        ).max_cooking_time_minutes
        == value
    )


@pytest.mark.parametrize("value", [0, 481, True, False, 1.5, 1.0, "1"])
def test_cooking_time_is_strict_integer(value):
    with pytest.raises(ValidationError):
        UserNutritionProfileUpdate(max_cooking_time_minutes=value)


@pytest.mark.parametrize("value", ["male", "female", None])
def test_sex_values(value):
    assert UserNutritionProfileUpdate(sex=value).sex == value


@pytest.mark.parametrize(
    "value",
    [
        "sedentary",
        "lightly_active",
        "moderately_active",
        "very_active",
        "extra_active",
        None,
    ],
)
def test_activity_values(value):
    assert UserNutritionProfileUpdate(activity_level=value).activity_level == value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sex", "other"),
        ("sex", True),
        ("activity_level", "active"),
        ("activity_level", 1),
    ],
)
def test_invalid_categories(field, value):
    with pytest.raises(ValidationError):
        UserNutritionProfileUpdate.model_validate({field: value})


@pytest.mark.parametrize(
    "schema", [UserNutritionProfileCreate, UserNutritionProfileUpdate]
)
@pytest.mark.parametrize("value", ["1900-01-01", "2026-10-04", None])
def test_birth_date_boundaries(schema, value, monkeypatch):
    monkeypatch.setattr(schemas, "utc_today", lambda: date(2026, 10, 4))
    assert schema(birth_date=value).birth_date == (
        date.fromisoformat(value) if value else None
    )


@pytest.mark.parametrize(
    "schema", [UserNutritionProfileCreate, UserNutritionProfileUpdate]
)
@pytest.mark.parametrize(
    "value",
    [
        "1899-12-31",
        "2026-10-05",
        "2026-02-30",
        "2026-10-04T00:00:00Z",
        "20261004",
        "2026-1-01",
        0,
        True,
    ],
)
def test_invalid_birth_date(schema, value, monkeypatch):
    monkeypatch.setattr(schemas, "utc_today", lambda: date(2026, 10, 4))
    with pytest.raises(ValidationError):
        schema(birth_date=value)


def test_utc_today_uses_utc(monkeypatch):
    real_datetime = schemas.datetime

    class Clock:
        @staticmethod
        def now(tz):
            assert tz is schemas.UTC
            return real_datetime(2026, 10, 4, 0, 0, tzinfo=tz)

    monkeypatch.setattr(schemas, "datetime", Clock)
    assert schemas.utc_today() == date(2026, 10, 4)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" eur ", "EUR"),
        ("\u00a0eur\u00a0", "EUR"),
        ("usd", "USD"),
        ("zzz", "ZZZ"),
        (None, None),
    ],
)
def test_currency_normalization_format_only(value, expected):
    assert UserNutritionProfileUpdate(budget_currency=value).budget_currency == expected


@pytest.mark.parametrize(
    "value", ["", "EU", "EURO", "E1R", "€UR", "ßa", "ＥＵＲ", "E R", 123, True]
)
def test_invalid_currency(value):
    with pytest.raises(ValidationError):
        UserNutritionProfileUpdate(budget_currency=value)


@pytest.mark.parametrize(
    "field",
    [
        "daily_calories_target",
        "daily_protein_target_g",
        "daily_carbs_target_g",
        "daily_fat_target_g",
    ],
)
def test_existing_integer_targets_postgres_limit(field):
    assert (
        getattr(
            UserNutritionProfileUpdate.model_validate({field: 2_147_483_647}), field
        )
        == 2_147_483_647
    )
    with pytest.raises(ValidationError):
        UserNutritionProfileUpdate.model_validate({field: 2_147_483_648})


def test_partial_fields_and_decimal_json_representation():
    patch = UserNutritionProfileUpdate(height_cm=170.5, weight_kg="70.25")
    assert patch.model_dump(exclude_unset=True) == {
        "height_cm": Decimal("170.5"),
        "weight_kg": Decimal("70.25"),
    }
    read = UserNutritionProfileRead.model_validate(patch.model_dump())
    assert read.model_dump(mode="json")["height_cm"] == "170.5"
    assert read.model_dump(mode="json")["weight_kg"] == "70.25"
