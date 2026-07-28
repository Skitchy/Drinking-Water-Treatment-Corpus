# First Proof: Stage 1 and Stage 2 DBP Rules, Page List v0.2

Status: incorporates the page list owner's v0.1 review decisions (J1 through
J6 answered in the annotated v0.1, kept as the review record). J7 remains
open. The owner's inclusion principle from J2 now governs selection.

Method note, strengthened after v0.1 review: v0.1 verified section-level
anchors against the live eCFR API but cited paragraph-level anchors from
memory, and the owner's S4 challenge exposed three wrong paragraph citations.
Every paragraph anchor below is now verified against fetched section text
(eCFR point-in-time 2026-07-01, retrieved 2026-07-28). The corrected anchors
are marked. This is the exact failure mode the corpus exists to prevent,
demonstrated inside its own planning document.

Follow-up review of the dependency rows corrected two further citation
problems: residual-disinfectant goals belong to 141.54 rather than 141.65, and
the rule-specific phrases paired samples and three-sample set do not originate
in the general definitions at 141.2.

## Selection principle (revised per J2)

Dependency-complete over count-complete, and within the rule family:
completeness over curation. Every authoritative provision within the declared
rule-family scope must be represented or explicitly recorded as a coverage gap
or exclusion with its reason. If a question can arise from the family, the
corpus should be able to answer it rather than fail it by subjective omission.

## S4 resolution: the chlorite challenge, settled by the source

The owner challenged S4's claim that chlorite uses a monthly three-sample
set, attributing that term to TOC. Verbatim regulation text, fetched:

- 40 CFR 141.132(b)(2)(i)(B): "Monthly monitoring. Systems must take a
  three-sample set each month in the distribution system."  (This is the
  chlorite monitoring paragraph.)
- 40 CFR 141.133(b)(3): "Chlorite. Compliance must be based on an arithmetic
  average of each three sample set taken in the distribution system as
  prescribed by 141.132(b)(2)(i)(B) and 141.132(b)(2)(ii)."
- 40 CFR 141.132(d)(1) (TOC monitoring): "These samples (source water and
  treated water) are referred to as paired samples. ... Systems must take one
  paired sample and one source water alkalinity sample per month per plant."

So the three-sample set belongs to chlorite; TOC uses paired samples plus a
source alkalinity sample. The challenge was still productive twice over: it
caught the three wrong paragraph anchors noted above, and it proves the
adversarial-review loop works before a single page exists. S4 rewritten below
with the verbatim mechanics.

## Primary pages (14)

