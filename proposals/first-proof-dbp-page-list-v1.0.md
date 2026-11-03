# First Proof: Stage 1 and Stage 2 DBP Rules, Page List v1.0 (frozen 2026-11-02)

Status: FROZEN under Charter v1.1 Done item 1 and Skitch's decision D2 (2026-11-01, Ari's version). Machine-readable copy: `evaluation/dbp-page-list-v1.0.json`. Supersedes v0.2, whose statement "No within-family sections remain excluded" is withdrawn: six captured sections had no page. Four are folded in below with a planned claim per requirement; two reporting sections are excluded with reason. Page IDs do not change after this date without a new list version.

## The 17 pages

| # | page_id | Topic | Anchors | Status |
|---|---|---|---|---|
| 1 | dbp.mcl.tthm | TTHM MCL 0.080 mg/L, LRAA basis | 141.64(b), 141.620 | planned |
| 2 | dbp.mcl.haa5 | HAA5 MCL 0.060 mg/L, LRAA basis | 141.64(b), 141.620 | planned |
| 3 | dbp.mcl.bromate | Bromate MCL 0.010 mg/L, ozone systems, RAA basis | 141.64(a), 141.132(b)(3), 141.133(b)(2) | planned |
| 4 | dbp.mcl.chlorite | Chlorite MCL 1.0 mg/L, chlorine dioxide systems | 141.64(a), 141.132(b)(2), 141.133(b)(3) | planned |
| 5 | dbp.mrdl.chlorine-chloramine | MRDLs 4.0 mg/L as Cl2, RAA basis | 141.65, 141.133(c)(1) | planned |
| 6 | dbp.mrdl.chlorine-dioxide | MRDL 0.8 mg/L, daily samples, acute violation mechanics | 141.65, 141.132(c)(2), 141.133(c)(2) | planned |
| 7 | dbp.compliance.lraa | Locational running annual average: definition and computation | 141.2 (LRAA), 141.620(c), 141.625 | planned |
| 8 | dbp.compliance.oel | Operational evaluation levels, TTHM and HAA5 only | 141.626 | planned |
| 9 | dbp.monitoring.routine | Routine monitoring by system size and source type, and the Subpart V monitoring plan | 141.621, 141.622 (D2 fold-in) | planned |
| 10 | dbp.monitoring.reduced-increased | Reduced monitoring criteria, conditions forcing return, and carry-over from subpart L results | 141.623, 141.625, 141.627 (D2 fold-in), 141.628 (D2 fold-in) | planned |
| 11 | dbp.applicability.stage2 | Who subparts L and V cover, compliance dates, consecutive systems, residual-increase allowance | 141.620(a)-(b), 141.624, 141.130 (D2 fold-in) | planned |
| 12 | dbp.precursors.toc | Treatment technique for DBP precursors, enhanced coagulation, TOC removal, paired-sample monitoring | 141.135, 141.132(d) | planned |
| 13 | dbp.monitoring.idse | IDSE program: what it was, how Subpart V monitoring locations were derived | 141.600, 141.601, 141.602, 141.603, 141.604, 141.605 | planned |
| 14 | dbp.analytical-methods | Approved analytical methods for DBP and residual monitoring | 141.131 | planned |
| 15 | dbp.definitions | Controlled definitions plus rule-specific sampling terminology | 141.2, 141.132(b)(2), 141.132(d) | stable |
| 16 | dbp.mclg | MCLGs for DBPs and MRDLGs for residual disinfectants | 141.53, 141.54 | stable |
| 17 | dbp.violations.notification | Public notification tiers for DBP violations | subpart Q, 141.133(c)(2) | planned |

## D2 fold-in: requirement to planned claim

A section citation alone is not enough (D2). Each requirement below becomes a claim on the named page when that page is built; the claim IDs are reserved here.

