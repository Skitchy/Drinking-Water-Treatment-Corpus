## Work reassignment and drafting brief: five-schema amendment set to Ari

Correction to the record first: my close-out said the v0.2 revision and the
five-schema amendment set would both come from CC. By maintainer decision of
2026-07-31, the work is split on the author/reviewer pattern that produced
PR #4: **Ari authors the five-schema amendment set and its acceptance cases;
CC authors only the RFC 004 v0.2 text revision and then adversarially
reviews Ari's PR.** The schemas encode safeguards Ari designed, so the
designer drafts and the counterparty attacks.

### Drafting brief (Ari)

**Scope: five artifacts, one PR, acceptance cases included.**

1. `procedure-contract/v0.1`: a fixed finite transition contract and nothing
   more. Controlled identifiers for resolution states, trigger conditions,
   permitted and mandatory transitions, ordering constraints, and terminal
   mappings to the three envelope outcomes and their reason gates. No
   expression language, no model-authored branches, no loops.
2. `evaluation-manifest/v0.1`: separately versioned; explicit compatibility
   pins to corpus-release digest, procedure/runbook digest, runtime under
   evaluation, and evaluation-schema and grader versions. Two named case
   classes: conformance/regression suite and capability challenge set. Per
   accepted case: stable ID, human reviewer and review time, rationale,
   severity and category, corpus digest, applicability inputs, explicit
   oracle (required, allowed-alternative, and forbidden claim/quote/cell IDs
   for evidence-backed; reason codes and policy gates for evidence-only and
   abstention).
3. `runtime-assurance-manifest/v0.2`: pins the runbook and procedure
   contract directly, fail-closed. Runbook declaration carries stable ID,
   version, owner, review time, `next_due_at`, supersession, and compatible
   procedure-contract digest. Overdue status derives at evaluation time per
   the source-watch precedent; a stored assertion never overrides it.
4. `audit-envelope/v0.2`: required `procedure` block whenever the named
   runtime manifest declares a procedure contract; answer reference becomes
   `answer_id` plus `artifact_sha256`; the audit record gets its own
   canonicalization and integrity digest; recorded procedure-contract digest
   must equal the manifest pin; transition sequence semantically validated
   against the pinned contract. One-way binding only.
5. `reviewer-registry/v0.2`: adds `procedure-domain` and
   `procedure-assurance` scopes.

**Maintainer rulings to encode, all on record in this thread:** the eval
split with the 100% offline target scoped to the conformance suite; the
capability pool named a public rotating challenge set with harness-enforced
isolation and no blind-holdout claim; a qualified human owns every accepted
oracle and every compatibility re-disposition; the runbook pins in the
runtime-assurance manifest.

**File boundary, to prevent edit collisions:** Ari owns `schemas/`,
`tests/`, and schema docs. CC owns `proposals/` and the new pages tree.
Neither edits the other's tree during this cycle; `PROJECT-STATE.md`
reconciliation happens at CC review time.

Separately, the maintainer has asked Ari to review the source-capture
commit (`2250962`) on the same author/reviewer principle. That review is
welcome and independent of this brief.

CC
