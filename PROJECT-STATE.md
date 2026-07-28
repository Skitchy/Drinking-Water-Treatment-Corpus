# Project State

Last updated: 2026-07-28

This is the repository's restart point. It records the currently accepted
design position without replacing the normative RFC discussions.

## Current checkpoint

The project is in the RFC and first-proof design phase. No regulatory pages
have been published. The immediate checkpoint is the v0.1 assurance
foundation:

- the Drinking Water Assurance Profile schema;
- the reviewer-registry schema;
- the verified-answer envelope schema;
- the minimal audit-envelope schema;
- the adversarial acceptance-test contract and foundation fixtures.

The schemas are proposed v0.1 artifacts. They become release contracts only
after project review and ratification.

## Normative design record

1. [RFC 001: The Corpus](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/1)
2. [RFC 002: The Reader](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/2)
3. [RFC 003: Cross-RFC Assurance Contract](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/3)

If this file conflicts with a later recorded RFC decision, the later decision
wins and this file must be updated.

## Accepted design position

### Corpus and review

- Human review binds to a canonical review-payload digest and becomes
  ineligible when that payload changes.
- Stable pages fail closed when required assurance or lifecycle fields are
  missing.
- Source authority, source authenticity, and reproduction licensing are
  separate determinations.
- Numeric and derived assertions use structured claims. Qualitative
  externally verifiable assertions should carry claim-level provenance.
- Context-completeness is an explicit human-review scope.
- Coverage and maintenance state are release artifacts.
- v0.1 has one declared use class: `regulatory-reference`.

### Retrieval and answers

- Pages remain the unit of publication, review, citation, and display.
  Disposable span indexes are permitted, but every match resolves to a whole
  immutable page.
- Eligibility gates run before relevance ranking. Trust may be displayed or
  used as a documented tie-breaker; it does not substitute for relevance.
- The reader has three outcomes: `evidence-backed`, `evidence-only`, and
  `abstention`.
- MCP is an evidence adapter, not an enforcement boundary.
- Verified-evidence mode does not stream unchecked model prose.
- The reference direction is a headless verified-answer gateway that owns
  retrieve, generate, validate, and envelope production.

### Enforcement boundary

The accepted claim is:

> The gateway emits only schema-valid, semantically validated,
> integrity-bound answer envelopes. A conforming renderer can produce only
> deterministic displays of those envelopes. Claims about what the user sees
> apply only to conforming clients.

The answer format is not proof by itself. The gateway must resolve stable
corpus claim and quote IDs against the named corpus release, validate their
review-payload and manifest digests, run the declared checks, and then bind
the resulting envelope to its integrity digest. `Sealed` is reserved for an
envelope carrying a verifiable signature; an unsigned artifact is a
`validated answer envelope`.

## First proof

The proposed first rule family is the Stage 1 and Stage 2 Disinfectants and
Disinfection Byproducts Rules. The proof should favor dependency-complete
coverage over an arbitrary page count and is expected to include:

- roughly 8–12 primary pages plus required definition, exception,
  cross-reference, and effective-date dependencies;
- MCL and MRDL tables, bromate and chlorite specifics, and running-annual-
  average compliance mechanics;
- 50–100 adversarial questions written before retrieval optimization;
- simulated edits, source changes, corrections, stale content, and watch
  failures.

## Implemented foundation

- [`schemas/drinking-water-profile-v0.1.schema.json`](schemas/drinking-water-profile-v0.1.schema.json)
- [`schemas/reviewer-registry-v0.1.schema.json`](schemas/reviewer-registry-v0.1.schema.json)
- [`schemas/verified-answer-v0.1.schema.json`](schemas/verified-answer-v0.1.schema.json)
- [`schemas/audit-envelope-v0.1.schema.json`](schemas/audit-envelope-v0.1.schema.json)
- [`tests/acceptance/manifest-v0.1.json`](tests/acceptance/manifest-v0.1.json)
- [`tests/acceptance/check-artifacts.mjs`](tests/acceptance/check-artifacts.mjs)

## Explicit deferrals

- Independent second review and audit sampling await additional qualified
  reviewer capacity.
- Broad state-law ingestion awaits a successful federal vertical slice.
- Retrieval architecture beyond the measured lexical baseline awaits the
  domain evaluation set.
- A production signing profile, key lifecycle, and transparency mechanism
  await the gateway implementation. The v0.1 answer schema reserves the
  integrity fields without pretending those operational controls already
  exist.

## Open decisions

- Strict-refusal versus evidence-only behavior for each stale-evidence class.
- The exact federal official-record cross-check procedure.
- Required human-review scopes by page and claim consequence class.
- The canonical review-payload serialization algorithm and conformance
  vectors.
- Signature algorithm, key identity, rotation, and revocation policy.
- The exact DBP page/dependency list and adversarial question set.
- Approved deterministic renderer templates and renderer-conformance suite.
- Retention and privacy policy for audit records and normalized queries.

## Next actions

1. Review and ratify or revise the four v0.1 schemas.
2. Add canonicalization test vectors and a real JSON Schema validator to CI.
3. Select the dependency-complete DBP proof set.
4. Author the 50–100 adversarial questions before tuning retrieval.
5. Implement corpus release manifests and stable claim/quote resolution.
6. Build the nonstreaming gateway and deliberately small conforming renderer.

## Restart procedure

On a new work session:

1. read this file;
2. inspect `git status` and the latest commits on `origin/main`;
3. read new comments in RFC Discussions 1–3;
4. reconcile any new decision into this file before implementation;
5. run `node tests/acceptance/check-artifacts.mjs`.
