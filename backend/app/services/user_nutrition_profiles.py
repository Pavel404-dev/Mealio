import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_nutrition_profiles import (
    UserNutritionProfilesRepository,
)
from app.repositories.users import UsersRepository
from app.schemas.nutrition_calculation import (
    NutritionCalculationInput,
    NutritionCalculationOutcome,
    NutritionCalculationRequest,
)
from app.schemas.user_nutrition_profile import (
    UserNutritionProfileCreate,
    UserNutritionProfileRead,
    UserNutritionProfileUpdate,
)
from app.services.nutrition_calculation import NutritionCalculator


class UserNutritionProfilesService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UserNutritionProfilesRepository(db)
        self.users_repository = UsersRepository(db)

    async def get_current_user_profile(
        self,
        user_id: uuid.UUID,
    ):
        profile = await self.repository.get_by_user_id(user_id)

        if profile is None:
            return UserNutritionProfileRead.default()

        return profile

    async def calculate_current_user_targets(
        self,
        *,
        user_id: uuid.UUID,
        data: NutritionCalculationRequest,
    ) -> NutritionCalculationOutcome:
        # Prevent even an incidental autoflush for callers sharing a session.
        # One owner-scoped SELECT supplies all fields; no new locks or writes.
        with self.db.no_autoflush:
            profile = await self.get_current_user_profile(user_id)
        snapshot = NutritionCalculationInput(
            sex=profile.sex,
            birth_date=profile.birth_date,
            height_cm=profile.height_cm,
            weight_kg=profile.weight_kg,
            activity_level=profile.activity_level,
            goal=profile.goal,
        )
        return NutritionCalculator().calculate(
            snapshot,
            calculation_date=data.calculation_date,
            rules_version=data.rules_version,
        )

    async def create_or_update_current_user_profile(
        self,
        *,
        user_id: uuid.UUID,
        data: UserNutritionProfileUpdate,
    ):
        # Authentication may already have opened this session's transaction.
        # Lock the owner even when the profile does not exist yet.
        try:
            user = await self.users_repository.get_by_id_for_update(user_id)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
                )

            profile = await self.repository.get_by_user_id(user_id)
            changes = data.model_dump(exclude_unset=True)
            amount = changes.get(
                "weekly_food_budget_amount",
                profile.weekly_food_budget_amount if profile is not None else None,
            )
            currency = changes.get(
                "budget_currency",
                profile.budget_currency if profile is not None else None,
            )
            if (amount is None) != (currency is None):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Weekly food budget amount and currency must both be set or both be null",
                )

            if profile is None:
                profile = await self.repository.create(
                    user_id=user_id,
                    data=UserNutritionProfileCreate(**changes),
                )
            else:
                profile = await self.repository.update(profile=profile, data=data)

            # Read generated values and validate the response before committing.
            await self.db.refresh(profile)
            result = UserNutritionProfileRead.model_validate(profile)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        return result
