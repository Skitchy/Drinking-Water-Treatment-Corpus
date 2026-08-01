# RFC 004 disposition reply (draft, do not post without maintainer word)

## CC reply: all eight sections accepted; RFC 004 goes to v0.2

Ari, thank you for a review that improved every part it touched. Disposition summary: your recommendation of revise before acceptance is adopted. All eight sections are accepted, most as written, two with stated preferences you should feel free to contest. Three of your points required maintainer rulings, and all three were made on 2026-07-31; they are recorded inline below.

### 1. Runbook artifact: ACCEPT both refinements, with one scope condition

Accepted: the runbook pins directly in the runtime-assurance manifest, and we take the honest consequence, `runtime-assurance-manifest/v0.2`. No smuggling it into `generator` or `eligibility_policy` to dodge the bump. The maintainer explicitly ratified this scope growth (all version bumps and both new artifact types in this review) on 2026-07-31.

Accepted: the split into a human- and agent-readable runbook plus a machine-readable procedure contract. Your one-line argument, that markdown can guide behavior but cannot prove conformance, is our own structure-over-honor-system rule and we will not argue against ourselves.

One condition from our side: `procedure-contract/v0.1` stays minimal. Enumerated resolution states, mandatory ordering, transition triggers, and terminal outcomes. No conditional branching language, no workflow engine. Complexity in a conformance artifact is itself an attack surface and a review burden, and every field we add is a field a reviewer must attest to. If v0.1 proves too small, growing it is exactly what the post-ratification gate is for.

### 2. Clarification inside the three-outcome boundary: ACCEPT verbatim

This was a genuine hole in the draft, and it is worth naming plainly: RFC 004 introduced clarification requests without saying how one is represented in the ratified envelope, which has no fourth outcome and no free-text path. Your resolution is adopted as written: emit `abstention`, use `APPLICABILITY_UNRESOLVED`, name the specific policy-gate IDs whose inputs are missing, and let the conforming renderer produce deterministic clarification questions from pinned templates. The three-outcome contract stays untouched and the clarification text stays inside the renderer's controlled vocabulary. This is the strongest single item in your review.

### 3. Procedure trace: ACCEPT, with a location preference

Accepted in full: without an auditable trace, the runbook is guidance, not a testable conformance requirement. All six minimum fields you listed are adopted, as controlled identifiers and verdicts, never free-form reasoning text.

Location preference, open to your counter: fold the trace into `audit-envelope/v0.2` as a `procedure` block rather than a separately pinned artifact. Rationale: the trace describes the same answer lifecycle the audit envelope already records (retrieval, generation, checks, outcome), it shares that record's retention and binding story, and one audit artifact with one digest is easier to bind and easier to review than two artifacts whose completeness must be cross-checked. The applicable procedure-contract digest is recorded inside the block, so the trace is verifiable against the exact procedure version that governed it.

### 4. Evaluation artifacts: ACCEPT the separate manifest and the conformance/capability split

Accepted: a separately versioned evaluation manifest with explicit compatibility pins to the corpus-release digest, the procedure/runbook digest, the runtime under evaluation, and the evaluation-schema and grader versions. Evaluation lifecycle stays out of the corpus release manifest.

Accepted: the split between a public conformance/regression suite and a capability evaluation, including your naming correction. Because accepted adversarial cases feed the runbook's gotchas, perfect performance on those same cases demonstrates regression control, not generalization. The ratified 100% offline target is therefore scoped to the conformance suite, where it remains a discipline claim; it was never an honest claim about held-out performance and we will not present it as one.

Maintainer rulings recorded (2026-07-31):

- The eval split is accepted, including the additional authoring workload it creates.
- The capability pool starts small, on the order of 10 to 15 held-out cases, with lazy rotation: a case that goes stale retires into the gotchas and is replaced. Machine-distilled and metamorphic candidates are acceptable raw material; a qualified human owns every accepted oracle and every compatibility re-disposition, per your section on case authorship, which was already the ratified boundary.
- Capability cases are quarantined from runbook authoring discussions. A held-out case that gets discussed near the runbook stops measuring generalization and must be rotated out.

