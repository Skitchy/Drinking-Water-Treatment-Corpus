"""THE ADAPTER/ENGINE BOUNDARY (Pass 2 brief section 7a; maintainer goal
ruling 2026-08-26: the tool that ingests any subject matter is the product).

Source adapters in front, one subject-agnostic engine behind. This module is
the whole interface. An adapter hands the engine exactly three kinds of
object; the engine promises back the same outputs for any source.

WHAT AN ADAPTER HANDS THE ENGINE
--------------------------------
1. SourceUnit  - one reviewable unit of source (a regulation section, a
   manual chapter, a document page). Carries the source bytes' identity, a
   canonical representation the engine can index by selector, and the
   anchor rules for that source type, including its custody chain.
2. Candidate   - one claim-and-evidence candidate bound to one unit: the
   claim payload (fixed shape below) and evidence entries, each an exact
   quote plus a support anchor into the unit's canonical representation.
3. UnitAmbiguities - the declared ambiguities for a unit (review inputs,
   never release objects; brief 1a).

WHAT THE ENGINE PROMISES BACK (any source)
------------------------------------------
Canonical claim-and-evidence records (Ari's canonicalization, engine/records.py),
verification records, the review universe and shards, the partition, the
release report and release-manifest digest. Nothing here names a source type.

THE CUSTODY CHAIN
-----------------
Every support anchor binds a quote to bytes through a chain of custody
links. For a captured text source the chain is one link: the capture bytes.
The contract leaves room, on purpose, for the PDF adapter's known constraint
(brief 7a): a scanned page has no text bytes, so its chain is two links, an
OCR-layer digest derived from a page-image digest, stated as such. The
engine carries the chain; it never interprets it. Pass 2 exercises the
one-link case only (Ari scope guard: minimum interface, no PDF/Word work).

The engine MUST NOT import or name anything specific to a source type. The
boundary test (tests/test_boundary.py) enforces this structurally.
"""

ADAPTER_CONTRACT_VERSION = "foundry-adapter-contract/experimental-v0.1"

# Claim payload: fixed shape, identical to the reviewer output schema's
# claimPayload so a record's payload digest means the same thing to the
# builder, both reviewers, and the grader.
CLAIM_PAYLOAD_FIELDS = (
    "kind", "subject", "relation", "value", "unit",
    "conditions", "applicability", "effective_time", "dependencies",
)
CLAIM_KINDS = ("numeric", "qualitative", "table-cell")

# Support anchor: representation-bound. The selector addresses one node of
# the unit's canonical representation; char offsets index that node's
# normalized text; span_sha256 is sha256 of the exact quote bytes (UTF-8).
SUPPORT_ANCHOR_FIELDS = (
    "capture_sha256", "selector", "char_start", "char_end",
    "span_sha256", "logical_anchor",
)

# Custody link kinds the contract recognizes. Pass 2 uses the first only.
CUSTODY_LINK_KINDS = (
    "capture-bytes",      # anchor binds directly to captured source bytes
    "ocr-layer",          # reserved: text layer derived from a page image
    "page-image",         # reserved: the image bytes an OCR layer came from
)


class ContractError(Exception):
    """An adapter object violates the boundary. Fail closed."""


def _require(condition, message):
    if not condition:
        raise ContractError(message)


def validate_source_unit(unit):
    """A SourceUnit is a plain dict:

    unit_id            str   stable identifier within the adapter (opaque to the engine)
    source_kind        str   adapter's declared source type, informational
    capture_path       str   repo-relative path of the captured source bytes
    capture_sha256     str   sha256 of those bytes (root of custody)
    canonical_sha256   str   digest of the canonical representation
    representation     dict  tree of nodes; every node has "selector" and
                             optionally "text" and "children"
    anchor_rules       dict  selector_scheme: str (human-readable rule id)
                             text_profile:    str (normalization rule id)
                             custody:         list of links, root first;
                                              each {kind, digest_field}
    """
    _require(isinstance(unit, dict), "unit must be a dict")
    for key in ("unit_id", "source_kind", "capture_path", "capture_sha256",
                "canonical_sha256", "representation", "anchor_rules"):
        _require(key in unit, f"unit missing {key}")
    rules = unit["anchor_rules"]
    for key in ("selector_scheme", "text_profile", "custody"):
        _require(key in rules, f"anchor_rules missing {key}")
    _require(isinstance(rules["custody"], list) and rules["custody"],
             "custody chain must be a non-empty list")
    for link in rules["custody"]:
        _require(link.get("kind") in CUSTODY_LINK_KINDS,
                 f"unknown custody link kind: {link.get('kind')}")
        _require(link.get("digest_field") in unit,
                 f"custody link digest_field not on unit: {link}")
    _require("selector" in unit["representation"],
             "representation root must carry a selector")
    return True


