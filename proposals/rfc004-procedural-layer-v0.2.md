# RFC 004 v0.2: The Procedural Layer. Runbook, Procedure Contract, and Evaluation Artifacts

Status: REVISED after review convergence (discussions/5, two rounds, closed
2026-07-31). This revision folds in every accepted disposition from the
Ari/Codex review, the three safeguards added in the follow-up round, and the
maintainer rulings of 2026-07-31. Nothing in this RFC modifies the ratified
`schema-foundation-v0.1` contracts by prose alone. Every schema consequence
identified below follows the post-ratification gate: version bump, recorded
rationale, pull-request review. The implementing schema set is delivered as
its own PR with acceptance cases.

Changes from v0.1 are summarized in section 8.

## 1. Motivation

The ratified foundation covers two of the three layers a trustworthy reader
needs:

- **Knowledge.** The corpus: pages, structured claims, sources, licensing,
  review bindings.
- **Enforcement.** The verified-answer gateway: selection-not-authorship,
  the three-outcome envelope, the digest-pinned `required_check_baseline`.

It does not yet cover **procedure**: a governed statement of how a reader
should work the corpus. Which resolution path to attempt first, when to ask a
clarifying question, when to abstain, which known wrong-answer modes to check
before finalizing, and what provenance must accompany each outcome.

External evidence suggests procedural guidance is plausibly a major remaining
success-rate lever. That phrasing is deliberate: the supporting numbers are
self-reported internal measurements from a different domain, and this
project's own evaluation program (section 2.4) is how the actual effect gets
measured here. Anthropic's published account of its internal analytics agent
("How Anthropic enables self-service data analytics with Claude," June 3,
2026) reports three results that motivate, without proving, the design below:

1. With knowledge and enforcement layers in place but no procedural layer,
   accuracy on their internal evals was 21%. Adding curated procedural
   guidance ("skills") moved it above 95% aggregate.
2. Raw retrieval access to a complete archive of previously correct work
   moved accuracy by less than one point. Distilled, structured reference
   material is what moved it. Access was not the bottleneck; structure was.
3. Unmaintained procedural guidance decayed from roughly 95% to roughly 65%
   accuracy in one month. Staleness of procedure is a first-class failure
   mode, matching this project's existing position on source staleness.

Their domain (business analytics) tolerates a raw-exploration fallback and
aggregate accuracy targets. Ours does not, which is why the proposal below is
stricter in one deliberate way, stated in section 4.

## 2. Proposal

### 2.1 Runbook and procedure contract

The procedural layer is two artifacts with different jobs:

- **The runbook.** A versioned, digest-pinned document for humans and agents:
  resolution order with pre-rebutted skip excuses, clarification triggers,
  abstention triggers, the gotcha catalog fed by accepted adversarial cases,
  and per-outcome provenance requirements. The runbook guides behavior.
- **The procedure contract (`procedure-contract/v0.1`).** A machine-readable
  conformance artifact: enumerated resolution states, mandatory ordering,
  transition triggers, and terminal outcomes, expressed as a fixed finite
  transition table. Each transition is classified `standard` or
  `fallback-entry`, so fallback use is a structural property of the observed
  path, not a self-report. The contract also declares the finite `conditions`
  and `controls` vocabulary (identifiers with human-readable descriptions,
  not predicates) that traces and audits must resolve against.

The split exists because markdown can guide behavior but cannot prove
conformance. The contract stays minimal by design: no conditional branching
language, no expression language, no workflow engine, no model-authored
branches. Complexity in a conformance artifact is itself attack surface and
review burden, and every added field is a field a reviewer must attest to.
If v0.1 proves too small, growing it is exactly what the post-ratification
gate is for.

Both artifacts are pinned directly by the runtime-assurance manifest
(`runtime-assurance-manifest/v0.2`) alongside the corpus-release digest and
the `required_check_baseline`. A stale or absent runbook or contract is a
fail-closed condition for the reader/runtime pair's conformance claim. The
version-bump cost of every runbook edit is accepted plainly; pinning
procedure anywhere weaker would rebuild the honor system this project exists
to replace.

Runbook staleness is executable, not asserted: overdue status derives at
evaluation time from the artifact's `next_due_at` field, never from a stored
overdue flag, matching the source-watch precedent where observations record
and evaluation derives.

### 2.2 Clarification inside the three-outcome boundary

The ratified envelope has exactly three outcomes (`evidence-backed`,
`evidence-only`, `abstention`) and no free-text path. A clarification request
is not a fourth outcome. When a clarification trigger fires, the reader emits
`abstention` with reason `APPLICABILITY_UNRESOLVED`, naming the specific
policy-gate IDs whose inputs are missing. A conforming renderer generates the
clarification question deterministically from pinned templates keyed to those
gate IDs. The clarification text never leaves the renderer's controlled
vocabulary, and the three-outcome contract stays untouched.

### 2.3 Procedure trace in the audit record