| Section | Into page | Requirement (paraphrase; the page quotes the rule) | Planned claim |
|---|---|---|---|
| 141.622(a)(1) | dbp.monitoring.routine | Develop and implement a monitoring plan kept on file for State and public review, complete no later than the initial Subpart V monitoring date, containing monitoring locations, monitoring dates, compliance calculation procedures, and plans for other systems in the combined distribution system where the State reduced requirements under 142.16(m) | claim.dbp.monitoring.routine.monitoring-plan-required |
| 141.622(a)(2) | dbp.monitoring.routine | Systems without an IDSE report and with too few subpart L locations identify additional compliance monitoring locations by alternating selection of high-TTHM and high-HAA5 locations, with rationale; systems with more subpart L locations than needed choose by the same alternation | claim.dbp.monitoring.routine.monitoring-plan-location-selection |
| 141.622(b) | dbp.monitoring.routine | Subpart H systems serving more than 3,300 people submit a copy of the monitoring plan to the State before initial monitoring unless the IDSE report already contains the required information | claim.dbp.monitoring.routine.monitoring-plan-submittal |
| 141.622(c) | dbp.monitoring.routine | Plan revisions for treatment, distribution or layout changes after State consultation; changed locations replace the lowest-LRAA locations with expected high TTHM or HAA5 locations; the State may require modifications; subpart H systems over 3,300 submit the modified plan before complying with it | claim.dbp.monitoring.routine.monitoring-plan-revision |
| 141.627 | dbp.monitoring.reduced-increased | Remaining on reduced monitoring after the 141.620(c) dates requires a 40/30 certification under 141.603 or a very small system waiver under 141.604, plus the 141.623(a) criteria, with no change or addition of monitoring locations from subpart L | claim.dbp.monitoring.reduced-increased.remain-reduced-subpart-l |
| 141.627 (second sentence) | dbp.monitoring.reduced-increased | If Subpart V monitoring locations differ from subpart L locations, the system may not remain on reduced monitoring after the 141.620(c) dates | claim.dbp.monitoring.reduced-increased.remain-reduced-locations-differ |
| 141.628 | dbp.monitoring.reduced-increased | A system on increased monitoring under 141.132(b)(1) remains on increased monitoring under 141.625 at the 141.622 plan locations from the 141.620(c) date until it qualifies for a return to routine monitoring under 141.625(c) | claim.dbp.monitoring.reduced-increased.remain-increased-subpart-l |
| 141.130(a)(1) | dbp.applicability.stage2 | Subpart L applies to CWSs and NTNCWSs that add a chemical disinfectant in any part of treatment: they must meet the MCLs in 141.64, the MRDLs in 141.65 and the precursor treatment technique in 141.135 | claim.dbp.applicability.stage2.subpart-l-scope-cws-ntncws |
| 141.130(a)(2) | dbp.applicability.stage2 | Transient NCWSs that use chlorine dioxide as a disinfectant or oxidant must meet the chlorine dioxide MRDL in 141.65 | claim.dbp.applicability.stage2.subpart-l-scope-tncws-chlorine-dioxide |
| 141.130(a)(3) | dbp.applicability.stage2 | Informational statement of purpose naming the regulated byproducts; not a requirement. Compositions are already claims on dbp.definitions | (context only, no claim) |
| 141.130(b)(1) | dbp.applicability.stage2 | Compliance dates for CWSs and NTNCWSs: subpart H systems serving 10,000 or more from January 1, 2002; subpart H systems under 10,000 and ground water systems not under the direct influence of surface water from January 1, 2004 | claim.dbp.applicability.stage2.subpart-l-compliance-dates-cws-ntncws |
| 141.130(b)(2) | dbp.applicability.stage2 | Compliance dates for transient NCWSs using chlorine dioxide: the same two dates by the same size and source split | claim.dbp.applicability.stage2.subpart-l-compliance-dates-tncws |
| 141.130(c) | dbp.applicability.stage2 | Each regulated CWS and NTNCWS must be operated by qualified personnel meeting State requirements and listed in the State register of qualified operators | claim.dbp.applicability.stage2.qualified-operators |
| 141.130(d) | dbp.applicability.stage2 | Notwithstanding the MRDLs, systems may raise chlorine or chloramine residuals (not chlorine dioxide) to the level and for the time needed to protect public health during specified microbiological contamination events | claim.dbp.applicability.stage2.residual-increase-allowance |

## Excluded sections

- 141.134 Reporting and recordkeeping requirements (subpart L): Reporting rule, excluded from Milestone 1 per D2 (Skitch 2026-11-01, Ari's version). Candidate for a later reporting family.
- 141.629 Reporting and recordkeeping requirements (subpart V): Reporting rule, excluded from Milestone 1 per D2 (Skitch 2026-11-01, Ari's version). Candidate for a later reporting family.

## Coverage rule

Every captured section in the family is either anchored by a page, folded in with a planned claim per requirement, or listed as excluded with its reason. Checked against the 27 section captures plus subpart Q on 2026-11-02: none unaccounted.
