import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.users import UsersRepository


@asynccontextmanager
async def pantry_transaction(
    db: AsyncSession, user_id: uuid.UUID
) -> AsyncIterator[None]:
    """Own one pantry mutation, including the transaction opened by authentication.

    Lock User before reading stock, even if no pantry rows exist. All pantry
    writers use this order; repositories must not commit inside this context.
    Demand is a statement snapshot, not a lock on recipe/meal-plan edits.
    """
    try:
        # Do not flush dependent rows before acquiring the owner lock.
        with db.no_autoflush:
            user = await UsersRepository(db).get_by_id_for_update(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        yield
        # Empty/no-op mutations must release the lock too.
        await db.commit()
    except BaseException:
        # Include request cancellation; dependency close is not the txn owner.
        await db.rollback()
        raise
