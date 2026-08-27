# Reviewer packet: candidate material for section 141.133

Quarantined experimental output. Disposition each block as accept / correct / reject. Nothing here has standing without your disposition.

Machine verification: 14 quotes verified, 0 rejected; 5 claims verified, 4 rejected; 7 questions kept.

## Page proposals
- [accepted] `compliance-general-requirements`: General compliance and monitoring-failure rules applicable across DBP/DBPP parameters
  - citations: 141.133(a)(1), 141.133(a)(2), 141.133(a)(3)
- [accepted] `tthm-haa5-compliance`: TTHM and HAA5 MCL compliance calculation
  - citations: 141.133(b)(1)
- [accepted] `bromate-compliance`: Bromate MCL compliance calculation
  - citations: 141.133(b)(2)
- [accepted] `chlorite-compliance`: Chlorite MCL compliance calculation
  - citations: 141.133(b)(3)
- [accepted] `chlorine-chloramines-mrdl-compliance`: Chlorine and chloramines MRDL compliance, including switching between disinfectants
  - citations: 141.133(c)(1)
- [accepted] `chlorine-dioxide-mrdl-violations`: Chlorine dioxide acute and nonacute MRDL violation conditions
  - citations: 141.133(c)(2)(i), 141.133(c)(2)(ii)
- [accepted] `dbpp-toc-removal-compliance`: Disinfection byproduct precursor (DBPP) compliance and Step 1 TOC removal treatment technique threshold
  - citations: 141.133(d)

## Verified quotes (binding recomputed from canonical bytes)
- `q1` [141.133(a)(1)] DIV8[N=141.133]/P[1]
  > Where compliance is based on a running annual average of monthly or quarterly samples or averages and the system fails to monitor for TTHM, HAA5, or bromate, this failure to monitor will be treated as a monitoring violation for the entire period covered by the annual average.
- `q2` [141.133(a)(2)] DIV8[N=141.133]/P[2]
  > All samples taken and analyzed under the provisions of this subpart must be included in determining compliance, even if that number is greater than the minimum required.
- `q3` [141.133(a)(3)] DIV8[N=141.133]/P[3]
  > If, during the first year of monitoring under § 141.132, any individual quarter's average will cause the running annual average of that system to exceed the MCL for total trihalomethanes, haloacetic acids (five), or bromate; or the MRDL for chlorine or chloramine, the system is out of compliance at the end of that quarter.
- `q4` [141.133(b)(1)] DIV8[N=141.133]/P[4]
  > For systems monitoring quarterly, compliance with MCLs in § 141.64 must be based on a running annual arithmetic average, computed quarterly, of quarterly arithmetic averages of all samples collected by the system as prescribed by § 141.132(b)(1).
- `q5` [no derived anchor] DIV8[N=141.133]/P[5]
  > For systems monitoring less frequently than quarterly, systems demonstrate MCL compliance if the average of samples taken that year under the provisions of § 141.132(b)(1) does not exceed the MCLs in § 141.64.
- `q6` [no derived anchor] DIV8[N=141.133]/P[6]
  > If the running annual arithmetic average of quarterly averages covering any consecutive four-quarter period exceeds the MCL, the system is in violation of the MCL and must notify the public pursuant to § 141.32 or § 141.202, whichever is effective for your system, in addition to reporting to the State pursuant to § 141.134.
- `q7` [141.133(b)(2)] DIV8[N=141.133]/P[8]
  > Compliance must be based on a running annual arithmetic average, computed quarterly, of monthly samples (or, for months in which the system takes more than one sample, the average f all samples taken during the month) collected by the system as prescribed by § 141.132(b)(3).
- `q8` [141.133(b)(3)] DIV8[N=141.133]/P[9]
  > Compliance must be based on an arithmetic average of each three sample set taken in the distribution system as prescribed by § 141.132(b)(2)(i)(B) and § 141.132(b)(2)(ii).
- `q9` [141.133(c)(1)] DIV8[N=141.133]/P[10]
  > Compliance must be based on a running annual arithmetic average, computed quarterly, of monthly averages of all samples collected by the system under § 141.132(c)(1).
- `q10` [no derived anchor] DIV8[N=141.133]/P[11]
  > In cases where systems switch between the use of chlorine and chloramines for residual disinfection during the year, compliance must be determined by including together all monitoring results of both chlorine and chloramines in calculating compliance.
- `q11` [141.133(c)(2)(i)] DIV8[N=141.133]/P[12]
  > If any daily sample taken at the entrance to the distribution system exceeds the MRDL, and on the following day one (or more) of the three samples taken in the distribution system exceed the MRDL, the system is in violation of the MRDL and must take immediate corrective action to lower the level of chlorine dioxide below the MRDL and must notify the public pursuant to the procedures for acute health risks in subpart Q in addition to reporting to the State pursuant to § 141.134.
