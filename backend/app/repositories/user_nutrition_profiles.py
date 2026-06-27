import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_nutrition_profile import UserNutritionProfile
from app.schemas.user_nutrition_profile import (
    UserNutritionProfileCreate,
    UserNutritionProfileUpdate,
)


class UserNutritionProfilesRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_user_id(
        self,
        user_id: uuid.UUID,
    ) -> UserNutritionProfile | None:
        result = await self.db.execute(
            select(UserNutritionProfile).where(
                UserNutritionProfile.user_id == user_id,
            )
        )

        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        data: UserNutritionProfileCreate,
    ) -> UserNutritionProfile:
        profile = UserNutritionProfile(
            user_id=user_id,
            **data.model_dump(),
        )

        self.db.add(profile)
        await self.db.commit()

        created_profile = await self.get_by_user_id(user_id)

        if created_profile is None:
            raise RuntimeError("Created nutrition profile was not found")

        return created_profile

    async def update(
        self,
        *,
        profile: UserNutritionProfile,
        data: UserNutritionProfileUpdate,
    ) -> UserNutritionProfile:
        update_data = data.model_dump(exclude_unset=True)

        for field_name, field_value in update_data.items():
            setattr(profile, field_name, field_value)

        await self.db.commit()
        await self.db.refresh(profile)

        return profile
