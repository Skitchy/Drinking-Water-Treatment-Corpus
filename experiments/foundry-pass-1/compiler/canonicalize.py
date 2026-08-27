"""Stages 1 and 2: captured eCFR XML to canonical normalized representation
with dual anchors.

The representation-bound selector is the sole authoritative binding. The
logical citation anchor is derived metadata; any derivation ambiguity is
recorded as a review item, never guessed (brief section 8).
"""

import re
import xml.etree.ElementTree as ET

from foundry_lib import content_digest, file_sha256, normalize_text

STRUCTURAL_TAGS = {"DIV", "THEAD", "TBODY"}
DESIGNATOR_RE = re.compile(r"^\s*(\((?:[a-z]{1,4}|[A-Z]{1,4}|\d{1,3})\))+")
SINGLE_DESIGNATOR_RE = re.compile(r"\(([^()]+)\)")

LOWER_ROMAN = re.compile(r"^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)$")
UPPER_ROMAN = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)$")


def _classify(designator):
    """Classify one designator token into candidate CFR hierarchy levels.

    CFR order: (a) lower-alpha, (1) numeric, (i) lower-roman, (A) upper-alpha,
    (1) numeric-2, (i) upper-roman... Tokens like 'i' or 'v' are ambiguous
    between lower-alpha and lower-roman; both candidates are returned and the
    stack context decides, or a review item results.
    """
    candidates = []
    if re.fullmatch(r"\d{1,3}", designator):
        candidates.append("numeric")
    if re.fullmatch(r"[a-z]{1,4}", designator):
        if LOWER_ROMAN.fullmatch(designator):
            candidates.append("lower-roman")
        if re.fullmatch(r"[a-z]{1,2}", designator):
            candidates.append("lower-alpha")
    if re.fullmatch(r"[A-Z]{1,4}", designator):
        if UPPER_ROMAN.fullmatch(designator):
            candidates.append("upper-roman")
        if re.fullmatch(r"[A-Z]{1,2}", designator):
            candidates.append("upper-alpha")
    return candidates


def _element_text(element):
    """All text of an element, entity-resolved by the parser, in document
    order, before normalization."""
    return "".join(element.itertext())


CONTINUATION_RE = re.compile(r"—\s*(\((?:[a-zA-Z]{1,4}|\d{1,3})\))+")
PERIOD_CONTINUATION_RE = re.compile(
    r"[^.—?]{0,120}[.?]\s+((?:\((?:[a-zA-Z]{1,4}|\d{1,3})\))+)")


def _continuation_designators(text, start):
    """eCFR inline continuations: a heading followed by an em dash or by a
    period, then the next designator chain opens in the same paragraph:
    '(a) Routine monitoring—(1) ...' or '(a) Applicability. (1) ...'.
    The period form is only honored for the first sentence after the leading
    chain, and the character class excludes periods inside that sentence, so
    cross-references like 'section 141.131(d)(3)' can never introduce one.
    Designators without either introduction are never treated as structure;
    a false continuation must additionally fit the hierarchy exactly or it
    becomes a review item rather than a label."""
    found = []
    period_end = None
    period_match = PERIOD_CONTINUATION_RE.match(text, start)
    if period_match:
        found.extend(SINGLE_DESIGNATOR_RE.findall(period_match.group(1)))
        period_end = period_match.end()
    for match in CONTINUATION_RE.finditer(text, start):
        if period_end is not None and match.start() < period_end:
            continue
        found.extend(SINGLE_DESIGNATOR_RE.findall(match.group(0)))
    return found


