"""
build_prereqs.py (UCLA): turn each course's requisite text into a tree.

    python pipeline/campuses/ucla/build_prereqs.py

Reads   data/ucla/raw_courses.json    (from extract.py)
        data/ucla/subjects.json       subject codes and names (from fetch.py)
Writes  data/ucla/prereqs.json        in the same shape as UCSB's data/prereqs.json

UCLA writes requisites like this:
    "course 31"                         a course in the same subject
    "courses 1A, 1B, 1C"                all three, same subject
    "Mathematics 31B, 32A"              another subject, named in words
    "courses 238A and 238B, or M265A and 265B"
    "Computer Science M51A or Electrical and Computer Engineering M16"
The shared parser (pipeline/parser.py) reads the rest, once three things
are turned into forms it knows:
    - "course 31" gets the course's own subject: "COM SCI 31";
    - codes with "&" ("C&EE 110", "MECH&AE 150A") get a plain stand-in
      ("CQEE"), since the parser reads "&" as "and";
    - numbers with letters in front (M51A multiple-listed, C111 concurrently
      scheduled, CM124) get them moved behind a marker ("51AQQM"), since
      the parser expects numbers to start with a digit.
Each is turned back in the tree that comes out.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from parser import Parser  # noqa: E402

INPUT = os.path.join("data", "ucla", "raw_courses.json")
SUBJECTS = os.path.join("data", "ucla", "subjects.json")
OUTPUT = os.path.join("data", "ucla", "prereqs.json")

# UCLA's condition phrasings (kind, pattern), as UCSD's EXTRA_RULES.
EXTRA_RULES = [
    # (up to three words before it, none of them "or"/"and": "or Japanese placement test")
    ("exam", r"\b(?:(?!(?:or|and)\b)[A-Za-z]+\s+){0,3}(?:placement|diagnostic)\s+(?:exam|test)(?:ination)?\b"),
    ("restriction", r"\b(?:enrollment\s+)?(?:restricted|limited)\s+(?:to|for)\s+(?:[^;.§]|\.(?=\d))*"),
    ("other", r"\battendance,?\s+but\s+not\s+enrollment,?\s+in\s+[^;§]*"),
]
OTHER_NAMES = {
    "Chemistry": "CHEM",
    "Electrical Engineering": "EC ENGR",
    "Mechanical Engineering": "MECH&AE",
    "Civil Engineering": "C&EE",
    "Materials Science": "MAT SCI",
    "Atmospheric Sciences": "A&O SCI",
    "Earth and Space Sciences": "EPS SCI",
    "Biomedical Engineering": "BIOENGR",
}
PREFIX_MARK = "QQ"
PREFIXED_NUMBER = re.compile(r"(?<![A-Za-z0-9])(CM|MC|C|M)(\d+[A-Z]*)(?![A-Za-z0-9])")
MARKED_NUMBER = re.compile(r"^(\d+[A-Z]*?)" + PREFIX_MARK + r"([A-Z]+)$")


def alias(code):
    """A stand-in the parser can read: "C&EE" -> "CQEE"."""
    return code.replace("&", "Q")


class Names:
    """UCLA's subjects in the parser's terms, and the way back."""

    def __init__(self, subjects, courses):
        codes = set(subjects) | {c["subject"] for c in courses}
        self.real = {alias(code): code for code in codes}
        self.names = {name: alias(code) for code, name in subjects.items()}
        # Shorter and older names the catalog still writes ("Chemistry 14A" for
        # Chemistry and Biochemistry; "Electrical Engineering 100").
        for name, short in OTHER_NAMES.items():
            if short in subjects and name not in self.names:
                self.names[name] = alias(short)
        self.codes = set(self.real)
        self.comma_names = sorted(((n, a) for n, a in self.names.items() if "," in n), key=lambda x: -len(x[0]))

    def to_parser(self, text, own_subject):
        for code in sorted((c for c in self.real.values() if "&" in c), key=len, reverse=True):
            text = re.sub(r"(?<![A-Za-z&])" + re.escape(code) + r"(?![A-Za-z&])", alias(code), text)
        # "course 31", "courses 238A and 238B" -> the course's own subject
        text = re.sub(r"\bcourses?\s+(?=(?:CM|MC|C|M)?\d)", alias(own_subject) + " ", text, flags=re.IGNORECASE)
        return PREFIXED_NUMBER.sub(lambda m: m.group(2) + PREFIX_MARK + m.group(1), text)

    def from_parser(self, node):
        if node is None:
            return None
        if node.get("type") == "course" and node.get("code"):
            subject, number = node["code"].rsplit(" ", 1)
            marked = MARKED_NUMBER.match(number)
            if marked:
                number = marked.group(2) + marked.group(1)
            node = dict(node, code=self.real.get(subject, subject) + " " + number)
        if node.get("items"):
            node = dict(node, items=[self.from_parser(i) for i in node["items"]])
        return node


def without_course(node, code):
    """The tree with `code` taken out: a course can't require itself."""
    if node is None:
        return None
    if node["type"] == "course":
        return None if node["code"] == code else node
    if node["type"] in ("and", "or"):
        items = [i for i in (without_course(i, code) for i in node["items"]) if i is not None]
        return None if not items else items[0] if len(items) == 1 else dict(node, items=items)
    return node


