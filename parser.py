"""
parser.py: turn a catalog prerequisite sentence into a logic tree.

Example
-------
    parser = Parser(subject_codes)
    parser.parse("Economics 10A or 100A; and, Economics 5 or PSTAT 109 or PSTAT 120A.")

gives (in its "requires" field) a tree that means

    (ECON 10A or ECON 100A)  AND  (ECON 5 or PSTAT 109 or PSTAT 120A)

The tree is made of four kinds of pieces ("nodes"):

    {"type": "course", "code": "ECON 10A", "concurrent": False, "min_grade": None}
    {"type": "condition", "kind": "standing", "text": "Upper-division standing"}
    {"type": "and", "items": [ ...other nodes... ]}
    {"type": "or",  "items": [ ...other nodes... ]}

How it works, in three passes
-----------------------------
1. PROTECT. Some phrases contain the words "and"/"or" or commas but are
   really one unit: "a grade of C or better", "consent of instructor and
   department", "open to computer science, electrical engineering, and
   computer engineering majors only". Before splitting anything, each such
   phrase is swapped for a placeholder like §b§ and remembered in a list.
   Department names are also rewritten as codes here ("Mathematics 3A" ->
   "MATH 3A") so "Film and Media Studies 96" can't be split on its "and".

2. SPLIT. The protected text is split from the biggest separator to the
   smallest, and each level becomes a layer of the tree:

        sentences (".")      joined with AND
        clauses   (";")      joined with AND, or OR when a clause starts "or"
        segments  (",")      list rules, see parse_clause()
        words     ("or", "and", "/")
        atoms                one course, a course sequence, or a condition

3. APPLY MARKERS. Grade and "may be taken concurrently" placeholders are
   attached to the courses they describe. Each marker's reach (one course,
   one comma segment, one clause, or the whole sentence) depends on where it
   sits; see the "scope rules" comments below.

Anything the parser can't classify is never thrown away: text with no course
in it becomes a condition of kind "other" (keeping its original words), and
leftover words next to a course are returned in the `unparsed` list.
"""

import re

from notation import to_notation
from subjects import SUBJECT_NAMES

# When "and" and "or" appear together with no punctuation ("A or B and C"),
# which one groups first? False means "or" groups first: (A or B) and C,
# which is how UCSB's catalog usually means it ("Mathematics 2B or 3B and
# Chemistry 1A-B-C"). Measured both ways on all 450 test courses: 427 right
# with False, 423 with True. Either way these cases are flagged "ambiguous".
AND_BINDS_TIGHTER = False

# Words that may sit next to a course without changing its meaning.
FILLER_WORDS = {
    "a", "an", "the", "either", "both", "in", "of", "with", "and", "or",
    "course", "courses", "preferred", "completion", "completed", "only",
    "is", "required", "prerequisite", "prerequisites", "previous", "prior",
}


# ===========================================================================
# Building tree nodes
# ===========================================================================

def make_course(code):
    return {"type": "course", "code": code, "concurrent": False, "min_grade": None}


def make_condition(kind, text):
    return {"type": "condition", "kind": kind, "text": text.strip(" ,;.")}


def combine(group_type, items):
    """Join nodes with "and" or "or", tidying as we go.

    - empty pieces (None) are dropped
    - an "and" inside an "and" is flattened: A and (B and C) -> A and B and C
    - exact duplicates are dropped (e.g. "consent of instructor and department"
      can produce two identical consent conditions)
    - a group of one is just that one thing
    """
    flat = []
    seen = set()
    for item in items:
        if item is None:
            continue
        if item["type"] == group_type:
            children = item["items"]
        else:
            children = [item]
        for child in children:
            key = to_notation(child)
            if key not in seen:
                seen.add(key)
                flat.append(child)
    if not flat:
        return None
    if len(flat) == 1:
        return flat[0]
    return {"type": group_type, "items": flat}


def all_courses(node):
    """List every course node inside a tree (used to apply grades etc.)."""
    if node is None:
        return []
    if node["type"] == "course":
        return [node]
    if node["type"] == "condition":
        return []
    found = []
    for item in node["items"]:
        found.extend(all_courses(item))
    return found


