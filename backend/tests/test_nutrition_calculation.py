import asyncio
from datetime import date, datetime
from decimal import Decimal, DefaultContext, ROUND_DOWN, getcontext, localcontext

import pytest
from pydantic import ValidationError

from app.schemas.nutrition_calculation import (
    RULES_VERSION,
    NutritionCalculationInput,
    NutritionCalculationRequest,
)
from app.schemas import user_nutrition_profile as profile_schemas
from app.services.nutrition_calculation import NutritionCalculator

DAY = date(2026, 10, 4)
ACTIVITIES = (
    "sedentary",
    "lightly_active",
    "moderately_active",
    "very_active",
    "extra_active",
)
GOALS = ("lose_weight", "maintain", "gain_weight")


def snapshot(**overrides):
    return NutritionCalculationInput(
        **{
            "sex": "male",
            "birth_date": date(1996, 10, 4),
            "height_cm": Decimal("180.0"),
            "weight_kg": Decimal("80.00"),
            "activity_level": "moderately_active",
            "goal": "maintain",
            **overrides,
        }
    )


def calculate(**overrides):
    return NutritionCalculator().calculate(snapshot(**overrides), calculation_date=DAY)


# Literal oracles derived independently with rational arithmetic (Fraction),
# never by this calculator. Rows: sex, activity index, goal index, REE, TDEE,
# calories, protein, fat, carbs, energy discrepancy.
REFERENCES = [
    ("male", 0, 0, "1780.00", "2492.00", 2243, 112, 75, 280, 0),
    ("male", 0, 1, "1780.00", "2492.00", 2492, 125, 83, 311, -1),
    ("male", 0, 2, "1780.00", "2492.00", 2741, 137, 91, 344, 2),
    ("male", 1, 0, "1780.00", "2848.00", 2563, 128, 85, 322, 2),
    ("male", 1, 1, "1780.00", "2848.00", 2848, 142, 95, 356, -1),
    ("male", 1, 2, "1780.00", "2848.00", 3133, 157, 104, 392, -1),
    ("male", 2, 0, "1780.00", "3204.00", 2884, 144, 96, 361, 0),
    ("male", 2, 1, "1780.00", "3204.00", 3204, 160, 107, 400, -1),
    ("male", 2, 2, "1780.00", "3204.00", 3524, 176, 117, 442, 1),
    ("male", 3, 0, "1780.00", "3560.00", 3204, 160, 107, 400, -1),
    ("male", 3, 1, "1780.00", "3560.00", 3560, 178, 119, 444, -1),
    ("male", 3, 2, "1780.00", "3560.00", 3916, 196, 131, 488, -1),
    ("male", 4, 0, "1780.00", "3916.00", 3524, 176, 117, 442, 1),
    ("male", 4, 1, "1780.00", "3916.00", 3916, 196, 131, 488, -1),
    ("male", 4, 2, "1780.00", "3916.00", 4308, 215, 144, 538, 0),
    ("female", 0, 0, "1320.25", "1848.35", 1664, 83, 55, 209, -1),
    ("female", 0, 1, "1320.25", "1848.35", 1848, 92, 62, 231, 2),
    ("female", 0, 2, "1320.25", "1848.35", 2033, 102, 68, 253, -1),
    ("female", 1, 0, "1320.25", "2112.40", 1901, 95, 63, 239, 2),
    ("female", 1, 1, "1320.25", "2112.40", 2112, 106, 70, 265, 2),
    ("female", 1, 2, "1320.25", "2112.40", 2324, 116, 77, 292, 1),
    ("female", 2, 0, "1320.25", "2376.45", 2139, 107, 71, 268, 0),
    ("female", 2, 1, "1320.25", "2376.45", 2376, 119, 79, 297, -1),
    ("female", 2, 2, "1320.25", "2376.45", 2614, 131, 87, 327, 1),
    ("female", 3, 0, "1320.25", "2640.50", 2376, 119, 79, 297, -1),
    ("female", 3, 1, "1320.25", "2640.50", 2641, 132, 88, 330, -1),
    ("female", 3, 2, "1320.25", "2640.50", 2905, 145, 97, 363, 0),
    ("female", 4, 0, "1320.25", "2904.55", 2614, 131, 87, 327, 1),
    ("female", 4, 1, "1320.25", "2904.55", 2905, 145, 97, 363, 0),
    ("female", 4, 2, "1320.25", "2904.55", 3195, 160, 107, 398, 0),
]


