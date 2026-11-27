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
    ("exam", r"\bAP\s+[A-Z][\w ]{0,30}?score\s+of\s+\d(?:\s+or\s+(?:more|higher|better|above))?"),
    # "junior or senior standing", "sophomore, junior, and senior standing",
    # "restricted enrollment to ...", "of first-year standing"
    ("standing", r"\b(?:restricted\s+enrollment\s+to\s+)?(?:of\s+)?(?:(?:freshman|first-year|sophomore|junior|senior)"
                 r"(?:\s*,\s*(?:and\s+|or\s+)?|\s+(?:and|or)\s+))+(?:freshman|first-year|sophomore|junior|senior)\s+standing"),
    ("standing", r"\b(?:student\s+must\s+be\s+)?of\s+(?:freshman|first-year|sophomore|junior|senior)\s+standing"),
    ("standing", r"\b(?:must\s+)?complet(?:ion\s+of|e)\s+(?:at\s+least\s+)?(?:\w+|\d+)\s+units(?:\s+of\s+(?:credit|undergraduate\s+study))?"
                 r"(?:\s+(?:of|at)\s+UC\s+San\s+Diego(?:\s+undergraduate\s+study)?)?"),
    # "restricted to X majors", stopping before "or by department approval"
    # or "with senior standing", which are conditions of their own.
    ("restriction", r"\b(?:enrollment\s+)?(?:restricted|limited)\s+(?:to|for)\s+(?:(?!\b(?:or\s+(?:by\s+)?(?:department|consent|permission)|"
                    r"with\s+(?:\w+[- ])?(?:\w+\s+)?standing))[^;.§])*"),
    ("restriction", r"\b(?:students\s+must\s+)?(?:(?:submit\s+(?:an\s+)?applications?|apply)\b[^;.§]*?\s+and\s+)?"
                    r"(?:be\s+)?accepted\s+(?:in|into|to)\s+(?:the\s+)?[^;.§]*?program\b"),
    # "admission to the major", stopping before "and a grade of C– in X" or a course.
    ("restriction", r"\b(?:formal\s+)?(?:admittance|acceptance|admission)\s+(?:to|in|into)\s+"
                    r"(?:(?!\band\s+(?:a\s+grade|[A-Z]{2,5}\s\d))[^;.§])*"),
    ("restriction", r"\b(?:students\s+)?must\s+apply\s+(?:for|to)\s+[^;.§]*?\s+and\s+be\s+(?:accepted|approved)(?:\s+to\s+enroll)?"),
    ("restriction", r"\b(?:students\s+)?must\s+be\s+(?:an?\s+)?[\w ]{0,40}?(?:students?|participants\s+in\s+[^;.§]*)"),
    # Major codes: "ED25 major", "CS25, CS26, and CS27 majors"
    ("restriction", r"\b[A-Z]{2} ?\d{2}(?:(?:,\s*(?:or\s+|and\s+)?|\s+or\s+|\s+and\s+)[A-Z]{2} ?\d{2})*\s+majors?\b"),
    ("consent", r"(?i:\b(?:instructor|department)\s*(?:and|/)\s*(?:instructor|department)\s+(?:approval|consent|permission)(?:\s+(?:is\s+)?required)?)"),
    ("consent", r"(?i:\b(?:approval\s+of\s+the\s+|an\s+approved\s+)?special\s+studies\s+(?:online\s+)?(?:form|application))"),
    ("consent", r"\bdepartment(?:al)?\s+(?:stamp|authorization|approval)(?:\s+(?:is\s+)?required)?"),
    ("consent", r"\benrollment\s+via\s+[^;.§]*"),
    ("consent", r"\b(?:students\s+)?must\s+meet\s+with\s+(?:a\s+)?faculty\s+member\s+for\s+approval[^;.§]*"),
    # "bioengineering, bioengineering: biotechnology, or ... majors only": no
    # course codes inside (no digits), so a course before it isn't swallowed.
    ("restriction", r"\b[a-z][^;.§\d]{0,200}?\bmajors?\s+only\b"),
    # "ethnic studies major or minor", "international studies major with ...", "a Regent's Scholar"
    ("restriction", r"\b(?:[a-z]+\s){1,3}major\s+or\s+minor\b"),
    ("restriction", r"\b(?:[a-z]+\s){1,3}major(?=\s+with\b)"),
    ("restriction", r"\b(?:a\s+)?regent[’']?s\s+scholar\b"),
    ("consent", r"\bby\s+invitation(?:\s+only)?"),
    ("consent", r"\b(?:and\s+)?(?:the\s+)?director\s+of\s+(?:[^;.§]*?program\b|[^;.,§]*)"),
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
    # (Not "consent of department": after "majors only" it waives that rule alone.)
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
    return Parser(subject_codes(courses), SUBJECT_NAMES, EXTRA_RULES, brackets=True)


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
        # "Music majors are recommended to take MUS 101C concurrently."
        if re.search(r"\b(?:are|is)\s+(?:strongly\s+)?recommended\s+to\b|\brecommended\s+that\b", body, re.IGNORECASE):
            continue
        if not re.search(r"\brecommended$", body):
            kept.append(clause)
            continue
        items = body.split(",")
        last = items[-1].strip()
        if len(items) == 1 or re.match(r"^(?:or|and)\b", last):
            continue                                    # the whole clause is a recommendation
        kept.append(",".join(items[:-1]).rstrip() + clause[len(body):])
    return " ".join(kept).strip()