def set_grade(node, grade):
    for course in all_courses(node):
        if course["min_grade"] is None:
            course["min_grade"] = grade


def set_concurrent(node, codes=None):
    """Mark courses as "may be taken concurrently" (all of them, or only `codes`)."""
    for course in all_courses(node):
        if codes is None or course["code"] in codes:
            course["concurrent"] = True


# ===========================================================================
# Pass 1: PROTECT
# ===========================================================================

# Each rule is (regular expression, what to store). Order matters: earlier
# rules claim their text first.

EXAM_RULES = [
    r"Exam: [A-Z]+ [A-Z0-9]+ ?>= ?\d+",
    r"\bAP\b[^;,.()§]*?\bscore of \d(?: or (?:better|higher|above))?",
    r"\bAP\b[^;,.()§]*?\bexam(?:ination)?\b",
    r"\bIB\b[^;,.()§]*?\d",
]

# "with a minimum grade of C-", "a grade of C or better in each course", ...
# Group "each1"/"each2" capture words that stretch the grade over the whole
# list ("each with", "in all").
GRADE_RULES = [
    r"(?:,\s*)?(?:(?P<each1>each|all|both)\s+)?(?:completed\s+)?(?:with\s+)?(?:an?\s+)?(?:minimum\s+)?(?:letter\s+)?"
    r"grades?\s+(?:of\s+)?(?:at\s+least\s+)?(?:P\s+or\s+(?:a\s+)?grade\s+of\s+)?(?:an?\s+(?=[A-D][+-]?\b))?"
    r"(?P<grade>[A-D][+-]?)(?![A-Za-z0-9])(?:\s+or\s+(?:better|higher|above))?"
    r"(?:\s+(?:or\s+better\s+)?(?:is\s+)?(?:required\s+)?(?:must\s+be\s+earned\s+)?"
    r"in\s+(?P<each2>each|all|both)(?:\s+of\s+the)?(?:\s+(?:listed\s+)?(?:courses?|prerequisites))?)?",

    r"(?:with\s+)?(?:at\s+least\s+)?(?:an?\s+)?(?<![A-Za-z0-9])(?P<grade>[A-D][+-]?)\s+or\s+better(?:\s+grade)?",

    # "with a C- grade or better"
    r"(?:with\s+)?(?:an?\s+)?(?<![A-Za-z0-9])(?P<grade>[A-D][+-]?)\s+grade(?:\s+or\s+(?:better|higher|above))?",

    # "a C- in ECE 152A"
    r"\ban?\s+(?P<grade>[A-D][+-]?)(?=\s+in\s)",
]

# Concurrency: "(may be taken concurrently)" and friends.
CONCURRENT_SPECIFIC = r"\(\s*(?P<inner>[^()]*?\d[^()]*?)\s+(?:may|can)\s+be\s+taken\s+concurrently[^()]*\)"
CONCURRENT_HERE = [
    r"\(\s*(?:may\s*be\s+taken\s+concurrently|may\s+be\s+concurrent|concurrent\s+enrollment"
    r"(?:\s+(?:is\s+)?(?:allowed|permitted))?|or\s+concurrent(?:\s+enrollment)?|or\s+concurrently|concurrently)\s*\)",
    r"(?:,\s*)?(?:which\s+)?(?:may|can)\s+be\s+taken\s+concurrently"
    r"(?:\s+with\s+[A-Z][A-Z ]*?\s?(?:W\s?)?\d+[A-Z]*)?",
    r"\bor\s+concurrent(?:ly)?(?:\s+enrollment)?\b",
]
CONCURRENT_LEADING = (r"\b(?:concurrent\s+enrollment\s+in|concurrently\s+enrolled\s+in|"
                      r"concurrent\s+with|co-?requisites?:?)")

