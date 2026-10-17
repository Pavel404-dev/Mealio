# Pantry refill transaction contract

`POST /api/v1/shopping-list/add-missing-to-pantry` adds the current deficit,
not another purchase event. Repeated calls with unchanged demand and stock
are no-ops. Concurrent calls for demand 100 g leave 100 g when starting from
either an absent row or 40 g; surplus is never reduced.

## Serialization and transaction ownership

The refill service and ordinary pantry POST/PATCH/DELETE use
`pantry_transaction`. It acquires the authenticated owner's existing User row
with `FOR UPDATE` before any stock reads. This covers absent pantry rows as well
as existing ones. It adopts the request session's transaction, which authentication
may already have opened; it does not start a nested transaction.

The service owns the single commit or rollback. Repositories execute/flush without
committing, and services construct response snapshots before releasing the lock.
Empty lists and no-ops also commit; exceptions, including cancellation, roll back.
Never call these repository mutations without the service transaction protocol.

The order is User, then dependent pantry rows. Refill writes ingredients in UUID
order while retaining the existing name/id order in the response. Pantry entity
queries refresh cached ORM state after waiting. The owner lock suppresses
autoflush before acquisition; request mutation sessions must not carry unrelated
pending writes. The shared User lock helper retains its existing F1 freshness
behavior. No provider/network call runs inside this pantry transaction.

## Guarantees and limits

At PostgreSQL's configured READ COMMITTED isolation, the combined query takes
one coherent demand/stock statement snapshot after acquiring the owner lock.
Ordinary pantry writers for that owner serialize with refill. Different owners
can progress independently, and combined GET remains a read-only query.
Operations already using the same User lock, including profile/security writes,
may wait for a pantry mutation.

This does not serialize arbitrary recipe or meal-plan edits, catalogue deletion,
or external SQL writers. A later demand edit may require another refill. Higher
transaction isolation levels would require a separate retry policy.

- Overlapping demands of 100 g and 150 g leave 150 g in either serial order.
- PATCH is absolute: PATCH 40 then refill 100 leaves 100; the reverse leaves 40.
- DELETE after refill can leave stock absent; DELETE before refill allows creation.
- POST still returns 409 for a duplicate; another owner's item remains 404.
- Expired stock still counts toward subtraction. Refill preserves `expires_at`
  and `created_at`; only changed rows update `updated_at`. No-op rows stay intact.

No endpoint/schema/status or persistent model change is involved; no migration
is needed. `test_pantry_refill_concurrency.py` exercises real HTTP handlers with
independent PostgreSQL sessions, observes actual blocking, and injects failures
after successful SQL to verify atomic rollback and subsequent progress. Its
baseline-compatible harness releases the first request when the second either
reaches the mutation boundary or waits in PostgreSQL, without a two-reader barrier.
