# Schema ratification candidate v0.1

Status: proposed; not ratified

This change set dispositions the adversarial findings recorded in RFC 002 and
RFC 003. Ratification requires explicit maintainer decisions after review of
the pull request and its executable acceptance cases.

## RFC 002 findings

| Finding | Disposition | Ratification artifact |
| --- | --- | --- |
| F1: vacuous evidence-backed pass | Accepted and strengthened. The runtime manifest declares required checks by outcome, subject kind, and where applicable claim kind. Semantic validation requires every check for every applicable envelope, page, claim, selected table cell, and quote; omission is failure. The minimum matrix is a separately digest-pinned machine-readable artifact loaded by the checker, so the vacuity cannot move upstream into a weak manifest or a stale hard-coded checker copy. | Required-check baseline, runtime manifest, answer schema, AT-016, AT-017, AT-031, AT-033 |
| F2: reason codes float free | Accepted. Reasons are structured causes naming a permitted failed check or policy gate and affected subjects. | Answer schema, runtime reason rules, AT-018 |
| F3: formats unenforced | Accepted. AJV 2020-12 and `ajv-formats` run in CI with strict compilation and format assertion. | `package.json`, workflow, AT-019 |
| F4: query digest canonicalization absent | Accepted. Answer and audit query records name the canonicalization ID pinned by the runtime manifest. | Runtime, answer, and audit schemas |
| F5: AT-014 instrument unstated | Accepted. AT-014 is backed by a versioned conformance-claims policy, not a claim of control over third-party code. | `CONFORMANCE-CLAIMS-v0.1.md` |
| F6: unexplained ineligibility | Accepted. `eligible: false` requires one or more ineligibility codes; eligible candidates carry none. | Audit schema, AT-020 |
| F7: regeneration attempts vanish | Accepted with privacy narrowing. Every attempt records its ordinal, response digest, candidate IDs, and rejection codes; rejected prose is not retained by default. | Audit schema and fixture |
| F8: digest privacy overstated | Accepted. Documentation calls the digest an integrity fingerprint, not anonymization. Query retention and any future keyed fingerprint require policy. | Answer and audit comments, project state |
| F9: too many independent versions | Accepted in diagnosis; remedy modified. Corpus evidence and reader behavior receive separate content-addressed manifests because they have different release lifecycles. Every answer and audit record pins both. | Corpus-release manifest, runtime-assurance manifest, AT-030 |

## RFC 003 findings

| Finding | Disposition | Ratification artifact |
| --- | --- | --- |
| P1: licensing review absent | Accepted at source/component scope. Approved reproduction decisions bind reviewer, time, evidence, covered components, exclusions, and decision-payload digest. Stable pages resolve those decisions through the pinned source registry. | Source registry, profile source refs, AT-022 |
| P2: actor scopes disagree | Accepted for v0.1. Human and process scopes are disjoint in the schema; the checker rejects instead of filtering invalid claims. | Profile schema, AT-023 |
| P3: watch snapshot presented as live | Accepted. Stored data is renamed as the last observed result. Effective overdue state is derived from evaluation time and `next_due_at`. | Profile schema and semantic check, AT-021 |
| P4: free-text relation and derivation | Accepted. Relations use controlled operators and regulatory metric classes. Derivations name a registered algorithm, typed parameters, inputs, and structured rounding. | Profile schema |
| P5: quote/source binding unstated | Accepted as a semantic invariant. | Profile semantic check, AT-024 |
| P6: bounds, uniqueness, anchors, cycles, formats | Accepted. Anchors are versioned selectors; semantic validation covers population ordering, ID uniqueness, and derivation cycles; AJV asserts formats. | Profile schema and AT-019, AT-025, AT-027, AT-028 |
| R1: expiry unused | Accepted with historical nuance. Qualification must cover the event timestamp. Later expiry blocks new review but does not silently invalidate earlier valid review; explicit revocation may do so under policy. | Reviewer schema and AT-026 |
| R2: registry verification self-attested | Accepted. The field is renamed `record_updated_at`; registry presence does not imply independent verification or competence. | Reviewer schema |

## Additional ratification correction

Schema `$id` values no longer point at the mutable `main` branch. They use
immutable logical `urn:dwtc:schema:*` identifiers; artifact manifests bind
those identifiers to exact bytes by digest. AT-029 enforces the identifier
policy.

## PR follow-up findings

| Finding | Disposition | Ratification artifact |
| --- | --- | --- |
| N1: two-anchor lifecycle churn unstated | Accepted. Exact compatibility is deliberate: every corpus release requires a newly minted runtime manifest, even when runtime-only bytes are unchanged. | Runtime manifest comment, schema README |
| N2: baseline duplicated in prose and checker | Accepted before ratification. `contracts/assurance-check-baseline-v0.1.json` is the single machine-readable minimum matrix. The runtime manifest pins its exact file digest and the checker loads it rather than maintaining a copy. | Baseline artifact and policy note, AT-031, AT-033 |
| N3: unresolved claim kind skipped | Accepted. Every answer claim reference must resolve to a claim and kind before kind-specific subject calculation. Failure to resolve is rejection, not exemption. | Answer semantic rule, AT-034 |

## First-proof table-claim amendment

The maintainer selected a table-valued claim for matrix-shaped regulatory
requirements rather than flattening each cell into an independent scalar
claim. The v0.1 profile therefore defines:

- stable dimension, band, and cell identifiers;
- explicit open or closed numeric band bounds;
- nonoverlapping bands and complete row-by-column cell coverage;
- independent units for both dimensions and the cell values; and
- a claim-level relation that applies uniformly to every cell.

An answer referencing a table claim must select one or more stable cell IDs.
Every selected cell becomes a `claim-cell` subject requiring a passing
`table-cell-fidelity` check. This closes the gap between storing a table
honestly and proving which cell supplied a deterministic display. AT-032 and
AT-035 through AT-040 exercise the amendment.

## F9 lifecycle boundary

The split is deliberate:

- A **corpus release manifest** pins the profile schema, review
  canonicalization, quote normalization, source and reviewer registries,
  coverage artifact, page bytes, and stable claim/quote IDs.
- A **runtime assurance manifest** pins a compatible corpus digest plus the
  answer and audit schemas, eligibility policy, verifier, generator, index,
  query canonicalization, deterministic algorithms, required-check matrix,
  outcome-reason mapping, and renderer templates.

Changing a verifier or renderer does not republish unchanged regulatory
evidence. Changing a source or page does not silently inherit an old runtime
policy. An answer is reproducible only when both manifest digests resolve and
the runtime manifest declares the exact corpus digest compatible.

The exact compatibility declaration creates intentional manifest churn: each
new corpus release also requires a new runtime manifest declaring that corpus,
even if its other runtime artifacts are unchanged. This is the cost of making
compatibility explicit instead of silently inherited.

## Ratification procedure

1. Review and disposition every row above.
2. Run `npm ci && npm test`.
3. Record `ratify` or `revise` for each of the seven schemas in RFC 003.
4. Merge only after all blocking findings are closed.
5. Tag the ratified schema foundation.
6. Require a pull request, rationale, and version decision for every later
   schema change.
