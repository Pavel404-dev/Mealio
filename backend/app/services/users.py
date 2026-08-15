import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.email_verification_tokens import (
    EmailVerificationTokensRepository,
)
from app.repositories.exceptions import DuplicateResourceError
from app.repositories.users import UsersRepository
from app.schemas.user import UserCreate, UserUpdate


class UsersService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UsersRepository(db)
        self.email_verification_repository = EmailVerificationTokensRepository(db)

    async def get_user(self, user_id: uuid.UUID):
        user = await self.repository.get_by_id(user_id)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return user

    async def create_user(self, data: UserCreate):
        existing_user = await self.repository.get_by_email(str(data.email))

        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        try:
            return await self.repository.create(data)
        except DuplicateResourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    async def update_user(
        self,
        user_id: uuid.UUID,
        data: UserUpdate,
    ):
        update_data = data.model_dump(exclude_unset=True)

        try:
            user = await self.repository.get_by_id_for_update(user_id)

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

            email_changed = False

            if "email" in update_data:
                normalized_email = str(update_data["email"]).strip().lower()
                email_changed = normalized_email != user.email.strip().lower()

                if email_changed:
                    existing_user = await self.repository.get_by_email(normalized_email)

                    if existing_user is not None and existing_user.id != user.id:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="User with this email already exists",
                        )

            updated_user = await self.repository.apply_update(
                user=user,
                data=data,
            )

            if email_changed:
                now = datetime.now(UTC)
                self.repository.set_email_verified_at(
                    user=updated_user,
                    verified_at=None,
                )
                await self.email_verification_repository.revoke_unused_for_user(
                    user_id=updated_user.id,
                    revoked_at=now,
                )

            await self.db.commit()
        except DuplicateResourceError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

        await self.db.refresh(updated_user)
        return updated_user
