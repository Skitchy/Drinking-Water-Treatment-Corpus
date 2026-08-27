"""Stage 5: class-1 deterministic reviewer projection with the WIP-5 cap.

The projection is a pure function of the verified-candidate record; running
it twice yields byte-identical packets. WIP equals packets emitted but not
dispositioned (a disposition file present under out/dispositions/); emission
refuses to push WIP past five. Batch approval does not exist.

Usage: python3 project_reviewer.py [max_to_emit]
"""

import json
import os
import sys

COMPILER_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENT_DIR = os.path.dirname(COMPILER_DIR)
OUT_DIR = os.path.join(EXPERIMENT_DIR, "out")
WIP_CAP = 5


def project(section_number):
    verified = json.load(open(os.path.join(
        OUT_DIR, "verified", f"verified-{section_number}.json")))
    lines = []
    lines.append(f"# Reviewer packet: candidate material for "
                 f"section {section_number}")
    lines.append("")
    lines.append("Quarantined experimental output. Disposition each block "
                 "as accept / correct / reject. Nothing here has standing "
                 "without your disposition.")
    lines.append("")
    counts = verified["counts"]
    lines.append(f"Machine verification: {counts['quotes_verified']} quotes "
                 f"verified, {counts['quotes_rejected']} rejected; "
                 f"{counts['claims_verified']} claims verified, "
                 f"{counts['claims_rejected']} rejected; "
                 f"{counts['questions_kept']} questions kept.")
    lines.append("")
    lines.append("## Page proposals")
    for proposal in verified["page_proposals"]:
        lines.append(f"- [{proposal.get('shape_verdict')}] "
                     f"`{proposal.get('candidate_page_id')}`: "
                     f"{proposal.get('topic')}")
        cites = ", ".join(proposal.get("citations", []))
        if cites:
            lines.append(f"  - citations: {cites}")
    lines.append("")
    lines.append("## Verified quotes (binding recomputed from canonical "
                 "bytes)")
    for quote in verified["verified_quotes"]:
        anchor = quote.get("logical_anchor") or "no derived anchor"
        lines.append(f"- `{quote['id']}` [{anchor}] "
                     f"{quote['binding']['selector']}")
        lines.append(f"  > {quote['exact_text']}")
    lines.append("")
    lines.append("## Verified claims")
    for claim in verified["verified_claims"]:
        unit = claim.get("unit") or ""
        conditions = "; ".join(claim.get("conditions", []))
        lines.append(f"- `{claim['candidate_claim_id']}` "
                     f"[{claim['kind']}] {claim['subject']} "
                     f"{claim['relation']} {claim['value']} {unit}".rstrip())
        if conditions:
            lines.append(f"  - conditions: {conditions}")
        lines.append(f"  - support: "
                     f"{', '.join(claim['supporting_quotes'])}")
    if verified["rejected_claims"] or verified["rejected_quotes"]:
        lines.append("")
        lines.append("## Machine-rejected material (for your awareness, "
                     "not for rescue)")
        for rejected in verified["rejected_quotes"]:
            lines.append(f"- quote `{rejected['id']}`: {rejected['reason']}")
        for rejected in verified["rejected_claims"]:
            lines.append(f"- claim `{rejected['id']}`: "
                         f"{', '.join(rejected['reasons'])}")
    lines.append("")
    lines.append("## Candidate challenge questions")
    for question in verified["challenge_questions"]:
        lines.append(f"- Q: {question.get('question')}")
        lines.append(f"  A: {question.get('expected_answer')}")
    if verified["ambiguities_declared"]:
        lines.append("")
        lines.append("## Ambiguities declared by the extraction role")
        for ambiguity in verified["ambiguities_declared"]:
            lines.append(f"- {ambiguity}")
    lines.append("")
    lines.append("## Disposition")
    lines.append("")
    lines.append("- [ ] accept as candidate page material")
    lines.append("- [ ] accept with corrections (list below)")
    lines.append("- [ ] reject (reason below)")
    lines.append("")
    lines.append(f"Source verification record: "
                 f"`out/verified/verified-{section_number}.json` "
                 f"(candidate response digest "
                 f"`{verified['candidate_response_sha256'][:16]}...`)")
    lines.append("")
    return "\n".join(lines)


def current_wip():
    packets_dir = os.path.join(OUT_DIR, "packets")
    dispositions_dir = os.path.join(OUT_DIR, "dispositions")
    emitted = set()
    if os.path.isdir(packets_dir):
        emitted = {name.replace("packet-", "").replace(".md", "")
                   for name in os.listdir(packets_dir)
                   if name.startswith("packet-")}
    dispositioned = set()
    if os.path.isdir(dispositions_dir):
        dispositioned = {
            name.replace("disposition-", "").split(".")[0]
            for name in os.listdir(dispositions_dir)
            if name.startswith("disposition-")}
    return emitted - dispositioned, emitted


def main():
    max_to_emit = int(sys.argv[1]) if len(sys.argv) > 1 else WIP_CAP
    wip, emitted = current_wip()
    budget = WIP_CAP - len(wip)
    if budget <= 0:
        print(f"WIP cap reached ({len(wip)}/{WIP_CAP} undispositioned: "
              f"{sorted(wip)}). Production paused; no batch approval "
              f"exists.")
        return
    verified_dir = os.path.join(OUT_DIR, "verified")
    ready = sorted(
        name.replace("verified-", "").replace(".json", "")
        for name in os.listdir(verified_dir)
        if name.startswith("verified-")) if os.path.isdir(verified_dir) \
        else []
    to_emit = [s for s in ready if s not in emitted][
        :min(budget, max_to_emit)]
    packets_dir = os.path.join(OUT_DIR, "packets")
    os.makedirs(packets_dir, exist_ok=True)
    for section_number in to_emit:
        packet = project(section_number)
        path = os.path.join(packets_dir, f"packet-{section_number}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(packet)
        print(f"emitted packet-{section_number}.md "
              f"(WIP now {len(wip) + len(to_emit[:to_emit.index(section_number) + 1])}/{WIP_CAP})")
    if not to_emit:
        print("nothing ready to emit within the WIP budget")


if __name__ == "__main__":
    main()
