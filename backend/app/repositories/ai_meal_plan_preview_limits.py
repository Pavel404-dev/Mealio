import math
import uuid
from datetime import timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_meal_plan_preview_limit import AIMealPlanPreviewLimit


class AIMealPlanPreviewLimitsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def reserve(
        self, *, user_id: uuid.UUID, limit: int, window_seconds: int
    ) -> int | None:
        """Reserve one attempt or return the seconds until the account can retry."""
        now = func.statement_timestamp()
        bucket = AIMealPlanPreviewLimit
        expired = bucket.expires_at <= now
        statement = insert(bucket).values(
            user_id=user_id,
            attempts=1,
            expires_at=now + timedelta(seconds=window_seconds),
        )
        reservation = statement.on_conflict_do_update(
            index_elements=[bucket.user_id],
            set_={
                "attempts": case((expired, 1), else_=bucket.attempts + 1),
                "expires_at": case(
                    (expired, statement.excluded.expires_at), else_=bucket.expires_at
                ),
            },
            where=or_(expired, bucket.attempts < limit),
        ).returning(bucket.user_id)
        if await self.db.scalar(reservation) is not None:
            return None

        # PostgreSQL holds the rejected row's lock through the current transaction.
        result = await self.db.execute(
            select(bucket.expires_at, now).where(bucket.user_id == user_id)
        )
        expires_at, checked_at = result.one()
        return max(1, math.ceil((expires_at - checked_at).total_seconds()))
