"""Canonical slot writes and reads that expose optional planned portions."""

import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_meal_plan_generation_provider
from app.db.session import get_db
from app.integrations.meal_plan_generation import MealPlanGenerationProvider
from app.models.user import User
from app.schemas.ai_meal_plan import AIMealPlanPreview, AIMealPlanPreviewRequest
from app.schemas.meal_plan_v2 import (
    MealPlanItemV2Create,
    MealPlanItemV2Read,
    MealPlanItemV2Update,
    MealPlanV2Create,
    MealPlanV2Read,
)
from app.services.ai_meal_plan_preview import AIMealPlanPreviewService
from app.services.meal_plans import MealPlansService

router = APIRouter(prefix="/meal-plans", tags=["Meal Plans V2"])
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9._~-]{1,128}$"


@router.post(
    "/ai/generate-preview",
    response_model=AIMealPlanPreview,
    responses={
        409: {
            "description": "AI meal plan preview is in progress or the key conflicts",
            "headers": {
                "Retry-After": {
                    "description": "Seconds before checking an in-progress preview again",
                    "schema": {"type": "integer", "minimum": 1},
                }
            },
        },
        429: {
            "description": "AI meal plan preview rate limit exceeded",
            "headers": {
                "Retry-After": {
                    "description": "Seconds until the account can make another attempt",
                    "schema": {"type": "integer", "minimum": 1},
                }
            },
        },
    },
)
async def generate_meal_plan_preview(
    payload: AIMealPlanPreviewRequest,
    current_user: User = Depends(get_current_user),
    provider: MealPlanGenerationProvider = Depends(get_meal_plan_generation_provider),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="Client key for retrying the same preview request",
        json_schema_extra={"pattern": IDEMPOTENCY_KEY_PATTERN},
    ),
):
    """Suggest one day of assignments from the authenticated user's saved recipes."""
    if idempotency_key is not None and not re.fullmatch(
        IDEMPOTENCY_KEY_PATTERN, idempotency_key
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid Idempotency-Key"
        )
    return await AIMealPlanPreviewService(db, provider).generate(
        user_id=current_user.id, request=payload, idempotency_key=idempotency_key
    )


@router.get("", response_model=list[MealPlanV2Read])
async def list_current_user_meal_plans(
    search: str | None = Query(default=None, min_length=1, max_length=100),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await MealPlansService(db).list_user_meal_plans(
        user_id=current_user.id,
        search=search,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )


@router.get("/{meal_plan_id}", response_model=MealPlanV2Read)
async def get_meal_plan(
    meal_plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await MealPlansService(db).get_meal_plan(
        user_id=current_user.id, meal_plan_id=meal_plan_id
    )


@router.post("", response_model=MealPlanV2Read, status_code=status.HTTP_201_CREATED)
async def create_meal_plan(
    payload: MealPlanV2Create,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create canonical slots, optionally selecting portions of each recipe."""
    return await MealPlansService(db).create_meal_plan(
        user_id=current_user.id,
        data=payload,
    )


@router.post(
    "/{meal_plan_id}/items",
    response_model=MealPlanItemV2Read,
    status_code=status.HTTP_201_CREATED,
)
async def add_meal_plan_item(
    meal_plan_id: uuid.UUID,
    payload: MealPlanItemV2Create,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a canonical slot to a new or legacy plan."""
    return await MealPlansService(db).add_meal_plan_item(
        user_id=current_user.id,
        meal_plan_id=meal_plan_id,
        data=payload,
    )


@router.patch(
    "/{meal_plan_id}/items/{item_id}",
    response_model=MealPlanItemV2Read,
)
async def update_meal_plan_item(
    meal_plan_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: MealPlanItemV2Update,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Omit meal_type to preserve a legacy label, or supply a canonical replacement."""
    return await MealPlansService(db).update_meal_plan_item(
        user_id=current_user.id,
        meal_plan_id=meal_plan_id,
        item_id=item_id,
        data=payload,
    )
