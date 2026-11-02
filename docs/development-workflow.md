# Development workflow

This workflow keeps `main` clean, makes changes reviewable, and preserves the
checks in the repository's current CI.

## Delivery path

This is a human-owned repository process. Under the current repository policy,
the user creates or modifies GitHub issues, creates branches, commits, pushes,
opens PRs, performs review actions, and merges.

Automated coding agents may inspect the provided working tree or branch, edit
files, run verification, inspect diffs, and report proposed work. They must not
perform the prohibited Git or GitHub mutations listed in [AGENTS.md](../AGENTS.md).

1. Create a focused GitHub issue with the feature form. Define the goal, scope,
   exclusions, acceptance criteria, verification, and security or migration
   impact before implementation. For changes to user behavior, write 2–4
   concrete examples of the expected result, including an edge case, before
   coding. Use them during review and testing. Pure documentation and mechanical
   changes do not need artificial behavior examples.
2. Start from an up-to-date, clean `main`, then create one focused branch, for
   example `feat/pantry-search` or `fix/token-refresh`. Do not mix unrelated
   cleanup into the branch.
3. Make small, cohesive commits using [Conventional Commits](https://www.conventionalcommits.org/):
   `feat(frontend-pantry): add item search`, `fix(auth): reject expired token`,
   or `docs: clarify development workflow`.
4. Run the smallest relevant local check first, then the full affected suite.
   Follow the commands and database-safety rules in `AGENTS.md`. Report only
   checks that actually ran.
5. Open a small PR linked to the issue and complete the PR template, including
   the deployment decision and scoped QA outcomes. Keep its title and commits
   focused on the same outcome.
6. The author reviews the complete diff. When available, an independent human
   reviewer checks the behavior examples, compatibility, concrete risks, tests,
   and security or migration implications. If no independent reviewer is
   available, record that honestly. A separate Codex review can help find
   defects but is not human approval. Green CI and no Copilot comments do not
   establish review when Copilot could not complete it.
7. Merge only after required reviews and GitHub Actions pass. `main` is not an
   integration branch for unreviewed work.
8. After merge, the owner records post-merge CI, deployment, APK and actual QA
   evidence in that PR; the final handoff links to it.

The current Actions workflows run backend quality checks, migrations, backend
tests, a backend image build, and Flutter format, analysis, and tests for PRs
targeting `main` and pushes to `main`. A separate workflow builds the Android
QA APK after frontend changes reach `main`. These checks complement relevant
local verification and review.
For the complete local Flutter checks from the repository root, run
`bash scripts/check-frontend.sh`.

## Sources and freshness

| Source | Role |
| --- | --- |
| Current Git `HEAD`, worktree, migrations/tests and topic docs | Implementation, contracts and accepted semantics; follow the source hierarchy in `AGENTS.md`. |
| PR, Actions runs and sanitized receipts | Observed review, CI, artifact, deployment and scoped QA evidence, tied to a SHA and date. |
| Notion | Roadmap and progress; not runtime or implementation evidence. |
| [Project status](project-status.md) | Compact dated index of the last verified delivery, open decisions and next action. |
| Portable checkpoint/handoff | Short index linking the above sources, not a chat transcript or new authority. |

At task start, read the status snapshot, current instructions and relevant topic
docs; check branch/HEAD, worktree/index and relevant refs. Inspect each reused
observation's date, source SHA, scope and evidence. An old snapshot need not
match today's HEAD. Resolve discrepancies by checking fresh authoritative
sources, not by changing documents from memory. If evidence or runtime access
is unavailable, preserve the last observation's date/source and mark the current
fact unknown or the dependent check BLOCKED. Do not run new runtime checks solely
to refresh a documentation snapshot.

Record substantial accepted decisions and constraints in existing topic docs or
linked rationale alongside the implementation. A checkpoint links to that
knowledge instead of copying it. No ADR is required for every change; avoid new
archive trees, transcripts and large command journals. Keep raw/private evidence
outside Git and publish only sanitized references.

## Deployment decisions and QA

Every task needs an explicit deployment decision; every merge does not need a
deployment. Record the target, relevant source/artifact SHA, date and evidence:

| Decision | Required record |
| --- | --- |
| Done | Actual delivery to the named target, verified SHA, observation date and evidence; limit the claim to the checks performed. |
| Pending | Delivery still needed, reason and concrete next action/owner. |
| Deferred | Reason for postponement and the follow-up or condition for reconsidering it. |
| N/A | Reason deployment does not apply, for example documentation-only changes. |

Record QA separately as **PASS / FAIL / NOT_RUN / BLOCKED / N/A**, with the
scenario/scope, environment/device when applicable, source/artifact SHA, date and
evidence. Explain FAIL, skipped, blocked or inapplicable checks and the next step.
Record APK build/run evidence independently of installation/device results and
the backend's own deployed SHA/as-of date. Health/OpenAPI checks do not establish
business-flow E2E. Automated review and green CI are not human approval.

The repository status is a snapshot, not a live dashboard. Its SHA identifies a
verified feature/artifact, not the containing documentation commit. Never invent
a future SHA. The owner keeps post-merge evidence in the linked PR; refresh the
snapshot in an ordinary agreed task branch when appropriate. Do not require a
new commit after every CI transition, merge or deploy, or leave dirty `main` after
handoff. A docs-only commit retains the last verified backend SHA.

The existing Backend/Frontend workflows run on PRs to `main` and pushes to `main`
without path filters, including docs-only changes; they remain delivery gates.
The Android workflow has its own path filters. Docs-only changes do not match
those filters and need no manual APK build or deployment. Relevant local checks for
docs-only work are complete-diff review, `git diff --check`, changed Markdown
links/anchors and rendered-document review; no local DB/Flutter suites are needed
solely for Markdown edits.

Use these cases when reviewing the delivery record:

| Case | Honest record and next step |
| --- | --- |
| Feature merged, CI green, staging still on an older SHA | Deployment Pending with next owner action, or Deferred with reason; retain the backend's observed SHA/date. |
| APK build passed, no installation | Record build/run SHA; device QA NOT_RUN. Record backend SHA/as-of independently before dependent flow checks. |
| Docs-only PR | Deployment N/A with reason; keep the backend SHA. Owner records later CI in the PR, without self-reference commits. |
| Old snapshot, runtime unavailable | Retain dated evidence; validate current refs/instructions, mark current state unknown or QA BLOCKED, and identify the missing access/evidence. Old permissions do not resume. |

## Task handoff

End each task with a short record, linking evidence instead of copying history:

- Branch/HEAD and worktree/index state; task result and remaining delivery work.
- Checks run, reused and not run, with results, source SHA/date and reasons or
  limitations. Reused evidence must not read as a new execution.
- CI and review status, separating owner, independent human and automated review;
  deployment decision; APK build and scoped QA outcomes with evidence links.
- Accepted decisions/constraints and links to topic docs or rationale; unresolved
  decisions and limits on what the evidence proves.
- Resources left running, local artifact paths, and concrete next action/owner.

Do not include transcripts, credentials or private data. Old checkpoints do not
renew database, role, cleanup or deployment permissions; check current authority
for the specific target/action. Git/GitHub mutations remain human-owned under
`AGENTS.md`. The final post-merge handoff links to the PR's delivery evidence;
an implementation handoff must label commit/push/PR, final-SHA CI and review as
outstanding when they have not happened.

## Local development and Codex Cloud

Local development is the default place to inspect the affected code, make the
change, and run the relevant checks. Keep the working tree intentional: inspect
`git status`, preserve unrelated work, and inspect the complete diff before a
PR.

Codex Cloud may be used for a bounded implementation task when the issue gives
clear scope, acceptance criteria, and verification expectations. The same agent
restrictions apply. The user takes its proposed work through the delivery path,
Actions checks, and human review described above.

## Model routing and token discipline

Use the approved routing policy according to change risk and ambiguity:

| Configuration | Use for |
| --- | --- |
| Luna / Light | Simple Git operations, status checks, concise commands, documentation, and low-risk mechanical work. |
| Sol / Medium | Default for normal FastAPI and Flutter implementation, tests, and focused debugging. |
| Astra / High | Security, JWT/OTP/authentication, migrations, rollback, concurrency, cross-cutting architecture, and difficult investigations. |
| Astra / Extra High | Only for critical final diff review. |

Normally select one configuration for the complete bounded task instead of
switching models for every terminal command. Do not use Fast mode without a
concrete reason.

Model routing must never be used to omit a relevant test, Actions check,
complete-diff review, or human review.

Save tokens without weakening quality:

- Keep one issue and PR to one outcome; record exclusions before implementation.
- Give the agent the affected paths, expected behavior, failing test or
  reproduction, and acceptance criteria instead of broad exploratory prompts.
- Inspect focused files and reuse existing patterns before proposing new ones.
- Run the smallest relevant check early, then all affected checks; avoid
  repeatedly running unchanged broad suites.
- Batch independent questions into one concise task, but resolve failures and
  review the final complete diff before handoff.
- Choose Luna, Sol, or Astra by risk, not by a desire to bypass verification.

## Staging and later delivery

See [Railway staging](staging.md) for the project IaC, manual secrets, plan/apply
workflow, verification, rollback, and $10 monthly budget. Railway backend
deployment is a user action independent of the Android APK build.

After frontend changes merge into `main`, Actions automatically builds an
internal Android staging QA APK. A person checks the run's source commit and
downloaded APK checksum, installs it on a phone, and records the scenarios
actually checked and their results. See the [Android QA guide](android-staging-qa.md).
Its manual install helper requires a specific run ID, full commit SHA, and
device serial.
An optional manual build remains available.

Broader manual mobile E2E, n8n automation, production Android distribution,
and TestFlight remain separate phases. Device checks already performed should
be reported as actual results; do not claim broader E2E coverage from an APK
build or a limited phone check.
