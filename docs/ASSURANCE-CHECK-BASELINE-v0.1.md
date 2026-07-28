# Assurance check baseline v0.1

Status: normative ratification-candidate artifact

The v0.1 cross-RFC assurance contract incorporates
[`contracts/assurance-check-baseline-v0.1.json`](../contracts/assurance-check-baseline-v0.1.json)
by reference as its machine-readable minimum check matrix.

A conforming v0.1 runtime assurance manifest:

1. names that artifact by `artifact_id`;
2. pins the SHA-256 digest of its exact committed UTF-8 file bytes;
3. declares every baseline rule and check, while permitting stricter
   additional rules; and
4. fails semantic validation when the artifact ID, digest, rule, or required
   check does not agree.

The reference checker loads this artifact at runtime. It does not maintain a
second hard-coded copy of the mandatory matrix. AT-031 proves that a runtime
manifest cannot weaken the loaded matrix; AT-033 proves that a manifest cannot
substitute different baseline bytes under the same artifact name.

This binding prevents accidental drift between prose, policy manifests, and
the checker. It does not make an arbitrary or modified verifier trustworthy:
assurance claims still require the verifier bytes pinned by the runtime
manifest and a conforming execution of those bytes.
