# Project State

Last updated: 2026-08-01

This is the repository's restart point. It records the currently accepted
design position without replacing the normative RFC discussions.

## Current checkpoint

The project has moved from RFC design into the first executable DBP vertical
slice. Two assurance layers are ratified:

1. **Foundation, ratified 2026-07-28.** Seven v0.1 schemas plus the
   digest-pinned assurance-check baseline, recorded in
   [RFC 003](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/3#discussioncomment-17819208)
   and tagged `schema-foundation-v0.1` at the PR #4 merge commit.
2. **Procedural and evaluation amendment, ratified 2026-08-01.** Five schema
   consequences of RFC 004, merged through PR #6 at `940109e` after
   adversarial re-review: `procedure-contract/v0.1`,
   `evaluation-manifest/v0.1`, `runtime-assurance-manifest/v0.2`,
   `audit-envelope/v0.2`, and `reviewer-registry/v0.2`.

The point-in-time source layer contains 28 eCFR section captures dated
2026-07-01 plus a derived EPA Comprehensive DBP Quick Reference Guide text
extraction with its derivation record. Two dependency pages are published as
stable artifacts: `dbp.definitions` and `dbp.mclg`. The next checkpoint is the
core MCL/MRDL page set against the ratified contracts.

All schema changes after ratification require a version bump, recorded
rationale, pull-request review, and executable acceptance evidence.

## Normative design record

1. [RFC 001: The Corpus](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/1)
2. [RFC 002: The Reader](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/2)
3. [RFC 003: Cross-RFC Assurance Contract](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/3)
4. [RFC 004: The Procedural Layer](https://github.com/Skitchy/Drinking-Water-Treatment-Corpus/discussions/5)

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

### Procedure and evaluation

- The procedural layer separates a human/agent runbook from a minimal,
  finite machine-readable procedure contract. Both are digest-pinned by the
  runtime-assurance manifest; stale or absent procedure fails closed for the
  reader/runtime pair's conformance claim, not for previously stable pages.
- Clarification remains inside the three-outcome boundary as an
  `APPLICABILITY_UNRESOLVED` abstention. A conforming renderer produces the
  clarification from controlled, pinned templates.
- Procedure traces are required when the runtime declares a procedure
  contract. Fallback authorization is derived from traversed
  `fallback-entry` transitions rather than accepted as self-report.
- Evaluation is split into a public conformance suite and a capability pool.
  Cases used to shape the runbook demonstrate regression control, not
  generalization. The public capability pool is a rotating challenge set;
  only an access-controlled private pool may be called a blind holdout.
- Active and retired capability cases are separate, content-bound ledgers.
  Only active cases count toward declared bounds, and retirement cannot erase
  its prior accepted disposition.
- The conformance target is 100 percent. Every failure is dispositioned as a
  corpus, procedure, runtime, or case defect rather than averaged away.

## First proof

The first rule family is the Stage 1 and Stage 2 Disinfectants and
Disinfection Byproducts Rules. The maintainer-reviewed
[`v0.2 page list`](proposals/first-proof-dbp-page-list-v0.2.md) governs the
17-page proof set and applies this coverage principle:

> Every authoritative provision within the declared rule-family scope must be
> represented or explicitly recorded as a coverage gap or exclusion with its
> reason.

The proof favors dependency-complete coverage over an arbitrary page count.
Current implementation state:

- **Published stable dependencies:** `pages/dbp.definitions.json` and
  `pages/dbp.mclg.json`.
- **Next page tranche:** core TTHM, HAA5, bromate, and chlorite MCL pages,
  followed by chlorine/chloramine and chlorine-dioxide MRDL pages.
- **Later pages:** LRAA, OEL, routine/reduced/increased monitoring,
  applicability, IDSE, analytical methods, notification, and the TOC matrix.
- **Question bank:** 40 maintainer-authored questions and answers in
  `docs/EPA_DBP_Challenge_Questions.md`, written before retrieval tuning and
  corrected through source-sensitive adversarial review. They are sufficient
  as the current coverage bank but are not yet an executable evaluation
  manifest. The declared first-proof target remains 50–100 cases, including a
  fresh 10–15-case rotating capability tranche.
- **Failure exercises still required:** simulated edits, source changes,
  corrections, stale content, watch failures, and process-level reader/grader
  isolation.

## Implemented assurance artifacts

### Ratified foundation

- [`schemas/drinking-water-profile-v0.1.schema.json`](schemas/drinking-water-profile-v0.1.schema.json)
- [`schemas/reviewer-registry-v0.1.schema.json`](schemas/reviewer-registry-v0.1.schema.json)
- [`schemas/source-registry-v0.1.schema.json`](schemas/source-registry-v0.1.schema.json)
- [`schemas/corpus-release-manifest-v0.1.schema.json`](schemas/corpus-release-manifest-v0.1.schema.json)
- [`schemas/runtime-assurance-manifest-v0.1.schema.json`](schemas/runtime-assurance-manifest-v0.1.schema.json)
- [`schemas/verified-answer-v0.1.schema.json`](schemas/verified-answer-v0.1.schema.json)
- [`schemas/audit-envelope-v0.1.schema.json`](schemas/audit-envelope-v0.1.schema.json)
- [`contracts/assurance-check-baseline-v0.1.json`](contracts/assurance-check-baseline-v0.1.json)

### Ratified RFC 004 amendment

- [`schemas/procedure-contract-v0.1.schema.json`](schemas/procedure-contract-v0.1.schema.json)
- [`schemas/evaluation-manifest-v0.1.schema.json`](schemas/evaluation-manifest-v0.1.schema.json)
- [`schemas/runtime-assurance-manifest-v0.2.schema.json`](schemas/runtime-assurance-manifest-v0.2.schema.json)
- [`schemas/audit-envelope-v0.2.schema.json`](schemas/audit-envelope-v0.2.schema.json)
- [`schemas/reviewer-registry-v0.2.schema.json`](schemas/reviewer-registry-v0.2.schema.json)
- [`docs/RFC004-SCHEMA-AMENDMENT-CANDIDATE-v0.1.md`](docs/RFC004-SCHEMA-AMENDMENT-CANDIDATE-v0.1.md)
- [`tests/acceptance/manifest-rfc004-amendment-v0.1.json`](tests/acceptance/manifest-rfc004-amendment-v0.1.json)
- [`tests/acceptance/check-rfc004-amendment.mjs`](tests/acceptance/check-rfc004-amendment.mjs)

The executable baseline currently covers seven foundation schemas with 40
acceptance cases plus five RFC 004 schemas with 36 executable adversarial
cases. Five process-level RFC 004 integration cases remain honestly marked
`specified`.

### Production and first-proof artifacts

- [`registry/reviewer-registry.json`](registry/reviewer-registry.json), using
  `reviewer-registry/v0.1`, with `human.skitch` qualified for the current page
  review scopes.
- [`pages/dbp.definitions.json`](pages/dbp.definitions.json)
- [`pages/dbp.mclg.json`](pages/dbp.mclg.json)
- [`docs/EPA_DBP_Challenge_Questions.md`](docs/EPA_DBP_Challenge_Questions.md)
- [`tests/acceptance/check-artifacts.mjs`](tests/acceptance/check-artifacts.mjs)
- [`.github/workflows/validate-artifacts.yml`](.github/workflows/validate-artifacts.yml)

## Explicit deferrals

- Independent qualified-human second review and audit sampling await
  additional reviewer capacity.
- Broad state-law ingestion awaits a successful federal vertical slice.
- Retrieval architecture beyond the measured lexical baseline awaits the
  domain evaluation set.
- A production signing profile, key lifecycle, and transparency mechanism
  await the gateway implementation. The v0.1 answer schema reserves the
  integrity fields without pretending those operational controls already
  exist.
- Production runbook, procedure-contract, evaluation-manifest, and audit-v0.2
  instances await first-proof content and reviewer-scope activation. Ratified
  schemas do not by themselves create a procedural-conformance claim.
- A private blind-holdout pool is not claimed or required for the public
  first proof.

## Open decisions

- Strict-refusal versus evidence-only behavior for each stale-evidence class.
- The exact federal official-record cross-check procedure.
- Required human-review scopes by page and claim consequence class.
- Canonicalization specifications and conformance vectors for the original
  v0.1 integrity-bearing artifacts, including review-payload serialization.
  The RFC 004 vectors cover only its four new integrity-bearing fixtures.
- Signature algorithm, key identity, rotation, and revocation policy.
- Approved deterministic renderer templates and renderer-conformance suite.
- Retention, keyed-fingerprint, and privacy policy for audit records and
  low-entropy normalized queries.
- A qualified holder for `procedure-assurance`. The maintainer holds
  `procedure-domain` by recorded ruling, but the production registry remains
  v0.1 until the v0.2 scope assignment is complete.
- Final conversion of the 40-question coverage bank into conformance and
  capability manifests, including the fresh rotating cases and retirement
  ledger.

## Next actions

1. Build the core TTHM, HAA5, bromate, chlorite, and disinfectant-residual
   pages in dependency order against the captured sources.
2. Complete human review and release disposition for each page before using
   it as evidence.
3. Give the 40 questions stable IDs and structured oracles, map them to page
   coverage, then expand toward the 50–100-case target with a fresh 10–15-case
   rotating capability tranche.
4. Complete canonicalization specifications and conformance vectors for the
   original v0.1 integrity-bearing artifacts.
5. Designate and qualify a `procedure-assurance` reviewer, then migrate the
   production reviewer registry to v0.2 before any procedural claim.
6. Instantiate the runbook, procedure contract, runtime v0.2, audit v0.2,
   and evaluation manifest after the required first-proof content exists.
7. Build the nonstreaming gateway and deliberately small conforming renderer.
8. Exercise source drift, correction, staleness, watch failure, and
   reader/grader isolation before promoting the first complete proof.

## Restart procedure

On a new work session:

1. read this file;
2. inspect `git status` and the latest commits on `origin/main`;
3. read new comments in RFC Discussions 1–3 and 5, plus open PR reviews;
4. reconcile any new decision into this file before implementation;
5. run `npm test`;
6. confirm which production manifests and reviewer-registry version are
   actually active before making any conformance claim.
