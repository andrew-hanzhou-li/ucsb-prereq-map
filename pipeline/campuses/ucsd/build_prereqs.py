"""
build_prereqs.py (UC San Diego): read every course's prerequisite text into a tree.

    python pipeline/campuses/ucsd/build_prereqs.py

Reads   data/ucsd/raw_courses.json   (from extract.py)
Writes  data/ucsd/prereqs.json       the same shape as UCSB's data/prereqs.json

The parser is shared with UCSB (pipeline/parser.py). What differs is
UCSD's subject codes and the other ways its catalog writes them.
"""

import json
import os
import re
import sys

PIPELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, PIPELINE)

from parser import Parser   # noqa: E402  (pipeline/parser.py, found through PIPELINE)

INPUT = os.path.join("data", "ucsd", "raw_courses.json")
OUTPUT = os.path.join("data", "ucsd", "prereqs.json")

# Other ways UCSD's catalog writes a subject before a course number. Matching
# ignores upper and lower case.
SUBJECT_NAMES = {
    "Math": "MATH",
    "Mathematics": "MATH",
    "Physics": "PHYS",
    "Chemistry": "CHEM",
    "Economics": "ECON",
    "Econ": "ECON",
    "Cognitive Science": "COGS",
}

# UCSD's own ways of writing conditions, tried before the shared ones in
# pipeline/parser.py.
EXTRA_RULES = [
    ("exam", r"\b(?:passing|qualifying)\s+score\s+on\s+(?:the\s+)?[\w ]{0,30}?(?:exam|test)\b"),
    ("exam", r"\b[\w ]{0,30}?placement\s+(?:exam|test)(?:ination)?(?:\s+qualifying\s+score)?"),
    ("exam", r"\bAP\s+[A-Z][\w ]{0,30}?score\s+of\s+\d"),
    ("standing", r"\b(?:freshman|sophomore|junior|senior)\s+or\s+(?:sophomore|junior|senior)\s+standing"),
    ("standing", r"\bcompletion\s+of\s+(?:\w+|\d+)\s+units(?:\s+of\s+UC\s+San\s+Diego\s+undergraduate\s+study)?"),
    # "restricted to X majors", stopping before "or by department approval"
    # or "with senior standing", which are conditions of their own.
    ("restriction", r"\brestricted\s+to\s+(?:(?!\b(?:or\s+(?:by\s+)?(?:department|consent|permission)|"
                    r"with\s+(?:\w+[- ])?(?:\w+\s+)?standing))[^;.§])*"),
    ("restriction", r"\b(?:students\s+must\s+)?(?:(?:submit\s+(?:an\s+)?applications?|apply)\b[^;.§]*?\s+and\s+)?"
                    r"(?:be\s+)?accepted\s+(?:in|into|to)\s+(?:the\s+)?[^;.§]*?program\b"),
    ("restriction", r"\b(?:formal\s+)?admittance\s+to\s+[^;.§]*"),
    ("consent", r"\bdepartment(?:al)?\s+(?:stamp|authorization|approval)(?:\s+(?:is\s+)?required)?"),
    ("consent", r"\benrollment\s+via\s+[^;.§]*"),
]

# A sentence saying the instructor can let anyone in: the whole requirement
# becomes "(...) or consent". Removed from the text before parsing.
CONSENT_FOR_ALL = re.compile(
    r"\s*(?:students\s+who\s+have\s+not\s+completed\s+(?:the\s+)?listed\s+prerequisites?\s+"
    r"may\s+enroll\s+with\s+(?:the\s+)?consent\s+of\s+(?:the\s+)?instructor|"
    r"consent\s+of\s+(?:the\s+)?instructor\s+if\s+students\s+do\s+not\s+meet\s+(?:the\s+)?prerequisites?|"
    r"[\w ,-]*students\s+cannot\s+enroll\s+without\s+(?:the\s+)?consent\s+of\s+(?:the\s+)?instructor)\.?",
    re.IGNORECASE)