def previous_course(code):
    """The course before `code` in its sequence: JAPN 140B -> JAPN 140A,
    CHIN 100BM -> CHIN 100AM. None when there's no earlier letter."""
    match = re.match(r"^([A-Z ]+ \d+)([B-Z])([A-Z]*)$", code or "")
    if not match:
        return None
    return match.group(1) + chr(ord(match.group(2)) - 1) + match.group(3)


def subject_list(match):
    """"POLI/ECON 5(D)" -> "(POLI 5 or POLI 5D or ECON 5 or ECON 5D)"."""
    subjects = match.group("subjects").split("/")
    numbers = [match.group("number")]
    if match.group("suffix"):
        numbers.append(match.group("number") + match.group("suffix"))
    return "(" + " or ".join("%s %s" % (s, n) for s in subjects for n in numbers) + ")"


def twin_sequence(match):
    """"PHYS 2A/2AR-B-C-D" -> "((PHYS 2A or PHYS 2AR) and PHYS 2B and PHYS 2C and PHYS 2D)"."""
    subject, number, first, twin = match.group("subject"), match.group("number"), match.group("first"), match.group("twin")
    rest = ["%s %s%s" % (subject, number, letter) for letter in match.group("rest").strip("-").split("-")]
    return "((%s %s%s or %s %s) and %s)" % (subject, number, first, subject, twin, " and ".join(rest))


def courses_for_this_course(text, number):
    """"EDS 135, 136, or 129A for 129B, and 129B for 129C": each "<courses>
    for <number>" phrase is about one course of the sequence. Keep the
    courses of the phrase for this one, drop the others."""
    course = r"(?:[A-Z]{2,5} )?\d+[A-Z]*"
    # Each join needs a comma or "or", so a run of digits can't split many
    # ways; "and" ends the list ("..., or 146, and 128A for 128B").
    join = r"(?:,\s*(?:or\s+)?|\s+or\s+)"
    phrase = re.compile(r"(%s(?:%s%s)*)\s+for\s+(?:[A-Z]{2,5}\s)?(\d+[A-Z]*)\b" % (course, join, course))
    if not phrase.search(text):
        return text
    text = phrase.sub(lambda m: m.group(1) if m.group(2) == number else "", text)
    # Tidy the joins left by dropped phrases: ", and ." -> "."
    text = re.sub(r"(?:,\s*(?:and|or)?\s*)+(?=[;.]|$)", "", text)
    text = re.sub(r"\b(?:completed|and|or)\s*(?=[;.]|$)", "", text)
    return re.sub(r"\s{2,}", " ", text)


def for_this_course(text, code):
    """A sequence's shared text with a part per course: "none for 5A; for
    5B, two or more years of French; LIFR 5B for 5C" -> the part for this
    course ("two or more years of French" for LIFR 5B). Only when every
    clause names the course it's for."""
    if not code:
        return text
    number = code.split(" ")[-1]
    clauses = [c.strip() for c in re.split(r";", text.rstrip(". ")) if c.strip()]
    pattern = r"\bfor\s+(?:[A-Z]{2,5}\s)?(\d+[A-Z]*)\b"
    if len(clauses) < 2 or not all(re.search(pattern, c) for c in clauses):
        return courses_for_this_course(text, number)
    for clause in clauses:
        if any(found == number for found in re.findall(pattern, clause)):
            part = re.sub(r",?\s*\bfor\s+(?:[A-Z]{2,5}\s)?\d+[A-Z]*\s*,?\s*", " ", clause).strip(" ,")
            return "none." if part.lower() in ("none", "") else part + "."
    # A part for each of the other courses and none for this one: nothing
    # is asked of it ("none for 5A; for 5B, ..." on LISP 5D).
    return "none."