def marked_concurrent(node, numbers):
    """Courses whose numbers are in `numbers` may be taken at the same time."""
    if node is None:
        return None
    if node.get("type") == "course" and node.get("code", "").rsplit(" ", 1)[-1] in numbers:
        return dict(node, concurrent=True)
    if node.get("items"):
        return dict(node, items=[marked_concurrent(i, numbers) for i in node["items"]])
    return node


def make_parser(names):
    return Parser(names.codes, names.names, EXTRA_RULES, brackets=True)


def split_outside(text, sep=","):
    """Split at `sep` where it isn't inside brackets."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        depth += ch == "("
        depth -= ch == ")"
        if ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def split_words(text, word):
    """Split at a word ("or") where it isn't inside brackets."""
    parts, depth, start = [], 0, 0
    for match in re.finditer(r"\(|\)|\b" + word + r"\b", text):
        if match.group(0) == "(":
            depth += 1
        elif match.group(0) == ")":
            depth -= 1
        elif depth == 0:
            parts.append(text[start:match.start()])
            start = match.end()
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def regroup(text):
    """UCLA's lists, in the bracketed form the parser reads:
        "Life Sciences 1 or 7B, course 100"   -> "(Life Sciences 1 or 7B) and course 100"
            (commas separate requirements; "or" binds within one)
        "courses 1, 2, or 3"                  -> "1 or 2 or 3" (no "and": one choice)
        "Physics 1A, 1B, and 1C, or 6A, 6B, and 6C", "238A and 238B, or M265A and 265B"
                                              -> "(… 1A and 1B and 1C) or (… 6A and 6B and 6C)"
            (with an "and" in it, ", or" separates whole groups)
        "courses 1A, 1B, 1C (or 1AH, 1BH, 1CH)"
                                              -> "((1A and 1B and 1C) or (1AH and 1BH and 1CH))"
    A group that starts with a bare number gets the words naming its subject
    from the group before ("or 20L and 30AL" -> "or courses 20L and 30AL").
    """
    number = r"[A-Z]{0,2}\d+[A-Z]*"
    lead = lambda item: re.match(r"^((?:(?!(?:or|and)\b)[A-Za-z&]+\s+)*)(?=" + number + r"\b)", item)

    def series(match):
        left = [x.strip() for x in match.group(1).split(",")]
        right = [x.strip() for x in match.group(2).split(",")]
        if len(left) != len(right):
            return match.group(0)
        words = lead(left[0])
        if words and words.group(1) and re.match(number, right[0]):
            right[0] = words.group(1) + right[0]
        return "((" + " and ".join(left) + ") or (" + " and ".join(right) + "))"
    text = re.sub(r"\(\d\.\d+\)", "", text)                        # "grades of B (3.0) or better"
    # "Chemistry 14A (or 20A)" -> "(Chemistry 14A or 20A)"
    text = re.sub(r"((?:(?:[A-Z][A-Za-z&]*|courses?)\s+)*)(" + number + r")\s*\(or\s+(" + number + r")\)", r"( \1\2 or \3 )", text)
    # "courses M20 (or Computer Science 31), 82": 82 is in the subject before
    # the brackets, so it gets those words again.
    def after_alternative(match):
        words = match.group(1) or ""
        return "( " + words + match.group(2) + " or " + match.group(3) + " ), " + words + match.group(4)
    text = re.sub(r"((?:(?:[A-Z][A-Za-z&]*|courses?)\s+)*)(" + number + r")\s*\(or\s+([^()]*?\s" + number + r")\),\s*(?=(" + number + r")\b)",
                  lambda m: after_alternative(m)[:-len(m.group(4))], text)
    # "one course from Mathematics 2, Statistics 10, or one term of calculus" is one choice
    text = re.sub(r"\b(?:one|any one)\s+(?:course\s+)?(?:from|of)\s+([^;]*?,[^;]*?\bor\b[^;,]*)",
                  lambda m: "( " + re.sub(r"^(?=(?:CM|MC|C|M)?\d)", "course ", re.sub(r",\s*(?:or\s+)?", " or ", m.group(1))) + " )",
                  text)
    text = re.sub(r"((?:[A-Za-z&]+\s+)*" + number + r"(?:,\s*" + number + r")+)\s*\(or\s+(" + number +
                  r"(?:,\s*" + number + r")+)\)", series, text)
    parts = split_outside(text)
    if len(parts) < 2:
        return text
    # "courses 1, 2, or equivalent": the list, or something equivalent to it
    # (not "1 or 2 or equivalent").
    if len(parts) > 2 and re.match(r"or\s+(?:equivalent|consent|approval)\b", parts[-1]):
        return "(" + regroup(", ".join(parts[:-1])) + ") " + parts[-1]
    if not any(re.search(r"\band\b", p) for p in parts) and re.match(r"or\b", parts[-1]):
        return " or ".join(re.sub(r"^or\s+", "", p) for p in parts)
    # Where an "or" reaches back to: "Physics 1A, 1B, and 1C, or 6A, 6B, and
    # 6C" is a series against a series; "Chemistry 14B and 14BL, or 20B and
    # 30AL, 153A, …" is one pair against another, and 153A is required
    # either way. So an "or" after a part with its own "and" takes just that
    # part and the one after it; otherwise it takes the whole run before it
    # and the run after it (up to a part starting with "and").
    items = []          # each a part, or a list of alternatives (lists of parts)
    pending, series = [], None
    has_and = lambda p: re.search(r"\S\s+and\s+", p)

    def ends_series(at):
        """Does a part starting with "and" come after parts[at], before the next "or"?"""
        for later in parts[at + 1:]:
            if re.match(r"or\b", later):
                return False
            if re.match(r"and\b", later):
                return True
        return False
    for at, part in enumerate(parts):
        if re.match(r"or\b", part):
            part = re.sub(r"^or\s+", "", part)
            if series is not None:
                alts, single_left = series, False
            elif not pending and items and isinstance(items[-1], list):
                alts, single_left = items.pop(), True        # "…, or C and D, or E and F"
            elif pending and has_and(pending[-1]):
                items.extend(pending[:-1])
                alts, single_left, pending = [[pending[-1]]], True, []
            elif pending:
                alts, single_left, pending = [pending], False, []
            else:
                pending.append(part)
                continue
            alts.append([part])
            # The alternative goes on ("or 6A, 6B, and 6C") unless it's a pair
            # of its own, or one part against a pair ("…, or 7A, Chemistry 20A").
            if has_and(part) or (single_left and not ends_series(at)):
                items.append(alts)
                series = None
            else:
                series = alts
        elif series is not None:
            series[-1].append(part)
            if re.match(r"and\b", part):
                items.append(series)
                series = None
        else:
            pending.append(part)
    if series is not None:
        items.append(series)
    items.extend(pending)

    def wrap(p):
        """One requirement with "or" in it, in brackets. "or" binds loosest:
        "41 or Mathematics 170E and 170S or Statistics 100A and 100B" is
        41, or 170E and 170S, or 100A and 100B."""
        p = re.sub(r"^and\s+", "", p)
        if not re.search(r"\bor\b", p) or (p.startswith("(") and p.endswith(")")):
            return p
        options = split_words(p, "or")
        if len(options) > 1 and any(re.search(r"\band\b", o) for o in options):
            return "(" + " or ".join("(" + o + ")" if re.search(r"\band\b", o) else o for o in options) + ")"
        return "(" + p + ")"

    def alternatives(alts):
        alts = [list(alt) for alt in alts]
        for i in range(1, len(alts)):
            before = lead(re.sub(r"^and\s+", "", alts[i - 1][0]))
            if before and before.group(1) and re.match(number + r"\b", alts[i][0]):
                alts[i][0] = before.group(1) + alts[i][0]
        joined = [" and ".join(wrap(p) for p in alt) for alt in alts]
        return " or ".join("(" + j + ")" for j in joined)
    if len(items) == 1 and isinstance(items[0], list):
        return alternatives(items[0])
    return " and ".join("(" + alternatives(item) + ")" if isinstance(item, list) else wrap(item) for item in items)


