# First Proof: Stage 1 and Stage 2 DBP Rules, Candidate Page List v0.1

Status: SUPERSEDED REVIEW RECORD. This annotated draft preserves the
maintainer's J1-J6 decisions and the S4 challenge; it is not the current page
list or a source of verified citations. See
`first-proof-dbp-page-list-v0.2.md` for the corrected candidate.

Method: every section anchor below was verified against the live eCFR API on
2026-07-28 (versions endpoint, Title 40, Part 141). Amendment dates come from
the API, not from memory. All DBP core sections were last amended 2016-12-28
except section 141.2 (Definitions), amended 2024-12-30, which is noted where
it matters.

Scope: federal only, per the accepted deferral of state-law ingestion. All
sources are 40 CFR 141 via the eCFR point-in-time API plus the public domain
EPA Stage 1 and Stage 2 Quick Reference Guides.

## Selection principle

Dependency-complete over count-complete. Each primary page names the failure
class it exists to test, drawn from the reviewer-concurred failure topology:
similar numbers with different meanings, applicability boundaries, derived
compliance calculations, exceptions, cross-references, and effective dates.

## Primary pages (12)

| # | page_id | Topic | Anchors (verified) | Failure class it tests |
|---|---------|-------|--------------------|------------------------|
| 1 | dbp.mcl.tthm | TTHM MCL 0.080 mg/L, LRAA basis | 141.64(b), 141.620 | Similar numbers: 0.080 vs 0.060; MCL vs OEL same number |
| 2 | dbp.mcl.haa5 | HAA5 MCL 0.060 mg/L, LRAA basis | 141.64(b), 141.620 | Paired confusion with TTHM; which five acids count (definition dependency) |
| 3 | dbp.mcl.bromate | Bromate MCL 0.010 mg/L, ozone systems, RAA basis | 141.64(a), 141.132(b)(3), 141.133(c) | Applicability: only systems using ozone monitor; RAA not LRAA |
| 4 | dbp.mcl.chlorite | Chlorite MCL 1.0 mg/L, chlorine dioxide systems, daily and monthly mechanics | 141.64(a), 141.132(b)(2), 141.133(c)(2) | Compliance period differs from every other DBP; no annual averaging |
| 5 | dbp.mrdl.chlorine-chloramine | MRDLs 4.0 mg/L as Cl2, RAA basis | 141.65, 141.133(c)(3) | Unit trap: as Cl2 for both; MRDL vs MCL category confusion |
| 6 | dbp.mrdl.chlorine-dioxide | MRDL 0.8 mg/L, daily samples, acute violation mechanics | 141.65, 141.132(c)(2), 141.133(c)(3) | Same rule family, radically different violation mechanics; feeds Tier 1 notification |
| 7 | dbp.compliance.lraa | Locational running annual average: definition and computation | 141.2 (LRAA), 141.620(c), 141.625 | Derived calculation; the Stage 1 RAA to Stage 2 LRAA transition |
| 8 | dbp.compliance.oel | Operational evaluation levels | 141.626 | Same numeric values as the MCLs but not violations; the strongest same-number trap in the family |
## OELs apply to only TTHM and HAA5

| 9 | dbp.monitoring.routine | Routine monitoring by system size and source type | 141.621 | Population and source-water applicability matrix |
| 10 | dbp.monitoring.reduced-increased | Reduced monitoring criteria and conditions forcing return | 141.623, 141.625 | Exceptions machinery in both directions |
| 11 | dbp.applicability.stage2 | Who Subpart V covers, including consecutive systems | 141.620(a)-(b), 141.624 | System-type boundaries: CWS, NTNCWS adding a disinfectant, consecutive systems; the transient-system trap |
| 12 | dbp.precursors.toc | Treatment technique for DBP precursors, enhanced coagulation, TOC removal | 141.135 | Applicability limited to conventional filtration; table-valued requirement (see strain note S3) |

## Dependency pages (3)

