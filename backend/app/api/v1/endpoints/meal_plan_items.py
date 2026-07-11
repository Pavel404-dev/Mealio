from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.meal_plan import (
    MealPlanItemCalendarRead,
    MealPlanNutritionGapRecommendationsRead,
    MealPlanNutritionGapsDayRead,
    MealPlanNutritionGapsSummaryRead,
    MealPlanNutritionProgressDayRead,
)
from app.services.meal_plan_nutrition_progress import (
    MealPlanNutritionProgressService,
)
from app.services.meal_plans import MealPlansService

router = APIRouter(
    prefix="/meal-plan-items",
    tags=["Meal Plan Items"],
)


@router.get(
    "/calendar/nutrition-progress",
    response_model=list[MealPlanNutritionProgressDayRead],
)
async def list_current_user_meal_plan_items_nutrition_progress(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlanNutritionProgressService(db)

    return await service.list_current_user_nutrition_progress(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/calendar/nutrition-gaps",
    response_model=list[MealPlanNutritionGapsDayRead],
)
async def list_current_user_meal_plan_items_nutrition_gaps(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlanNutritionProgressService(db)

    return await service.list_current_user_nutrition_gaps(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/calendar/nutrition-gaps/summary",
    response_model=MealPlanNutritionGapsSummaryRead,
)
async def get_current_user_meal_plan_items_nutrition_gaps_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlanNutritionProgressService(db)

    return await service.get_current_user_nutrition_gaps_summary(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/calendar/nutrition-gaps/recommendations",
    response_model=MealPlanNutritionGapRecommendationsRead,
)
async def get_current_user_meal_plan_items_nutrition_gap_recommendations(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlanNutritionProgressService(db)

    return await service.get_current_user_nutrition_gap_recommendations(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("", response_model=list[MealPlanItemCalendarRead])
async def list_current_user_meal_plan_items_calendar(
    from_date: date = Query(...),
    to_date: date = Query(...),
    meal_type: str | None = Query(default=None, min_length=1, max_length=50),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlansService(db)

    return await service.list_user_meal_plan_items_calendar(
        user_id=current_user.id,
        from_date=from_date,
        to_date=to_date,
        meal_type=meal_type,
        limit=limit,
        offset=offset,
    )
