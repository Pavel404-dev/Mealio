"""Lock shared by catalog nutrition and recipe composition writers."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Dedicated two-int PostgreSQL advisory-lock namespace: 'MEAL', nutrition v1.
NUTRITION_LOCK_NAMESPACE = 1296384332
NUTRITION_LOCK_KEY = 207


async def lock_nutrition_writes(db: AsyncSession) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :key)"),
        {"namespace": NUTRITION_LOCK_NAMESPACE, "key": NUTRITION_LOCK_KEY},
    )
