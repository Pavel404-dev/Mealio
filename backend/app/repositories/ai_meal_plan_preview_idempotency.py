import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import ColumnElement, and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_meal_plan_preview_idempotency import AIMealPlanPreviewIdempotency

PREVIEW_KEY_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class PreviewReservation:
    user_id: uuid.UUID
    key_hash: str
    id: uuid.UUID


class AIMealPlanPreviewIdempotencyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def claim(
        self, reservation: PreviewReservation, input_hash: str
    ) -> tuple[str, dict[str, Any] | None] | None:
        """Claim an available key or return its existing input hash and result."""
        record = AIMealPlanPreviewIdempotency
        now = func.statement_timestamp()
        await self.db.execute(
            delete(record).where(
                record.user_id == reservation.user_id, record.expires_at <= now
            )
        )
        proposed = insert(record).values(
            user_id=reservation.user_id,
            key_hash=reservation.key_hash,
            input_hash=input_hash,
            reservation_id=reservation.id,
            expires_at=now + PREVIEW_KEY_TTL,
        )
        statement = proposed.on_conflict_do_update(
            index_elements=[record.user_id, record.key_hash],
            set_={
                "input_hash": proposed.excluded.input_hash,
                "reservation_id": proposed.excluded.reservation_id,
                "expires_at": proposed.excluded.expires_at,
                "preview": None,
            },
            where=record.expires_at <= now,
        ).returning(record.reservation_id)
        if await self.db.scalar(statement) is not None:
            return None

        # The excluded update holds the conflicting row lock until this transaction ends.
        existing = await self.db.execute(
            select(record.input_hash, record.preview).where(
                record.user_id == reservation.user_id,
                record.key_hash == reservation.key_hash,
            )
        )
        previous_hash, preview = existing.one()
        return previous_hash, preview

    async def complete(
        self, reservation: PreviewReservation, preview: dict[str, Any]
    ) -> bool:
        record = AIMealPlanPreviewIdempotency
        now = func.statement_timestamp()
        statement = (
            update(record)
            .where(self._pending(reservation), record.expires_at > now)
            .values(preview=preview, expires_at=now + PREVIEW_KEY_TTL)
            .returning(record.reservation_id)
        )
        return await self.db.scalar(statement) is not None

    async def release(self, reservation: PreviewReservation) -> None:
        await self.db.execute(
            delete(AIMealPlanPreviewIdempotency).where(self._pending(reservation))
        )

    @staticmethod
    def _pending(reservation: PreviewReservation) -> ColumnElement[bool]:
        record = AIMealPlanPreviewIdempotency
        return and_(
            record.user_id == reservation.user_id,
            record.key_hash == reservation.key_hash,
            record.reservation_id == reservation.id,
            record.preview.is_(None),
        )