Every governed answer carries an auditable procedure trace; without it the
runbook is advice, not a testable requirement. The trace is a required
`procedure` block inside `audit-envelope/v0.2` whenever the runtime-assurance
manifest declares a procedure contract. It records, as controlled identifiers
and verdicts and never as free-form reasoning text: whether structured-claim
resolution was attempted, what authorized any fallback, which policy gates
fired, which gotcha checks ran, the terminal outcome, and the digest of the
procedure contract that governed the run.

Audit semantics enforce the fallback biconditional structurally:
`fallback.authorized` must equal "the observed path contains a
fallback-entry transition," with both sides derived from the resolved
contract, and the observed transition sequence must validate against the
pinned transition table. Every trigger condition, terminal reason, and
recorded gate must resolve to a compatible declared identifier in the
contract's vocabulary.

The audit record itself gains integrity binding in v0.2: it names its answer
by `answer_id` and binds it by `artifact_sha256`, and the audit record
carries its own canonicalization and digest. Binding is deliberately one-way
(audit binds answer; answer does not digest the audit) to avoid a circular
digest dependency.

### 2.4 Evaluation artifacts

The planned adversarial questions become machine-readable evaluation
artifacts under a separately versioned `evaluation-manifest/v0.1` with
explicit compatibility pins: the corpus-release digest, the runbook and
procedure-contract digests, the runtime under evaluation, and the
evaluation-schema and grader versions. Evaluation lifecycle stays out of the
corpus release manifest, per the two-anchor precedent.

The evaluation program is two pools with different jobs and different honest
claims:

- **Conformance suite.** The accepted adversarial cases, including every
  prior failure and every gotcha. These cases feed the runbook, so perfect
  performance here demonstrates regression control, not generalization. The
  offline target for this suite is 100%: the domain is deterministic (a
  maximum contaminant level is a fact with an authoritative source), so any
  failure is a defect in the corpus, the runbook, or the case itself, and
  must be dispositioned, not averaged away.
- **Capability evaluation.** A pool of cases the runbook has never seen,
  measuring generalization. Isolation is harness-enforced, not
  discussion-disciplined: the reader under evaluation receives only the
  question; the grader holds the oracle. In a public repository a committed
  case is not durably blind regardless of conversational discipline, so the
  public pool is named honestly as a **rotating challenge set**. Only an
  access-controlled private pool may ever be called a blind holdout, and no
  such claim is made for the public set. Active cases are separated from a
  content-bound `retired_cases` ledger; only active cases count toward
  declared bounds and grading, and a retirement must end in a content-bound
  `retired` disposition so removal cannot masquerade as rotation.

Per-case metadata: stable ID, human reviewer and review time, rationale,
severity and category, corpus digest, applicability inputs, explicit oracle.
For `evidence-backed` expectations the oracle distinguishes required,
allowed-alternative, and forbidden claim, quote, and cell IDs, with
disjointness between required or allowed selections and forbidden selections
asserted structurally; for `evidence-only` and `abstention` it names
acceptable reason codes and policy gates.

Case authorship: machine-distilled candidates from reader transcripts and
metamorphic perturbations of accepted cases are acceptable raw material. A
qualified human owns every accepted oracle and every compatibility
re-disposition. Rotation is lazy: a case that goes stale or gets exposed
retires into the gotcha catalog and is replaced.

### 2.5 Invariance assertions

The layered design implies a testable property, stated precisely:

- **Answer invariance given success.** Two conforming readers that select the
  same claim, quote, and cell IDs against the same pinned corpus release,
  runtime-assurance manifest, applicability inputs, and renderer-template set
  must produce equivalent answers under a defined **semantic display
  projection**. Envelope identity, timestamps, signatures, and nondisplay
  audit metadata legitimately differ and are excluded from the comparison.
- **Defect definition.** Two different valid evidence selections may be
  semantically equivalent, so a gateway defect is unsupported or semantically
  contradictory displayed content, or nondeterministic display under the same
  declared inputs. A merely different valid evidence selection is not a
  defect.
- **Success-rate telemetry.** Reader capability and runbook quality affect
  how often a valid outcome is reached, not what a valid answer contains. A
  weaker conforming reader may reach `evidence-only` or `abstention` more
  often; it must never emit unsupported or semantically contradictory
  `evidence-backed` content. Per-reader success and abstention rates against
  the evaluation set are the measure of runbook quality.

### 2.6 Drift semantics

If the corpus release advances and the runbook, procedure contract, or
evaluation set has not been re-dispositioned against it, the reader/runtime
pair's conformance claim fails closed at runtime qualification and
release-pair promotion. Corpus pages are never retroactively un-stabled by
procedural or evaluation lag: knowledge validity and reader qualification are
different claims, and the exact `compatible_corpus` pin is the enforcement
point.

### 2.7 Review scopes

Two new reviewer scopes enter through `reviewer-registry/v0.2`, because
reusing an adjacent scope would overstate what was reviewed:

- **`procedure-domain`.** Clarification triggers, applicability judgment,
  domain gotchas. Held by the maintainer under the same signature model as
  the page list.
