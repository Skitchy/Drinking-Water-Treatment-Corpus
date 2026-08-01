# RFC 004: The Procedural Layer. Runbook and Evaluation Artifacts

Status: DRAFT for discussion. Nothing in this RFC modifies the ratified
`schema-foundation-v0.1` contracts. Any schema consequence identified during
discussion follows the post-ratification gate: version bump, recorded
rationale, pull-request review.

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

External evidence suggests this gap is the largest remaining accuracy lever,
not a documentation nicety. Anthropic's published account of its internal
analytics agent ("How Anthropic enables self-service data analytics with
Claude," June 3, 2026) reports three measured results:

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

### 2.1 Runbook artifact

A versioned, digest-pinned procedural document governing reader behavior in
front of the gateway. Proposed minimum contents:

- **Resolution order.** Structured claim resolution against the pinned corpus
  release is the mandatory first path. Free retrieval over page prose is the
  fallback, permitted only after claim resolution is shown not to cover the
  ask. The runbook enumerates and pre-rebuts the known excuses for skipping
  the first path, so that a capable model cannot rationalize its way around
  the ordering.
- **Clarification triggers.** The question classes that must produce a
  clarification request rather than a best guess (ambiguous entity, missing
  applicability context, ambiguous time basis).
- **Abstention triggers.** The conditions that must produce `abstention`,
  aligned with the ratified envelope invariants.
- **Gotchas.** Known wrong-answer modes, maintained as a first-class section.
  The adversarial question set (section 2.2) is the source that feeds it.
- **Provenance requirements.** What the reader must surface with each of the
  three outcomes (`evidence-backed`, `evidence-only`, `abstention`), beyond
  what the envelope already enforces.

Governance: the runbook is reviewed and versioned like any other ratified
artifact. Open question 5.1 addresses where it is pinned.

### 2.2 Evaluation-set artifact

The planned adversarial questions become a machine-readable evaluation
artifact rather than review notes:

- Each case carries: the question, the expected outcome class, and, for
  `evidence-backed` expectations, the specific claim and quote IDs a correct
  answer must select.
- The set is pinned to a corpus release digest. Ground truth is evaluated
  against that release, not against a floating "current" state, so staleness
  cannot silently invalidate the evaluation.
- The set runs in CI against every corpus release. Because this domain is
  deterministic (a maximum contaminant level is a fact with an authoritative
  source), the offline target is 100%, not an aggregate score. Any failure is
  a defect in the corpus, the runbook, or the case itself, and must be
  dispositioned, not averaged away.

### 2.3 Invariance assertions

The layered design implies a testable property worth stating as a contract
claim rather than a slogan:

- **Answer invariance given success.** Two conforming readers that select the
  same claim and quote IDs against the same pinned release must produce
  equivalent answer envelopes. Divergence between valid answers is a gateway
  defect by definition, never a model property. This follows from
  selection-not-authorship and should be asserted in the acceptance suite.
- **Success-rate telemetry.** Reader capability and runbook quality affect
  how often the valid outcome is reached, not what a valid answer contains.
  Per-reader success and abstention rates against the evaluation set are the
  measure of runbook quality. A weaker reader must degrade toward more
  abstentions, never toward different answers.

### 2.4 Cross-layer integrity check

Borrowing a practice reported in the same external account: a change to a
corpus page that does not touch its structured claims, its evaluation cases,
or an explicit "no change needed" disposition should be flagged in CI review.
This prevents the procedural and evaluation layers from silently drifting
away from the knowledge layer they describe.

## 3. What this RFC does not change

- No modification to the seven ratified schemas is proposed at this stage.
- The gateway remains the sole validity authority. The runbook cannot make an
  invalid answer pass; it can only change how often the reader reaches a
  valid outcome. Assurance claims stay exactly as narrow as they are today.
- The first-proof page list (v0.2, signed) and its sequencing are unchanged.
  Capture remains the next build.

## 4. One deliberate divergence from the cited practice

The cited analytics system keeps a raw-exploration fallback that can produce
free-text answers with provenance footers, accepting aggregate accuracy in
the mid-90s. This project's envelope has no free-text path and no aggregate
target. The runbook therefore treats the fallback path as ending at the same
gateway as the primary path. Procedure improves the hit rate; it never
widens what the format can express. Their reported failure mode ("plausible
wrong answers used without objection are the hardest to catch") is the
argument for keeping this divergence, not softening it.

## 5. Open questions for review

1. **Pinning location.** Should the runbook be pinned by the
   runtime-assurance manifest as a third digest-pinned artifact alongside the
   corpus release and `required_check_baseline` (making a stale or absent
   runbook a fail-closed condition), or referenced per deployment as a
   profile-level declaration? The stricter option is preferred by the author
   but has a cost: every runbook edit forces a runtime manifest update.
2. **Evaluation-set versioning.** Part of the corpus release manifest, or a
   separately versioned artifact with an explicit compatibility pin to a
   release digest? The two-anchor precedent suggests the latter.
3. **Drift semantics.** If the corpus release advances and the evaluation set
   or runbook has not been re-dispositioned against it, is that a warning or
   a fail-closed condition for `stable` status claims?
4. **Review scopes.** Which reviewer scopes sign the runbook? The procedure
   is partly mechanics (resolution order, envelope alignment) and partly
   domain judgment (clarification triggers, gotchas). The registry's existing
   scope split appears to cover it, but the assignment should be explicit.
5. **Case authorship boundary.** Evaluation questions originate from human
   domain review (they are the domain specification). Distillation of prior
   reader transcripts into candidate cases is permitted as raw material, per
   the same curation-not-retrieval principle the external evidence supports,
   but a human owns every accepted case. Confirm or contest.

## 6. Requested dispositions

- Concur or contest: runbook as a ratified, digest-pinned artifact
  (section 2.1, question 5.1).
- Concur or contest: evaluation set pinned to release digests with a 100%
  offline target (section 2.2).
- Concur or contest: invariance assertions entering the acceptance suite
  (section 2.3).
- Position on questions 5.1 through 5.5.