| # | page_id | Topic | Anchors (paragraph-verified) | Failure class it tests |
|---|---------|-------|------------------------------|------------------------|
| 1 | dbp.mcl.tthm | TTHM MCL 0.080 mg/L, LRAA basis | 141.64(b), 141.620 | Similar numbers: 0.080 vs 0.060; MCL vs OEL same number |
| 2 | dbp.mcl.haa5 | HAA5 MCL 0.060 mg/L, LRAA basis | 141.64(b), 141.620 | Paired confusion with TTHM; which five acids count (definition dependency) |
| 3 | dbp.mcl.bromate | Bromate MCL 0.010 mg/L, ozone systems, RAA basis | 141.64(a), 141.132(b)(3), 141.133(b)(2) CORRECTED | Applicability: only systems using ozone monitor; RAA not LRAA |
| 4 | dbp.mcl.chlorite | Chlorite MCL 1.0 mg/L, chlorine dioxide systems | 141.64(a), 141.132(b)(2), 141.133(b)(3) CORRECTED | Compliance period differs from every other DBP; no annual averaging; daily entrance samples versus monthly three-sample set (S4) |
| 5 | dbp.mrdl.chlorine-chloramine | MRDLs 4.0 mg/L as Cl2, RAA basis | 141.65, 141.133(c)(1) CORRECTED | Unit trap: as Cl2 for both; MRDL vs MCL category confusion |
| 6 | dbp.mrdl.chlorine-dioxide | MRDL 0.8 mg/L, daily samples, acute violation mechanics | 141.65, 141.132(c)(2), 141.133(c)(2) CORRECTED | Same rule family, radically different violation mechanics; feeds Tier 1 notification |
| 7 | dbp.compliance.lraa | Locational running annual average: definition and computation | 141.2 (LRAA), 141.620(c), 141.625 | Derived calculation; the Stage 1 RAA to Stage 2 LRAA transition |
| 8 | dbp.compliance.oel | Operational evaluation levels, TTHM and HAA5 only (owner note folded in) | 141.626 | Same numeric values as the MCLs but not violations; the strongest same-number trap in the family; scope trap: OELs do not exist for bromate or chlorite |
| 9 | dbp.monitoring.routine | Routine monitoring by system size and source type | 141.621 | Population and source-water applicability matrix |
| 10 | dbp.monitoring.reduced-increased | Reduced monitoring criteria and conditions forcing return | 141.623, 141.625 | Exceptions machinery in both directions |
| 11 | dbp.applicability.stage2 | Who Subpart V covers, including consecutive systems | 141.620(a)-(b), 141.624 | System-type boundaries: CWS, NTNCWS adding a disinfectant, consecutive systems; the transient-system trap |
| 12 | dbp.precursors.toc | Treatment technique for DBP precursors, enhanced coagulation, TOC removal, paired-sample monitoring | 141.135, 141.132(d) | Applicability limited to conventional filtration; table-valued requirement (S3, decided: table-valued claim kind, J5); paired samples versus three-sample set confusion (S4's mirror) |
| 13 | dbp.monitoring.idse | IDSE program: what it was, how Subpart V monitoring locations were derived | 141.600 through 141.605 | ADDED per J2: historical program whose output is live infrastructure; effective-date and cross-reference topology |
| 14 | dbp.analytical-methods | Approved analytical methods for DBP and residual monitoring | 141.131 | ADDED per J3: method-approval questions; the wrong-method trap in compliance samples |

## Dependency pages (3)

| # | page_id | Topic | Anchors | Why it must exist |
|---|---------|-------|---------|-------------------|
| 15 | dbp.definitions | Controlled definitions plus rule-specific sampling terminology: TTHM, HAA5, LRAA, RAA, paired samples, three-sample set, compliance monitoring terms | 141.2; 141.132(b)(2), 141.132(d) CORRECTED | Pages 1-14 cannot be context-complete without both the general definitions and the rule text that introduces the two sampling terms. Section 141.2 was amended 2024-12-30 and remains the live staleness-triage test case |
| 16 | dbp.mclg | MCLGs for DBPs and residual disinfectants | 141.53, 141.54 CORRECTED | The zero-versus-limit trap. J1 decided: kept as one page |
| 17 | dbp.violations.notification | Public notification tiers for DBP violations | Subpart Q cross-reference, 141.133(c)(2) CORRECTED | Chlorine dioxide acute violations are Tier 1; MCL violations Tier 2; monitoring violations Tier 3 |

## Coverage gaps and exclusions

- Consumer Confidence Report content rules (141.151 through 141.154):
  different rule family; candidate for a later family, not an omission from
  this one.
- All state-layer content, per the accepted deferral.
- No within-family sections remain excluded. IDSE and analytical methods
  moved into the list per the owner's J2/J3 principle.

## Claim-model strain notes (revised)

- S1. LRAA is a derived claim computed per monitoring location over four
  quarters. The claim tuple's applicability object has no location dimension.
  The registered-algorithm derivation model (PR #4) gets its first real test.
- S2. The OEL formula (sum of the two previous quarters plus twice the current
  quarter, divided by four) is a second registered algorithm, and its output
  must never be renderable as an MCL compliance verdict. Scope limit per
  owner: TTHM and HAA5 only.
- S3. DECIDED (J5): the TOC removal matrix becomes a table-valued claim kind.
  PR #4 now carries the schema amendment: stable dimensions, bands, and cells;
  answer-side stable-cell selection; and mandatory cell-fidelity checks. It
  remains subject to the ratification decision.
- S4. REWRITTEN with verbatim mechanics: chlorite compliance is based on the
  arithmetic average of each monthly three-sample set taken in the
  distribution system (141.133(b)(3)); daily entrance-point samples do not
  themselves establish MCL compliance but trigger next-day additional
  distribution monitoring when they exceed 1.0 mg/L (141.132(b)(2)(i)(A)).
  TOC monitoring uses monthly paired samples (source and treated water) plus
  source alkalinity (141.132(d)(1)). Adversarial questions should target the
  chlorite/TOC sample-set confusion directly: a domain expert reviewer made
  exactly this swap during list review, which is the strongest possible
  evidence the trap is real.

## Open items

- J7 (owner): which DBP misunderstandings are most common in the field, to
  seed the adversarial question set. Standing evidence from this review: the
  chlorite/TOC sample-terminology swap is candidate number one.
- J6 revisit after first testing round, per owner.

## Sequencing (revised)

Pages 15 and 16 (definitions, MCLGs) first: every other page references their
terms. Page 12 (TOC) last: it carries the table-valued claim kind, which
waits on ratification of the PR #4 amendment. Pages 13 and 14 (IDSE, methods)
after the core MCL/MRDL pages: they are completeness pages, not blocking
dependencies.
