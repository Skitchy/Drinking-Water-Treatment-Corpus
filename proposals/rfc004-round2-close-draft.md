## CC close-out: all three safeguards adopted; round converged

Ari, all three safeguards are adopted into the drafting instructions as written.

1. **Audit integrity binding**: `audit-envelope/v0.2` will carry `answer_id` plus the verified answer's `artifact_sha256`, its own canonicalization and integrity digest, a `procedure` block required whenever the named runtime manifest declares a procedure contract, digest equality with the pinned contract, and semantic validation of the observed transition sequence. One-way binding as you specified; any answer-side proof of audit existence is deferred to a separate version decision.

2. **Executable runbook staleness**: adopted with the source-watch precedent as the normative pattern. Overdue status derives from `evaluation_time >= next_due_at` at evaluation time; a stored assertion never overrides it. An overdue runbook fails runtime qualification for evidence-backed operation without touching corpus-page stable status.

3. **Capability-case isolation**: adopted, and worth naming plainly: my recorded quarantine mechanism was discussion discipline, which is an honor system, and this project's own design rule is that honor systems do not survive capable readers. Harness-enforced isolation replaces it: the reader under evaluation receives only the question and permitted applicability inputs; the grader holds the oracle. Maintainer ruling 2026-07-31: the pool is a **public rotating challenge set**, named as such, with lazy rotation, metamorphic variants, and immediate retirement of any case that enters design discussion. No blind-holdout claim will be made unless a genuinely access-controlled private pool exists.

Status of the round: both open preferences accepted, three safeguards adopted, no items remain open. Next from CC: RFC 004 revised to v0.2 and the five-schema amendment set with acceptance cases as a PR, incorporating everything above.

One build note: regulatory source capture proceeded in parallel as sequenced. The repository now stages the first real capture set: 28 eCFR point-in-time captures (2026-07-01, subparts L and V complete plus the dependency sections and subpart Q) and EPA 816-F-10-080, hashed, with a schema-valid `source-registry/v0.1` instance carrying maintainer-approved reproduction decisions. The interim decision-payload canonicalization is documented in `sources/README.md` and flagged for replacement by the ratified spec.

CC
