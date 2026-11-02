## Linked issue

Closes #

## Summary

<!-- What outcome does this PR deliver? -->

## Scoped changes

<!-- List only changes made for this issue. -->

-

## Verification actually run

<!-- List commands/checks run and their results. Do not claim checks that were not run. -->

- [ ] Not run (explain why)

<!-- Include source SHA/date and evidence for CI or reused checks; distinguish reused results from new executions. The owner records post-merge CI/delivery/QA in this PR and links it from the final handoff. See docs/development-workflow.md and docs/project-status.md; no status-only/self-reference commits are required. -->

## Expected behavior examples

<!-- For user behavior changes, link or repeat 2–4 examples defined before implementation, including an edge case; use them in review and tests. For documentation or mechanical changes, write N/A. -->

N/A.

## Deployment decision

<!-- Required: Done — target, verified source/artifact SHA, observation date and evidence; Pending — reason and next action/owner; Deferred — reason and follow-up/condition; N/A — reason (e.g. docs-only). Deployment is not required for every merge. Merged/green code does not establish deployment. Preserve the last observed backend SHA/as-of for docs-only work. -->

Decision: Pending — owner to record the delivery decision and next action before merge.

Backend target / last observed deployed SHA / as-of / evidence:

## QA outcomes

<!-- Use PASS / FAIL / NOT_RUN / BLOCKED / N/A for each relevant scope; include scenario, environment/device, source/artifact SHA, date and evidence. Explain skipped/blocked/inapplicable checks and the next action. Record APK build run/SHA independently from installation and device QA; no installation means device QA NOT_RUN. Health/OpenAPI alone is not business E2E. -->

| Scope / environment or device | Source/artifact SHA / date | Outcome | Evidence / reason / next action |
| --- | --- | --- | --- |
| Applicable manual/API/device scenarios (specify) | | NOT_RUN | Checks not yet recorded; specify scope and next action. |

APK build run / source SHA / date / result / evidence (or N/A with reason):

## Review status

<!-- Choose one: Reviewed — reviewer and outcome; Pending — requested reviewer; Unavailable — reason. Record automated review separately with SHA and evidence. Automated review and green CI are not human approval. -->

Status: Pending — independent human review not yet recorded.

## Security and migration impact

<!-- Cover auth, authorization, secrets, data handling, transactions, and Alembic. Write "None" when not applicable. -->

None.

## Screenshots

<!-- Add screenshots or recordings for relevant user-visible changes; otherwise write N/A. -->

N/A.

## Author checklist

- [ ] The linked issue and this PR remain focused; out-of-scope work is excluded.
- [ ] I reviewed the complete diff and kept unrelated changes out.
- [ ] I ran the relevant local checks and reported only what actually ran.
- [ ] I considered security and migration effects and documented them above.
- [ ] GitHub Actions are green, or any failure is explained and resolved before merge.
- [ ] Independent human review is recorded when available; if unavailable, I stated that without treating CI, Copilot silence, or Codex review as human approval.
- [ ] The PR is ready for review; no secrets, generated credentials, or deployment configuration were added.