def validate_claim_payload(payload):
    _require(isinstance(payload, dict), "payload must be a dict")
    _require(tuple(sorted(payload)) == tuple(sorted(CLAIM_PAYLOAD_FIELDS)),
             f"payload fields must be exactly {CLAIM_PAYLOAD_FIELDS}")
    _require(payload["kind"] in CLAIM_KINDS, f"bad kind {payload['kind']}")
    _require(isinstance(payload["subject"], str) and payload["subject"],
             "subject must be a non-empty string")
    _require(isinstance(payload["relation"], str) and payload["relation"],
             "relation must be a non-empty string")
    _require(isinstance(payload["value"], (str, int, float, bool)),
             "value must be string, number, or boolean")
    _require(payload["unit"] is None or isinstance(payload["unit"], str),
             "unit must be string or null")
    for key in ("conditions", "applicability", "dependencies"):
        _require(isinstance(payload[key], list) and
                 all(isinstance(v, str) for v in payload[key]),
                 f"{key} must be a list of strings")
    _require(payload["effective_time"] is None or
             isinstance(payload["effective_time"], dict),
             "effective_time must be object or null")
    return True


def validate_support_anchor(anchor):
    _require(isinstance(anchor, dict), "anchor must be a dict")
    _require(tuple(sorted(anchor)) == tuple(sorted(SUPPORT_ANCHOR_FIELDS)),
             f"anchor fields must be exactly {SUPPORT_ANCHOR_FIELDS}")
    _require(isinstance(anchor["char_start"], int) and
             isinstance(anchor["char_end"], int) and
             0 <= anchor["char_start"] <= anchor["char_end"],
             "anchor offsets must be ints with start <= end")
    _require(anchor["logical_anchor"] is None or
             isinstance(anchor["logical_anchor"], str),
             "logical_anchor must be string or null")
    return True


def validate_candidate(candidate):
    """A Candidate is a plain dict:

    unit_id        str
    candidate_id   str    adapter-local id, informational (never digested)
    claim_payload  dict   validate_claim_payload
    evidence       list   [{exact_text: str, support_anchor: anchor}], >= 1
    """
    _require(isinstance(candidate, dict), "candidate must be a dict")
    for key in ("unit_id", "candidate_id", "claim_payload", "evidence"):
        _require(key in candidate, f"candidate missing {key}")
    validate_claim_payload(candidate["claim_payload"])
    _require(isinstance(candidate["evidence"], list) and candidate["evidence"],
             "evidence must be a non-empty list")
    for entry in candidate["evidence"]:
        _require(isinstance(entry.get("exact_text"), str) and
                 entry["exact_text"], "evidence needs exact_text")
        validate_support_anchor(entry["support_anchor"])
    return True


class SourceAdapter:
    """The minimum interface an adapter implements. Pure data access; an
    adapter never sees engine outputs and never reviews anything."""

    contract_version = ADAPTER_CONTRACT_VERSION
    source_kind = "unspecified"

    def unit_ids(self):
        """Sorted list of unit ids in this source."""
        raise NotImplementedError

    def unit(self, unit_id):
        """SourceUnit dict for one id (validate_source_unit)."""
        raise NotImplementedError

    def candidates(self, unit_id):
        """List of Candidate dicts for one unit, adapter order."""
        raise NotImplementedError

    def ambiguities(self, unit_id):
        """List of declared ambiguity strings for one unit."""
        raise NotImplementedError

    def fixed_input_identity(self):
        """Dict describing the fixed inputs this adapter reads (paths and
        digests), for the run record. Never consulted by the engine's
        logic; recorded only."""
        raise NotImplementedError