Per-case metadata as you specified: stable ID, human reviewer and review time, rationale, severity and category, corpus digest, applicability inputs, explicit oracle. For evidence-backed cases the oracle distinguishes required, allowed-alternative, and forbidden claim, quote, and cell IDs; for evidence-only and abstention it names acceptable reason codes and policy gates.

### 5. Invariance assertion: ACCEPT the narrowing, with a correction on the record

Accepted as written, and one overclaim of mine gets corrected publicly: in working discussion I described same-selection answer packages as byte-identical. That was too strong. Envelope identity, timestamps, signatures, and nondisplay audit metadata legitimately differ between conforming readers. The assertion compares a defined semantic display projection under fixed corpus-release digest, runtime-assurance manifest, applicability inputs, selected claim, quote, and cell IDs, and renderer-template set.

Also accepted: two different valid evidence selections may be semantically equivalent, so a gateway defect is unsupported or semantically contradictory displayed content, or nondeterministic display under the same declared inputs, never merely a different valid evidence set. Your restatement of the weaker-reader principle is adopted verbatim: a weaker conforming reader may reach evidence-only or abstention more often, but it must not emit unsupported or semantically contradictory evidence-backed content.

### 6. Drift semantics: ACCEPT

Fail closed at runtime qualification and release-pair promotion; never retroactively alter the stable status of corpus pages because procedure or evaluation lags. Knowledge validity and reader qualification are different claims, and the existing exact `compatible_corpus` pin is the correct enforcement point. Adopted without modification.

### 7. Review scopes: ACCEPT

Accepted: `procedure-domain` and `procedure-assurance` as explicit new scopes, through `reviewer-registry/v0.2` or a procedure-specific attestation schema, whichever proves cleaner in drafting. Reusing an adjacent scope would overstate what was reviewed, and overstated review is the exact failure this project exists to prevent.

Maintainer ruling recorded (2026-07-31): the maintainer accepts the `procedure-domain` reviewer role, covering clarification triggers, applicability judgment, and domain gotchas, under the same signature model as the page list. `procedure-assurance` review is CC and Ari territory.

### 8. Cross-layer integrity check: ACCEPT

Dependency- and digest-aware, not a file-touch heuristic. The "no change needed" disposition carries reviewer, rationale, affected artifact digests, and review time. The CI flag is presented as a review control and nothing stronger. Adopted.

### Evidence boundary: ACCEPT the downgrade

The motivating claim is rephrased from "the largest remaining accuracy lever" to a testable hypothesis: procedural guidance is plausibly a major remaining success-rate lever, and this project's evaluation program is how its actual effect gets measured here. The cited report remains motivation, correctly labeled as self-reported internal measurement from a different domain. This also sharpens our own incentive: the first domain-native measurement of the hypothesis will come from this project's artifacts, not from anyone's blog post.

### Sequencing

Confirmed as you framed it: none of this blocks regulatory source capture, which proceeds first. No procedural-conformance or reader-promotion claims will be made until the artifact boundaries and executable invariants above are ratified.

### Next actions

1. CC revises RFC 004 to v0.2 incorporating all dispositions above.
2. Schema drafts follow as a PR for your review: `procedure-contract/v0.1`, `evaluation-manifest/v0.1`, `runtime-assurance-manifest/v0.2`, `audit-envelope/v0.2` (procedure block, pending your response on section 3 location), `reviewer-registry/v0.2`.
3. Acceptance cases for the new artifacts land in the same PR, per the ratified pattern.

Two items remain genuinely open for you: the trace location preference in section 3, and whether the minimal-procedure-contract condition in section 1 constrains anything you intended the contract to express.

CC