- **`procedure-assurance`.** State transitions, envelope alignment,
  auditability, trace semantics.

### 2.8 Cross-layer integrity check

A CI review control, digest- and dependency-aware rather than file-touch:
a change to a corpus page that does not touch its structured claims, its
evaluation cases, or an explicit "no change needed" disposition is flagged
for review. The disposition carries reviewer, rationale, affected artifact
digests, and review time. This check is presented as a review control and
nothing stronger; it prevents the procedural and evaluation layers from
silently drifting away from the knowledge layer they describe.

## 3. What this RFC does not change

- The ratified `schema-foundation-v0.1` contracts are not modified by this
  document. The schema consequences in section 6 land only through the
  post-ratification gate.
- The gateway remains the sole validity authority. The runbook cannot make an
  invalid answer pass; it can only change how often the reader reaches a
  valid outcome. Assurance claims stay exactly as narrow as they are today.
- The first-proof page list (v0.2, signed) and its sequencing are unchanged.
- No procedural-conformance or reader-promotion claims will be made until the
  artifact boundaries and executable invariants above are ratified.

## 4. One deliberate divergence from the cited practice

The cited analytics system keeps a raw-exploration fallback that can produce
free-text answers with provenance footers, accepting aggregate accuracy in
the mid-90s. This project's envelope has no free-text path and no aggregate
target. The runbook therefore treats the fallback path as ending at the same
gateway as the primary path. Procedure improves the hit rate; it never
widens what the format can express. Their reported failure mode ("plausible
wrong answers used without objection are the hardest to catch") is the
argument for keeping this divergence, not softening it.

## 5. Resolved questions

The five open questions of v0.1, with their converged answers:

1. **Pinning location.** Resolved: the runbook and procedure contract are
   pinned by the runtime-assurance manifest as digest-pinned artifacts,
   fail-closed when stale or absent. The version-bump cost is accepted.
2. **Evaluation-set versioning.** Resolved: a separately versioned
   evaluation manifest with explicit compatibility pins to release digests,
   per the two-anchor precedent.
3. **Drift semantics.** Resolved: fail closed for the reader/runtime pair's
   claims; never retroactive un-stabling of corpus pages (section 2.6).
4. **Review scopes.** Resolved: two new scopes, `procedure-domain` and
   `procedure-assurance`, through `reviewer-registry/v0.2` (section 2.7).
5. **Case authorship boundary.** Confirmed: distillation and metamorphic
   generation are raw material; a qualified human owns every accepted case
   and every re-disposition (section 2.4).

## 6. Schema consequences

Implementing this RFC requires, through the post-ratification gate:

- `procedure-contract/v0.1` (new)
- `evaluation-manifest/v0.1` (new)
- `runtime-assurance-manifest/v0.2` (pins runbook and procedure contract)
- `audit-envelope/v0.2` (required `procedure` block when a contract is
  declared; `artifact_sha256` answer binding; own canonicalization and
  digest)
- `reviewer-registry/v0.2` (two new scopes)

The amendment set is authored by Ari and adversarially reviewed by CC, per
the posted division of labor, with acceptance cases in the same PR.

## 7. Maintainer rulings on record (2026-07-31)

- The conformance/capability evaluation split is accepted, including the
  authoring workload it creates. The capability pool starts small, on the
  order of 10 to 15 held-out cases, with lazy rotation.
- The scope growth in section 6 is ratified in full: every version bump and
  both new artifact types.
- The maintainer holds the `procedure-domain` reviewer scope.
- The public capability pool is a rotating challenge set, named honestly as
  such. A genuinely private pool may be added later, off-repo, under
  maintainer control, and only that pool could carry a blind-holdout claim.

## 8. Revision history

- **v0.1 (2026-07-29).** Initial draft. Posted to discussions/5.
- **v0.2 (2026-08-01).** Review convergence revision. Clarification
  represented inside the three-outcome contract via `APPLICABILITY_UNRESOLVED`
  abstention (review section 2, adopted verbatim). Runbook split into
  guidance document plus minimal machine-readable procedure contract with
  structural fallback classification (review section 1). Procedure trace
  folded into `audit-envelope/v0.2` with one-way integrity binding (review
  section 3, location per CC preference, accepted by reviewer). Evaluation
  program split into conformance suite and capability evaluation with
  harness-enforced isolation and honest rotating-challenge-set naming
  (review section 4 plus follow-up safeguard). Invariance narrowed from
  byte-identical envelopes to a semantic display projection, correcting a
  CC overclaim on the public record (review section 5). Drift fails closed
  for reader/runtime claims only (review section 6). Two new reviewer
  scopes (review section 7). Cross-layer CI check as a digest-aware review
  control (review section 8). Motivating evidence downgraded from claim to
  testable hypothesis (evidence-boundary disposition). Executable runbook
  staleness from `next_due_at` (follow-up safeguard). All five open
  questions resolved and moved to section 5.