class Canonicalizer:
    def __init__(self, capture_path, capture_sha256):
        self.capture_path = capture_path
        self.capture_sha256 = capture_sha256
        self.review_items = []

    def canonicalize(self, root):
        """Return the list of canonical section objects found under root."""
        sections = []
        for div8 in root.iter("DIV8"):
            sections.append(self._section(div8))
        return sections

    def _section(self, div8):
        section_number = div8.get("N", "")
        selector = f"DIV8[N={section_number}]"
        head = div8.find("HEAD")
        heading = normalize_text(_element_text(head)) if head is not None else ""
        node = self._node(div8, selector, skip_head=True)
        self.review_items = []
        anchors = self._derive_logical_anchors(node, section_number)
        return {
            "capture_path": self.capture_path,
            "capture_sha256": self.capture_sha256,
            "section_number": section_number,
            "heading": heading,
            "tree": node,
            "logical_anchors": anchors,
            "review_items": list(self.review_items),
        }

    def _node(self, element, selector, skip_head=False):
        children = []
        counters = {}
        for child in element:
            tag = child.tag
            if skip_head and tag == "HEAD":
                continue
            counters[tag] = counters.get(tag, 0) + 1
            child_selector = f"{selector}/{tag}[{counters[tag]}]"
            if tag == "TABLE":
                children.append(self._table(child, child_selector))
            elif tag in STRUCTURAL_TAGS:
                # transparent wrapper: recurse, children adopt inner content
                wrapper = self._node(child, child_selector)
                children.append(wrapper)
            else:
                children.append(self._node(child, child_selector))
        text = ""
        if element.tag not in {"TABLE", "TR"} and not list(element):
            text = normalize_text(_element_text(element))
        elif element.tag == "P" or element.tag == "HEAD" or element.tag == "CITA":
            text = normalize_text(_element_text(element))
        kind = {
            "DIV8": "section", "HEAD": "head", "P": "paragraph",
            "TABLE": "table", "CITA": "citation", "FP": "flush-paragraph",
            "NOTE": "note", "EXTRACT": "extract",
        }.get(element.tag, "other")
        node = {"selector": selector, "tag": element.tag, "kind": kind}
        if text:
            node["text"] = text
        if children:
            node["children"] = children
        return node

    def _table(self, table, selector):
        rows = []
        row_index = 0
        for tr in table.iter("TR"):
            row_index += 1
            cells = []
            cell_index = 0
            for cell in tr:
                if cell.tag not in {"TD", "TH"}:
                    continue
                cell_index += 1
                cells.append({
                    "selector": f"{selector}/TR[{row_index}]/{cell.tag}[{cell_index}]",
                    "tag": cell.tag,
                    "kind": "cell",
                    "row": row_index,
                    "col": cell_index,
                    "text": normalize_text(_element_text(cell)),
                })
            rows.append({
                "selector": f"{selector}/TR[{row_index}]",
                "tag": "TR", "kind": "row", "row": row_index,
                "children": cells,
            })
        return {"selector": selector, "tag": "TABLE", "kind": "table",
                "children": rows}

    # ---- Stage 2: derived logical citation anchors -------------------------

    LEVELS = ["lower-alpha", "numeric", "lower-roman", "upper-alpha",
              "numeric-2", "upper-roman"]

    def _derive_logical_anchors(self, node, section_number):
        anchors = []
        stack = []  # list of (level_index, designator)
        self._walk_paragraphs(node, section_number, stack, anchors)
        return anchors

    def _walk_paragraphs(self, node, section_number, stack, anchors):
        if node.get("kind") == "paragraph" and node.get("text"):
            match = DESIGNATOR_RE.match(node["text"])
            if match:
                designators = SINGLE_DESIGNATOR_RE.findall(match.group(0))
                designators += _continuation_designators(
                    node["text"], match.end())
                resolved = self._resolve(designators, stack)
                if resolved is None:
                    self.review_items.append({
                        "kind": "logical-anchor-ambiguity",
                        "selector": node["selector"],
                        "designators": designators,
                        "reason": "designator level ambiguous in context; "
                                  "no label guessed",
                    })
                    anchors.append({
                        "selector": node["selector"],
                        "status": "review-item",
                    })
                else:
                    stack[:] = resolved
                    label = section_number + "".join(
                        f"({d})" for _, d in resolved)
                    anchors.append({
                        "selector": node["selector"],
                        "status": "derived",
                        "label": label,
                    })
        for child in node.get("children", []):
            self._walk_paragraphs(child, section_number, stack, anchors)

    def _resolve(self, designators, stack):
        """Resolve a designator chain against the current stack. Returns the
        new stack, or None when ambiguous."""
        new_stack = list(stack)
        for token in designators:
            candidates = _classify(token)
            if not candidates:
                return None
            placement = self._place(token, candidates, new_stack)
            if placement is None:
                return None
            new_stack = placement
        return new_stack

    def _place(self, token, candidates, stack):
        options = []
        for level_name in candidates:
            for level_index, name in enumerate(self.LEVELS):
                if name != level_name and not (
                        level_name == "numeric" and name == "numeric-2"):
                    continue
                option = self._try_level(token, level_index, stack)
                if option is not None:
                    options.append(option)
        # dedupe identical resulting stacks
        unique = []
        for option in options:
            if option not in unique:
                unique.append(option)
        if len(unique) == 1:
            return unique[0]
        return None

    def _try_level(self, token, level_index, stack):
        """A token fits a level either as a sibling successor at that level
        (deeper levels pop: '(2)' after '(b)(1)(vi)' resolves to '(b)(2)')
        or as the first designator opening the next-deeper level."""
        depths = [li for li, _ in stack]
        if level_index in depths:
            position = depths.index(level_index)
            prev = stack[position][1]
            if self._is_successor(prev, token, level_index):
                return stack[:position] + [(level_index, token)]
            return None
        # opening a deeper level: must be exactly one deeper than current
        # deepest, and the first value of its sequence
        expected_depth = (depths[-1] + 1) if depths else 0
        if level_index == expected_depth and self._is_first(token, level_index):
            return stack + [(level_index, token)]
        return None

    @staticmethod
    def _is_first(token, level_index):
        firsts = {0: "a", 1: "1", 2: "i", 3: "A", 4: "1", 5: "I"}
        return token == firsts.get(level_index)

    @staticmethod
    def _is_successor(prev, token, level_index):
        if level_index in (1, 4):
            return token.isdigit() and prev.isdigit() and int(token) == int(prev) + 1
        if level_index in (2, 5):
            order = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix",
                     "x", "xi", "xii", "xiii", "xiv", "xv"]
            seq = order if level_index == 2 else [t.upper() for t in order]
            return prev in seq and token in seq and \
                seq.index(token) == seq.index(prev) + 1
        # alpha levels, including aa after z
        def alpha_next(value):
            if len(value) == 1 and value not in ("z", "Z"):
                return chr(ord(value) + 1)
            if value in ("z", "Z"):
                return value * 2
            if len(value) == 2 and value[0] == value[1]:
                return None
            return None
        return alpha_next(prev) == token


def canonicalize_capture(repo_root, capture_rel_path):
    """Parse one verified capture and return its canonical sections plus the
    canonical payload digest of each."""
    import os
    full = os.path.join(repo_root, capture_rel_path)
    capture_sha = file_sha256(full)
    tree = ET.parse(full)
    canonicalizer = Canonicalizer(capture_rel_path, capture_sha)
    sections = canonicalizer.canonicalize(tree.getroot())
    results = []
    for section in sections:
        results.append({
            "section": section,
            "canonical_sha256": content_digest(section),
        })
    return results
