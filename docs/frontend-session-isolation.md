# Frontend login-session isolation

Issue: [#191](https://github.com/Pavel404-dev/Mealio/issues/191).

`SecureStorageService.sessionLifetime` identifies one local login lifetime.
It is independent of `tokenPairRevision`, which tracks completed pair mutations
and lets a delayed 401 reuse an already rotated pair in the same lifetime,
even when the access JWT string did not change. Neither identity nor lifetime
is inferred from token contents, user ID, or email.

## Ownership and pending operations

- Login starts by synchronously advancing the lifetime and queuing local cleanup,
  before awaiting storage or the login response. The returned pair is installed
  conditionally for that captured lifetime. Even a login of the same user starts
  a new lifetime; a failed login does not revive the old one.
- Logout and explicit pair deletion advance the lifetime at invocation, before
  waiting for pending writes. Logout reads the latest refresh token inside the
  queue, deletes locally, and then best-effort revokes that captured token.
- Direct `writeTokenPair` represents a new login and advances lifetime at
  invocation. Login's conditional write and refresh rotation do not advance it.
- Conditional failure cleanup checks ownership inside the queue, ends only its
  own lifetime, and rechecks ownership after deletion before invalidation.
- Pair reads, writes and cleanup use the same queue. A platform operation already
  started for A may finish after B's intent, but B's write cannot interleave with
  it. Reads for B wait for complete storage operations and cannot borrow A's
  credentials. Partial-write cleanup remains inside that queue. Low-level token
  I/O methods are platform hooks; application code uses the session/pair methods.

The lifetime is local to the shared storage service in one running application.
At startup, existing persisted credentials belong to its initial lifetime.
This does not add a multi-process lock or crash-atomic platform storage.

## Requests, refresh and state

`ApiClient` captures the lifetime synchronously when an application request is
created. The protected interceptor retains it through retry, checks it after
async reads, and rejects stale successes. Internal direct Dio callers fall back
to capture at the first interceptor invocation; application feature code must
use the configured `ApiClient`. `/auth/me` also accepts its repository operation's
original lifetime so an earlier await cannot silently rebind it.

`SessionHttpClientAdapter` checks ownership immediately before delegating to the
HTTP transport, after Dio's async interceptors and request transformation. This
closes the gap between the interceptor check and actual transport dispatch.
Already dispatched requests cannot be unsent or rolled back by the client.
Public auth endpoints retain their exclusions; refresh uses an explicit owner
on the bare transport, and orphan-token revocation uses only its captured token.

Refresh single-flight is keyed by lifetime. A's completion/finally cannot remove
B's registration. Stale success revokes only the returned orphan refresh token;
stale failure does not delete or invalidate B. Same-session network/503 failures
preserve credentials. Each protected request retries at most once.

AuthRepository pins login/restore/current-user reads and conditional cleanup.
AuthController uses a separate operation counter and mounted checks for state
publication across restore, login, reload, logout and disposal. Logout publishes
local unauthenticated state immediately; completion of remote revocation cannot
clear a later login. No general feature-cache redesign is included.

## Verification

On baseline `3b2aa5eed59137c038e2ea33a1e84bf83ce1924a`, the two
`session isolation:` tests in `auth_interceptor_test.dart` were run before
production changes. Both failed: delayed initial PATCH 401 produced a second
transport request, and delayed refresh 401 removed B's access token.

Regression coverage uses Completer barriers and the real storage base-class
orchestration via `FakeSecureStorageService`. Additional tests cover reads,
transport dispatch, pending writes and cleanup, per-lifetime single-flight,
same-token relogin, stale repository/controller completion, and disposal.
Existing auth, recovery, router and widget tests remain the compatibility gate.

Run the focused gate from `frontend/`:

```sh
flutter test --no-pub test/core/network test/core/storage \
  test/features/auth/data/auth_repository_test.dart \
  test/features/auth/presentation/auth_controller_test.dart
```

Run the full gate from the repository root:

```sh
bash scripts/check-frontend.sh
git diff --check
```

Exact-commit CI, independent review and post-merge phone QA are separate delivery
steps. Automated widget tests do not establish device E2E coverage.
