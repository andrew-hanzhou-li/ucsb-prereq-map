"""
extract.py (UCLA): read the saved catalog records into a course list.

    python pipeline/campuses/ucla/extract.py

Reads   data/ucla/raw/courses/*.json    (from fetch.py)
        data/ucla/offerings.json        the quarters each course ran (if present)
Writes  data/ucla/raw_courses.json      every undergraduate course, in the same
                                        shape as UCSB's data/raw_courses.json

How a course record looks
-------------------------
    code                 "COM SCI 32"
    title                "Introduction to Computer Science II"
    credit_points_header "4 units"
    course_level         "Undergraduate lower division (0-99)"
    description          "<p>Lecture, four hours; discussion, two hours; outside
                         study, six hours. Enforced requisite: course 31.
                         Object-oriented software development. … Letter grading.</p>"

The requisites are sentences inside the description:
    "Enforced requisite: course 31."            needed first (the system checks)
    "Requisites: courses 120A, 120B, 120C."     needed first (not checked)
    "Enforced corequisite: Mathematics 32B."    before or in the same quarter
    "Recommended requisite: course 1."          advice only: kept as a comment
    "Recommended preparation: …"                advice only: kept as a comment
    "M7A is requisite to M7B, …"                about a later course: a comment
They're taken out of the description into prereq_text (the required ones,
corequisites marked "(may be taken concurrently)") and comments (the rest).

Graduate courses (200 and up, and the 300-500 series) are left out: the site
is for undergraduates; the record's course_level says which is which.
"""

import glob
import html
import json
import os
import re

RAW_DIR = os.path.join("data", "ucla", "raw", "courses")
OFFERINGS = os.path.join("data", "ucla", "offerings.json")
OUTPUT = os.path.join("data", "ucla", "raw_courses.json")
SITE = "https://catalog.registrar.ucla.edu"
YEAR = "2026"
QUARTER_ORDER = ["Fall", "Winter", "Spring", "Summer"]

# A requisite sentence: its label, then everything up to the sentence's end.
# (A period inside a code or number, "3.5", doesn't end it.)
REQUISITE = re.compile(
    r"(?P<label>(?:Enforced\s+|Recommended\s+)?(?:co)?requisites?|Recommended\s+preparation|Prerequisites?)\s*:\s*"
    r"(?P<text>(?:[^.]|\.(?=\d))*)\.", re.IGNORECASE)
SEQUENCE_NOTE = re.compile(r"(?:[A-Z]{0,2}\d+[A-Z]*\s+is\s+)?requisite\s+to\s+(?:[^.]|\.(?=\d))*\.", re.IGNORECASE)


def plain_text(markup):
    """HTML -> one line of text."""
    text = re.sub(r"<[^>]+>", " ", markup or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def level_of(record):
    label = record.get("course_level") or ""
    label = label.get("label", "") if isinstance(label, dict) else label
    if "lower division" in label.lower():
        return "lower"
    if "upper division" in label.lower():
        return "upper"
    return "graduate"


def split_description(text):
    """(description, prereq_text, comments): the requisite sentences taken out."""
    required, comments = [], []

    def take(match):
        label = match.group("label").lower()
        words = match.group("text").strip()
        if label.startswith("recommended"):
            comments.append(match.group(0).strip())
        elif "corequisite" in label:
            required.append("(" + words + ") (may be taken concurrently)")
        else:
            required.append(words)
        return " "

    body = REQUISITE.sub(take, text)
    body = SEQUENCE_NOTE.sub(lambda m: comments.append(m.group(0).strip()) or " ", body)
    prereq = "; and ".join(r for r in required if r)
    return re.sub(r"\s+", " ", body).strip(), prereq, " ".join(comments)


def units_of(record):
    header = record.get("credit_points_header") or record.get("credit_points") or ""
    match = re.search(r"(\d+(?:\.\d+)?)(?:\s*(?:to|-|or)\s*(\d+(?:\.\d+)?))?", str(header))
    if not match:
        return ""
    return match.group(1) + ("-" + match.group(2) if match.group(2) else "")


def main():
    offerings = {}
    if os.path.exists(OFFERINGS):
        with open(OFFERINGS, encoding="utf-8") as f:
            offerings = json.load(f)["courses"]
    courses, skipped = [], 0
    for path in sorted(glob.glob(os.path.join(RAW_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        code = re.sub(r"\s+", " ", (record.get("code") or "").strip())
        level = level_of(record)
        if not code or level == "graduate":
            skipped += 1
            continue
        subject, number = code.rsplit(" ", 1)
        description, prereq, comments = split_description(plain_text(record.get("description")))
        name = os.path.basename(path)[:-5]
        courses.append({
            "code": code, "subject": subject, "number": number, "level": level,
            "title": (record.get("title") or "").strip(), "units": units_of(record),
            "offered": offerings.get(code, []), "offered_source": "schedule" if code in offerings else "",
            "prereq_text": prereq, "comments": comments, "description": description,
            "departments": [subject], "cross_listed": [], "tags": [],
            "url": SITE + "/course/" + YEAR + "/" + name,
        })
    # (A few courses have a letter for a number: AERO ST A.)
    number_of = lambda n: int(re.search(r"\d+", n).group()) if re.search(r"\d", n) else 0
    courses.sort(key=lambda c: (c["subject"], number_of(c["number"]), c["number"]))
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"catalog_year": "2026-27", "courses": courses}, f, indent=1, ensure_ascii=False)
    print("Wrote %s: %d undergraduate courses (%d graduate left out), %d with requisites"
          % (OUTPUT, len(courses), skipped, sum(1 for c in courses if c["prereq_text"])))


if __name__ == "__main__":
    main()
