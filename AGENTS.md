# AGENTS.md

## Scope

These instructions apply to the entire Mealio repository.

Mealio is a long-term AI-powered meal-planning application and a bachelor's thesis project.
The backend uses FastAPI, async SQLAlchemy, PostgreSQL, Alembic, Pydantic,
pytest, Ruff, and Docker Compose. The frontend uses Flutter, Dart, Riverpod,
GoRouter, Dio, and flutter_secure_storage.

## Source of truth

- Treat the current `HEAD`, working tree, migrations, tests, and checked-in
  documentation as authoritative for the current task.
- Use `main` only as an explicitly selected comparison base, and verify the
  relevant refs before relying on it.
- Historical chats and project checkpoints are supporting context only.
- Before changing code, inspect the relevant implementation, tests, Git history,
  and documentation. Do not assume an earlier architecture still exists.
- Preserve unrelated and user-authored changes in a dirty worktree.

## Repository structure

- `backend/app/api`: FastAPI endpoints and dependencies.
- `backend/app/services`: business logic and transaction orchestration.
- `backend/app/repositories`: persistence queries and row-locking operations.
- `backend/app/models`: SQLAlchemy models.
- `backend/app/schemas`: Pydantic request and response schemas.
- `backend/app/integrations`: external-provider interfaces and adapters.
- `backend/alembic`: database migrations.
- `backend/tests`: backend unit, API, security, rollback, and concurrency tests.
- `frontend/lib`: Flutter application code.
- `frontend/test`: Flutter repository, controller, interceptor, router, and widget tests.

## Working agreement

- Respond in Russian unless the user requests another language.
- Work one terminal command or one verification step at a time, then wait for the
  complete output before continuing.
- Start every implementation task with a focused audit.
- Prefer one carefully reviewed patch when practical.
- Explain assumptions and security or migration tradeoffs before implementation.
- Do not create or modify GitHub issues, remote branches, pull requests, comments,
  reviews, or merges. Do not commit or push. Provide commands for the user to run.
- GitHub may be inspected read-only when relevant.
- Never run destructive Git commands or discard existing changes without explicit,
  target-specific user approval.
- Never print, commit, or expose secrets, credentials, tokens, OTP values, or
  private configuration.

## Backend conventions

- Preserve the layered flow: endpoint -> service -> repository -> model/schema.
- Reuse existing services, repositories, dependency injection, and integrations
  instead of creating parallel implementations.
- Keep transaction ownership explicit. Security-sensitive state changes that must
  succeed together belong in one database transaction.
- Add an Alembic migration for every persistent model change and verify that there
  is exactly one migration head.
- Keep async database access non-blocking.
- Preserve API status codes, response shapes, and generic enumeration-safe auth
  responses unless the task explicitly changes the contract.
- For authentication changes, test invalid, expired, replayed, malformed,
  cross-purpose, rollback, and concurrency behavior where applicable.
- Never leak secrets through validation errors, exception strings, logs, or tests.

## Frontend conventions

- Follow the existing Riverpod, repository/domain/presentation, GoRouter, and Dio
  patterns.
- Preserve opaque tokens, leading-zero OTP codes, and intentionally untrimmed
  passwords when sending requests.
- Keep public authentication endpoints excluded from bearer attachment and
  automatic token refresh.
- Prevent duplicate submissions and handle loading, success, validation,
  rate-limit, connection, and unexpected failure states safely.
- Clear secret input fields and local session material when the security flow
  requires it.
- Add repository/interceptor tests for network contracts and widget tests for
  user-visible behavior.

## Verification

Run the smallest relevant checks first, followed by the full affected suites.

From the repository root, backend quality checks:

```bash
python -m ruff check backend
python -m ruff format --check backend
```

From `backend/`, with the test database variables configured as documented:

```bash
alembic upgrade head
alembic current
alembic check
python -m pytest -v
python -m pytest -v --cov=app --cov-report=term-missing
```

From `frontend/`:

```bash
dart format --output=none --set-exit-if-changed .
flutter analyze
flutter test
```

For container changes, from the repository root:

```bash
docker compose up --build
docker build -t mealio-backend ./backend
```

Before handoff, always run `git diff --check`, inspect the complete diff and
status, report every check actually run, and state clearly what could not be
verified. Do not treat a task as complete while relevant CI or review findings
remain unresolved.