# Non-course conditions, as (kind, regular expression).
CONDITION_RULES = [
    ("standing", r"\bnot\s+open\s+to\s+freshm[ae]n\b"),
    ("restriction", r"[\w ]*\bmajor\s+standing\b"),
    ("standing", r"\b(?:upper|lower)[- ]division\s+(?:standing|status)(?:\s+only)?"),
    ("standing", r"\b(?:upper|lower)[- ]division\b(?!\s+courses?)"),
    ("standing", r"\b(?:freshman|sophomore|junior|senior|graduate)\s+standing\s+in\s+[^;.§]*"),
    ("standing", r"\b(?:freshman|freshmen|sophomore|junior|senior|graduate|grad)"
                 r"(?:\s+student|\s+level)?\s+(?:standing|status)(?:\s+or\s+(?:higher|above))?"),
    ("standing", r"\b(?:freshm[ae]n|seniors?|juniors?|graduate\s+students?)\s+only\b"),
    ("standing", r"\badvancement\s+to\s+candidacy\b"),
    ("restriction", r"\b(?:only\s+)?open\s+(?:only\s+)?to\s+[^;.§]*"),
    ("restriction", r"[^;.,§]*\bmajors?(?:\s+and\s+minors?)?\s+only\b"),
    ("restriction", r"[^;.,§]*\bstudents\s+only\b"),
    ("restriction", r"\badmission\s+to\s+[^;.§]*"),
    ("restriction", r"\b(?:active\s+)?member\s+of\s+[^;.§]*"),
    ("consent", r"\b(?:by\s+)?(?:consent|permission|approval)\s+(?:of|from)\s+(?:the\s+)?"
                r"(?:[\w ]{0,30}?\s)?(?:instructor|department|dept\.?|program|chair|adviser|advisor|committee)"
                r"(?:\s+(?:and|or)\s+(?:the\s+)?(?:[\w ]{0,30}?\s)?"
                r"(?:instructor|department|adviser|advisor))?"),
    ("consent", r"\b(?:instructor|department(?:al)?|dept\.?)(?:\s+and\s+instructor)?\s+"
                r"(?:approval|consent|permission)(?:\s+to\s+(?:finalize\s+registration|enroll))?"),
]


def letters_for(number):
    """0 -> 'a', 1 -> 'b', ... 26 -> 'ba'. Placeholders use letters, not digits,
    so the course-number finder never mistakes a placeholder for a course."""
    text = ""
    while True:
        text = chr(ord("a") + number % 26) + text
        number //= 26
        if number == 0:
            return text


class Protector:
    """Swaps protected phrases for placeholders and remembers what they were."""

    def __init__(self):
        self.stash = []   # list of dicts, one per placeholder

    def placeholder(self, info):
        self.stash.append(info)
        return " §" + letters_for(len(self.stash) - 1) + "§ "

    def lookup(self, token):
        """'§b§' -> the stored dict."""
        name = token.strip("§")
        index = 0
        for char in name:
            index = index * 26 + (ord(char) - ord("a"))
        return self.stash[index]

    def replace(self, pattern, text, make_info, flags=re.IGNORECASE):
        def swap(match):
            return self.placeholder(make_info(match))
        return re.sub(pattern, swap, text, flags=flags)


def build_subject_pattern(subject_codes):
    """One regular expression that finds a department (code or name) followed by a number.

    Official codes must match exactly (uppercase); names ignore case. All are
    tried longest-first, so "PHYS CS" wins over "PHYS" and "ART CS" (a real
    code) wins over the name "Art".
    """
    choices = []
    for code in subject_codes:
        choices.append((code, re.escape(code)))
    for name in SUBJECT_NAMES:
        choices.append((name, "(?i:" + re.escape(name) + ")"))
    choices.sort(key=lambda pair: len(pair[0]), reverse=True)
    alternatives = "|".join(pattern for _, pattern in choices)
    return re.compile(r"(?<![A-Za-z])(" + alternatives + r")\s*(?=(?:W\s?)?\d)")