- `q12` [141.133(c)(2)(ii)] DIV8[N=141.133]/P[13]
  > If any two consecutive daily samples taken at the entrance to the distribution system exceed the MRDL and all distribution system samples taken are below the MRDL, the system is in violation of the MRDL and must take corrective action to lower the level of chlorine dioxide below the MRDL at the point of sampling and will notify the public pursuant to the procedures for nonacute health risks in subpart Q in addition to reporting to the State pursuant to § 141.134.
- `q13` [141.133(d)] DIV8[N=141.133]/P[14]
  > For systems required to meet Step 1 TOC removals, if the value calculated under § 141.135(c)(1)(iv) is less than 1.00, the system is in violation of the treatment technique requirements and must notify the public pursuant to subpart Q of this part, in addition to reporting to the State pursuant to § 141.134.
- `q14` [141.133(d)] DIV8[N=141.133]/P[14]
  > Compliance must be determined as specified by § 141.135(c).

## Verified claims
- `c1` [qualitative] TTHM and HAA5 compliance-basis running annual arithmetic average, computed quarterly, of quarterly arithmetic averages of all samples collected by the system
  - conditions: systems monitoring quarterly; as prescribed by § 141.132(b)(1)
  - support: q4
- `c3` [qualitative] Chlorite compliance-basis arithmetic average of each three sample set taken in the distribution system
  - conditions: as prescribed by § 141.132(b)(2)(i)(B) and § 141.132(b)(2)(ii)
  - support: q8
- `c4` [qualitative] Chlorine and chloramines (MRDL) compliance-basis running annual arithmetic average, computed quarterly, of monthly averages of all samples collected by the system
  - conditions: under § 141.132(c)(1)
  - support: q9
- `c7` [numeric] DBPP Step 1 TOC removal ratio (§ 141.135(c)(1)(iv)) requires-treatment-technique 1.00
  - conditions: systems required to meet Step 1 TOC removals
  - support: q13
- `c8` [qualitative] TTHM, HAA5, or bromate monitoring failure compliance-basis treated as a monitoring violation for the entire period covered by the annual average
  - conditions: compliance based on a running annual average of monthly or quarterly samples or averages
  - support: q1

## Machine-rejected material (for your awareness, not for rescue)
- claim `c2`: value-not-verbatim-in-support
- claim `c5`: value-not-verbatim-in-support
- claim `c6`: value-not-verbatim-in-support
- claim `c9`: value-not-verbatim-in-support

## Candidate challenge questions
- Q: If a system fails to monitor for TTHM, HAA5, or bromate under running-annual-average compliance, what is the consequence?
  A: The failure to monitor is treated as a monitoring violation for the entire period covered by the annual average.
- Q: How is TTHM/HAA5 MCL compliance calculated for a system that monitors quarterly?
  A: As a running annual arithmetic average, computed quarterly, of quarterly arithmetic averages of all samples collected as prescribed by § 141.132(b)(1).
- Q: How is bromate MCL compliance calculated?
  A: As a running annual arithmetic average, computed quarterly, of monthly samples collected as prescribed by § 141.132(b)(3).
- Q: How is chlorite MCL compliance calculated?
  A: As the arithmetic average of each three-sample set taken in the distribution system.
- Q: What sample results must a system combine if it switches between chlorine and chloramines during the year?
  A: It must include together all monitoring results of both chlorine and chloramines when calculating compliance.
- Q: What combination of results constitutes an acute chlorine dioxide MRDL violation?
  A: A daily sample at the entrance to the distribution system exceeding the MRDL, followed the next day by one or more of the three distribution system samples also exceeding the MRDL.
- Q: For DBPP Step 1 TOC removal, what value of the § 141.135(c)(1)(iv) calculation triggers a treatment technique violation?
  A: A calculated value less than 1.00.

## Ambiguities declared by the extraction role
- Paragraphs at DIV8[N=141.133]/P[5], P[6], and P[7] carry designators (ii), (iii), (iv) but their parent-level anchor (e.g., 141.133(b)(1)(ii)) is not confirmed by the source's own logical_anchors, which mark them as review-item designator ambiguities rather than derived labels.
- Paragraph DIV8[N=141.133]/P[11] carries designator (ii) but its parent-level anchor (e.g., 141.133(c)(1)(ii)) is likewise flagged as a review-item designator ambiguity in the source rather than derived.
- P[8] contains the text 'the average f all samples taken during the month', which appears to be a transcription/OCR error for 'the average of all samples'; quoted verbatim as it appears in the source rather than corrected.

## Disposition

- [ ] accept as candidate page material
- [ ] accept with corrections (list below)
- [ ] reject (reason below)

Source verification record: `out/verified/verified-141.133.json` (candidate response digest `06d32e6d624f793a...`)
