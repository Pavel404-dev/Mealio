---
name: code-review
description: Review Mealio pull requests and code changes for correctness, security, regressions, transaction safety, API compatibility, migration safety, and adequate tests. Use for pull-request reviews, code-review requests, and pre-merge audits involving the FastAPI/PostgreSQL backend, Flutter frontend, authentication, integrations, infrastructure, or documentation.
---

# Mealio Code Review

## Establish context

- Read `AGENTS.md` and follow it as the authoritative repository guidance.
- Compare the complete change with the verified base and current repository state.
- Inspect affected implementation, tests, schemas, migrations, configuration, workflows, and documentation.
- Review only; do not modify code unless explicitly requested.
- Do not infer correctness solely from green CI or newly added tests.

## Prioritize risks

Review in this order:

1. Security vulnerabilities, secret exposure, and data loss.
2. Incorrect behavior, regressions, and broken API contracts.
3. Transaction, concurrency, rollback, retry, replay, and idempotency defects.
4. Missing or misleading tests and operational risks.
5. Maintainability problems with a concrete failure mode.

Avoid style-only comments, duplicates of automated lint findings, and speculative concerns without a plausible failure scenario.

## Review backend changes

- Preserve the `endpoint -> service -> repository -> model/schema` architecture.
- Verify async work remains non-blocking and transaction ownership is explicit.
- Ensure persistent model changes include a safe Alembic migration with one migration head.
- Check status codes, response shapes, backward compatibility, and enumeration-safe authentication responses.
- For authentication changes, inspect invalid, expired, replayed, malformed, cross-purpose, rollback, and concurrent paths.
- Ensure failures do not consume one-time tokens or OTPs or commit partial state unless explicitly intended.
- Ensure credentials, tokens, OTPs, provider responses, and secrets cannot leak through logs, errors, tests, or configuration.
- Check external integrations for bounded timeouts, safe error mapping, and retry or idempotency risks.

## Review frontend changes

- Preserve existing Riverpod, repository/domain/presentation, GoRouter, and Dio patterns.
- Ensure public authentication requests do not attach bearer tokens or trigger token refresh.
- Preserve opaque tokens, leading-zero OTP codes, and intentionally untrimmed passwords.
- Check loading, duplicate submission, retry, validation, rate-limit, connection, and unexpected failure states.
- Retain sensitive form state only when retry requires it, and clear it after success, cancellation, or expiry.
- Verify navigation and user-visible messages match backend contracts.

## Review tests and operations

- Require regression tests for every plausible failure path introduced or fixed by the change.
- Prefer API or service tests for backend behavior and repository, interceptor, router, or widget tests for frontend contracts.
- Require rollback, retry, replay, and concurrency coverage when relevant.
- Check that environment examples, Railway and Docker configuration, CI workflows, and documentation remain aligned.
- Treat missing verification as a finding when the change cannot otherwise be trusted.

## Report findings

- Report actionable findings first, ordered as `critical`, `high`, `medium`, then `low`.
- For each finding, provide the exact file and narrowest line range, failure scenario, impact, and concrete remediation.
- Keep findings independent and concise.
- Do not report praise or general summaries as findings.
- If no actionable findings exist, state that clearly and identify any material verification gaps.
