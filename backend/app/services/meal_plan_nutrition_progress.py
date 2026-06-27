import uuid
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.meal_plans import MealPlansRepository
from app.schemas.meal_plan import (
    MealPlanNutritionGapsDayRead,
    MealPlanNutritionGapsSummaryRead,
    MealPlanNutritionProgressDayRead,
    NutritionGapStatus,
    NutritionGapStatusCountsRead,
    NutritionGapsAverageRead,
    NutritionGapsMacroStatusCountsRead,
    NutritionGapsOverallStatus,
    NutritionGapsOverallStatusCountsRead,
)
from app.services.user_nutrition_profiles import UserNutritionProfilesService

OVERALL_STATUSES: tuple[NutritionGapsOverallStatus, ...] = (
    "unknown",
    "needs_attention",
    "over_target",
    "on_track",
)
MACRO_STATUSES: tuple[NutritionGapStatus, ...] = (
    "under",
    "met",
    "over",
    "unknown",
)
MACRO_STATUS_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("calories", "calories_status", "calories_gap"),
    ("protein", "protein_status", "protein_gap_g"),
    ("carbs", "carbs_status", "carbs_gap_g"),
    ("fat", "fat_status", "fat_gap_g"),
)
ISSUE_MACRO_PRIORITY = {
    "protein": 0,
    "calories": 1,
    "carbs": 2,
    "fat": 3,
}
ISSUE_STATUS_PRIORITY = {
    "under": 0,
    "over": 1,
}


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

    def build_day_gaps(
        self,
        *,
        row: dict,
        profile: NutritionProfileLike,
    ) -> MealPlanNutritionGapsDayRead:
        total_calories = self._to_decimal(row.get("total_calories"))
        total_protein_g = self._to_decimal(row.get("total_protein_g"))
        total_carbs_g = self._to_decimal(row.get("total_carbs_g"))
        total_fat_g = self._to_decimal(row.get("total_fat_g"))

        calories_gap, calories_status = self._calculate_gap(
            total=total_calories,
            target=profile.daily_calories_target,
        )
        protein_gap_g, protein_status = self._calculate_gap(
            total=total_protein_g,
            target=profile.daily_protein_target_g,
        )
        carbs_gap_g, carbs_status = self._calculate_gap(
            total=total_carbs_g,
            target=profile.daily_carbs_target_g,
        )
        fat_gap_g, fat_status = self._calculate_gap(
            total=total_fat_g,
            target=profile.daily_fat_target_g,
        )

        macro_statuses = [
            calories_status,
            protein_status,
            carbs_status,
            fat_status,
        ]

        return MealPlanNutritionGapsDayRead(
            date=row["date"],
            total_calories=total_calories,
            daily_calories_target=profile.daily_calories_target,
            calories_gap=calories_gap,
            calories_status=calories_status,
            total_protein_g=total_protein_g,
            daily_protein_target_g=profile.daily_protein_target_g,
            protein_gap_g=protein_gap_g,
            protein_status=protein_status,
            total_carbs_g=total_carbs_g,
            daily_carbs_target_g=profile.daily_carbs_target_g,
            carbs_gap_g=carbs_gap_g,
            carbs_status=carbs_status,
            total_fat_g=total_fat_g,
            daily_fat_target_g=profile.daily_fat_target_g,
            fat_gap_g=fat_gap_g,
            fat_status=fat_status,
            overall_status=self._calculate_overall_status(macro_statuses),
            missing_targets=self._build_missing_targets(profile=profile),
        )

    def build_gaps_summary(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
        daily_gaps: list[MealPlanNutritionGapsDayRead],
    ) -> MealPlanNutritionGapsSummaryRead:
        overall_status_counts = {status: 0 for status in OVERALL_STATUSES}
        macro_status_counts = {
            macro: {status: 0 for status in MACRO_STATUSES}
            for macro, _, _ in MACRO_STATUS_FIELDS
        }
        gap_sums = {gap_field: Decimal("0") for _, _, gap_field in MACRO_STATUS_FIELDS}
        gap_counts = {gap_field: 0 for _, _, gap_field in MACRO_STATUS_FIELDS}
        missing_targets: set[str] = set()

        for day in daily_gaps:
            overall_status_counts[day.overall_status] += 1
            missing_targets.update(day.missing_targets)

            for macro, status_field, gap_field in MACRO_STATUS_FIELDS:
                macro_status = getattr(day, status_field)
                macro_status_counts[macro][macro_status] += 1

                gap_value = getattr(day, gap_field)
                if gap_value is not None:
                    gap_sums[gap_field] += gap_value
                    gap_counts[gap_field] += 1

        return MealPlanNutritionGapsSummaryRead(
            start_date=start_date,
            end_date=end_date,
            days_count=len(daily_gaps),
            overall_status_counts=NutritionGapsOverallStatusCountsRead(
                **overall_status_counts,
            ),
            macro_status_counts=NutritionGapsMacroStatusCountsRead(
                calories=NutritionGapStatusCountsRead(
                    **macro_status_counts["calories"],
                ),
                protein=NutritionGapStatusCountsRead(
                    **macro_status_counts["protein"],
                ),
                carbs=NutritionGapStatusCountsRead(
                    **macro_status_counts["carbs"],
                ),
                fat=NutritionGapStatusCountsRead(
                    **macro_status_counts["fat"],
                ),
            ),
            average_gaps=NutritionGapsAverageRead(
                calories_gap=self._average_gap(
                    total=gap_sums["calories_gap"],
                    count=gap_counts["calories_gap"],
                ),
                protein_gap_g=self._average_gap(
                    total=gap_sums["protein_gap_g"],
                    count=gap_counts["protein_gap_g"],
                ),
                carbs_gap_g=self._average_gap(
                    total=gap_sums["carbs_gap_g"],
                    count=gap_counts["carbs_gap_g"],
                ),
                fat_gap_g=self._average_gap(
                    total=gap_sums["fat_gap_g"],
                    count=gap_counts["fat_gap_g"],
                ),
            ),
            missing_targets=sorted(missing_targets),
            main_issues=self._build_main_issues(
                macro_status_counts=macro_status_counts,
                missing_targets=missing_targets,
            ),
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

    def _calculate_gap(
        self,
        *,
        total: Decimal,
        target: int | None,
    ) -> tuple[Decimal | None, NutritionGapStatus]:
        if target is None:
            return None, "unknown"

        decimal_target = Decimal(target)
        gap = decimal_target - total

        if total < decimal_target:
            return gap, "under"

        if total == decimal_target:
            return gap, "met"

        return gap, "over"

    def _calculate_overall_status(
        self,
        statuses: list[NutritionGapStatus],
    ) -> NutritionGapsOverallStatus:
        known_statuses = [status for status in statuses if status != "unknown"]

        if not known_statuses:
            return "unknown"

        if "under" in known_statuses:
            return "needs_attention"

        if "over" in known_statuses:
            return "over_target"

        return "on_track"

    def _build_missing_targets(
        self,
        *,
        profile: NutritionProfileLike,
    ) -> list[str]:
        missing_targets: list[str] = []

        if profile.daily_calories_target is None:
            missing_targets.append("daily_calories_target")

        if profile.daily_protein_target_g is None:
            missing_targets.append("daily_protein_target_g")

        if profile.daily_carbs_target_g is None:
            missing_targets.append("daily_carbs_target_g")

        if profile.daily_fat_target_g is None:
            missing_targets.append("daily_fat_target_g")

        return missing_targets

    def _average_gap(
        self,
        *,
        total: Decimal,
        count: int,
    ) -> Decimal | None:
        if count == 0:
            return None

        return (total / Decimal(count)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def _build_main_issues(
        self,
        *,
        macro_status_counts: dict[str, dict[NutritionGapStatus, int]],
        missing_targets: set[str],
    ) -> list[str]:
        issues: list[str] = []

        if missing_targets:
            issues.append("missing_targets")

        scored_issues: list[tuple[int, str, str, str]] = []

        for macro in ISSUE_MACRO_PRIORITY:
            for status_name in ISSUE_STATUS_PRIORITY:
                count = macro_status_counts[macro][status_name]

                if count > 0:
                    scored_issues.append(
                        (
                            count,
                            macro,
                            status_name,
                            f"{macro}_{status_name}",
                        )
                    )

        scored_issues.sort(
            key=lambda item: (
                -item[0],
                ISSUE_MACRO_PRIORITY[item[1]],
                ISSUE_STATUS_PRIORITY[item[2]],
            )
        )

        issues.extend(issue_label for _, _, _, issue_label in scored_issues)

        return issues

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

    async def list_current_user_nutrition_gaps(
        self,
        *,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MealPlanNutritionGapsDayRead]:
        self._validate_date_filters(
            start_date=start_date,
            end_date=end_date,
        )

        start_date, end_date = self._apply_default_date_range(
            start_date=start_date,
            end_date=end_date,
        )

        return await self._list_current_user_nutrition_gaps_for_range(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_current_user_nutrition_gaps_summary(
        self,
        *,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MealPlanNutritionGapsSummaryRead:
        self._validate_date_filters(
            start_date=start_date,
            end_date=end_date,
        )

        start_date, end_date = self._apply_default_date_range(
            start_date=start_date,
            end_date=end_date,
        )

        daily_gaps = await self._list_current_user_nutrition_gaps_for_range(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        return self.progress_calculator.build_gaps_summary(
            start_date=start_date,
            end_date=end_date,
            daily_gaps=daily_gaps,
        )

    async def _list_current_user_nutrition_gaps_for_range(
        self,
        *,
        user_id: uuid.UUID,
        start_date: date | None,
        end_date: date | None,
    ) -> list[MealPlanNutritionGapsDayRead]:
        profile = await self.nutrition_profiles_service.get_current_user_profile(
            user_id,
        )
        rows = await self.repository.list_nutrition_progress_for_user_calendar(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        return [
            self.progress_calculator.build_day_gaps(
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