def protect(text, subject_pattern, protector):
    """Pass 1: clean the text and swap fragile phrases for placeholders."""
    text = text.replace("�", " ").replace("–", "-").replace("—", "-")
    text = text.replace("&", " and ")
    text = re.sub(r'"([A-F][+-]?)"', r"\1", text)          # grade of "C" -> grade of C
    text = re.sub(r"^\s*(?:prerequisites?|prereqs?)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(\s*or\s+([^()]*)\)", r" or \1 ", text)  # "4A (or 4AI)" -> "4A or 4AI"
    text = re.sub(r"(\d+) ([A-Z](?:-[A-Z])+)\b", r"\1\2", text)  # "118 A-B-C" -> "118A-B-C"

    # Department names -> codes ("Mathematics 3A" -> "MATH 3A")
    def to_code(match):
        written = match.group(1)
        for name, code in SUBJECT_NAMES.items():
            if name.lower() == written.lower():
                return code + " "
        return written + " "
    text = subject_pattern.sub(to_code, text)

    text = re.sub(r"\bOR\b", "or", text)
    text = re.sub(r"\bAND\b", "and", text)

    for rule in EXAM_RULES:
        text = protector.replace(rule, text, lambda m: {"marker": "condition", "kind": "exam",
                                                        "text": m.group(0)})
    for rule in GRADE_RULES:
        text = protector.replace(rule, text, lambda m: {
            "marker": "grade",
            "grade": m.group("grade").upper(),
            "each": bool(m.groupdict().get("each1") or m.groupdict().get("each2")),
            "text": m.group(0)})

    text = protector.replace(CONCURRENT_SPECIFIC, text, lambda m: {
        "marker": "concurrent_specific", "inner": m.group("inner"), "text": m.group(0)})
    for rule in CONCURRENT_HERE:
        text = protector.replace(rule, text, lambda m: {"marker": "concurrent", "text": m.group(0)})
    text = protector.replace(CONCURRENT_LEADING, text, lambda m: {"marker": "concurrent_leading",
                                                                  "text": m.group(0)})

    for kind, rule in CONDITION_RULES:
        text = protector.replace(rule, text, lambda m, kind=kind: {
            "marker": "condition", "kind": kind, "text": m.group(0)})

    return re.sub(r"\s+", " ", text).strip()


# ===========================================================================
# Pass 2 and 3: SPLIT and APPLY MARKERS
# ===========================================================================

PLACEHOLDER = re.compile(r"§[a-z]+§")