def expand_shorthand(text, code):
    """UCSD's shorthand, written out so the shared parser reads it."""
    # "(formerly MUS 161)": an old number for the same course.
    text = re.sub(r"\s*\(formerly [^)]*\)", "", text, flags=re.IGNORECASE)
    # "may require ... such as POLI 30": an example, not a requirement.
    text = re.sub(r"[,;]?\s*\(?\bsuch as\b[^;.)]*\)?", "", text)
    # "SYN 1/1R, must be taken for a letter grade to count toward ...": about grading.
    text = re.sub(r"[,;]?\s*must be taken for a letter grade[^;.]*", "", text, flags=re.IGNORECASE)
    # "Prerequisite courses must have been completed with a grade of C–":
    # only the grade matters ("with a grade of C–", applied to every course).
    text = re.sub(r"\b(?:all\s+)?(?:listed\s+)?prerequisites?(?:\s+courses?)?\s+must\s+(?:have\s+been\s+|be\s+)?completed\s+(?=with\b)",
                  "", text, flags=re.IGNORECASE)
    # "Must be take(n) concurrently with PSYC 199" -> "concurrent enrollment in PSYC 199"
    text = re.sub(r"\bmust\s+be\s+taken?\s+concurrently\s+with\b", "concurrent enrollment in", text, flags=re.IGNORECASE)
    # "PHYS 2A/2AR-B-C-D": the first course or its remote twin, then the rest of the sequence.
    text = re.sub(r"\b(?P<subject>[A-Z]{2,5}) (?P<number>\d+)(?P<first>[A-Z])/(?P<twin>\d+[A-Z]+R)(?P<rest>(?:-[A-Z])+)\b",
                  twin_sequence, text)
    # "POLI/ECON 5(D)", "POLI 30(D)": either subject, with or without the letter.
    text = re.sub(r"\b(?P<subjects>[A-Z]{2,5}(?:/[A-Z]{2,5})+) (?P<number>\d+)(?:\((?P<suffix>[A-Z]+)\))?", subject_list, text)
    text = re.sub(r"\b([A-Z]{2,5}) (\d+)\(([A-Z]+)\)", r"(\1 \2 or \1 \2\3)", text)
    # "MATH 31 AH", "MATH 20 C": a space slipped into the code.
    text = re.sub(r"\b([A-Z]{2,5} \d+) ([A-Z]{1,2})\b(?=\s*(?:[).,;]|\band\b|\bor\b|$))", r"\1\2", text)
    # "May be taken concurrently with ECON 102 or after completion of ECON 102"
    text = re.sub(r"\bmay\s+be\s+taken\s+concurrently\s+with\s+([A-Z]{2,5} \d+[A-Z]*)\s+or\s+after\s+completion\s+of\s+\1\b",
                  r"concurrent enrollment in \1", text, flags=re.IGNORECASE)
    # Words around a course that don't change it.
    text = re.sub(r"\b(?:successful|satisfactory)\s+completion\s+of\s+|\bprevious\s+enrollment\s+in\s+", "", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"\bsatisfaction\s+of\s+(?:the\s+)?([A-Z]{2,5} \d+[A-Z]*)(?:\s+requirement)?", r"\1", text)
    text = re.sub(r"\s*\(P/NP grades only\)", "", text)
    # "the combination of PHYS 100A and 110A": both, as one choice.
    text = re.sub(r"\bthe\s+combination\s+of\s+((?:[A-Z]{2,5} )?\d+[A-Z-]*(?:\s+and\s+(?:[A-Z]{2,5} )?\d+[A-Z-]*)+)",
                  r"(\1)", text)
    # "students must apply to enroll in order to gauge their experience": the
    # application is how consent is asked for; "Consent of instructor" follows.
    text = re.sub(r"\b(?:students\s+)?must\s+apply\s+to\s+enroll\s+in\s+order\s+to\b[^.;]*[.;]?\s*", "", text, flags=re.IGNORECASE)
    # "Department approval required for nonmajors": majors, or department approval.
    text = re.sub(r"\bdepartment\s+approval\s+(?:is\s+)?required\s+for\s+non-?majors\b",
                  "restricted to majors or department approval", text, flags=re.IGNORECASE)
    # "ETHN 100A, ethnic studies major or minor, or consent of instructor": the
    # course and the major, or consent.
    text = re.sub(r"(\b[A-Z]{2,5} \d+[A-Z]*), ((?:[a-z]+ ){1,3}majors? or minors?\b)", r"\1 and \2", text)
    # "Restricted to students with upper-division standing": standing.
    text = re.sub(r"\brestricted\s+to\s+students\s+with\s+((?:upper|lower)-division|junior|senior|sophomore)\s+standing",
                  r"\1 standing", text, flags=re.IGNORECASE)
    # "approval required to monitor enrollment and to ensure ...": the reason isn't a requirement.
    text = re.sub(r"\brequired\s+to\s+(?:monitor|ensure|confirm)\b[^.;]*", "required", text, flags=re.IGNORECASE)
    # "CAT 2 and 3 or CCE 1 and 2 or ...": a choice of two-course pairs, each
    # one subject. (Not "ECON 1 or 100B and 2 or 3", where the pair has no subject.)
    text = re.sub(r"\b([A-Z]{2,5} \d+)([A-Z]+) (and|or) ([A-Z])\b(?![\s-]*\d)(?!\w)", r"\1\2 \3 \1\4", text)
    pair_pattern = re.compile(r"(?:(?<=^)|(?<=\bor ))([A-Z]{2,5}) (\d+[A-Z]*) and (\1 )?(\d+[A-Z]*)"
                              r"(?=\s+or\s+[A-Z]{2,5}\s\d|\s*[.;]?\s*$)")
    pairs_in_text = len(pair_pattern.findall(text))

    def pair(match):
        subject, first, repeated, second = match.groups()
        # With the subject written twice ("WCWP 10A and WCWP 10B"), only a
        # lettered pair of one number, and only in a chain of pairs: alone,
        # "COGS 14A and COGS 14B or MATH 11" is the usual or-groups-joined-by-and.
        if repeated and (pairs_in_text < 2 or re.match(r"\d+", first).group() != re.match(r"\d+", second).group()):
            return match.group(0)
        return "(%s %s and %s %s)" % (subject, first, subject, second)
    text = pair_pattern.sub(pair, text)
    # "ANSC 121, ANSC 148, ..., or ANTH 103, department approval required, and
    # upper-division standing": the course list is one choice.
    text = re.sub(r"(?<!\bor )(?<!\band )(?<!, )\b((?:[A-Z]{2,5} \d+[A-Z]*, )+or [A-Z]{2,5} \d+[A-Z]*)\b(?=,\s+[a-z])",
                  lambda m: "(" + re.sub(r",\s+(?:or\s+)?", " or ", m.group(1)) + ")", text)
    # "PHYS 2A and B" -> "PHYS 2A and PHYS 2B"
    text = re.sub(r"\b([A-Z]{2,5} \d+)([A-Z]+) (and|or) ([A-Z])\b(?![\s-]*\d)(?!\w)", r"\1\2 \3 \1\4", text)
    # "LISP 1D/DX" -> "LISP 1D or LISP 1DX"; "DSC 40B/R" -> "DSC 40B or DSC 40BR"
    def letter_twin(match):
        subject, number, letters, after = match.groups()
        twin = number + (after if after.startswith(letters) else letters + after)
        return "%s %s%s or %s %s" % (subject, number, letters, subject, twin)
    text = re.sub(r"\b([A-Z]{2,5}) (\d+)([A-Z]+)/([A-Z]{1,3})\b(?!\s?\d)", letter_twin, text)
    # "EDS 139 must be taken as a corequisite" -> "concurrent enrollment in EDS 139"
    text = re.sub(r"\b([A-Z]{2,5} \d+[A-Z]*) must be taken as (?:a )?corequisite", r"concurrent enrollment in \1", text)
    # "EDS 130 or ... or 146 must be completed before EDS 128A": the list is the requirement.
    text = re.sub(r"\s+must\s+be\s+completed\s+before\s+(?:[A-Z]{2,5}\s)?\d+[A-Z]*", "", text, flags=re.IGNORECASE)
    # "must have successfully completed EDS 135" -> "EDS 135"
    text = re.sub(r"\bmust\s+have\s+(?:successfully\s+)?completed\s+", "", text, flags=re.IGNORECASE)
    # "undergraduate: BILD 3 or consent. Graduate: graduate-level standing ...": the undergraduate part.
    text = re.sub(r"(?<!under)\bgraduates?:\s*[^.]*\.?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bundergraduates?:\s*", "", text, flags=re.IGNORECASE)
    text = for_this_course(text, code)
    # "EDS 128A and EDS 128B are restricted for students applying to ...":
    # the courses are what's restricted, not requirements.
    text = re.sub(r"\b(?:[A-Z]{2,5} )?\d+[A-Z]*(?:\s+and\s+(?:[A-Z]{2,5} )?\d+[A-Z]*)*\s+(?:are|is)\s+(restricted|limited)\b",
                  r"\1", text)
    # "EDS (20S or 30 or 31)": the subject goes inside the brackets.
    text = re.sub(r"\b([A-Z]{2,5}) \((\d+[A-Z]*\s+(?:or|and)\s)", r"(\1 \2", text)
    # "previous course or consent": the course before this one in its sequence.
    before = previous_course(code)
    if before:
        text = re.sub(r"\bprevious\s+course\b", before, text, flags=re.IGNORECASE)
    return text


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
    text = expand_shorthand(text, code)
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
    if re.search(r"\b(?:restricted\s+to|open\s+to)\s+(?:\w+\s+){0,2}?(?:seniors?|juniors?|upper-division)\b|"
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
