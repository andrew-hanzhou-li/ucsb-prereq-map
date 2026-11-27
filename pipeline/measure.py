"""
measure.py: how accurate is the parser?

Runs the parser on every course in test_labels.json and compares its answer
to the labeled one. A course counts as correct only if the whole tree
matches exactly: every course, every and/or, every grade, every
"concurrent" flag and the kind of every condition. A second score ignores the
condition kinds ("restriction" vs "other"), since only course logic draws
arrows on the map.

    py pipeline/measure.py            prints the score and every miss
    py pipeline/measure.py --quiet    prints only the score

The answers were generated with AI, not written by a person.

The 450 test courses come in three groups:
  tuning   150 courses I looked at while writing the parser. It was adjusted
           until these passed, so their score is optimistic.
  heldout  150 different courses, labeled BEFORE the parser was run
           on them. Its first score was the first honest number; I then fixed
           the parser using its misses, so later scores are optimistic too.
  final    150 more courses, labeled after the parser was frozen and scored
           once. This is the number to quote.
Each group is split into two sets:
  random   100 random courses that have prerequisite text (most are short,
           like "Upper-division standing")
  major    50 random courses from ECON, PSTAT, MATH, ECE, CMPSC and PHYS
           (harder, course-heavy text; the courses the site shows first)

    py pipeline/measure.py final      score only one group
    py pipeline/measure.py --campus ucsd
                                      score UC San Diego's parser on
                                      tests/ucsd_labels.json (same groups)
"""

import json
import os
import re
import sys

from notation import from_notation, to_notation
from parser import Parser, subject_of


def load_parser():
    with open("data/raw_courses.json", encoding="utf-8") as f:
        courses = json.load(f)["courses"]
    subjects = {subject_of(c["code"]) for c in courses}
    subjects.discard(None)
    return Parser(subjects)


def load_ucsd():
    """A function parsing a label's text the way UCSD's pipeline does: the
    labels hold everything after "Prerequisites:", and extract.py splits
    enrollment notes off it first."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "campuses", "ucsd"))
    import build_prereqs
    import extract
    with open(build_prereqs.INPUT, encoding="utf-8") as f:
        courses = json.load(f)["courses"]
    parser = build_prereqs.make_parser(courses)
    return lambda text, code: build_prereqs.parse(parser, extract.split_prereq_text(text)[0], code)


def without_repeats(notation):
    """The same answer written one way: an & inside an & (or | inside |) is
    flattened, and a tag or course repeated inside one & or | is written once
    ("@consent & @consent & X" -> "@consent & X"). The meaning is the same."""
    def tidy(node):
        if node is None or node["type"] not in ("and", "or"):
            return node
        flat = []
        for item in (tidy(i) for i in node["items"]):
            flat.extend(item["items"] if item["type"] == node["type"] else [item])
        items, seen = [], set()
        for item in flat:
            key = to_notation(item)
            if key not in seen:
                seen.add(key)
                items.append(item)
        return items[0] if len(items) == 1 else dict(node, items=items)
    return to_notation(tidy(from_notation(notation)))


def course_logic_only(notation):
    """Treat every kind of condition as the same, so only the course logic
    (what draws arrows on the map) is compared."""
    return re.sub(r"@\w+", "@condition", notation)


def main():
    # Windows consoles can't print every character the catalog uses; show "?" instead of crashing.
    sys.stdout.reconfigure(errors="replace")
    quiet = "--quiet" in sys.argv
    campus = sys.argv[sys.argv.index("--campus") + 1] if "--campus" in sys.argv else "ucsb"
    only = [a for a in sys.argv[1:] if not a.startswith("--") and a != campus]
    if campus == "ucsd":
        parse = load_ucsd()
        labels = "tests/ucsd_labels.json"
    else:
        ucsb_parser = load_parser()
        parse = lambda text, code: ucsb_parser.parse(text)
        labels = "tests/test_labels.json"
    with open(labels, encoding="utf-8") as f:
        tests = json.load(f)["courses"]

    scores = {}
    logic = {}
    misses = []
    for test in tests:
        if only and test["group"] not in only:
            continue
        tree = parse(test["prereq_text"], test["code"])["requires"]
        got = without_repeats(to_notation(tree))
        expected = without_repeats(test["expected"])
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

    for group in ("tuning", "heldout", "final", "final2", "final3", "final4", "final5", "final6"):
        for name in ("random", "major"):
            if (group, name) in scores:
                right, total = scores[(group, name)]
                print("%-8s %-7s %3d / %3d exactly right (%3.0f%%)   %3d / %3d course logic right (%3.0f%%)" % (
                    group, name, right, total, 100.0 * right / total,
                    logic[(group, name)], total, 100.0 * logic[(group, name)] / total))


if __name__ == "__main__":
    main()
