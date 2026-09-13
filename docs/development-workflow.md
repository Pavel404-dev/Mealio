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
   impact before implementation.
2. Start from an up-to-date, clean `main`, then create one focused branch, for
   example `feat/pantry-search` or `fix/token-refresh`. Do not mix unrelated
   cleanup into the branch.
3. Make small, cohesive commits using [Conventional Commits](https://www.conventionalcommits.org/):
   `feat(frontend-pantry): add item search`, `fix(auth): reject expired token`,
   or `docs: clarify development workflow`.
4. Run the smallest relevant local check first, then the full affected suite.
   Follow the commands and database-safety rules in `AGENTS.md`. Report only
   checks that actually ran.
5. Open a small PR linked to the issue and complete the PR template. Keep its
   title and commits focused on the same outcome.
6. The author reviews the complete diff. A human reviewer checks the scope,
   behavior, tests, security and migration implications, and whether Actions
   results support the change.
7. Merge only after required review and GitHub Actions pass. `main` receives
   reviewed PRs only; do not use it as an integration branch for unreviewed work.

The current Actions workflows run backend quality checks, migrations, backend
tests, a backend image build, and Flutter format, analysis, and tests for PRs
targeting `main` and pushes to `main`. They complement, rather than replace,
relevant local verification and human review.

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

## Future delivery phases

See [Railway staging](staging.md) for the project IaC, manual secrets, plan/apply
workflow, verification, rollback, and $10 monthly budget. Infrastructure is
prepared in the repository; provisioning and deployment remain user actions.

Staging activation, Android distribution, manual E2E, n8n automation, and
TestFlight are
future phases. They are not current merge gates or deployment commitments. Until
then, record manual E2E as `N/A — manual E2E is a future phase` unless an issue
is explicitly preparing a future scenario.
