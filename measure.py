"""
measure.py: how accurate is the parser?

Runs the parser on every course in test_labels.json and compares its answer
to the hand-written one. A course counts as correct only if the whole tree
matches exactly: every course, every and/or, every grade, every
"concurrent" flag and the kind of every condition. A second score ignores the
condition kinds ("restriction" vs "other"), since only course logic draws
arrows on the map.

    py measure.py            prints the score and every miss
    py measure.py --quiet    prints only the score

The 450 test courses come in two groups:
  tuning   150 courses I looked at while writing the parser. It was adjusted
           until these passed, so their score is optimistic.
  heldout  150 different courses, labeled by hand BEFORE the parser was run
           on them. Its first score was the first honest number; I then fixed
           the parser using its misses, so later scores are optimistic too.
  final    150 more courses, labeled after the parser was frozen and scored
           once. This is the number to quote.
Each group is split into two sets:
  random   100 random courses that have prerequisite text (most are short,
           like "Upper-division standing")
  major    50 random courses from ECON, PSTAT, MATH, ECE, CMPSC and PHYS
           (harder, course-heavy text; the courses the site shows first)

    py measure.py final      score only one group
"""

import json
import re
import sys

from notation import from_notation, to_notation
from parser import Parser, subject_of


def load_parser():
    with open("raw_courses.json", encoding="utf-8") as f:
        courses = json.load(f)["courses"]
    subjects = {subject_of(c["code"]) for c in courses}
    subjects.discard(None)
    return Parser(subjects)


def course_logic_only(notation):
    """Treat every kind of condition as the same, so only the course logic
    (what draws arrows on the map) is compared."""
    return re.sub(r"@\w+", "@condition", notation)


def main():
    # Windows consoles can't print every character the catalog uses; show "?" instead of crashing.
    sys.stdout.reconfigure(errors="replace")
    quiet = "--quiet" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    parser = load_parser()
    with open("test_labels.json", encoding="utf-8") as f:
        tests = json.load(f)["courses"]

    scores = {}
    logic = {}
    misses = []
    for test in tests:
        if only and test["group"] not in only:
            continue
        tree = parser.parse(test["prereq_text"])["requires"]
        got = to_notation(tree)
        expected = to_notation(from_notation(test["expected"]))
        key = (test["group"], test["set"])
        right, total = scores.get(key, (0, 0))
        scores[key] = (right + (got == expected), total + 1)
        logic_right = logic.get(key, 0)
        logic[key] = logic_right + (course_logic_only(got) == course_logic_only(expected))
        if got != expected:
            misses.append((test, expected, got))

    if not quiet:
        for test, expected, got in misses:
            print("%s  [%s/%s]" % (test["code"], test["group"], test["set"]))
            print("  text:     " + test["prereq_text"])
            print("  expected: " + expected)
            print("  got:      " + got)
            print()

    for group in ("tuning", "heldout", "final"):
        for name in ("random", "major"):
            if (group, name) in scores:
                right, total = scores[(group, name)]
                print("%-8s %-7s %3d / %3d exactly right (%3.0f%%)   %3d / %3d course logic right (%3.0f%%)" % (
                    group, name, right, total, 100.0 * right / total,
                    logic[(group, name)], total, 100.0 * logic[(group, name)] / total))


if __name__ == "__main__":
    main()
