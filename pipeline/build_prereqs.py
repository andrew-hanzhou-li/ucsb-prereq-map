"""
build_prereqs.py: parse every course in the catalog and save the results.

    py pipeline/build_prereqs.py

Reads   raw_courses.json   (from Part 1)
        overrides.json     (hand corrections for text the parser gets wrong)
Writes  prereqs.json       (one entry per course, used by Part 4)

Each entry in prereqs.json looks like:

    {
      "code": "ECON 100B",
      "prereq_text": "Economics 10A or 100A; and, Economics 5 or PSTAT 109 or PSTAT 120A.",
      "requires": { ...tree, see parser.py... },
      "source": "parser",          # or "override"
      "ambiguous": false,          # "A or B and C" with no punctuation
      "unparsed": []               # leftover words next to courses
    }
"""

import json
import sys

from notation import from_notation
from parser import Parser, all_courses, subject_of


def main():
    # Windows consoles can't print every character the catalog uses; show "?" instead of crashing.
    sys.stdout.reconfigure(errors="replace")
    with open("data/raw_courses.json", encoding="utf-8") as f:
        courses = json.load(f)["courses"]
    with open("data/overrides.json", encoding="utf-8") as f:
        overrides = json.load(f)["overrides"]

    subjects = {subject_of(c["code"]) for c in courses}
    subjects.discard(None)
    parser = Parser(subjects)
    known_codes = {c["code"] for c in courses}

    results = []
    used_overrides = 0
    stale_overrides = []
    for course in courses:
        text = course.get("prereq_text") or ""
        parsed = parser.parse(text)
        entry = {
            "code": course["code"],
            "prereq_text": text,
            "requires": parsed["requires"],
            "source": "parser",
            "ambiguous": parsed["ambiguous"],
            "unparsed": parsed["unparsed"],
        }

        override = overrides.get(course["code"])
        if override:
            if override["for_text"] == text:
                entry["requires"] = from_notation(override["requires"])
                entry["source"] = "override"
                entry["ambiguous"] = False
                entry["unparsed"] = []
                used_overrides += 1
            else:
                # The catalog changed since the override was written: don't
                # apply an old answer to new text. Re-check it by hand.
                stale_overrides.append(course["code"])

        results.append(entry)

    with open("data/prereqs.json", "w", encoding="utf-8") as f:
        json.dump({"courses": results}, f, indent=1, ensure_ascii=False)

    # ----------------------------------------------------------- summary
    with_text = [r for r in results if r["prereq_text"]]
    with_courses = [r for r in results if all_courses(r["requires"])]
    referenced = set()
    for r in results:
        for c in all_courses(r["requires"]):
            referenced.add(c["code"])
    missing = sorted(referenced - known_codes)

    print("Courses in catalog:            %5d" % len(results))
    print("  with prerequisite text:      %5d" % len(with_text))
    print("  requiring at least 1 course: %5d" % len(with_courses))
    print("  flagged ambiguous:           %5d" % sum(r["ambiguous"] for r in results))
    print("  with leftover words:         %5d" % sum(bool(r["unparsed"]) for r in results))
    print("  corrected by overrides.json: %5d" % used_overrides)
    if stale_overrides:
        print("  STALE overrides (catalog text changed, re-check): " + ", ".join(stale_overrides))
    print("Prerequisite courses not in the current catalog: %d" % len(missing))
    print("  (old or renamed courses, e.g. %s)" % ", ".join(missing[:8]))
    print("Wrote prereqs.json")


if __name__ == "__main__":
    main()
