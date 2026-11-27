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
    ("restriction", r"\b(?:formal\s+)?(?:admittance|acceptance)\s+(?:to|in|into)\s+[^;.§]*"),
    ("restriction", r"\b(?:students\s+)?must\s+be\s+(?:an?\s+)?[\w ]{0,40}?(?:students?|participants\s+in\s+[^;.§]*)"),
    # Major codes: "ED25 major", "CS25, CS26, and CS27 majors"
    ("restriction", r"\b[A-Z]{2}\d{2}(?:(?:,\s*(?:or\s+|and\s+)?|\s+or\s+|\s+and\s+)[A-Z]{2}\d{2})*\s+majors?\b"),
    ("consent", r"\bdepartment(?:al)?\s+(?:stamp|authorization|approval)(?:\s+(?:is\s+)?required)?"),
    ("consent", r"\benrollment\s+via\s+[^;.§]*"),
    ("consent", r"\bby\s+invitation(?:\s+only)?"),
]

# A sentence saying the instructor can let anyone in: the whole requirement
# becomes "(...) or consent". Removed from the text before parsing.
CONSENT_FOR_ALL = re.compile(
    r"\s*(?:students\s+who\s+have\s+not\s+completed\s+(?:the\s+)?(?:listed\s+)?prerequisites?(?:\(s\))?\s+"
    r"may\s+enroll\s+with\s+(?:the\s+)?consent\s+of\s+(?:the\s+)?instructor|"
    r"consent\s+of\s+(?:the\s+)?instructor\s+if\s+students\s+do\s+not\s+meet\s+(?:the\s+)?prerequisites?|"
    r"[\w ,-]*students\s+cannot\s+enroll\s+without\s+(?:the\s+)?consent\s+of\s+(?:the\s+)?instructor|"
    # "...; MAE 143B; and MAE 170, or consent of instructor." at the very end:
    # UCSD means consent instead of everything before it.
    r"[,;]?\s+or\s+(?:by\s+)?(?:the\s+)?consent\s+of\s+(?:the\s+)?instructor\.?\s*$)\.?",
    re.IGNORECASE)

