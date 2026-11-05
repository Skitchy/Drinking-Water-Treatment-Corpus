#!/usr/bin/env python3
"""Batch 1 page builder (Water Advisor session 5; moved into tools/ in session 6
so the authoring path is on record; session 7 closed Ari's six support gaps; session 9 applied Ari's session 8 claim-level fixes). Rebuilding rewrites the four Batch 1 pages
with a fresh generated/verified timestamp, so run it only on purpose. Every quote is anchored by exact substring search in
the quote tool's normalized text; the span hash and review-payload hash come
from quote_tool itself. A substring that is absent or occurs more than once
stops the build. Pages are written status "draft" with a process verification
only; Skitch's signature is a separate step."""
import datetime as dt, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import quote_tool

REG = {s["source_id"]: s for s in json.load(open(ROOT / "sources/source-registry.dbp-first-proof.json"))["sources"]}
CAP = ROOT / "sources/captures/ecfr-2026-07-01"
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
DRIFT_CHECKED = "2026-11-02T07:10:07Z"   # sources/watch/drift-2026-10-28.json checked_at
STALE_AFTER = "2027-01-31"               # aligned with the two renewed pages
_texts = {}

def text(sec):
    if sec not in _texts:
        _texts[sec] = quote_tool.normalized_text(str(CAP / f"section-{sec}.xml"))
    return _texts[sec]

def src_id(sec):
    return "source.ecfr.2026-07-01." + sec.replace(".", "-")

def source_ref(sec):
    s = REG[src_id(sec)]
    return {"source_id": s["source_id"], "captured_sha256": s["captured_sha256"],
            "licensing_decision_payload_sha256": s["reproduction_decision"]["decision_payload_sha256"]}

def quote(page_id, name, sec, needle):
    t = text(sec)
    i = t.find(needle)
    if i < 0:
        sys.exit(f"NOT FOUND in {sec}: {needle[:80]!r}")
    if t.find(needle, i + 1) >= 0:
        sys.exit(f"AMBIGUOUS in {sec}: {needle[:80]!r}")
    return {"quote_id": f"quote.{page_id}.{name}", "source_id": src_id(sec),
            "captured_source_sha256": REG[src_id(sec)]["captured_sha256"],
            "anchor": {"selector_type": "text-position", "selector_version": "v0.1", "value": f"normalized:{i}-{i+len(needle)}"},
            "source_version": "eCFR point-in-time 2026-07-01", "normalization": "dw-quote-normalization/v0.1",
            "span_sha256": quote_tool.span_hash(needle), "verified_at": NOW}

def claim(page_id, name, kind, subject, operator, metric, value, quotes, applicability, conditions=(), exceptions=(), unit=None):
    c = {"claim_id": f"claim.{page_id}.{name}", "kind": kind, "subject": subject,
         "relation": {"operator": operator, "regulatory_metric": metric}, "value": value,
         "conditions": list(conditions), "exceptions": list(exceptions), "jurisdiction": "US-federal",
         "applicability": applicability, "supporting_quote_ids": [f"quote.{page_id}.{q}" for q in dict.fromkeys(quotes)]}
    if unit:
        c["unit"] = unit
    return c

