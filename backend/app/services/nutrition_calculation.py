"""Pure, versioned personal nutrition estimate. No clocks, I/O, or ORM objects."""

from datetime import date
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    FloatOperation,
    InvalidOperation,
    Overflow,
    ROUND_HALF_UP,
    localcontext,
)
from types import MappingProxyType

from app.schemas.nutrition_calculation import (
    RULES_VERSION,
    CalculatedNutrition,
    IncompleteNutritionProfile,
    NutritionCalculationInput,
    NutritionCalculationOutcome,
    NutritionCalculationRequest,
    NutritionCalculationResult,
    NutritionUsedInputs,
    UnsupportedNutritionProfile,
)

_REQUIRED_FIELDS = (
    "sex",
    "birth_date",
    "height_cm",
    "weight_kg",
    "activity_level",
    "goal",
)
_ACTIVITY_FACTORS = MappingProxyType(
    {
        "sedentary": Decimal("1.40"),
        "lightly_active": Decimal("1.60"),
        "moderately_active": Decimal("1.80"),
        "very_active": Decimal("2.00"),
        "extra_active": Decimal("2.20"),
    }
)
_GOAL_FACTORS = MappingProxyType(
    {
        "lose_weight": Decimal("0.90"),
        "maintain": Decimal("1.00"),
        "gain_weight": Decimal("1.10"),
    }
)
_OFFSETS = MappingProxyType({"male": Decimal("5"), "female": Decimal("-161")})


class NutritionCalculationInvariantError(RuntimeError):
    """A programming/arithmetic defect, never an expected profile outcome."""


class NutritionCalculator:
    def calculate(
        self,
        profile: NutritionCalculationInput,
        *,
        calculation_date: date,
        rules_version: str = RULES_VERSION,
    ) -> NutritionCalculationOutcome:
        # Revalidate internal callers too, including model_copy-created inputs.
        request = NutritionCalculationRequest(
            calculation_date=calculation_date, rules_version=rules_version
        )
        profile = NutritionCalculationInput.model_validate(profile)
        calculation_date = request.calculation_date
        missing = tuple(
            field for field in _REQUIRED_FIELDS if getattr(profile, field) is None
        )
        if missing:
            return IncompleteNutritionProfile(
                calculation_date=calculation_date, missing_fields=missing
            )

        inputs = NutritionUsedInputs(**profile.model_dump())
        # Every Context setting is explicit, including flags and traps; neither
        # the ambient context nor decimal.DefaultContext supplies rule settings.
        context = Context(
            prec=28,
            rounding=ROUND_HALF_UP,
            Emin=-999999,
            Emax=999999,
            capitals=1,
            clamp=0,
            flags=[],
            traps=[InvalidOperation, DivisionByZero, Overflow, FloatOperation],
        )
        with localcontext(context):
            return self._calculate_v1(inputs, calculation_date)

    def _calculate_v1(
        self, inputs: NutritionUsedInputs, calculation_date: date
    ) -> NutritionCalculationOutcome:
        def unsupported(reason):
            return UnsupportedNutritionProfile(
                calculation_date=calculation_date, reason_codes=(reason,)
            )

        birth = inputs.birth_date
        if birth > calculation_date:
            return unsupported("birth_date_after_calculation_date")
        age = (
            calculation_date.year
            - birth.year
            - (
                (calculation_date.month, calculation_date.day)
                < (birth.month, birth.day)
            )
        )
        if not 19 <= age <= 78:
            return unsupported("age_out_of_range")
        height, weight = inputs.height_cm, inputs.weight_kg
        if not Decimal("130.0") <= height <= Decimal("230.0"):
            return unsupported("height_out_of_range")
        if not Decimal("35.00") <= weight <= Decimal("250.00"):
            return unsupported("weight_out_of_range")
        # Exact cross-products on bounded, fixed-scale inputs; no BMI division.
        height_squared = height * height
        scaled_weight = weight * Decimal("10000")
        if not (
            Decimal("18.5") * height_squared
            <= scaled_weight
            < Decimal("40") * height_squared
        ):
            return unsupported("bmi_out_of_range")

        activity_factor = _ACTIVITY_FACTORS[inputs.activity_level]
        goal_factor = _GOAL_FACTORS[inputs.goal]
        ree = (
            Decimal("10") * weight
            + Decimal("6.25") * height
            - Decimal("5") * age
            + _OFFSETS[inputs.sex]
        )
        tdee = ree * activity_factor
        if ree <= 0 or tdee <= 0:
            return unsupported("nonpositive_energy")
        raw_calories = tdee * goal_factor
        if not Decimal("1000") <= raw_calories <= Decimal("6000"):
            return unsupported("calories_out_of_range")
        calories = int(raw_calories.quantize(Decimal("1")))
        if not 1000 <= calories <= 6000:
            return unsupported("calories_out_of_range")
        protein = int(
            (Decimal(calories) * Decimal("0.20") / Decimal("4")).quantize(Decimal("1"))
        )
        fat = int(
            (Decimal(calories) * Decimal("0.30") / Decimal("9")).quantize(Decimal("1"))
        )
        carb_energy = Decimal(calories) - Decimal("4") * protein - Decimal("9") * fat
        carbs = int((carb_energy / Decimal("4")).quantize(Decimal("1")))
        delta = 4 * protein + 9 * fat + 4 * carbs - calories
        if min(calories, protein, fat, carbs) <= 0 or abs(delta) > 2:
            raise NutritionCalculationInvariantError(
                "Invalid nutrition target invariants"
            )

        return CalculatedNutrition(
            calculation_date=calculation_date,
            result=NutritionCalculationResult(
                age_years=age,
                used_inputs=inputs,
                activity_factor=activity_factor,
                goal_factor=goal_factor,
                ree_kcal=ree.quantize(Decimal("0.01")),
                tdee_kcal=tdee.quantize(Decimal("0.01")),
                calories_target_kcal=calories,
                protein_target_g=protein,
                fat_target_g=fat,
                carbs_target_g=carbs,
                energy_delta_kcal=delta,
            ),
        )