class Parser:
    def __init__(self, subject_codes):
        self.subject_codes = set(subject_codes)
        self.subject_pattern = build_subject_pattern(subject_codes)
        codes = sorted(subject_codes, key=len, reverse=True)
        subjects = "|".join(re.escape(code) for code in codes)
        # A course reference: optional subject, optional W, a number with an
        # optional letter suffix and optional sequence ("113A-B-C", "1-6").
        self.course_pattern = re.compile(
            r"(?<![A-Za-z§])(?:(?P<subject>" + subjects + r")\s*)?"
            r"(?P<w>W\s?)?(?P<number>\d+[A-Z]*(?:-[A-Z0-9]+)*)(?![A-Za-z0-9])")
        self.shared_number = re.compile(
            r"\b(" + subjects + r")\s+(or|and)\s+(" + subjects + r")\s+(\d+[A-Z]*)\b")

    # ----------------------------------------------------------------- entry
    def parse(self, text):
        """Parse one course's prerequisite text. Returns a dict:

            requires    the tree, or None when there's no requirement
            unparsed    leftover words found next to courses (never dropped silently)
            ambiguous   True if the text mixes "and" and "or" with no punctuation
                        ("MATH 2B or 3B and CHEM 1A"), where the grouping is a guess
        """
        self.unparsed = []
        self.ambiguous = False
        self.last_subject = None
        self.protector = Protector()

        cleaned = text.strip()
        if re.fullmatch(r"(?i)\s*(none|n/a|no prerequisites?)\.?\s*", cleaned) or not cleaned:
            return {"requires": None, "unparsed": [], "ambiguous": False}

        protected = protect(cleaned, self.subject_pattern, self.protector)

        # "ECE or CMPSC 181" -> "ECE 181 or CMPSC 181"
        protected = self.shared_number.sub(r"\1 \4 \2 \3 \4", protected)

        # "MATH 3A-B (AP Math BC Exam score of 3 or better)": an exam in
        # parentheses is another way to meet the requirement, so it becomes "or".
        def exam_in_parens(match):
            if self.protector.lookup(match.group(1)).get("kind") == "exam":
                return " or " + match.group(1) + " "
            return " " + match.group(1) + " "
        protected = re.sub(r"\(\s*(§[a-z]+§)\s*\)", exam_in_parens, protected)

        sentences = re.split(r"\.\s+(?=[A-Z§(])|\.\s*$", protected)

        main_parts = []
        for sentence in sentences:
            sentence = sentence.strip(" .")
            if not sentence:
                continue
            # A "recommended" sentence is advice, not a requirement: keep it as
            # text so it shows up on the site but doesn't draw an arrow.
            if re.search(r"\brecommended\b", sentence, flags=re.IGNORECASE):
                main_parts.append(make_condition("other", self.restore(sentence)))
                continue

            node = self.parse_sentence(sentence)
            courses_so_far = all_courses(combine("and", main_parts))

            # Scope rule: a sentence with a grade but no courses ("Completion of
            # all listed prerequisites with a grade of C or better.") applies the
            # grade to every course listed before it, and adds nothing else.
            sentence_grade = self.grade_in(sentence)
            if sentence_grade and not all_courses(node) and courses_so_far:
                for course in courses_so_far:
                    if course["min_grade"] is None:
                        course["min_grade"] = sentence_grade
                if node is None or (node["type"] == "condition" and node["kind"] == "other"):
                    continue
            if node is None and sentence_grade:
                node = make_condition("other", self.restore(sentence))

            # Scope rule: "ECE 153A may be taken concurrently with ECE 188A." only
            # adds a flag to a course already listed; it isn't a new requirement.
            sentence_courses = all_courses(node)
            known_codes = {course["code"] for course in courses_so_far}
            if (sentence_courses and node["type"] in ("course", "and")
                    and all(c["concurrent"] for c in sentence_courses)
                    and all(c["code"] in known_codes for c in sentence_courses)):
                set_concurrent(combine("and", main_parts), {c["code"] for c in sentence_courses})
                continue

            main_parts.append(node)

        return {"requires": combine("and", main_parts),
                "unparsed": self.unparsed,
                "ambiguous": self.ambiguous}

    def grade_in(self, text):
        """The first grade mentioned in a piece of protected text, or None."""
        for token in PLACEHOLDER.findall(text):
            info = self.protector.lookup(token)
            if info["marker"] == "grade":
                return info["grade"]
        return None

    # -------------------------------------------------------------- sentence
    def parse_sentence(self, sentence):
        """Split on ';'. Clauses are ANDed, except a clause starting with "or"
        begins a new alternative: "A; and B; or C" means (A and B) or C."""
        groups = [[]]
        nodes_so_far = []         # clauses in the current alternative
        for clause in sentence.split(";"):
            clause = clause.strip(" ,")
            if not clause:
                continue
            start = re.match(r"^(and|or)\b[\s,]*", clause, flags=re.IGNORECASE)
            if start:
                clause = clause[start.end():]
                if start.group(1).lower() == "or" and groups[-1]:
                    groups.append([])
                    nodes_so_far = []
            node, each_grade = self.parse_clause(clause)

            # Scope rule: a grade with "each"/"all"/"both" covers every course
            # before it in the same sentence (but not across a "; or" into a
            # different alternative).
            if each_grade:
                for earlier in nodes_so_far + [node]:
                    set_grade(earlier, each_grade)
            if node is not None:
                groups[-1].append(node)
                nodes_so_far.append(node)

        # Scope rule: "...; or B; open to EE majors only." The restriction at the
        # end isn't part of alternative B; it applies to every alternative.
        applies_to_all = []
        if len(groups) > 1:
            last = groups[-1]
            while len(last) > 1 and last[-1]["type"] == "condition" and \
                    last[-1]["kind"] in ("restriction", "standing"):
                applies_to_all.insert(0, last.pop())

        alternatives = [combine("and", group) for group in groups]
        return combine("and", [combine("or", alternatives)] + applies_to_all)

    # ---------------------------------------------------------------- clause
    def parse_clause(self, clause):
        """Split on commas and decide how the comma-separated pieces join.

        "A, B, and C"      -> the last connector applies to the whole list
        "A, B, or C"       -> OR list
        "A or B, and C"    -> (A or B) and C
        "A, B or C"        -> if A is a single course and "B or C" uses one
                              connector, it's one OR list: A or B or C
        "A or W142A, 142B" -> no connector after the comma: AND

        Returns (node, each_grade)."""
        clause_markers = []

        # Pull out markers that come before the first course in the clause
        # ("Concurrent enrollment in ...", "Grade of C- or better in ...");
        # those reach the whole clause.
        blanked = PLACEHOLDER.sub(lambda m: " " * len(m.group(0)), clause)
        first_course = self.course_pattern.search(blanked)
        cutoff = first_course.start() if first_course else len(clause)
        for token in PLACEHOLDER.findall(clause[:cutoff]):
            info = self.protector.lookup(token)
            if info["marker"] in ("concurrent_leading", "grade"):
                clause_markers.append(info)
                clause = clause.replace(token, " ", 1)

        # Split on commas; a segment ending in "and"/"or" passes it on.
        segments = []
        connector = None
        for piece in clause.split(","):
            piece = piece.strip()
            start = re.match(r"^(and|or)\b\s*", piece)
            if start:
                connector = start.group(1)
                piece = piece[start.end():]
            end = re.search(r"\s*\b(and|or)$", piece)
            next_connector = None
            if end:
                next_connector = end.group(1)
                piece = piece[:end.start()]
            if piece:
                segments.append([connector, piece])
            connector = next_connector

        # Segments that are only a marker ("each with a minimum grade of C")
        # describe the whole clause.
        kept = []
        each_grade = None
        for segment in segments:
            without = PLACEHOLDER.sub("", segment[1]).strip()
            tokens = PLACEHOLDER.findall(segment[1])
            infos = [self.protector.lookup(t) for t in tokens]
            if not without and infos and all(i["marker"] != "condition" for i in infos):
                for info in infos:
                    if info["marker"] == "grade" and info["each"]:
                        each_grade = info["grade"]
                    else:
                        clause_markers.append(info)
            else:
                kept.append(segment)
        segments = kept
        if not segments:
            return None, each_grade

        segments = self.merge_simple_lists(segments)

        # Fill in missing connectors: take the next explicit one to the right,
        # or AND if there is none at all.
        connectors = [segment[0] for segment in segments[1:]]
        for i in range(len(connectors)):
            if connectors[i] is None:
                later = [c for c in connectors[i:] if c]
                earlier = [c for c in connectors[:i] if c]
                if later:
                    connectors[i] = later[0]
                elif earlier:
                    connectors[i] = earlier[-1]
                else:
                    connectors[i] = "and"

        # Parse each segment, then join: AND inside, OR between (like ";").
        nodes = []
        for index, segment in enumerate(segments):
            is_last = index == len(segments) - 1
            node, local_each = self.parse_segment(segment[1], is_last, clause_markers)
            if local_each:
                each_grade = local_each
            nodes.append(node)

        groups = [[nodes[0]]]
        for connector, node in zip(connectors, nodes[1:]):
            if connector == "or":
                groups.append([node])
            else:
                groups[-1].append(node)
        clause_node = combine("or", [combine("and", group) for group in groups])

        for info in clause_markers:
            self.apply_marker(clause_node, info)
        return clause_node, each_grade

    def merge_simple_lists(self, segments):
        """'PHYS 3, 7B or 23' -> one segment 'PHYS 3 or 7B or 23'."""
        if len(segments) < 2:
            return segments
        if any(segment[0] for segment in segments[1:]):
            return segments            # explicit connectors: handled by caller

        def is_single(text):
            text = PLACEHOLDER.sub("", text)
            return not re.search(r"\b(and|or)\b|/", text) and len(self.course_pattern.findall(text)) == 1

        last = PLACEHOLDER.sub("", segments[-1][1])
        uses_or = bool(re.search(r"\bor\b", last))
        uses_and = bool(re.search(r"\band\b", last))
        if all(is_single(s[1]) for s in segments[:-1]) and uses_or != uses_and:
            joiner = " or " if uses_or else " and "
            merged = joiner.join(segment[1] for segment in segments)
            return [[segments[0][0], merged]]
        return segments

    # --------------------------------------------------------------- segment
    def parse_segment(self, text, is_last, clause_markers):
        """One comma-separated piece. Pull out grade/concurrency markers, parse
        the and/or logic, then apply the markers.

        Scope rules for a marker found here:
          - grade with "each/all/both"           -> returned to the sentence
          - plain grade in the clause's LAST
            segment ("A, B, and C with C-")       -> whole clause
          - plain grade in an earlier segment    -> this segment only
          - concurrency                          -> this segment only
        """
        markers = []
        for token in PLACEHOLDER.findall(text):
            info = self.protector.lookup(token)
            if info["marker"] != "condition":
                markers.append(info)
                text = text.replace(token, " ", 1)
        text = re.sub(r"\s+", " ", text).strip()

        node = self.parse_words(text)

        each_grade = None
        for info in markers:
            if info["marker"] == "grade" and info["each"]:
                each_grade = info["grade"]
            elif info["marker"] == "grade" and is_last:
                clause_markers.append(info)
            else:
                self.apply_marker(node, info)
        return node, each_grade

    def apply_marker(self, node, info):
        if node is None:
            return
        if info["marker"] == "grade":
            set_grade(node, info["grade"])
        elif info["marker"] in ("concurrent", "concurrent_leading"):
            set_concurrent(node)
        elif info["marker"] == "concurrent_specific":
            codes = {course["code"] for course in all_courses(self.parse_words(info["inner"]))}
            set_concurrent(node, codes)

    # ----------------------------------------------------------------- words
    def parse_words(self, text):
        """Split on 'or' and 'and' (and '/'), respecting AND_BINDS_TIGHTER."""
        if AND_BINDS_TIGHTER:
            outer, inner = ("or", "and")
        else:
            outer, inner = ("and", "or")
        # A sentence of prose whose only course numbers have no subject ("Part
        # of a three quarter sequence with 207B and 207C") describes courses;
        # it doesn't list requirements. Splitting it on "and" would turn the
        # last number into a requirement, so keep the whole thing as text.
        # (Found by Part 4's cycle check: PSTAT 207A seemed to require 207C.)
        bare = PLACEHOLDER.sub(" ", text)
        has_subject = any(m.group("subject") for m in self.course_pattern.finditer(bare))
        prose_words = [w for w in re.findall(r"[A-Za-z][A-Za-z'\-]*", bare)
                       if w.lower() not in FILLER_WORDS]
        if not has_subject and len(prose_words) >= 3 and self.course_pattern.search(bare):
            # Keep any conditions found inside it ("upper division standing").
            kept = [make_condition(info["kind"], info["text"])
                    for info in (self.protector.lookup(t) for t in PLACEHOLDER.findall(text))
                    if info["marker"] == "condition"]
            return combine("and", kept + [make_condition("other", self.restore(text))])

        if re.search(r"\sand\s", text) and re.search(r"\sor\s", text):
            self.ambiguous = True
        parts = re.split(r"\s+%s\s+" % outer, " " + text + " ")
        nodes = []
        for part in parts:
            pieces = re.split(r"\s+%s\s+" % inner, " " + part + " ")
            nodes.append(combine(inner, [self.parse_slash(p.strip()) for p in pieces if p.strip()]))
        return combine(outer, nodes)

    def parse_slash(self, text):
        """'MATH 2A/3A' means 2A or 3A. But 'PHYS 5/PHYS 5L' is a lecture and its
        lab, and you need both: when the second course is the first one's lab
        (same subject and number, ending in L), the slash means AND."""
        if "/" not in text:
            return self.parse_atom(text)
        nodes = [self.parse_atom(piece.strip()) for piece in text.split("/") if piece.strip()]
        if len(nodes) == 2 and nodes[0] and nodes[1] and \
                nodes[0]["type"] == nodes[1]["type"] == "course":
            first, second = nodes[0]["code"], nodes[1]["code"]
            first_digits = re.match(r"(.*?\d+)", first).group(1)
            if second.endswith("L") and second.startswith(first_digits):
                return combine("and", nodes)
        return combine("or", nodes)

    # ------------------------------------------------------------------ atom
    def parse_atom(self, text):
        """The smallest piece: course(s), condition placeholder(s), or leftover words."""
        leaves = []

        for token in PLACEHOLDER.findall(text):
            info = self.protector.lookup(token)
            if info["marker"] == "condition":
                leaves.append(make_condition(info["kind"], info["text"]))

        bare = PLACEHOLDER.sub(" ", text)
        found_course = False
        leftover = bare
        for match in self.course_pattern.finditer(bare):
            subject = match.group("subject")
            if subject is None:
                # A bare number like the "100A" in "Economics 10A or 100A".
                # Only trust it when the piece holds nothing else but filler.
                rest = bare[:match.start()] + bare[match.end():]
                words = re.findall(r"[A-Za-z]+", rest)
                if self.last_subject is None or any(w.lower() not in FILLER_WORDS for w in words):
                    continue
                subject = self.last_subject
            else:
                self.last_subject = subject
            expanded = self.expand_number(subject, match.group("w"), match.group("number"))
            if expanded is None:
                leaves.append(make_condition("other", match.group(0)))
            else:
                leaves.append(combine("and", expanded))
            found_course = True
            leftover = leftover.replace(match.group(0), " ", 1)

        words = [w for w in re.findall(r"[A-Za-z][A-Za-z'\-]*", leftover)
                 if w.lower() not in FILLER_WORDS]
        if found_course and len(words) >= 3:
            # A sentence that only mentions a course ("taken with the instructor
            # for EACS 199", "Note: ITAL 144XX is the ... version") isn't a
            # course requirement; keep it as text.
            return make_condition("other", self.restore(text))
        if found_course and words:
            self.unparsed.append(self.restore(text))
        if not leaves and words:
            leaves.append(make_condition("other", self.restore(text)))

        return combine("and", leaves)

    def online_prefix(self, subject):
        """Online ("W") versions of courses have their own subject code, written
        two ways in the catalog: "CHEM W 142A" (subject "CHEM W") but
        "CMPSCW 8" (subject "CMPSCW"). Use whichever form exists."""
        if subject + "W" in self.subject_codes:
            return subject + "W "
        return subject + " W "

    def expand_number(self, subject, w_prefix, number):
        """'113A-B-C' -> [113A, 113B, 113C];  '1-6' -> [1, 2, 3, 4, 5, 6];
        '3AH-BH' -> [3AH, 3BH];  '5AA-ZZ' or '105A-Z' (any course in a range) -> None."""
        prefix = self.online_prefix(subject) if w_prefix else subject + " "
        parts = number.split("-")
        first = parts[0]
        if len(parts) == 1:
            return [make_course(prefix + first)]
        if "ZZ" in parts:
            return None
        if all(p.isdigit() for p in parts) and int(parts[-1]) > int(first) and \
                int(parts[-1]) - int(first) <= 12:
            return [make_course(prefix + str(n)) for n in range(int(first), int(parts[-1]) + 1)]
        digits = re.match(r"\d+", first).group(0)
        letter = first[len(digits):]
        if len(parts) == 2 and len(letter) == 1 and len(parts[1]) == 1 and parts[1].isalpha() \
                and ord(parts[1]) - ord(letter) > 1:
            span = ord(parts[1]) - ord(letter)
            if span > 3:
                # "105A-Z" means "any course from 105A to 105Z", not all 26
                return None
            # "1A-C" is a short sequence: 1A, 1B, 1C
            return [make_course(prefix + digits + chr(n)) for n in range(ord(letter), ord(parts[1]) + 1)]
        courses = [make_course(prefix + first)]
        for part in parts[1:]:
            if part[0].isdigit():                 # "172-172L": a full number
                courses.append(make_course(prefix + part))
            else:                                 # "113A-B": just the letter
                courses.append(make_course(prefix + digits + part))
        return courses

    def restore(self, text):
        """Put the original words back in place of placeholders, for display."""
        def put_back(match):
            return self.protector.lookup(match.group(0))["text"].strip()
        return re.sub(r"\s+", " ", PLACEHOLDER.sub(put_back, text)).strip(" ,;.")


def subject_of(code):
    """'MATH 3A' -> 'MATH', 'PHYS CS 15C' -> 'PHYS CS', 'SPAN W 2' -> 'SPAN'."""
    match = re.match(r"^(.*?)\s+(?:W\s+)?\d", code)
    return match.group(1) if match else None
