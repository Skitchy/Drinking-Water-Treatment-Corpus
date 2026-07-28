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

## Compatibility policy

The profile permits unknown extension fields so that the normalized record
can remain OKF-compatible. The answer and audit envelopes are closed:
unrecognized fields fail validation, which prevents a client from smuggling
unchecked narrative into a verified-answer object.

Every schema uses an immutable logical `urn:dwtc:schema:*` identifier rather
than a mutable `main`-branch URL. Every incompatible change requires a new
schema version. Published manifests and answer envelopes name exact artifact
digests, not floating branches.
