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
- the source-registry schema;
- separate corpus-release and runtime-assurance manifests;
- the verified-answer envelope schema;
- the minimal audit-envelope schema;
- the adversarial acceptance-test contract and foundation fixtures.

RATIFIED 2026-07-28: all seven v0.1 schemas plus the digest-pinned
assurance-check baseline were ratified by explicit maintainer decision,
recorded in [RFC 003](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/3#discussioncomment-17819208)
and tagged `schema-foundation-v0.1` at the PR #4 merge commit. From this
point, schema changes require a version bump, recorded rationale, and
pull-request review.

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
- Reproduction decisions are content-bound at the source/component level and
  resolve through the source registry; stable pages may not rely on pending or
  unattested licensing data.
- Numeric, derived, and table-valued assertions use structured claims.
  Qualitative externally verifiable assertions should carry claim-level
  provenance. Table answers select stable cell IDs rather than flattening or
  reauthoring matrix values.
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
- Corpus evidence and reader behavior have separate content-addressed
  manifests so either lifecycle can change without falsely republishing the
  other.
- The minimum answer-check matrix is one machine-readable, digest-pinned
  artifact loaded by the verifier rather than duplicated in prose and code.

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
Disinfection Byproducts Rules. The maintainer-reviewed
[`v0.2 page list`](proposals/first-proof-dbp-page-list-v0.2.md) applies this
coverage principle:

> Every authoritative provision within the declared rule-family scope must be
> represented or explicitly recorded as a coverage gap or exclusion with its
> reason.

The proof favors dependency-complete coverage over an arbitrary page count
and currently includes:

- 14 primary pages plus three definition, goal, and notification dependency
  pages;
- MCL and MRDL tables, bromate and chlorite specifics, and running-annual-
  average compliance mechanics;
- a table-valued claim for the TOC removal matrix;
- 50–100 adversarial questions written before retrieval optimization;
- simulated edits, source changes, corrections, stale content, and watch
  failures.

## Implemented foundation

- [`schemas/drinking-water-profile-v0.1.schema.json`](schemas/drinking-water-profile-v0.1.schema.json)
- [`schemas/reviewer-registry-v0.1.schema.json`](schemas/reviewer-registry-v0.1.schema.json)
- [`schemas/source-registry-v0.1.schema.json`](schemas/source-registry-v0.1.schema.json)
- [`schemas/corpus-release-manifest-v0.1.schema.json`](schemas/corpus-release-manifest-v0.1.schema.json)
- [`schemas/runtime-assurance-manifest-v0.1.schema.json`](schemas/runtime-assurance-manifest-v0.1.schema.json)
- [`schemas/verified-answer-v0.1.schema.json`](schemas/verified-answer-v0.1.schema.json)
- [`schemas/audit-envelope-v0.1.schema.json`](schemas/audit-envelope-v0.1.schema.json)
- [`contracts/assurance-check-baseline-v0.1.json`](contracts/assurance-check-baseline-v0.1.json)
- [`docs/ASSURANCE-CHECK-BASELINE-v0.1.md`](docs/ASSURANCE-CHECK-BASELINE-v0.1.md)
- [`tests/acceptance/manifest-v0.1.json`](tests/acceptance/manifest-v0.1.json)
- [`tests/acceptance/check-artifacts.mjs`](tests/acceptance/check-artifacts.mjs)
- [`.github/workflows/validate-artifacts.yml`](.github/workflows/validate-artifacts.yml)

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
- Retention, keyed-fingerprint, and privacy policy for audit records and
  low-entropy normalized queries.

## Next actions

1. Review the schema-ratification pull request and disposition every finding.
2. Record explicit ratify-or-revise decisions for each schema in RFC 003.
3. Add canonicalization specifications and conformance vectors.
4. Complete the maintainer review of the v0.2 DBP proof set and seed J7
   field-confusion cases.
5. Author the 50–100 adversarial questions before tuning retrieval.
6. Implement the first real corpus release and stable claim/quote resolution.
7. Build the nonstreaming gateway and deliberately small conforming renderer.

## Restart procedure

On a new work session:

1. read this file;
2. inspect `git status` and the latest commits on `origin/main`;
3. read new comments in RFC Discussions 1–3;
4. reconcile any new decision into this file before implementation;
5. run `node tests/acceptance/check-artifacts.mjs`.