def parse(parser, names, text, code):
    subject = code.rsplit(" ", 1)[0]
    # Subject names with commas in them ("Lesbian, Gay, Bisexual, Transgender,
    # and Queer Studies") become their codes first, so lists aren't split there.
    for name, short in names.comma_names:
        text = text.replace(name, short)
    # A part after "; and" that starts with a bare number ("; and (103L)")
    # is in the course's own subject, not the subject named last before it.
    # "3C (3C may be taken concurrently)": the note is taken out (its brackets
    # confuse the grouping) and 3C is marked afterwards.
    concurrent = re.findall(r"\((?:courses?\s+)?([A-Z]{0,2}\d+[A-Z]*)\s+may be taken concurrently\)", text)
    text = re.sub(r"\s*\((?:courses?\s+)?[A-Z]{0,2}\d+[A-Z]*\s+may be taken concurrently\)", "", text)
    # "Physics 1A, 1B, and 1C (may be taken concurrently), or 1AH, …": the note
    # is for the series before it; its courses are marked afterwards.
    def series_note(match):
        before = re.split(r";|,\s*or\b|\bor\b|\(", match.group(1))[-1]
        concurrent.extend(re.findall(r"\b([A-Z]{0,2}\d+[A-Z]*)\b", before))
        return match.group(1)
    text = re.sub(r"([^;]*?\d[A-Z]*)\s*\(may be taken concurrently\)(?=\s*(?:,\s*or\b|;|$))", series_note, text)
    # "(for life sciences majors)" says who an option is for; it isn't a requirement.
    text = re.sub(r"\s*\(for [^()]*\)", "", text)
    pieces = re.split(r"(;\s*(?:and\s+)?)", text)
    text = "".join(piece if i % 2 else regroup(re.sub(r"^(\(?)(?=(?:CM|MC|C|M)?\d)", r"\1course ", piece) if i else piece)
                   for i, piece in enumerate(pieces))
    parsed = parser.parse(names.to_parser(text, subject))
    parsed["requires"] = without_course(names.from_parser(parsed["requires"]), code)
    if concurrent:
        parsed["requires"] = marked_concurrent(parsed["requires"], set(concurrent))
    return parsed


def main():
    with open(INPUT, encoding="utf-8") as f:
        courses = json.load(f)["courses"]
    with open(SUBJECTS, encoding="utf-8") as f:
        subjects = json.load(f)
    names = Names(subjects, courses)
    parser = make_parser(names)
    results = []
    for course in courses:
        parsed = parse(parser, names, course["prereq_text"], course["code"])
        results.append({
            "code": course["code"], "prereq_text": course["prereq_text"], "requires": parsed["requires"],
            "source": "parser", "ambiguous": parsed["ambiguous"], "unparsed": parsed["unparsed"],
        })
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"courses": results}, f, indent=1, ensure_ascii=False)
    print("Wrote %s: %d courses, %d with leftover words, %d ambiguous" % (
        OUTPUT, len(results), sum(1 for r in results if r["unparsed"]), sum(1 for r in results if r["ambiguous"])))


if __name__ == "__main__":
    main()
