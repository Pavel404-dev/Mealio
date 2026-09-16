# Railway backend staging

This is the preparation and future operator runbook for Issue #165. No Railway
project, service, database, domain, variables, or deployment was created by this
change. The dashboard and CLI steps below are for the user to perform later.

Use one Railway project with a persistent `staging` environment containing two
separate services: `backend` and `Postgres`. PostgreSQL owns its own persistent
volume; the backend has no volume. Use only disposable synthetic accounts and
fixtures. Never copy production databases, real user data, or local/production
secrets into staging. Test email delivery only to controlled test mailboxes.

## Repository-managed infrastructure

[.railway/railway.ts](../.railway/railway.ts) is the single project-level
infrastructure definition. It uses the supported TypeScript
[Railway IaC workflow](https://docs.railway.com/infrastructure-as-code), checked
on 2026-09-13. Legacy `railway.json`/`railway.toml` is deprecated and unavailable
to new services; no legacy configuration file is retained.

The definition describes project `mealio-staging`, a `Postgres` database, and a
`backend` service sourced from GitHub `Pavel404-dev/Mealio`, branch `main`. It
refuses to evaluate for any environment other than `staging`; it does not create
or select that environment. The user must link the intended project/environment.
The graph owns the whole environment: removing a resource or variable from the
file can plan its deletion. Do not apply it to an environment with unrelated
services. See the [IaC reference](https://docs.railway.com/infrastructure-as-code/reference).

The pinned SDK's `postgres("Postgres")` helper selects PostgreSQL 18 and lets
Railway provision the database and its volume. Local Compose and CI remain on
PostgreSQL 17. On 2026-09-14, compatibility was verified locally against a new,
disposable `postgres:18` container running PostgreSQL **18.6**. `alembic heads`
reported the single head `b7e3c9a1d5f8`; `upgrade head`, `current`, and `check`
passed with no schema drift. The full backend pytest suite ran in the backend
Docker image (Python 3.12.14, pytest 8.3.4), with the checked-in tests mounted
read-only and the repository's asyncio settings: **758 passed in 736.94 seconds**,
with **82% total `app` coverage** (`--cov=app --cov-report=term-missing`).
The database used `tmpfs`, synthetic credentials, an isolated internal Docker
network, and no published ports or existing volumes. Both verification containers
and their network were removed after the run; existing databases were untouched.
This verifies PostgreSQL 18 application compatibility, not Railway networking or
the Railway-specific database image. Repeat compatibility verification if the
helper version changes. See the
[SDK database helper](https://github.com/railwayapp/railway-ts-sdk/blob/v3.11.0/src/iac/sdk.ts).

The backend service **Root Directory must be `backend`**. This makes the backend
directory the Docker build context, equivalent to the local command
`docker build -t mealio-backend ./backend`. Use the existing
[Dockerfile](../backend/Dockerfile), whose path within that context is
`Dockerfile`, not `backend/Dockerfile`. The image includes the application,
Alembic, its configuration, and migrations; `.env` files are excluded.

| Setting | Required configuration |
| --- | --- |
| Root Directory | `backend`, declared on the GitHub source |
| Builder | `DOCKERFILE` |
| Dockerfile path | `Dockerfile` within the backend build context |
| Custom Build Command | Leave unset; use Dockerfile build instructions |
| Custom Start Command | Leave unset; use Dockerfile `CMD` |
| Pre-deploy Command | `alembic upgrade head` |
| Healthcheck Path | `/health/db` |
| Healthcheck Timeout | 120 seconds |
| Replicas | 1 total, in one region |
| Restart Policy | On Failure, maximum 5 retries |

The build and restart fields are supported by the pinned SDK's
[BuildConfig and DeployConfig types](https://github.com/railwayapp/railway-ts-sdk/blob/v3.11.0/src/iac/schema.ts).
Generated domains, secret values, billing controls, and the initial project/link
are supplied separately. After apply, verify that the backend and database use
the same single region and the backend has one total replica.

The Dockerfile starts Uvicorn on `0.0.0.0` using `${PORT:-8000}`. Quoting keeps the
port in one argument; `exec` makes Uvicorn receive container shutdown signals.
The application target and `--no-proxy-headers` are preserved. An unset or empty
`PORT` falls back to 8000. Let Railway supply `PORT`; do not hardcode a different
domain target port. The existing proxy-header policy means IP-based auth limits
use the immediate network peer, which can be shared by testers behind Railway's
proxy. Changing proxy trust is outside this issue.

[Local Docker Compose](../docker-compose.yml) keeps its existing command, local
migration step, and `8000:8000` mapping. Railway uses the Dockerfile directly and
does not run that Compose command.

## Runtime variables and manually supplied secrets

Before the first apply, open **Project Settings → Shared Variables**, select
`staging`, and add the required shared values below. The IaC uses `ctx.shared`
to reference these existing values on the backend; it does not generate, read,
or manage their plaintext. Unlike preserving a service variable that does not
yet exist, shared references allow values to be supplied before service creation.
Enter values only in Railway's private variable editor. Do not import the
development defaults suggested from `.env.example`, put secrets in Git, or paste
resolved variables into logs, issues, screenshots, or chat.

| Variable name | Purpose |
| --- | --- |
| `DATABASE_URL` | Managed by IaC using PostgreSQL references below; do not supply a credential value manually |
| `JWT_SECRET_KEY` | Required independent shared JWT signing secret, at least 32 characters |
| `AUTH_ABUSE_PEPPER` | Required independent shared auth-abuse secret, at least 32 characters |
| `EMAIL_OTP_PEPPER` | Independent shared OTP secret, at least 32 characters |
| `MAILTRAP_API_TOKEN` | Secret API token from the controlled Mailtrap sandbox |
| `MAILTRAP_SANDBOX_ID` | Numeric ID of the controlled Mailtrap sandbox |
| `SMTP_FROM_EMAIL` | Sender address used by both Mailtrap API and SMTP delivery |
| `EMAIL_VERIFICATION_URL_BASE` | Controlled staging-client destination for verification links |
| `PORT` | Supplied at runtime by Railway; consumed by the Dockerfile command |

Generate `JWT_SECRET_KEY`, `EMAIL_OTP_PEPPER`, and `AUTH_ABUSE_PEPPER` independently:
in a trusted password manager, use its random password generator three separate
times with a length of at least 64 characters. Save each under its own variable
name and transfer it directly to Railway. All three must be different from each
other and from every local or future production secret. The application enforces
a minimum length of 32 characters and rejects reuse between these secrets.

Do not configure `TEST_DATABASE_URL` on the deployed service or run pytest
against staging: the test fixtures recreate database tables.

### PostgreSQL reference URL

IaC sets `DATABASE_URL` on **backend** to this reference expression:

```text
postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
```

This is a reference template, not a connection string containing credentials.
Railway resolves the database service's variables inside the same environment.
If the service name changes, update every `Postgres` reference in the IaC. Use
its private `PGHOST`, not a public TCP proxy. Keep Railway-generated credentials;
do not substitute the repository's local Compose credentials.

The reference is deliberately a literal Railway template. SDK `db.env` references
are objects; interpolating them into a JavaScript string would not build this URL.
The PostgreSQL service's ordinary `DATABASE_URL` does not supply the required
SQLAlchemy `postgresql+asyncpg://` driver prefix. Compose the references above
instead of copying its resolved URL. See Railway's
[PostgreSQL variables](https://docs.railway.com/databases/postgresql) and
[reference-variable syntax](https://docs.railway.com/variables#reference-variables).

### Optional integrations

To enable an integration later, create its staging shared variables and add the
corresponding `ctx.shared` references to the backend's IaC `env`, then review a
new plan. Do not only add unmanaged backend variables: a later apply may remove
variables omitted from the desired state. No optional credentials are included.

| Variable names | Behavior when omitted |
| --- | --- |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_USERNAME`, `SMTP_PASSWORD` | Optional SMTP fallback for environments where outbound SMTP is available. For authenticated SMTP, supply username and password together. |
| `PASSWORD_RESET_URL_BASE` | Password-reset link delivery is unavailable without this destination URL. Password-reset OTP delivery does not require it. Configure only a destination handled by a controlled staging client. |
| `OPENAI_API_KEY` | AI recipe preview generation is unavailable and returns the existing HTTP 503 configuration response. Other backend features and health checks remain available. |
| `OPENAI_MODEL`, `AI_REQUEST_TIMEOUT_SECONDS` | The defaults in `app/core/config.py` apply when omitted; these variables only tune the optional AI integration. |

Railway currently permits outbound SMTP only on Pro and above. Free, Trial,
and Hobby block it, so staging uses the Mailtrap Sandbox HTTPS API configured by
`MAILTRAP_API_TOKEN` and `MAILTRAP_SANDBOX_ID`. The backend prefers this API when
both values are present and retains SMTP as a fallback for environments where
outbound SMTP is available. This allows authentication email testing on Hobby
without upgrading solely for SMTP access. See
[outbound networking](https://docs.railway.com/networking/outbound-networking).

Leave token lifetimes, OTP limits, JWT algorithm, and auth-abuse policies at their
checked-in defaults unless a separate task requires changing them. Optional
variables may be omitted entirely instead of being set to empty numeric values.

## Local tooling, plan, and apply — user actions for later

Use Node.js 22 or newer for the pinned SDK. Install Railway CLI 5.42.1 or
newer separately by following the official
[CLI installation instructions](https://docs.railway.com/cli#installing-the-cli),
then verify it with `railway --version`. Keep the CLI outside the repository
dependency tree.

[.railway/package.json](../.railway/package.json) pins the IaC SDK `railway` to
`3.11.0`. Install its exact locked dependency tree from the repository root:

```bash
npm ci --prefix .railway
npm test --prefix .railway
npm run typecheck --prefix .railway
```

Node.js and the SDK are used only for Railway IaC evaluation and are not
included in the backend Docker image. The offline tests invoke the exported
`RailwayProgram` with `createRailwayContext({ environment: "staging" })` and check
the actual project definition: both resources, PostgreSQL image and storage,
GitHub source and build context, deploy settings, and unresolved variable
references. They also require rejection of `production`, `development`,
case-mismatched `Staging`, and an unset environment. No Railway login, linked
project, API request, or secret values are needed. CI runs these tests and the
TypeScript check after `npm ci`.

The backend Docker CI job also runs the same runtime smoke check available locally:

```bash
docker build -t mealio-backend ./backend
bash scripts/smoke-backend.sh mealio-backend
```

It starts the image's default command with synthetic `PORT=18765` and security
configuration, waits up to 30 seconds for `GET /health` to return HTTP 200 with
the expected JSON, and checks that PID 1 is Uvicorn with the expected port and
startup arguments. It uses `--network none` and requires no database. An exit
trap removes the container on success, failure, or interruption. This smoke
check passed locally on 2026-09-14; `/health/db` remains a separate deployment
check requiring the real staging database.

The following steps create/apply remote infrastructure and are **not performed
as part of this repository change**:

1. Select the intended Railway workspace. Configure the budget controls below
   before starting services. In the dashboard choose **New Project → Empty
   Project**, then name this single project `mealio-staging`.
2. Open the environment selector → **New Environment → Empty Environment** and
   name it `staging`. Select it before adding services. Railway creates an empty
   `production` environment by default; leave it unused. Do not duplicate an
   environment containing real data or secrets. See
   [environment creation](https://docs.railway.com/environments#create-an-environment).
3. Create the three independent security secrets and the Mailtrap delivery
   shared values described above. Keep SMTP credentials and OpenAI unconfigured.
   Give Railway's GitHub integration access to `Pavel404-dev/Mealio`. The
   reviewed change must reach `main` through the
   human-owned delivery workflow before the first backend deployment; the IaC
   deliberately does not deploy this uncommitted branch.
4. From the repository root, run `railway login`, then `railway link`. Select
   only project `mealio-staging` and environment `staging`. Do not create the
   backend or PostgreSQL manually; their intent is in the IaC. Keep PR
   environments disabled to avoid extra resources and charges.
5. Run `railway config plan`. This reads remote state and previews changes;
   it does not apply them. Confirm the target environment, both resources,
   GitHub `main` source, `backend` context, migration hook, health check,
   replica count, restart policy, and secret reference names. Reject unexpected
   deletions, public database exposure, or changes outside this staging project.
   Do not use `--show-values` or export decrypted variables.
6. Only after reviewing the plan, run `railway config apply` interactively and
   confirm the intended changes. Apply is a remote mutation and may provision
   and deploy resources; it is not a validation command. Do not use automatic
   confirmation flags. Re-run plan after any dashboard edit before applying.
7. In **backend → Settings**, verify the build/deploy table above, the intended
   region, and no custom web start override. Verify PostgreSQL is private and
   its volume is present. In **Deployments → deployment details/logs**, check
   the Dockerfile build, successful pre-deploy migration, and health check.
   Review GitHub autodeploy settings; keep automatic deployments disabled until
   the first staging verification is accepted by the user.
8. After the backend becomes healthy, open **Settings → Networking → Public
   Networking → Generate Domain**. Use the detected runtime port; if a target
   port is requested, match the port shown in Uvicorn's startup log. Then perform
   both HTTP checks below. See Railway's
   [domain/port setup](https://docs.railway.com/guides/deploying-a-monorepo).

Editing `.railway/railway.ts` in Git alone does not apply infrastructure. The
operator repeats plan/review/apply for later infrastructure changes. No GitHub
Actions deployment workflow is added. In an unlinked checkout, do not treat
`railway config plan` as an offline check: the CLI will prompt for a target.

## Migrations and deployment verification

Railway runs `alembic upgrade head` in a separate pre-deploy container after the
image build and before activating the new web version. It uses `/app` as the
image working directory, the backend variables, and the private PostgreSQL
network. A failed pre-deploy command blocks the deployment and is not retried
automatically. See [pre-deploy behavior](https://docs.railway.com/deployments/pre-deploy-command).

Do not add migrations to the Dockerfile web startup command or run a second
migration process manually alongside pre-deploy. Serialize staging deployments.
The previous web version can still be serving while migrations run, so review
future migrations for compatibility with both versions. A failed health check
does not undo a migration that already succeeded.

After a future deployment, open the backend's generated HTTPS domain and verify:

| Request | Expected HTTP result |
| --- | --- |
| `GET /health` | 200 with `{"status":"ok","service":"mealio-backend"}` |
| `GET /health/db` | 200 with `{"status":"ok","database":"connected"}` |

`/health` verifies the web process. `/health/db` executes `SELECT 1` against the
configured database; it does not prove that every migration or business flow
works. Confirm migration success separately in the pre-deploy logs. Record the
commit and deployment identifiers and these check results without secrets.

The deployment health check is `/health/db`, with a 120-second readiness window.
Railway activates a deployment only after HTTP 200; an unsuccessful check leaves
it failed. This is a deployment gate, not continuous database monitoring. See
[Railway health checks](https://docs.railway.com/deployments/healthchecks).

## Rollback

1. Select the same project, `staging` environment, and `backend` service. Disable
   automatic deployments and abort any unwanted pending deployment.
2. Check which migrations completed and whether the previous application can
   run on the current schema. Prefer a forward fix if it cannot. Database schema
   and data are not restored by an application rollback; never run an automatic
   `alembic downgrade` or reset a database as part of this procedure. If a
   database restore is necessary, plan it separately against a verified staging
   backup with explicit approval for that staging database.
3. Open **Deployments**, find the last known-good compatible deployment, click
   its **three-dot menu → Rollback**, and confirm. Railway restores that image
   and its custom variables. Check private variable references and any secret
   rotation before restoring old settings; never expose the values. If the
   image is outside the plan's retention period, use **Redeploy** on the chosen
   historical deployment, which rebuilds its original source/configuration.
   See [deployment recovery actions](https://docs.railway.com/deployments/deployment-actions).
4. Repeat both health checks, confirm the active deployment identifier and
   database compatibility, and record the result. An application rollback does
   not revert project IaC. If infrastructure also needs reverting, review the
   intended source change and its new plan separately; do not remove PostgreSQL
   from the graph or reapply an old graph blindly. Diagnose the failed release
   before scheduling another deployment.

## Monthly budget: maximum $10

The total monthly staging budget is **at most $10**, covering both backend and
PostgreSQL, storage, and networking. Account for any taxes and optional external
provider charges within that ceiling; leave optional integrations disabled until
their cost fits. This is a spending ceiling, not a promise that two always-on
services cost less than $10.

Use Hobby or an available lower-cost plan. Hobby currently has a $5 monthly
minimum including $5 of usage; it is not $5 plus the same usage again. Pro's
minimum is already above this budget. Recheck billing before enabling staging.
See [Railway billing](https://docs.railway.com/pricing/understanding-your-bill).

In the workspace selector, choose the workspace that will own staging, then:

1. Open **Usage → Set Usage Limits** as a workspace administrator.
2. Under **Compute Usage**, set **Custom email alert** to $5 and **Hard limit**
   to $10. Save and confirm the settings and alert recipient. Limits apply to
   the workspace, not just this project; account for any other workloads there.
   Reaching the hard limit takes workloads offline. Railway documents $10 as
   the minimum hard limit. See
   [usage controls](https://docs.railway.com/pricing/cost-control) and
   [the minimum limit](https://docs.railway.com/guides/right-size-cpu-memory#cap-total-spend-with-usage-limits).
3. Do not use the separately billed Railway Agent for staging. Compute limits
   do not cap Agent usage or external SMTP/OpenAI bills. A compute hard limit
   also does not guarantee a $10 tax-inclusive final invoice.
4. Inspect actual and projected usage after the first day and regularly during
   testing. At the alert, or whenever the projected total exceeds $10 including
   other charges, stop staging early: **each service → Deployments → active
   deployment → three-dot menu → Remove**. Keep autodeploy disabled. Retained
   volumes and subscriptions may still cost money; include them in the remaining
   budget and arrange separate, deliberate cleanup if needed.

Keep one backend replica in one region and use private PostgreSQL networking.
Do not raise the budget or silently upgrade the plan to keep staging running.
If the ceiling cannot be maintained, leave staging offline and use local Compose.

Mobile manual E2E remains `N/A — manual E2E is a future phase`.