def page(page_id, title, applicability, sections, quotes, claims):
    p = {"schema_version": "drinking-water-profile/v0.1", "type": "concept", "page_id": page_id, "title": title,
         "status": "draft", "assurance_profile": "drinking-water/v0.1", "use_class": "regulatory-reference",
         "jurisdiction": "US-federal", "applicability": applicability,
         "generated": {"by": "cc", "at": NOW},
         "review_payload": {"canonicalization": "dw-review-payload/v0.1", "sha256": "0" * 64},
         "normalization": "dw-quote-normalization/v0.1", "verified": [],
         "stale_after": STALE_AFTER,
         "source_watch": {"watch_id": f"watch.{page_id}", "last_result": "unchanged",
                          "last_checked_at": DRIFT_CHECKED, "next_due_at": "2026-12-02T07:10:07Z"},
         "source_refs": [source_ref(s) for s in sections], "quotes": quotes, "claims": claims}
    h = quote_tool.review_payload_hash(p)
    p["review_payload"]["sha256"] = h
    p["verified"] = [{"by": "process:quote-tool/v0.1-interim", "actor_type": "process", "at": NOW,
                      "review_payload_sha256": h, "scopes": ["source-capture", "quote-fidelity"]}]
    assert quote_tool.review_payload_hash(p) == h
    out = ROOT / "pages" / f"{page_id}.json"
    out.write_text(json.dumps(p, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}: {len(quotes)} quotes, {len(claims)} claims, review sha {h[:12]}")

# ---------- shared text ----------
LV = "Terms apply to public water systems subject to subparts L and V of 40 CFR part 141"
APP_LV = {"system_types": ["community-water-system", "nontransient-noncommunity-water-system"],
          "conditions": ["Subpart V applies to community and nontransient noncommunity water systems that use a primary or residual disinfectant other than ultraviolet light, or deliver water treated with one (141.620(b))"],
          "exclusions": ["Transient noncommunity water systems are reached by subpart L only for the chlorine dioxide MRDL (141.130(a)(2)); the TTHM and HAA5 MCL criteria are set for community and nontransient noncommunity systems (141.130(a)(1), 141.620(b))"]}
APP_OZONE = {"system_types": ["community-water-system", "nontransient-noncommunity-water-system"],
             "conditions": ["Community and nontransient noncommunity water systems using ozone for disinfection or oxidation (141.132(b)(3))"],
             "exclusions": ["Systems that do not use ozone are not required to monitor for bromate"]}
APP_CLO2 = {"system_types": ["community-water-system", "nontransient-noncommunity-water-system"],
            "conditions": ["Community and nontransient noncommunity water systems using chlorine dioxide for disinfection or oxidation (141.132(b)(2))"],
            "exclusions": ["Systems that do not use chlorine dioxide are not required to monitor for chlorite; transient noncommunity systems using chlorine dioxide are reached by subpart L for the chlorine dioxide MRDL in 141.65 (141.130(a)(2)), while chlorite monitoring applies to community and nontransient noncommunity systems (141.132(b)(2))"]}

# 141.64 spans (the two MCL tables for TTHM/HAA5 repeat verbatim, so each span carries its own lead-in)
S64_B2 = "Subpart V—LRAA compliance. (i) Compliance dates. The subpart V MCLs for TTHM and HAA5 must be complied with as a locational running annual average at each monitoring location beginning the date specified for subpart V compliance in § 141.620(c). Disinfection byproduct MCL (mg/L) Total trihalomethanes (TTHM) 0.080 Haloacetic acids (five) (HAA5) 0.060"
S64_B1 = "Subpart L—RAA compliance. (i) Compliance dates. Subpart H systems serving 10,000 or more persons must comply with this paragraph (b)(1) beginning January 1, 2002. Subpart H systems serving fewer than 10,000 persons and systems using only ground water not under the direct influence of surface water must comply with this paragraph (b)(1) beginning January 1, 2004. All systems must comply with these MCLs until the date specified for subpart V compliance in § 141.620(c). Disinfection byproduct MCL (mg/L) Total trihalomethanes (TTHM) 0.080 Haloacetic acids (five) (HAA5) 0.060"
S64_B2_BAT = "for all systems that disinfect their source water: Disinfection byproduct Best available technology Total trihalomethanes (TTHM) and Haloacetic acids (five) (HAA5) Enhanced coagulation or enhanced softening, plus GAC10; or nanofiltration with a molecular weight cutoff ≤1000 Daltons; or GAC20"
S64_B2_BAT_CONSEC = "for consecutive systems and applies only to the disinfected water that consecutive systems buy or otherwise receive: Disinfection byproduct Best available technology Total trihalomethanes (TTHM) and Haloacetic acids (five) (HAA5) Systems serving ≥10,000: Improved distribution system and storage tank management to reduce residence time, plus the use of chloramines for disinfectant residual maintenance Systems serving <10,000: Improved distribution system and storage tank management to reduce residence time"
S620_D1 = "To comply with subpart V MCLs in § 141.64(b)(2), you must calculate LRAAs for TTHM and HAA5 using monitoring results collected under this subpart and determine that each LRAA does not exceed the MCL. If you fail to complete four consecutive quarters of monitoring, you must calculate compliance with the MCL based on the average of the available data from the most recent four quarters. If you take more than one sample per quarter at a monitoring location, you must average all samples taken in the quarter at that location to determine a quarterly average to be used in the LRAA calculation."
S620_D2 = "To determine compliance with subpart V MCLs in § 141.64(b)(2), you must determine that each sample taken is less than the MCL. If any sample exceeds the MCL, you must comply with the requirements of § 141.625. If no sample exceeds the MCL, the sample result for each monitoring location is considered the LRAA for that monitoring location."
S620_C7 = "If you are required to conduct quarterly monitoring, you must make compliance calculations at the end of the fourth calendar quarter that follows the compliance date and at the end of each subsequent quarter (or earlier if the LRAA calculated based on fewer than four quarters of data would cause the MCL to be exceeded regardless of the monitoring results of subsequent quarters)."
S620_B = "(b) Applicability. You are subject to these requirements if your system is a community water system or a nontransient noncommunity water system that uses a primary or residual disinfectant other than ultraviolet light or delivers water that has been treated with a primary or residual disinfectant other than ultraviolet light."
S130_A12 = "(1) The regulations in this subpart establish criteria under which community water systems (CWSs) and nontransient, noncommunity water systems (NTNCWSs) which add a chemical disinfectant to the water in any part of the drinking water treatment process must modify their practices to meet MCLs and MRDLs in §§ 141.64 and 141.65, respectively, and must meet the treatment technique requirements for disinfection byproduct precursors in § 141.135. (2) The regulations in this subpart establish criteria under which transient NCWSs that use chlorine dioxide as a disinfectant or oxidant must modify their practices to meet the MRDL for chlorine dioxide in § 141.65."
S133_B1I = "(b) Disinfection byproducts—(1) TTHMs and HAA5. (i) For systems monitoring quarterly, compliance with MCLs in § 141.64 must be based on a running annual arithmetic average, computed quarterly, of quarterly arithmetic averages of all samples collected by the system as prescribed by § 141.132(b)(1)."
S133_B1II = "(ii) For systems monitoring less frequently than quarterly, systems demonstrate MCL compliance if the average of samples taken that year under the provisions of § 141.132(b)(1) does not exceed the MCLs in § 141.64. If the average of these samples exceeds the MCL, the system must increase monitoring to once per quarter per treatment plant and such a system is not in violation of the MCL until it has completed one year of quarterly monitoring, unless the result of fewer than four quarters of monitoring will cause the running annual average to exceed the MCL, in which case the system is in violation at the end of that quarter."
S64_A = "(a) Bromate and chlorite. The maximum contaminant levels (MCLs) for bromate and chlorite are as follows: Disinfection byproduct MCL (mg/L) Bromate 0.010 Chlorite 1.0"
S64_A1 = "Subpart H systems serving 10,000 or more persons must comply with this paragraph (a) beginning January 1, 2002. Subpart H systems serving fewer than 10,000 persons and systems using only ground water not under the direct influence of surface water must comply with this paragraph (a) beginning January 1, 2004."
S64_A2_BROMATE = "Bromate Control of ozone treatment process to reduce production of bromate"
S64_A2_CHLORITE = "Chlorite Control of treatment processes to reduce disinfectant demand and control of disinfection treatment processes to reduce disinfectant levels"

def mcl_lraa_page(page_id, analyte, long_name, value, value_text):
    other = "HAA5" if analyte == "TTHM" else "TTHM"
    qs = [quote(page_id, "mcl-subpart-v", "141.64", S64_B2),
          quote(page_id, "mcl-subpart-l", "141.64", S64_B1),
          quote(page_id, "bat-subpart-v", "141.64", S64_B2_BAT),
          quote(page_id, "bat-subpart-v-consecutive", "141.64", S64_B2_BAT_CONSEC),
          quote(page_id, "lraa-quarterly", "141.620", S620_D1),
          quote(page_id, "lraa-less-than-quarterly", "141.620", S620_D2),
          quote(page_id, "first-compliance-calculation", "141.620", S620_C7),
          quote(page_id, "applicability", "141.620", S620_B),
          quote(page_id, "subpart-l-scope", "141.130", S130_A12),
          quote(page_id, "raa-subpart-l", "141.133", S133_B1I),
          quote(page_id, "raa-subpart-l-less-than-quarterly", "141.133", S133_B1II)]
    SHARED = ["applicability", "subpart-l-scope"]   # 141.620(b) scope and 141.130(a) scope, explicit on every claim (Ari session 8)
    cond_table = [f"The 141.64(b) MCL table lists {long_name} ({analyte}) at {value_text} mg/L and the other Stage 2 byproduct group ({other}) beside it; this claim covers {analyte} only",
                  "The same value applies under subpart L (running annual average, 141.64(b)(1)) until the system's subpart V compliance date in 141.620(c), and under subpart V (locational running annual average at each monitoring location, 141.64(b)(2)) from that date"]
    cs = [claim(page_id, "mcl", "numeric", f"Maximum contaminant level for {long_name} ({analyte})", "eq", "mcl", value, ["mcl-subpart-v", "mcl-subpart-l"] + SHARED, APP_LV, cond_table, unit="mg/L"),
          claim(page_id, "compliance-basis-lraa", "qualitative", f"Compliance basis for the {analyte} MCL under subpart V", "eq", "other",
                "Locational running annual average (LRAA) at each monitoring location, beginning the date specified for subpart V compliance in 141.620(c)", ["mcl-subpart-v", "mcl-subpart-l", "raa-subpart-l"] + SHARED, APP_LV,
                ["Before the subpart V compliance date the MCL is met under subpart L (141.64(b)(1)); for systems monitoring quarterly that is a running annual arithmetic average, computed quarterly, of quarterly arithmetic averages of all samples collected by the system (system-wide) (141.133(b)(1)(i))"]),
          claim(page_id, "compliance-basis-raa-subpart-l", "qualitative", f"Compliance basis for the {analyte} MCL under subpart L", "eq", "other",
                "Running annual arithmetic average (RAA), computed quarterly, of quarterly arithmetic averages of all samples collected by the system (system-wide), required until the date specified for subpart V compliance in 141.620(c)", ["mcl-subpart-l", "raa-subpart-l", "raa-subpart-l-less-than-quarterly"] + SHARED, APP_LV,
                ["The quoted 141.133(b)(1)(i) basis is for systems monitoring quarterly; systems monitoring less frequently than quarterly demonstrate compliance if the average of that year's samples does not exceed the MCL, and an exceedance moves them to quarterly monitoring per treatment plant (141.133(b)(1)(ii))",
                 "Subpart L compliance dates: subpart H systems serving 10,000 or more persons from January 1, 2002; subpart H systems serving fewer than 10,000 and ground water systems not under the direct influence of surface water from January 1, 2004"]),
          claim(page_id, "lraa-computation-quarterly", "qualitative", f"LRAA computation for {analyte} by systems monitoring quarterly", "required", "other",
                "Calculate the LRAA from monitoring results collected under subpart V and determine that each LRAA does not exceed the MCL; more than one sample in a quarter at a location is averaged into one quarterly value; if four consecutive quarters are not completed, compliance is based on the average of the available data from the most recent four quarters", ["lraa-quarterly"] + SHARED, APP_LV),
          claim(page_id, "lraa-less-than-quarterly", "qualitative", f"LRAA determination for {analyte} by systems monitoring yearly or less frequently", "required", "other",
                "Each sample must be less than the MCL; a sample that exceeds the MCL triggers the increased-monitoring requirements of 141.625; when no sample exceeds the MCL, each location's sample result is its LRAA", ["lraa-less-than-quarterly"] + SHARED, APP_LV,
                ["Equality edge flagged, not resolved: the quote requires each sample to be less than the MCL but uses 'exceeds' for the 141.625 trigger, so a sample exactly equal to the MCL is not classified by this page"]),
          claim(page_id, "first-compliance-calculation", "qualitative", f"Timing of the first {analyte} LRAA compliance calculation for quarterly monitors", "required", "other",
                "At the end of the fourth calendar quarter following the compliance date and at the end of each subsequent quarter, or earlier if an LRAA from fewer than four quarters would exceed the MCL regardless of later results", ["first-compliance-calculation"] + SHARED, APP_LV),
          claim(page_id, "bat-subpart-v", "qualitative", f"Best available technology for the {analyte} MCL under subpart V (systems that disinfect their source water)", "eq", "other",
                "Enhanced coagulation or enhanced softening, plus GAC10; or nanofiltration with a molecular weight cutoff of 1000 Daltons or less; or GAC20", ["bat-subpart-v"] + SHARED, APP_LV,
                [f"Consecutive systems have a separate BAT for the disinfected water they buy or receive; see claim.{page_id}.bat-subpart-v-consecutive on this page"]),
          claim(page_id, "bat-subpart-v-consecutive", "qualitative", f"Best available technology for the {analyte} MCL under subpart V (consecutive systems, disinfected water bought or received)", "eq", "other",
                "Improved distribution system and storage tank management to reduce residence time; systems serving 10,000 or more also use chloramines for disinfectant residual maintenance", ["bat-subpart-v-consecutive"] + SHARED, APP_LV,
                ["Applies only to the disinfected water that consecutive systems buy or otherwise receive (141.64(b)(2)(iii))"])]
    page(page_id, f"{analyte} maximum contaminant level: {value_text} mg/L as a locational running annual average", APP_LV, ["141.64", "141.620", "141.130", "141.133"], qs, cs)

mcl_lraa_page("dbp.mcl.tthm", "TTHM", "total trihalomethanes", 0.080, "0.080")
mcl_lraa_page("dbp.mcl.haa5", "HAA5", "haloacetic acids (five)", 0.060, "0.060")

# ---------- bromate ----------
pid = "dbp.mcl.bromate"
B_ROUTINE = "Community and nontransient noncommunity systems using ozone, for disinfection or oxidation, must take one sample per month for each treatment plant in the system using ozone. Systems must take samples monthly at the entrance to the distribution system while the ozonation system is operating under normal conditions."
B_REDUCED_HIST = "(A) Until March 31, 2009, systems required to analyze for bromate may reduce monitoring from monthly to quarterly, if the system's average source water bromide concentration is less than 0.05 mg/L based on representative monthly bromide measurements for one year. The system may remain on reduced bromate monitoring until the running annual average source water bromide concentration, computed quarterly, is equal to or greater than 0.05 mg/L based on representative monthly measurements. If the running annual average source water bromide concentration is ≥0.05 mg/L, the system must resume routine monitoring required by paragraph (b)(3)(i) of this section in the following month."
B_REDUCED = "Beginning April 1, 2009, systems may no longer use the provisions of paragraph (b)(3)(ii)(A) of this section to qualify for reduced monitoring. A system required to analyze for bromate may reduce monitoring from monthly to quarterly, if the system's running annual average bromate concentration is ≤0.0025 mg/L based on monthly bromate measurements under paragraph (b)(3)(i) of this section for the most recent four quarters, with samples analyzed using Method 317.0 Revision 2.0, 326.0 or 321.8."
B_RESUME = "If the running annual average bromate concentration is >0.0025 mg/L, the system must resume routine monitoring required by paragraph (b)(3)(i) of this section."
B_COMPLIANCE = "(2) Bromate. Compliance must be based on a running annual arithmetic average, computed quarterly, of monthly samples (or, for months in which the system takes more than one sample, the average f all samples taken during the month) collected by the system as prescribed by § 141.132(b)(3). If the average of samples covering any consecutive four-quarter period exceeds the MCL, the system is in violation of the MCL and must notify the public pursuant to subpart Q, in addition to reporting to the State pursuant to § 141.134. If a PWS fails to complete 12 consecutive months' monitoring, compliance with the MCL for the last four-quarter compliance period must be based on an average of the available data."
qs = [quote(pid, "mcl-table", "141.64", S64_A), quote(pid, "compliance-dates", "141.64", S64_A1), quote(pid, "bat", "141.64", S64_A2_BROMATE),
      quote(pid, "routine-monitoring", "141.132", B_ROUTINE), quote(pid, "reduced-monitoring", "141.132", B_REDUCED), quote(pid, "resume-routine", "141.132", B_RESUME), quote(pid, "reduced-monitoring-historical", "141.132", B_REDUCED_HIST),
      quote(pid, "compliance", "141.133", B_COMPLIANCE)]
SHARED = ["routine-monitoring"]   # 141.132(b)(3)(i): ozone-system scope, explicit on every claim (Ari session 9)
cs = [claim(pid, "mcl", "numeric", "Maximum contaminant level for bromate", "eq", "mcl", 0.010, ["mcl-table"] + SHARED, APP_OZONE,
            ["The 141.64(a) table lists bromate (0.010 mg/L) and chlorite (1.0 mg/L) together; this claim covers bromate only"], unit="mg/L"),
      claim(pid, "applies-to-ozone-systems", "qualitative", "Systems subject to bromate monitoring", "required", "monitoring-trigger",
            "Community and nontransient noncommunity water systems using ozone for disinfection or oxidation", ["routine-monitoring"] + SHARED, APP_OZONE),
      claim(pid, "routine-monitoring", "qualitative", "Routine bromate monitoring", "required", "monitoring-trigger",
            "One sample per month for each treatment plant using ozone, taken at the entrance to the distribution system while the ozonation system is operating under normal conditions", ["routine-monitoring"] + SHARED, APP_OZONE),
      claim(pid, "compliance-basis-raa", "qualitative", "Compliance basis for the bromate MCL", "eq", "other",
            "Running annual arithmetic average, computed quarterly, of monthly samples taken at the entrance to the distribution system (months with more than one sample use the monthly average)", ["compliance", "routine-monitoring"] + SHARED, APP_OZONE,
            ["If a system fails to complete 12 consecutive months of monitoring, compliance for the last four-quarter period is based on an average of the available data",
             "The captured eCFR text reads 'the average f all samples' (sic); the quote reproduces the capture exactly"]),
      claim(pid, "violation", "qualitative", "Bromate MCL violation", "eq", "other",
            "The running annual average covering any consecutive four-quarter period exceeds the MCL; the system must notify the public under subpart Q and report to the State under 141.134", ["compliance"] + SHARED, APP_OZONE),
      claim(pid, "reduced-monitoring-threshold", "numeric", "Bromate running annual average threshold for reduced (quarterly) monitoring", "lte", "monitoring-trigger", 0.0025, ["reduced-monitoring", "resume-routine", "reduced-monitoring-historical"] + SHARED, APP_OZONE,
            ["From April 1, 2009: based on monthly bromate measurements for the most recent four quarters, analyzed by Method 317.0 Revision 2.0, 326.0 or 321.8",
             "If the running annual average bromate concentration exceeds 0.0025 mg/L, routine monthly monitoring must resume",
             "Until March 31, 2009, reduced monitoring could instead be based on source water bromide (average below 0.05 mg/L from representative monthly measurements for one year, 141.132(b)(3)(ii)(A)); that route is closed from April 1, 2009"], unit="mg/L"),
      claim(pid, "compliance-dates", "qualitative", "Compliance dates for the bromate MCL", "required", "other",
            "Subpart H systems serving 10,000 or more persons from January 1, 2002; subpart H systems serving fewer than 10,000 persons and systems using only ground water not under the direct influence of surface water from January 1, 2004", ["compliance-dates"] + SHARED, APP_OZONE),
      claim(pid, "bat", "qualitative", "Best available technology for the bromate MCL", "eq", "other",
            "Control of the ozone treatment process to reduce production of bromate", ["bat"] + SHARED, APP_OZONE)]
page(pid, "Bromate maximum contaminant level: 0.010 mg/L for systems using ozone, running annual average", APP_OZONE, ["141.64", "141.132", "141.133"], qs, cs)

# ---------- chlorite ----------
pid = "dbp.mcl.chlorite"
C_SCOPE_DAILY = "(2) Chlorite. Community and nontransient noncommunity water systems using chlorine dioxide, for disinfection or oxidation, must conduct monitoring for chlorite. (i) Routine monitoring—(A) Daily monitoring. Systems must take daily samples at the entrance to the distribution system. For any daily sample that exceeds the chlorite MCL, the system must take additional samples in the distribution system the following day at the locations required by paragraph (b)(2)(ii) of this section, in addition to the sample required at the entrance to the distribution system."
C_MONTHLY = "(B) Monthly monitoring. Systems must take a three-sample set each month in the distribution system. The system must take one sample at each of the following locations: near the first customer, at a location representative of average residence time, and at a location reflecting maximum residence time in the distribution system. Any additional routine sampling must be conducted in the same manner (as three-sample sets, at the specified locations)."
C_ADDITIONAL = "(ii) Additional monitoring. On each day following a routine sample monitoring result that exceeds the chlorite MCL at the entrance to the distribution system, the system is required to take three chlorite distribution system samples at the following locations: as close to the first customer as possible, in a location representative of average residence time, and as close to the end of the distribution system as possible (reflecting maximum residence time in the distribution system)."
C_REDUCED = "(iii) Reduced monitoring. (A) Chlorite monitoring at the entrance to the distribution system required by paragraph (b)(2)(i)(A) of this section may not be reduced. (B) Chlorite monitoring in the distribution system required by paragraph (b)(2)(i)(B) of this section may be reduced to one three-sample set per quarter after one year of monitoring where no individual chlorite sample taken in the distribution system under paragraph (b)(2)(i)(B) of this section has exceeded the chlorite MCL and the system has not been required to conduct monitoring under paragraph (b)(2)(ii) of this section. The system may remain on the reduced monitoring schedule until either any of the three individual chlorite samples taken quarterly in the distribution system under paragraph (b)(2)(i)(B) of this section exceeds the chlorite MCL or the system is required to conduct monitoring under paragraph (b)(2)(ii) of this section, at which time the system must revert to routine monitoring."
C_COMPLIANCE = "(3) Chlorite. Compliance must be based on an arithmetic average of each three sample set taken in the distribution system as prescribed by § 141.132(b)(2)(i)(B) and § 141.132(b)(2)(ii). If the arithmetic average of any three sample set exceeds the MCL, the system is in violation of the MCL and must notify the public pursuant to subpart Q, in addition to reporting to the State pursuant to § 141.134."
qs = [quote(pid, "mcl-table", "141.64", S64_A), quote(pid, "compliance-dates", "141.64", S64_A1), quote(pid, "bat", "141.64", S64_A2_CHLORITE),
      quote(pid, "scope-and-daily-monitoring", "141.132", C_SCOPE_DAILY), quote(pid, "monthly-three-sample-set", "141.132", C_MONTHLY),
      quote(pid, "additional-monitoring", "141.132", C_ADDITIONAL), quote(pid, "reduced-monitoring", "141.132", C_REDUCED),
      quote(pid, "compliance", "141.133", C_COMPLIANCE), quote(pid, "subpart-l-scope", "141.130", S130_A12)]
SHARED = ["scope-and-daily-monitoring", "subpart-l-scope"]   # 141.132(b)(2) chlorine-dioxide-system scope (Ari session 9) and 141.130(a)(1)-(2): CWS/NTNCWS meet the MCLs; transient NCWSs using chlorine dioxide meet the 141.65 MRDL (Ari session 8)
cs = [claim(pid, "mcl", "numeric", "Maximum contaminant level for chlorite", "eq", "mcl", 1.0, ["mcl-table"] + SHARED, APP_CLO2,
            ["The 141.64(a) table lists bromate (0.010 mg/L) and chlorite (1.0 mg/L) together; this claim covers chlorite only",
             "The MCLG for chlorite is a separate value recorded on page dbp.mclg (claim.dbp.mclg.chlorite); it is not asserted here"], unit="mg/L"),
      claim(pid, "applies-to-chlorine-dioxide-systems", "qualitative", "Systems subject to chlorite monitoring", "required", "monitoring-trigger",
            "Community and nontransient noncommunity water systems using chlorine dioxide for disinfection or oxidation", ["scope-and-daily-monitoring"] + SHARED, APP_CLO2),
      claim(pid, "daily-entrance-monitoring", "qualitative", "Routine daily chlorite monitoring", "required", "monitoring-trigger",
            "Daily samples at the entrance to the distribution system; any daily sample exceeding the chlorite MCL requires additional distribution system samples the following day", ["scope-and-daily-monitoring"] + SHARED, APP_CLO2),
      claim(pid, "monthly-three-sample-set", "qualitative", "Routine monthly chlorite monitoring", "required", "monitoring-trigger",
            "A three-sample set each month in the distribution system: one sample near the first customer, one at a location representative of average residence time, one at a location reflecting maximum residence time; any additional routine sampling is conducted in the same manner, as three-sample sets at those locations", ["monthly-three-sample-set"] + SHARED, APP_CLO2,
            ["The term three-sample set is also recorded on page dbp.definitions (claim.dbp.definitions.chlorite-three-sample-set)"]),
      claim(pid, "additional-monitoring-after-exceedance", "qualitative", "Additional chlorite monitoring after an entrance exceedance", "required", "monitoring-trigger",
            "On each day following a routine entrance sample that exceeds the chlorite MCL, three distribution system samples: as close to the first customer as possible, at average residence time, and as close to the end of the distribution system as possible", ["additional-monitoring"] + SHARED, APP_CLO2),
      claim(pid, "reduced-monitoring", "qualitative", "Reduced chlorite monitoring", "eq", "monitoring-trigger",
            "Entrance monitoring may not be reduced; distribution system monitoring may be reduced to one three-sample set per quarter after one year of monitoring in which no individual routine distribution system sample taken under 141.132(b)(2)(i)(B) exceeded the chlorite MCL and the system was not required to conduct additional monitoring under 141.132(b)(2)(ii)", ["reduced-monitoring"] + SHARED, APP_CLO2,
            ["The system must revert to routine monitoring if any of the three quarterly distribution system samples exceeds the MCL or additional monitoring is triggered (141.132(b)(2)(iii)(B), second sentence)"]),
      claim(pid, "compliance-basis-three-sample-average", "qualitative", "Compliance basis for the chlorite MCL", "eq", "other",
            "Arithmetic average of each three-sample set taken in the distribution system, whether routine monthly sets or triggered additional sets", ["compliance"] + SHARED, APP_CLO2),
      claim(pid, "violation", "qualitative", "Chlorite MCL violation", "eq", "other",
            "The arithmetic average of any three-sample set exceeds the MCL; the system must notify the public under subpart Q and report to the State under 141.134", ["compliance", "scope-and-daily-monitoring"] + SHARED, APP_CLO2,
            ["A single daily entrance sample above the MCL triggers additional monitoring the following day (141.132(b)(2)(i)(A)); it is not by itself an MCL violation"]),
      claim(pid, "compliance-dates", "qualitative", "Compliance dates for the chlorite MCL", "required", "other",
            "Subpart H systems serving 10,000 or more persons from January 1, 2002; subpart H systems serving fewer than 10,000 persons and systems using only ground water not under the direct influence of surface water from January 1, 2004", ["compliance-dates"] + SHARED, APP_CLO2),
      claim(pid, "bat", "qualitative", "Best available technology for the chlorite MCL", "eq", "other",
            "Control of treatment processes to reduce disinfectant demand and control of disinfection treatment processes to reduce disinfectant levels", ["bat"] + SHARED, APP_CLO2)]
page(pid, "Chlorite maximum contaminant level: 1.0 mg/L for systems using chlorine dioxide, three-sample set average", APP_CLO2, ["141.64", "141.132", "141.133", "141.130"], qs, cs)
