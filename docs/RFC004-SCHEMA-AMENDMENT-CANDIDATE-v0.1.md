# RFC 004 schema amendment candidate v0.1

Status: CANDIDATE for pull-request review and explicit maintainer
ratification. This document does not modify the seven schemas ratified as
`schema-foundation-v0.1`.

Normative discussion record:
[RFC 004](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/5),
including the accepted review safeguards and the
[five-schema drafting brief](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/5#discussioncomment-17851951).

## Amendment boundary

| Artifact | Version | Candidate consequence |
| --- | --- | --- |
| Procedure contract | v0.1 | Creates a closed finite transition table for mandatory resolution behavior. |
| Evaluation manifest | v0.1 | Separates regression conformance from capability measurement and pins every compatibility input. |
| Runtime assurance manifest | v0.2 | Directly pins the runbook and procedure contract; an absent or overdue runbook fails runtime qualification. |
| Audit envelope | v0.2 | Binds the exact answer digest and records the controlled procedure path. |
| Reviewer registry | v0.2 | Adds `procedure-domain` and `procedure-assurance` scopes without reinterpreting prior scopes. |

The version bumps are additive. Existing v0.1 runtime, audit, and reviewer
artifacts retain their original meaning. They do not acquire RFC 004
procedure-conformance claims retroactively.

## Procedure contract

`procedure-contract/v0.1` intentionally contains only:

- controlled states and one initial state;
- finite declarations for trigger conditions and terminal controls;
- permitted or mandatory transitions in declared order, each classified as
  standard or fallback entry; and
- terminal mappings to `evidence-backed`, `evidence-only`, or `abstention`
  with controlled reason gates for non-backed outcomes.

Semantic validation supplies what JSON Schema cannot: unique declarations;
resolved state, trigger, condition, and terminal-control references; compatible
condition and control kinds; exactly one initial state; reachability;
acyclicity; deterministic state-and-trigger routing; no outgoing terminal
transitions; and complete terminal mappings. The declarations are finite,
human-readable identifiers, not predicates. General branching expressions,
model-authored control flow, and loops are outside v0.1.

Clarification remains inside the ratified three-outcome boundary. A missing
applicability input maps to `abstention`, `APPLICABILITY_UNRESOLVED`, and one
or more controlled policy-gate IDs. A conforming renderer—not the answer or
audit envelope—turns those IDs into deterministic clarification text from the
template set pinned by the runtime manifest.

## Runtime and runbook qualification

`runtime-assurance-manifest/v0.2` retains every v0.1 pin and adds two direct
runtime-side dependencies:

1. the human- and agent-readable runbook; and
2. its compatible machine-readable procedure contract.

The runbook declaration records stable ID, version, digest, owner, review
time, `next_due_at`, supersession, compatible procedure digest, controlled
fallback reasons, and controlled gotcha checks. The last two lists make audit
completeness testable without trying to infer identifiers from prose.

Effective status is derived, never stored as an override:

```text
evaluation_time >= next_due_at  =>  runbook overdue
```

An overdue runbook prevents evidence-backed runtime qualification or
promotion. It does not change corpus-page stable status because knowledge
validity and reader qualification are separate claims.

## Audit binding and trace

`audit-envelope/v0.2` replaces the unbound `answer_id` field with
`answer_id` plus the verified answer's `artifact_sha256`. The audit has its
own canonicalization and integrity digest. Binding is deliberately one-way:
the audit identifies the exact answer, while verified-answer/v0.1 does not
claim that an audit exists.

The `procedure` block remains shape-optional because the cross-artifact rule
is conditional. Semantic validation requires it whenever the resolved runtime
declares a procedure contract. A conforming trace proves:

- the procedure digest equals the runtime pin;
- structured-claim resolution was attempted first;
- fallback authorization is true if and only if the trace traverses a
  contract-declared fallback-entry transition, and any such fallback cites a
  reason declared by the pinned runbook;
- observed transitions resolve, remain continuous, obey declared order, and
  terminate at the recorded state;
- the terminal mapping agrees with the audit and answer outcome;
- every recorded gate resolves to a compatible controlled declaration, and
  relevant clarification or abstention gates are recorded; and
- every gotcha ID declared by the runbook is accounted for.

The trace contains controlled identifiers and verdicts, not free-form chain of
thought.

## Evaluation boundary

`evaluation-manifest/v0.1` pins the exact corpus release, procedure contract,
runbook, runtime manifest, evaluation schema, and grader. Each active case
carries stable identity, question, rationale, severity, category, corpus
digest, applicability inputs, structured oracle, and one or more human-owned
compatibility dispositions.

The two case classes make different claims:

- The public conformance/regression suite has an exact 100% offline target.
  It measures preservation of known required behavior.
- The capability pool is named a `public-rotating-challenge-set`, not a blind
  holdout. Its current fixture declares the maintainer-ratified 10-to-15
  active range. The bounds are manifest policy rather than permanent schema
  constants, allowing future size changes without redefining the artifact
  type.

The isolation declaration permits a conforming harness to give the reader only
the current question and permitted applicability inputs while the grader holds
the oracle and remaining pool. Schema validation can describe that contract;
only a future process-level integration test can prove that the reader cannot
access grader state. AT-069 therefore remains explicitly specified rather than
falsely marked passing.

Evidence-backed oracles separate required selections, allowed alternatives,
and forbidden claim, quote, and cell IDs. Semantic validation requires both
required and alternative selections to be disjoint from forbidden IDs on all
three identifier kinds. Evidence-only and abstention oracles name acceptable
reason codes and their check or policy-gate sources. Every
compatibility re-disposition records a qualified human reviewer, time,
rationale, the exact four compatibility digests, and a
`case_review_payload_sha256` over the case excluding disposition history. A
post-review change to the question, rationale, applicability inputs, expected
outcome, or oracle therefore invalidates the human disposition.

The case review payload uses the same recursive key ordering, preserved array
ordering, whitespace-free UTF-8 JSON, and SHA-256 rules described below, but
removes `compatibility_dispositions` rather than an integrity field.

The capability challenge set keeps active `cases` separate from a content-bound
`retired_cases` ledger. Only active cases count toward declared bounds or
grading. A retired entry retains its accepted history and must end in a
content-bound `retired` disposition, making exercise of
`retire_on_design_exposure` auditable rather than erasing the record.

## Reviewer scopes

`reviewer-registry/v0.2` adds:

- `procedure-domain`: clarification triggers, applicability judgment, domain
  gotchas, and accepted evaluation oracles; and
- `procedure-assurance`: transition mechanics, envelope and gateway
  alignment, integrity binding, and trace completeness.

Later inactivity or qualification expiry does not silently rewrite an earlier
valid review. Explicit revocation remains the mechanism capable of
invalidating prior events under policy.

## Candidate canonicalization profile

The four new integrity-bearing fixtures use this candidate profile:

1. remove only `/integrity/artifact_sha256` from the artifact being hashed;
2. order object member names lexicographically at every depth;
3. preserve array order;
4. serialize as whitespace-free UTF-8 JSON with no trailing newline; and
5. calculate SHA-256 over those bytes.

The executable values are recorded in
`tests/acceptance/fixtures/rfc004-canonicalization-vectors-v0.1.json`.
Signature fields are not present in these four schemas, so the v0.1
verified-answer signature exclusion does not apply here. This profile becomes
normative only through review, merge, and explicit ratification.

## Acceptance disposition

AT-041 through AT-068 and AT-074 through AT-081 are executable candidate cases.
They cover schema closure, condition and control resolution, acyclicity,
deterministic routing, reason gates, direct pins, staleness, answer and audit
integrity, procedure-trace continuity, bidirectional fallback authorization,
complete gotcha accounting, evaluation classification and bounds, satisfiable
oracle selections, reviewer authorization, auditable case retirement, and
compatibility re-disposition and content-bound human oracle ownership.

AT-069 through AT-073 remain explicit integration requirements:

- process-level challenge-set isolation;
- invariant semantic display projection under fixed inputs;
- weaker-reader degradation without unsupported evidence-backed output;
- dependency- and digest-aware cross-layer change review; and
- deterministic renderer clarification from controlled applicability gates.

The distinction is deliberate: schema and semantic fixtures establish the
contract foundation, but do not claim that an as-yet-unbuilt reader, renderer,
or isolated evaluation runner already conforms.

## Ratification procedure

1. CC adversarially reviews the five schemas, fixtures, semantic checker, and
   candidate canonicalization vectors.
2. Every finding is dispositioned in RFC 004 or the pull request.
3. `npm ci && npm test` must pass from a clean checkout.
4. The maintainer records `ratify` or `revise` for each schema version.
5. Merge only after all blocking findings are closed.
6. Reconcile `PROJECT-STATE.md` at CC review time, per the agreed file
   ownership boundary.