# "one from COMM 100A, 100B, 100C" or "two of the following: ...": any of
# the listed courses (the count can't be shown on the map, so "two from"
# reads as "any of", like the catalog's own "or").
CHOICE_LIST = re.compile(
    r"\b(?:any\s+(?:one\s+)?courses?|(?:any\s+)?(?:one|two|three|four)(?:\s+courses?)?)\s+(?:from|of|out\s+of)"
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
    """"one from A, B, and C" -> "(A or B or C)". Words between "the
    following" and the colon stay after the list: "any one of the following
    or department approval: A, B" -> "(A or B) or department approval"."""
    text = match.group("items").strip()
    before = ""
    if ":" in text:
        before, text = text.split(":", 1)
    items = [i for i in re.split(r"\s*,\s*(?:and\s+|or\s+)?|\s+or\s+", text.strip()) if i]
    return "(" + " or ".join(items) + ")" + (" " + before.strip() if before.strip() else "")


def without_course(node, code):
    """The tree with `code` taken out: a course can't require itself (ECE
    190's text says "The department stamp is required to enroll in ECE 190")."""
    if node is None:
        return None
    if node["type"] == "course":
        return None if node["code"] == code else node
    if node["type"] in ("and", "or"):
        items = [i for i in (without_course(i, code) for i in node["items"]) if i is not None]
        return None if not items else items[0] if len(items) == 1 else dict(node, items=items)
    return node


def without_recommendations(text):
    """Take out what's only recommended, keeping what's required:
        "CHEM 40B (a grade of C ... is strongly recommended)"   -> "CHEM 40B"
        "upper-division standing and background in X is recommended" -> "upper-division standing"
        "consent of instructor, MUS 171 recommended"             -> "consent of instructor"
        "MUS 172; MUS 4, 8–10, or 120 recommended"               -> "MUS 172"
    In a clause ending "recommended", only its last comma item is, unless
    that item starts with "or"/"and" (then the whole list is)."""
    text = re.sub(r"\s*\([^()]*\brecommended\b[^()]*\)", "", text)
    text = re.sub(r"\s+and\s+[^;,.()]*?\b(?:is|are)\s+(?:strongly\s+)?recommended\b", "", text)
    clauses = re.split(r"(?<=[;.])\s+", text)
    kept = []
    for clause in clauses:
        body = clause.rstrip(";. ")
        if not re.search(r"\brecommended$", body):
            kept.append(clause)
            continue
        items = body.split(",")
        last = items[-1].strip()
        if len(items) == 1 or re.match(r"^(?:or|and)\b", last):
            continue                                    # the whole clause is a recommendation
        kept.append(",".join(items[:-1]).rstrip() + clause[len(body):])
    return " ".join(kept).strip()


def parse(parser, prereq_text, code=None):
    """The parser's answer for one course (`code`), with UCSD's rewrites:
    recommendations dropped, choice lists, consent that stands in for
    everything, and the course itself left out."""
    # "...; MUS 4, 8–10, or 120 recommended." and "MUS 170 recommended; ...":
    # a recommendation isn't a requirement.
    text = without_recommendations(prereq_text)
    # "...; students who have completed MATH 154 ... may not receive credit
    # for CSE 21; ...": about credit, not a requirement.
    text = re.sub(r"(?:^|;)\s*[^;.]*\b(?:may not|will not|cannot) receive (?:duplicate )?credit\b[^;.]*", "", text).lstrip("; ")
    # "none. Open to visual arts majors": "none" is about courses; the rest still counts.
    text = re.sub(r"^\s*none\.\s*(?=\S)", "", text, flags=re.IGNORECASE)
    # "AP Calculus AB score of 3 (or equivalent AB subscore on BC exam)": part of the exam.
    text = re.sub(r"(score of \d)\s*\(or equivalent[^)]*\)", r"\1", text)
    consent_for_all = 0
    match = CONSENT_FOR_ALL.search(text)
    # A plain list ending ", or consent of instructor" ("BILD 1, BILD 2,
    # BILD 3, or consent of instructor") already reads right; only rewrite
    # when something before it is joined with "and" or ";".
    if match and (not match.group(0).lstrip(",; ").lower().startswith("or ") or
                  re.search(r";|\band\b", text[:match.start()])):
        text, consent_for_all = text[:match.start()] + text[match.end():], 1
    text = CHOICE_LIST.sub(as_alternatives, text)
    # "CHEM 7L or 7LM and CHEM 40A, 40AH, or 41A": the comma list after "and"
    # is one choice -> "... and (CHEM 40A or 40AH or 41A)".
    course = r"(?:[A-Z]{2,5}\s)?\d+[A-Z]*"
    text = re.sub(r"\band\s+(%s(?:,\s+%s)+),?\s+or\s+(%s)" % (course, course, course),
                  lambda m: "and (" + re.sub(r",\s+", " or ", m.group(1)) + " or " + m.group(2) + ")", text)
    # "DSC 10/R": the course or its remote twin, DSC 10R.
    text = re.sub(r"\b([A-Z]{2,5} \d+[A-Z]*)/R\b", r"\1 or \1R", text)
    # "MATH 20A or higher": the course named is the one the map can show.
    text = re.sub(r"(\b[A-Z]{2,5} \d+[A-Z]*) or higher\b", r"\1", text)
    # The language courses: "LIIT 1A with a grade of C– or better, or
    # equivalent and LIIT 1AX ...": each "or equivalent" belongs to its course.
    text = re.sub(r"(\b[A-Z]{2,5} \d+[A-Z]* with a grade of [A-D][+\-–]? or better), or equivalent\b",
                  r"(\1 or equivalent)", text)
    # "or by department approval" -> "or department approval"
    text = re.sub(r"\bor\s+by\s+(department|consent|permission)\b", r"or \1", text)
    parsed = parser.parse(text)
    parsed["requires"] = without_course(parsed["requires"], code)
    # "Restricted to seniors within the major", "upper-division public health
    # majors only": class standing too.
    if re.search(r"\b(?:restricted\s+to|open\s+to)\s+(?:\w+\s+){0,2}?(?:seniors|juniors|upper-division)\b|"
                 r"\bupper-division\s+[\w ]{0,40}majors\s+only\b", text, re.IGNORECASE):
        standing = {"type": "condition", "kind": "standing", "text": "class standing"}
        tree = parsed["requires"]
        already = tree is not None and any(
            i.get("kind") == "standing" for i in ([tree] if tree["type"] != "and" else tree["items"]))
        if already:
            pass
        elif tree is None:
            parsed["requires"] = standing
        elif tree["type"] == "and":
            parsed["requires"] = dict(tree, items=tree["items"] + [standing])
        else:
            parsed["requires"] = {"type": "and", "items": [tree, standing]}
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
        parsed = parse(parser, course["prereq_text"], course["code"])
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