@pytest.mark.parametrize("sex,activity,goal,ree,tdee,c,p,f,carbs,delta", REFERENCES)
def test_exact_references(sex, activity, goal, ree, tdee, c, p, f, carbs, delta):
    inputs = snapshot(
        sex=sex,
        height_cm=Decimal("180.0" if sex == "male" else "165.0"),
        weight_kg=Decimal("80.00" if sex == "male" else "60.00"),
        activity_level=ACTIVITIES[activity],
        goal=GOALS[goal],
    )
    outcome = NutritionCalculator().calculate(inputs, calculation_date=DAY)
    assert outcome.model_dump(mode="json") == {
        "status": "calculated",
        "rules_version": RULES_VERSION,
        "calculation_date": "2026-10-04",
        "result": {
            "age_years": 30,
            "used_inputs": inputs.model_dump(mode="json"),
            "activity_factor": ["1.40", "1.60", "1.80", "2.00", "2.20"][activity],
            "goal_factor": ["0.90", "1.00", "1.10"][goal],
            "ree_kcal": ree,
            "tdee_kcal": tdee,
            "calories_target_kcal": c,
            "protein_target_g": p,
            "fat_target_g": f,
            "carbs_target_g": carbs,
            "energy_delta_kcal": delta,
        },
    }
    assert 4 * p + 9 * f + 4 * carbs - c == delta


@pytest.mark.parametrize(
    "birthday,day,age",
    [
        ("2007-10-04", "2026-10-03", None),
        ("2007-10-04", "2026-10-04", 19),
        ("2007-10-04", "2026-10-05", 19),
        ("1947-10-04", "2026-10-03", 78),
        ("1947-10-04", "2026-10-04", None),
        ("1947-10-04", "2026-10-05", None),
        ("1996-02-29", "2025-02-28", 28),
        ("1996-02-29", "2025-03-01", 29),
        ("1996-02-29", "2024-02-28", 27),
        ("1996-02-29", "2024-02-29", 28),
        ("1996-02-29", "2024-03-01", 28),
        ("1980-02-29", "2000-02-28", 19),
        ("1980-02-29", "2000-02-29", 20),
        ("2080-02-29", "2100-02-28", 19),
        ("2080-02-29", "2100-03-01", 20),
        ("1870-10-04", "1900-10-04", 30),
    ],
)
def test_age_and_historical_dates(birthday, day, age, monkeypatch):
    def clock_forbidden():
        pytest.fail("W5 must not use the W4 wall clock validator")

    monkeypatch.setattr(profile_schemas, "utc_today", clock_forbidden)
    outcome = NutritionCalculator().calculate(
        snapshot(birth_date=date.fromisoformat(birthday)),
        calculation_date=date.fromisoformat(day),
    )
    if age is None:
        assert outcome.reason_codes == ("age_out_of_range",)
        assert outcome.result is None
    else:
        assert outcome.result.age_years == age


def test_birth_after_date_and_failure_precedence():
    result = calculate(birth_date=date(2027, 1, 1), height_cm=Decimal("1"))
    assert result.reason_codes == ("birth_date_after_calculation_date",)
    assert result.result is None
    result = calculate(birth_date=date(2027, 1, 1), weight_kg=None)
    assert result.missing_fields == ("weight_kg",)
    empty = NutritionCalculator().calculate(
        NutritionCalculationInput(), calculation_date=DAY
    )
    assert empty.missing_fields == (
        "sex",
        "birth_date",
        "height_cm",
        "weight_kg",
        "activity_level",
        "goal",
    )
    assert empty.result is None


