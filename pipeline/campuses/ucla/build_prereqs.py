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
        self.codes = set(self.real)

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


def make_parser(names):
    return Parser(names.codes, names.names, (), brackets=True)


def parse(parser, names, text, code):
    subject = code.rsplit(" ", 1)[0]
    parsed = parser.parse(names.to_parser(text, subject))
    parsed["requires"] = without_course(names.from_parser(parsed["requires"]), code)
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
