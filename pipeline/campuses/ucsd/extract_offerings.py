"""
extract_offerings.py (UC San Diego): the quarters each course ran.

    python pipeline/campuses/ucsd/extract_offerings.py

Reads   data/ucsd/raw/soc/<TERM>/*.html     (from fetch_offerings.py)
Writes  data/ucsd/offerings.json            {"terms": [...], "courses": {"CSE 12": ["Fall", "Winter", "Spring"], ...}}

A course counts as offered in a quarter if it ran in that quarter in either
of the years fetched. The summer sessions (S1, S2, S3) all count as Summer.
extract.py reads this file to fill each course's "offered" when the catalog
itself doesn't say.
"""

import glob
import json
import os
import re

SOC_DIR = os.path.join("data", "ucsd", "raw", "soc")
OUTPUT = os.path.join("data", "ucsd", "offerings.json")
QUARTER_OF_TERM = {"FA": "Fall", "WI": "Winter", "SP": "Spring", "S1": "Summer", "S2": "Summer", "S3": "Summer",
                   "SU": "Summer"}
QUARTER_ORDER = ["Fall", "Winter", "Spring", "Summer"]
COURSE_NUMBER = re.compile(r'class="crsheader">\s*([0-9]+[A-Z]*)\s*<')


def courses_on_page(path):
    """Course codes on one saved result page: its subject (from the file
    name) plus each course number listed."""
    subject = re.sub(r"-\d+\.html$", "", os.path.basename(path)).replace("_", " ")
    with open(path, encoding="utf-8") as f:
        return {"%s %s" % (subject, number) for number in COURSE_NUMBER.findall(f.read())}


def main():
    offered = {}
    terms = sorted(os.listdir(SOC_DIR)) if os.path.isdir(SOC_DIR) else []
    for term in terms:
        quarter = QUARTER_OF_TERM.get(term[:2])
        if not quarter:
            continue
        for path in glob.glob(os.path.join(SOC_DIR, term, "*.html")):
            for code in courses_on_page(path):
                offered.setdefault(code, set()).add(quarter)
    courses = {code: [q for q in QUARTER_ORDER if q in quarters] for code, quarters in sorted(offered.items())}
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"terms": terms, "courses": courses}, f, indent=1)
    print("Wrote %s: %d courses from %d terms (%s)" % (OUTPUT, len(courses), len(terms), ", ".join(terms)))


if __name__ == "__main__":
    main()