@pytest.mark.parametrize(
    "height,weight,reason",
    [
        ("130.0", "35.00", None),
        ("129.9", "35.00", "height_out_of_range"),
        ("230.0", "100.00", None),
        ("230.1", "100.00", "height_out_of_range"),
        ("130.0", "34.99", "weight_out_of_range"),
        ("200.0", "74.00", None),
        ("200.0", "73.99", "bmi_out_of_range"),
        ("200.0", "159.99", None),
        ("200.0", "160.00", "bmi_out_of_range"),
        # At 250 kg even the tallest supported profile violates BMI < 40. The
        # weight edge itself passes; it cannot be a calculated production example.
        ("230.0", "250.00", "bmi_out_of_range"),
        ("230.0", "250.01", "weight_out_of_range"),
        ("0", "80", "height_out_of_range"),
        ("180", "-1", "weight_out_of_range"),
    ],
)
def test_measurement_and_exact_bmi_boundaries(height, weight, reason):
    outcome = calculate(height_cm=Decimal(height), weight_kg=Decimal(weight))
    if reason:
        assert outcome.reason_codes == (reason,)
        assert outcome.result is None
    else:
        assert outcome.status == "calculated"


@pytest.mark.parametrize(
    "age,height,weight,activity,goal,expected",
    [
        (76, "130.0", "35.35", "lightly_active", "maintain", 1000),
        (76, "130.0", "35.34", "lightly_active", "maintain", None),  # 999.84
        (76, "130.0", "35.36", "lightly_active", "maintain", 1000),  # 1000.16
        (19, "218.0", "189.35", "very_active", "maintain", 6000),
        (19, "218.0", "189.34", "very_active", "maintain", 6000),  # 5999.8
        (19, "218.0", "189.36", "very_active", "maintain", None),  # 6000.2
        (19, "130.2", "44.25", "very_active", "maintain", 2001),  # 2000.5
        (78, "130.0", "35.00", "sedentary", "lose_weight", None),
    ],
)
def test_raw_calorie_bounds_and_half_up(age, height, weight, activity, goal, expected):
    outcome = calculate(
        sex="female",
        birth_date=date(2026 - age, 10, 4),
        height_cm=Decimal(height),
        weight_kg=Decimal(weight),
        activity_level=activity,
        goal=goal,
    )
    if expected is None:
        assert outcome.reason_codes == ("calories_out_of_range",)
        assert outcome.result is None
    else:
        assert outcome.result.calories_target_kcal == expected


@pytest.mark.parametrize(
    "weight,c,p,f,carbs,delta",
    [
        ("41.85", 2090, 105, 70, 260, 0),
        ("43.10", 2115, 106, 71, 263, 0),
    ],
)
def test_protein_and_fat_half_ties(weight, c, p, f, carbs, delta):
    result = calculate(
        sex="female",
        height_cm=Decimal("150.0"),
        weight_kg=Decimal(weight),
        activity_level="very_active",
    ).result
    assert (
        result.calories_target_kcal,
        result.protein_target_g,
        result.fat_target_g,
        result.carbs_target_g,
        result.energy_delta_kcal,
    ) == (c, p, f, carbs, delta)


def test_display_rounding_never_feeds_downstream_math():
    # Exact REE=1323.925, TDEE=1853.495. Rounding either intermediate
    # to 0.01 first incorrectly raises the integer target to 1854.
    result = calculate(
        sex="female",
        height_cm=Decimal("165.3"),
        weight_kg=Decimal("60.18"),
        activity_level="sedentary",
    ).result
    assert result.ree_kcal == Decimal("1323.93")
    assert result.tdee_kcal == Decimal("1853.50")
    assert result.calories_target_kcal == 1853
    assert (result.protein_target_g, result.fat_target_g, result.carbs_target_g) == (
        93,
        62,
        231,
    )
    assert result.energy_delta_kcal == 1


@pytest.mark.parametrize(
    "field", ["sex", "birth_date", "height_cm", "weight_kg", "activity_level", "goal"]
)
def test_each_required_field_is_reported_without_targets(field):
    outcome = calculate(**{field: None})
    assert outcome.status == "incomplete_profile"
    assert outcome.missing_fields == (field,)
    assert outcome.result is None


