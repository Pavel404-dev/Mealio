# Project status snapshot

Snapshot recorded: **2026-11-01 (Europe/Prague)**, from the linked delivery
evidence below. This is the last recorded observation, not a live dashboard.
Recheck current refs, instructions, and relevant evidence at task start using the
[workflow](development-workflow.md#sources-and-freshness). Unavailable runtime
access leaves the dated observation intact; current runtime state is unknown.

SHAs identify verified feature/artifact sources, not the commit containing this
document. A docs-only commit does not update the deployed backend SHA. The owner
records later CI/deploy/QA evidence in the linked PR; refresh this snapshot in a
normal agreed branch when useful, without a commit after every transition.

## Last verified feature and delivery evidence

- Issue [#209](https://github.com/Pavel404-dev/Mealio/issues/209): CLOSED;
  PR [#210](https://github.com/Pavel404-dev/Mealio/pull/210): MERGED.
- Reviewed feature SHA: `2895d77c0d50f2e2f8e599bdab7624ffd58f0908`.
- Recorded merge/artifact SHA: `fdfe5d48089f01907851c662177915dec1a5741a`.
  The merge tree matched the reviewed feature tree.
- Last recorded post-merge CI, 2026-11-01, on that merge SHA:
  [Backend PASS](https://github.com/Pavel404-dev/Mealio/actions/runs/41308442094),
  [Frontend PASS](https://github.com/Pavel404-dev/Mealio/actions/runs/41308442116).
- Last recorded review, 2026-11-01, on the feature SHA: owner reviewed the complete
  diff with no findings; independent human reviewer unavailable, as recorded in
  [PR review status](https://github.com/Pavel404-dev/Mealio/pull/210).
  [Automated code review](https://github.com/Pavel404-dev/Mealio/pull/210#issuecomment-6556842213)
  completed with no findings. This is neither human approval nor a security audit.

## Last observed backend deployment

- Decision for #209/#210: **Done**, staging backend delivery only, observed
  2026-11-01 around **19:48 Europe/Prague**. Target:
  `mealio-staging / staging / backend`; deployment
  `cde87253-1b90-4aa0-98da-9e78b0aef1f9` was sole active / SUCCESS.
- Last verified backend source/runtime SHA:
  `fdfe5d48089f01907851c662177915dec1a5741a`.
  DOCKERFILE builder, expected migration hook and `/health/db` check confirmed.
- Evidence: [published delivery result](https://github.com/Pavel404-dev/Mealio/pull/210).
  Owner-local sanitized receipts, outside Git, under
  `209-staging-audit-fdfe5d4-go2b9eoe/deploy-fdfe5d4/`:
  `deployment-check-20261101T194834401208.json` and `runtime-db-after.json`.
  These were readable during snapshot preparation; the PR is the portable source.

## Last recorded APK build and scoped QA

All rows are observations recorded on **2026-11-01**, not newly executed checks.
Build success does not establish installation or device QA. Backend identity has
its own SHA and observation time above.

| Observed scope | Source SHA | Last recorded outcome / evidence |
| --- | --- | --- |
| Android QA APK build | `fdfe5d48089f01907851c662177915dec1a5741a` | PASS — [run 41308442023](https://github.com/Pavel404-dev/Mealio/actions/runs/41308442023); no new installation recorded. |
| Local owner API QA, before merge | `2895d77c0d50f2e2f8e599bdab7624ffd58f0908` | PASS — 9/9 cases plus overflow rollback; [scope and results](https://github.com/Pavel404-dev/Mealio/pull/210). |
| Automated local ASGI/PostgreSQL walkthrough | `2895d77c0d50f2e2f8e599bdab7624ffd58f0908` | PASS — 28 requests / 8 groups; [verification](https://github.com/Pavel404-dev/Mealio/pull/210). |
| Staging health/OpenAPI/per100g contract, about 19:48 Europe/Prague | `fdfe5d48089f01907851c662177915dec1a5741a` | PASS — health, DB health, OpenAPI HTTP 200 and contract checks; [delivery evidence](https://github.com/Pavel404-dev/Mealio/pull/210). |
| Staging runtime/DB metadata, about 19:51 Europe/Prague | `fdfe5d48089f01907851c662177915dec1a5741a` | PASS — identity, 118 source/config files and four in-memory projection examples; same delivery evidence. |
| Staging business-flow E2E | `fdfe5d48089f01907851c662177915dec1a5741a` | NOT_RUN — not covered by the staging verification, per delivery evidence. |
| Physical device/UI QA for the merge APK | `fdfe5d48089f01907851c662177915dec1a5741a` | NOT_RUN — new APK not installed, per delivery evidence. |

The 19:51 receipt recorded PostgreSQL 18.6 and the single image/database Alembic
head `b205c8d15a01`. DB metadata/revision matched the pre-deploy observation;
the read-only transaction rolled back and the Postgres deployment was unchanged.
This does **not** establish full schema/data equality or staging business E2E.

## Open scope, decisions, and next action recorded

- [#207 foundation](https://github.com/Pavel404-dev/Mealio/issues/207) and #209
  per100g are complete. Technical W9 remains open: provenance and broader
  missing/zero semantics are separate work. Accepted semantics live in
  [storage consistency](nutrition-storage-consistency.md) and
  [per100g reads](nutrition-per100g-read.md).
- Notion is the roadmap/progress source. Per the owner handoff it was not updated
  after #209 in that session; no fresh Notion read is claimed here.
- Last reported local resources: PostgreSQL left running; `mealio_test` contains
  synthetic QA fixtures. Dedicated localhost:8209 QA backend stopped. These
  resources were not rechecked for this snapshot; no DB/role/cleanup/deployment
  permission carries forward. The owner already removed the #209 branch;
  cleanup was verified then and must not be repeated from this handoff.
- Next action recorded: owner takes [#211](https://github.com/Pavel404-dev/Mealio/issues/211)
  through commit/push/PR, Backend/Frontend CI on the final SHA, and review.
  Deployment and new device QA for that docs-only scope: **N/A**, because no
  runtime or app artifact changes. Keep the backend observation above intact;
  record post-merge evidence in that task's PR and link it in the final handoff.
