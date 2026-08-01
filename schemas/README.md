# Versioned assurance schemas

These JSON Schema 2020-12 documents turn the accepted RFC vocabulary into
machine-checkable shapes:

- `drinking-water-profile-v0.1.schema.json` validates a normalized JSON
  representation of an OKF concept page and its Drinking Water Assurance
  Profile extension fields, including scalar, derived, and table-valued
  claims with stable cells.
- `reviewer-registry-v0.1.schema.json` defines the minimum credible registry,
  even while the project has only one reviewer.
- `source-registry-v0.1.schema.json` binds source authority, authenticity,
  captured bytes, and per-component reproduction decisions to a named human
  review.
- `corpus-release-manifest-v0.1.schema.json` pins corpus-side schemas,
  registries, canonicalization procedures, coverage, pages, claims, and
  quotes.
- `runtime-assurance-manifest-v0.1.schema.json` separately pins reader-side
  policy, verifier, generator, index, algorithms, query canonicalization,
  renderer templates, the machine-readable mandatory-check baseline, and the
  compatible corpus release.
- `verified-answer-v0.1.schema.json` defines the gateway's native answer
  envelope, including explicit stable-cell selections for table claims. It
  deliberately has no arbitrary narrative field.
- `audit-envelope-v0.1.schema.json` records enough retrieval and validation
  state to investigate a decision without asserting that a full audit system
  already exists.

RFC 004 adds five post-ratification candidates without modifying the seven
ratified v0.1 files:

- `procedure-contract-v0.1.schema.json` defines a finite transition table for
  mandatory resolution order, finite condition and terminal-control
  declarations, controlled triggers, standard or fallback-entry transitions,
  and terminal mappings to the three answer outcomes. It has no expression
  language, model-authored branches, or loops.
- `evaluation-manifest-v0.1.schema.json` separates conformance regression from
  a public rotating capability challenge set and pins the exact corpus,
  procedure, runbook, runtime, case schema, and grader used for evaluation. It
  also separates active cases from a content-bound retirement ledger.
- `runtime-assurance-manifest-v0.2.schema.json` directly pins both the governed
  runbook and procedure contract. The runbook declaration carries ownership,
  review and due times, supersession, compatibility, and controlled fallback
  and gotcha identifiers.
- `audit-envelope-v0.2.schema.json` binds the exact answer digest and records a
  controlled procedure trace. Its procedure block is required semantically
  whenever the resolved runtime declares a procedure contract.
- `reviewer-registry-v0.2.schema.json` adds the explicit `procedure-domain`
  and `procedure-assurance` human-review scopes.

## Three validation layers

1. **Schema-valid:** required fields, types, enums, and closed envelope
   surfaces match the versioned schema.
2. **Semantically validated:** referenced claim, quote, page, reviewer, and
   release IDs exist; duplicated digests and canonical values match; policy
   gates and declared checks pass.
3. **Integrity-bound:** the canonical envelope bytes match the recorded
   digest. `Sealed` additionally requires a verifiable signature.

JSON Schema alone cannot establish semantic truth or compare a review event's
digest with canonical page bytes. Those requirements are named in `$comment`
annotations and exercised by the acceptance-test contract.

## Two lifecycle anchors

The corpus and reader do not share one release lifecycle. A source or page
change produces a new corpus release manifest. A policy, verifier, index,
generator, or renderer change produces a new runtime assurance manifest.
Every answer and audit record names the exact digest of both. This allows
reader behavior to evolve without republishing unchanged evidence while
preserving full reproducibility.

Compatibility remains intentionally one-way and exact: a new corpus release
requires a newly minted runtime manifest that explicitly names the new corpus
digest, even when the runtime artifacts are otherwise unchanged. Clients that
pin runtime manifests therefore observe manifest churn at the union of the two
lifecycles rather than silently inheriting compatibility.

The runbook and procedure contract remain on the runtime side of this
boundary. Changing either qualifies a new runtime manifest; it does not
republish unchanged corpus evidence or alter a page's stable status. An
overdue runbook fails runtime qualification for evidence-backed operation at
`evaluation_time >= next_due_at`.

## Compatibility policy

The profile permits unknown extension fields so that the normalized record
can remain OKF-compatible. The answer and audit envelopes are closed:
unrecognized fields fail validation, which prevents a client from smuggling
unchecked narrative into a verified-answer object.

Every schema uses an immutable logical `urn:dwtc:schema:*` identifier rather
than a mutable `main`-branch URL. Every incompatible change requires a new
schema version. Published manifests and answer envelopes name exact artifact
digests, not floating branches.

The RFC 004 candidate canonicalization profile recursively sorts object keys,
preserves array order, emits whitespace-free UTF-8 JSON with no trailing
newline, excludes only `/integrity/artifact_sha256`, and hashes the result with
SHA-256. Executable vectors live in
`tests/acceptance/fixtures/rfc004-canonicalization-vectors-v0.1.json`. This PR
presents that profile for review; merge and ratification, not authorship,
determine its normative status.