@pytest.mark.parametrize(
    "field,bad",
    [
        *[
            (field, bad)
            for field in ("height_cm", "weight_kg")
            for bad in (
                True,
                False,
                180,
                180.0,
                "180.0",
                "malformed",
                Decimal("NaN"),
                Decimal("sNaN"),
                Decimal("Infinity"),
                Decimal("-Infinity"),
            )
        ],
        ("height_cm", Decimal("180.00")),
        ("weight_kg", Decimal("80.000")),
        ("birth_date", datetime(1996, 10, 4)),
        ("birth_date", "1996-10-04"),
        ("sex", "unknown"),
        ("goal", "unknown"),
        ("activity_level", "active"),
    ],
)
def test_internal_input_invariants(field, bad):
    with pytest.raises(ValidationError):
        snapshot(**{field: bad})
    forged = snapshot().model_copy(update={field: bad})
    with pytest.raises(ValidationError):
        NutritionCalculator().calculate(forged, calculation_date=DAY)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"calculation_date": None},
        *[
            {"calculation_date": value}
            for value in (
                True,
                0,
                1791072000,
                1.5,
                "2026-10-04T00:00:00Z",
                "20261004",
                "2026-1-04",
                "2026-02-29",
                " 2026-10-04",
                "2026-10-04 ",
            )
        ],
        *[
            {"calculation_date": "2026-10-04", "rules_version": value}
            for value in (None, 1, True, [], {}, "unknown", "mealio-nutrition-v2")
        ],
        *[
            {"calculation_date": "2026-10-04", field: "synthetic-override"}
            for field in ("user_id", "id", "age", "profile", "weight_kg")
        ],
    ],
)
def test_request_contract_rejects_malformed_values(payload):
    with pytest.raises(ValidationError):
        NutritionCalculationRequest.model_validate(payload)


def test_fixed_version_and_immutable_results():
    request = NutritionCalculationRequest(calculation_date="2026-10-04")
    assert request.rules_version == RULES_VERSION
    result = calculate()
    for model, field, value in [
        (snapshot(), "goal", "lose_weight"),
        (result, "status", "unsupported_profile"),
        (result.result, "protein_target_g", 0),
        (result.result.used_inputs, "weight_kg", Decimal("1")),
    ]:
        with pytest.raises(ValidationError):
            setattr(model, field, value)
    for version in (None, "unknown", "mealio-nutrition-v2"):
        with pytest.raises(ValidationError):
            NutritionCalculator().calculate(
                snapshot(), calculation_date=DAY, rules_version=version
            )


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


def test_ambient_and_default_decimal_contexts_do_not_change_rules(monkeypatch):
    expected = calculate(
        sex="female",
        height_cm=Decimal("165.0"),
        weight_kg=Decimal("60.00"),
        activity_level="sedentary",
        goal="lose_weight",
    )
    global_before = context_state(getcontext())
    monkeypatch.setattr(DefaultContext, "prec", 1)
    monkeypatch.setattr(DefaultContext, "rounding", ROUND_DOWN)
    with localcontext() as hostile:
        hostile.prec = 1
        hostile.rounding = ROUND_DOWN
        hostile.Emax = 1
        hostile.Emin = -1
        hostile.clamp = 1
        for signal in hostile.traps:
            hostile.traps[signal] = True
            hostile.flags[signal] = True
        before = context_state(hostile)
        for _ in range(3):
            assert (
                calculate(
                    sex="female",
                    height_cm=Decimal("165.0"),
                    weight_kg=Decimal("60.00"),
                    activity_level="sedentary",
                    goal="lose_weight",
                )
                == expected
            )
            assert calculate(
                height_cm=Decimal("200.0"), weight_kg=Decimal("73.99")
            ).reason_codes == ("bmi_out_of_range",)
            assert calculate(weight_kg=None).result is None
        assert context_state(hostile) == before
    assert context_state(getcontext()) == global_before


async def test_independent_task_contexts():
    async def run(precision, goal):
        with localcontext() as context:
            context.prec = precision
            context.rounding = ROUND_DOWN
            await asyncio.sleep(0)
            outcome = calculate(goal=goal)
            assert context.prec == precision
            return outcome.result.calories_target_kcal

    assert await asyncio.gather(
        run(1, "maintain"), run(2, "gain_weight"), run(28, "lose_weight")
    ) == [3204, 3524, 2884]