| # | page_id | Topic | Anchors (verified) | Why it must exist |
|---|---------|-------|--------------------|-------------------|
| 13 | dbp.definitions | Controlled definitions: TTHM, HAA5, LRAA, RAA, compliance monitoring terms | 141.2 | Pages 1-12 cannot be context-complete without it. Amended 2024-12-30: the one recently amended anchor in the set, which makes it the live staleness-triage test case (does an amendment touching unrelated definitions flag DBP pages or correctly leave them alone) |
| 14 | dbp.mclg | MCLGs for DBPs and residuals | 141.53, 141.65 | The zero-versus-limit trap (bromate MCLG zero, MCL 0.010); kept as one page rather than per-contaminant fields, see judgment call J1 |
| 15 | dbp.violations.notification | Public notification tiers for DBP violations | Subpart Q cross-reference, 141.133(c)(3) | Chlorine dioxide acute violations are Tier 1; MCL violations Tier 2; monitoring violations Tier 3. Without it page 6 dead-ends at its most consequential cross-reference |

## Explicitly excluded from the first proof (published as exclusions)

- Subpart U, IDSE (141.600 through 141.605): a completed historical program.
  Its output (monitoring locations) is context for page 9, cited not ingested.
  See judgment call J2.
- Analytical methods (141.131): long method lists, low question value for the
  proof. Cited not ingested. See judgment call J3.
- Consumer Confidence Report content rules (141.151 through 141.154): adjacent
  but a different rule family.
- All state-layer content, per the accepted deferral.

## Claim-model strain notes (what this proof will stress)

- S1. LRAA is a derived claim computed per monitoring location over four
  quarters. The claim tuple's applicability object has system-type and
  source-water dimensions but no location dimension. The structured derivation
  proposal (running-annual-average as a declared operation) gets its first
  real test here.
- S2. The OEL formula (sum of the two previous quarters plus twice the current
  quarter, divided by four) is a second declared operation, and its output
  must never be renderable as an MCL compliance verdict.
- S3. The TOC removal requirement (141.135) is a matrix: source-water TOC
  band by alkalinity band yielding required percent removal. A scalar
  value field cannot carry it. Options: one claim per cell (nine claims) or
  a new table-valued claim kind. See judgment call J5.
- S4. Chlorite has two different compliance answers depending on whether the
  question is about the daily distribution-entry check or the monthly
  three-sample set. A page that cannot represent both invites the exact
  wrong-meaning failure the claim checks exist to catch.
  ## how is the Chlorite compliance answer different depending on whether the question is about the daily distribution-entry check or the monthly in-distribution check? The "three-sample set" you are referring to has nothing to do with Chlorite, rather it has to do with TOC removal requirements.

## Judgment calls for the page list owner

- J1. MCLGs: one dependency page (as drafted) or a field on each contaminant
  page? One page keeps the zero-versus-limit contrast teachable in one place;
  per-page fields keep each contaminant self-contained.
  ## Answer: keep as drafted

- J2. IDSE exclusion: agree, or does operator experience say monitoring-site
  questions come up often enough to earn a page?
  ## Answer: Regardless of whether a question comes up often or infrequently, why would we choose to omit data? The possibility exists that a question may arise regarding IDSE so why fail the possibility of answering it by subjectively excluding information?

- J3. Analytical methods exclusion: agree, or are method questions (which
  method is approved for TTHM) real exam material worth a page?
  ## Answer: Same answer as J2

- J4. TTHM and HAA5 as separate pages (as drafted) or one combined page? Split
  tests the paired-confusion failure class harder; combined reads more like
  how operators encounter them.
  ## Answer: Split. defer to testing the paired-confusion failure harder rather than easier

- J5. The TOC matrix (S3): nine per-cell claims or a table-valued claim kind?
  Per-cell claims work in the current schema today; a table kind is honest
  about the data's shape but requires a schema amendment before ratification.
  ## Answer: So what I hear is that we have something that works and is easy, or something that is honest about the data's shape but will take a little more work. I would think my answer to this question would be understood by now. Table-valued claim is the decision.

- J6. Missing pages: what do new operators actually ask about DBPs that this
  list has no page for? The gap only your exam-prep and control-room
  experience can see.
  ## Answer: No input right now. Gaps will become more evident after testing.

- J7. Adversarial question seeding: pages 4, 6, and 8 are drafted as trap-rich
  on purpose. Confirm from experience which DBP misunderstandings are most
  common in the field so question writing starts where errors live.

## Sequencing note

Page 13 (definitions) and page 14 (MCLGs) should be authored first: every
other page's claims reference their terms. Page 12 should be authored last:
it carries the hardest open modeling question (S3/J5).
