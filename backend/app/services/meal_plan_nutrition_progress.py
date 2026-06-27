import uuid
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.meal_plans import MealPlansRepository
from app.schemas.meal_plan import MealPlanNutritionProgressDayRead
from app.services.user_nutrition_profiles import UserNutritionProfilesService


class NutritionProfileLike(Protocol):
    daily_calories_target: int | None
    daily_protein_target_g: int | None
    daily_carbs_target_g: int | None
    daily_fat_target_g: int | None


class MealPlanNutritionProgressCalculator:
    def build_day_progress(
        self,
        *,
        row: dict,
        profile: NutritionProfileLike,
    ) -> MealPlanNutritionProgressDayRead:
        total_calories = self._to_decimal(row.get("total_calories"))
        total_protein_g = self._to_decimal(row.get("total_protein_g"))
        total_carbs_g = self._to_decimal(row.get("total_carbs_g"))
        total_fat_g = self._to_decimal(row.get("total_fat_g"))

        remaining_calories, calories_percent = self._calculate_progress(
            total=total_calories,
            target=profile.daily_calories_target,
        )
        remaining_protein_g, protein_percent = self._calculate_progress(
            total=total_protein_g,
            target=profile.daily_protein_target_g,
        )
        remaining_carbs_g, carbs_percent = self._calculate_progress(
            total=total_carbs_g,
            target=profile.daily_carbs_target_g,
        )
        remaining_fat_g, fat_percent = self._calculate_progress(
            total=total_fat_g,
            target=profile.daily_fat_target_g,
        )

        return MealPlanNutritionProgressDayRead(
            date=row["date"],
            total_calories=total_calories,
            daily_calories_target=profile.daily_calories_target,
            remaining_calories=remaining_calories,
            calories_percent=calories_percent,
            total_protein_g=total_protein_g,
            daily_protein_target_g=profile.daily_protein_target_g,
            remaining_protein_g=remaining_protein_g,
            protein_percent=protein_percent,
            total_carbs_g=total_carbs_g,
            daily_carbs_target_g=profile.daily_carbs_target_g,
            remaining_carbs_g=remaining_carbs_g,
            carbs_percent=carbs_percent,
            total_fat_g=total_fat_g,
            daily_fat_target_g=profile.daily_fat_target_g,
            remaining_fat_g=remaining_fat_g,
            fat_percent=fat_percent,
        )

    def _calculate_progress(
        self,
        *,
        total: Decimal,
        target: int | None,
    ) -> tuple[Decimal | None, Decimal | None]:
        if target is None:
            return None, None

        decimal_target = Decimal(target)

        if decimal_target <= 0:
            return None, None

        remaining = decimal_target - total
        percent = (total / decimal_target * Decimal("100")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        return remaining, percent

    def _to_decimal(self, value) -> Decimal:
        if value is None:
            return Decimal("0")

        if isinstance(value, Decimal):
            return value

        return Decimal(str(value))


class MealPlanNutritionProgressService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = MealPlansRepository(db)
        self.nutrition_profiles_service = UserNutritionProfilesService(db)
        self.progress_calculator = MealPlanNutritionProgressCalculator()

    async def list_current_user_nutrition_progress(
        self,
        *,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MealPlanNutritionProgressDayRead]:
        self._validate_date_filters(
            start_date=start_date,
            end_date=end_date,
        )

        start_date, end_date = self._apply_default_date_range(
            start_date=start_date,
            end_date=end_date,
        )

        profile = await self.nutrition_profiles_service.get_current_user_profile(
            user_id,
        )
        rows = await self.repository.list_nutrition_progress_for_user_calendar(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        return [
            self.progress_calculator.build_day_progress(
                row=row,
                profile=profile,
            )
            for row in rows
        ]

    def _validate_date_filters(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
    ) -> None:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="start_date must be less than or equal to end_date",
            )

    def _apply_default_date_range(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
    ) -> tuple[date | None, date | None]:
        if start_date is not None or end_date is not None:
            return start_date, end_date

        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        return week_start, week_end
