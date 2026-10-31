from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.nutrition_writes import lock_nutrition_writes


@asynccontextmanager
async def nutrition_transaction(db: AsyncSession) -> AsyncIterator[None]:
    """Own a nutrition/recipe mutation, including auth's autobegun transaction.

    Acquire the gate before any participating read, row lock or flush. Readers
    in repositories repopulate ORM state after waiting. Repositories only flush.
    This deliberately serializes writers, including composition replacements,
    without locking user rows or changing Pantry's independent lock protocol.
    """
    try:
        with db.no_autoflush:
            await lock_nutrition_writes(db)
        yield
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
