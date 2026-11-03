"""
build_credit.py: check the AP credit table and copy it to the site.

    py build_credit.py

Reads   ap_credit.json          UCSB's AP chart, typed in from the catalog
        raw_courses.json        the current course list (Part 1)
Writes  site/data/credit.json   the table, ready for the site's Credit box,
                                plus the catalog's subject codes (for the
                                transcript reader)

The AP chart is a page of text in the catalog, not data, so ap_credit.json
was copied from it by hand. That's exactly the kind of file that goes
wrong quietly, so this script checks every course code against the current
catalog and lists any that don't match. A code that doesn't match isn't
necessarily a typo: the chart still names some courses the catalog has
since retired (ARTHI 1, EEMB 22). Those stay in the table; they just never
appear on a map.

It also expands "PSTAT 5AA-ZZ" (every lettered version of PSTAT 5) into
the courses that exist now (PSTAT 5LS).
"""

import json
import os
import re
import sys


def expand(code, current):
    """'PSTAT 5AA-ZZ' -> every current code like 'PSTAT 5LS'; others unchanged."""
    if code.endswith("AA-ZZ"):
        base = code[:-len("AA-ZZ")]
        return sorted(c for c in current if re.fullmatch(re.escape(base) + "[A-Z]{2}", c))
    return [code]


def main():
    sys.stdout.reconfigure(errors="replace")
    with open("ap_credit.json", encoding="utf-8") as f:
        table = json.load(f)
    with open("raw_courses.json", encoding="utf-8") as f:
        current = {c["code"] for c in json.load(f)["courses"]}

    missing = set()
    for exam in table["exams"]:
        for row in exam["rows"]:
            row["equivalents"] = [c for code in row["equivalents"] for c in expand(code, current)]
            missing.update(c for c in row["equivalents"] if c not in current)

    # Every subject code in the catalog ("ECE", "CMPSC", "ENV S"), so the
    # transcript reader (site/transcript.js) can tell a course line from
    # any other line of text.
    with open("raw_courses.json", encoding="utf-8") as f:
        subjects = sorted({c["subject"] for c in json.load(f)["courses"]})
    out = {"source": table["source"], "catalog_year": table["catalog_year"], "ap": table["exams"], "subjects": subjects}
    os.makedirs(os.path.join("site", "data"), exist_ok=True)
    with open(os.path.join("site", "data", "credit.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)

    print("AP exams: %d" % len(table["exams"]))
    if missing:
        print("Named in the AP chart but not in the current catalog (kept): " + ", ".join(sorted(missing)))
    print("Wrote site/data/credit.json")


if __name__ == "__main__":
    main()
