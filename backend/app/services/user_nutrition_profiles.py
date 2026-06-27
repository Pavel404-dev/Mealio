import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_nutrition_profiles import (
    UserNutritionProfilesRepository,
)
from app.schemas.user_nutrition_profile import (
    UserNutritionProfileCreate,
    UserNutritionProfileRead,
    UserNutritionProfileUpdate,
)


class UserNutritionProfilesService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = UserNutritionProfilesRepository(db)

    async def get_current_user_profile(
        self,
        user_id: uuid.UUID,
    ):
        profile = await self.repository.get_by_user_id(user_id)

        if profile is None:
            return UserNutritionProfileRead.default()

        return profile

    async def create_or_update_current_user_profile(
        self,
        *,
        user_id: uuid.UUID,
        data: UserNutritionProfileUpdate,
    ):
        profile = await self.repository.get_by_user_id(user_id)

        if profile is None:
            create_data = UserNutritionProfileCreate(
                **data.model_dump(exclude_unset=True),
            )

            return await self.repository.create(
                user_id=user_id,
                data=create_data,
            )

        return await self.repository.update(
            profile=profile,
            data=data,
        )
