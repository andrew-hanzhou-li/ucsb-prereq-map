"""
extract_offerings.py (UCLA): the quarters each course ran.

    python pipeline/campuses/ucla/extract_offerings.py

Reads   data/ucla/raw/soc/<TERM>/*.html     (from fetch_offerings.py)
Writes  data/ucla/offerings.json            {"terms": [...], "courses": {"COM SCI 31": ["Fall", "Winter", "Spring"], ...}}

Each course on a page is a button whose id is the subject and number run
together and whose text starts with the number: id="COMSCI0051AM-title" …
>M51A - Logic Design of Digital Systems. The subject comes from the file
name (the page is one subject's), the number from the text. A course counts
as offered in a quarter if it ran then in either year fetched; the summer
sessions (term codes ending in a digit) count as Summer. extract.py reads
this file into each course's "offered".
"""

import glob
import json
import os
import re

SOC_DIR = os.path.join("data", "ucla", "raw", "soc")
SUBJECTS = os.path.join("data", "ucla", "subjects.json")
OUTPUT = os.path.join("data", "ucla", "offerings.json")
QUARTER_OF = {"F": "Fall", "W": "Winter", "S": "Spring"}
QUARTER_ORDER = ["Fall", "Winter", "Spring", "Summer"]
COURSE_BUTTON = re.compile(r'id="\w+-title"[^>]*>\s*([A-Z]{0,2}\d+[A-Z]*)\s+-\s')


def main():
    with open(SUBJECTS, encoding="utf-8") as f:
        by_file = {re.sub(r"[^A-Za-z0-9]+", "_", code): code for code in json.load(f)}
    offered = {}
    terms = sorted(os.listdir(SOC_DIR)) if os.path.isdir(SOC_DIR) else []
    for term in terms:
        quarter = QUARTER_OF.get(term[-1], "Summer" if term[-1].isdigit() else None)
        if not quarter:
            continue
        for path in glob.glob(os.path.join(SOC_DIR, term, "*.html")):
            subject = by_file.get(re.sub(r"-\d+\.html$", "", os.path.basename(path)))
            if not subject:
                continue
            with open(path, encoding="utf-8") as f:
                for number in COURSE_BUTTON.findall(f.read()):
                    offered.setdefault(subject + " " + number, set()).add(quarter)
    courses = {code: [q for q in QUARTER_ORDER if q in quarters] for code, quarters in sorted(offered.items())}
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"terms": terms, "courses": courses}, f, indent=1)
    print("Wrote %s: %d courses from %d terms (%s)" % (OUTPUT, len(courses), len(terms), ", ".join(terms)))


if __name__ == "__main__":
    main()