# "one from COMM 100A, 100B, 100C" or "two of the following: ...": any of
# the listed courses (the count can't be shown on the map, so "two from"
# reads as "any of", like the catalog's own "or").
CHOICE_LIST = re.compile(
    r"\b(?:any\s+)?(?:one|two|three|four)(?:\s+courses?)?\s+(?:from|of|out\s+of)"
    r"(?:\s+the\s+following(?:\s+courses)?)?:?\s+(?P<items>[^;.]+)", re.IGNORECASE)

# Capitalized words written before a number that are not subjects.
NOT_SUBJECTS = {"GPA", "AP", "IB", "SAT", "ACT", "UC", "US", "USA", "TOEFL", "ELWR", "AM", "PM",
                "ID", "II", "III", "IV", "CA", "MCAT", "GRE", "A", "B", "C", "D", "E", "F"}


def subject_codes(courses):
    """UCSD's subject codes: those of its current courses, plus any written
    in capitals right before a number in a prerequisite (older or graduate
    subjects, like SOCB or FMPH, that a prerequisite can still name)."""
    codes = {c["subject"] for c in courses}
    for course in courses:
        for word in re.findall(r"\b([A-Z]{2,5}) \d", course["prereq_text"]):
            if word not in NOT_SUBJECTS:
                codes.add(word)
    return codes


def make_parser(courses):
    return Parser(subject_codes(courses), SUBJECT_NAMES, EXTRA_RULES)


def as_alternatives(match):
    """"one from A, B, and C" -> "(A or B or C)"."""
    items = [i for i in re.split(r"\s*,\s*(?:and\s+|or\s+)?|\s+or\s+", match.group("items").strip()) if i]
    return "(" + " or ".join(items) + ")"


def parse(parser, prereq_text):
    """The parser's answer for one course, with UCSD's two rewrites: choice
    lists, and consent that stands in for everything."""
    text, consent_for_all = CONSENT_FOR_ALL.subn("", prereq_text)
    text = CHOICE_LIST.sub(as_alternatives, text)
    # "MATH 20A or higher": the course named is the one the map can show.
    text = re.sub(r"(\b[A-Z]{2,5} \d+[A-Z]*) or higher\b", r"\1", text)
    # The language courses: "LIIT 1A with a grade of C– or better, or
    # equivalent and LIIT 1AX ...": each "or equivalent" belongs to its course.
    text = re.sub(r"(\b[A-Z]{2,5} \d+[A-Z]* with a grade of [A-D][+\-–]? or better), or equivalent\b",
                  r"(\1 or equivalent)", text)
    # "or by department approval" -> "or department approval"
    text = re.sub(r"\bor\s+by\s+(department|consent|permission)\b", r"or \1", text)
    parsed = parser.parse(text)
    if consent_for_all:
        consent = {"type": "condition", "kind": "consent", "text": "consent of instructor"}
        tree = parsed["requires"]
        if tree is None:
            parsed["requires"] = consent
        elif tree["type"] == "or":          # "A or B" + consent -> "A or B or consent"
            parsed["requires"] = dict(tree, items=tree["items"] + [consent])
        else:
            parsed["requires"] = {"type": "or", "items": [tree, consent]}
    return parsed


def main():
    with open(INPUT, encoding="utf-8") as f:
        courses = json.load(f)["courses"]
    parser = make_parser(courses)
    results = []
    for course in courses:
        parsed = parse(parser, course["prereq_text"])
        results.append({
            "code": course["code"],
            "prereq_text": course["prereq_text"],
            "requires": parsed["requires"],
            "source": "parser",
            "ambiguous": parsed["ambiguous"],
            "unparsed": parsed["unparsed"],
        })
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"courses": results}, f, indent=1, ensure_ascii=False)
    print("Wrote %s: %d courses, %d with leftover words, %d ambiguous" % (
        OUTPUT, len(results), sum(1 for r in results if r["unparsed"]),
        sum(1 for r in results if r["ambiguous"])))


if __name__ == "__main__":
    main()
