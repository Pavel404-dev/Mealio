from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user_nutrition_profile import (
    UserNutritionProfileRead,
    UserNutritionProfileUpdate,
)
from app.services.user_nutrition_profiles import UserNutritionProfilesService

router = APIRouter(
    prefix="/user-preferences",
    tags=["User Preferences"],
)


@router.get(
    "/nutrition",
    response_model=UserNutritionProfileRead,
)
async def get_current_user_nutrition_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserNutritionProfilesService(db)

    return await service.get_current_user_profile(current_user.id)


@router.patch(
    "/nutrition",
    response_model=UserNutritionProfileRead,
)
async def patch_current_user_nutrition_profile(
    payload: UserNutritionProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserNutritionProfilesService(db)

    return await service.create_or_update_current_user_profile(
        user_id=current_user.id,
        data=payload,
    )
