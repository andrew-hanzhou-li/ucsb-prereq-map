"""
test_parser.py: checks for parser.py and notation.py.

    py tests/test_parser.py

Three kinds of tests:

1. notation.py: writing a tree as one line and reading it back.
2. parser.py on short made-up sentences, one or two per rule (sequences,
   slashes, grades, "may be taken concurrently", conditions, the scope
   rules). If one fails, the rule it's named after has changed.
3. The parser's score on tests/test_labels.json must not drop below what it
   is now (measure.py prints the same numbers, but never fails).
"""

import json
import os
import sys

# The pipeline scripts live in pipeline/; tell Python to look there for them.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
from notation import from_notation, to_notation
from parser import Parser, all_courses, combine, letters_for, make_course, set_concurrent, set_grade, subject_of

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print("FAIL: %s %s" % (name, detail))


def raises(function, *args):
    try:
        function(*args)
    except ValueError:
        return True
    return False


# ---------------------------------------------------------------------------
# 1. notation.py
# ---------------------------------------------------------------------------

def test_notation():
    check("no prerequisite is '-'", to_notation(None) == "-" and from_notation(" - ") is None)

    tree = from_notation("MATH 4B*[C-]")
    check("a course with * and a grade",
          tree == {"type": "course", "code": "MATH 4B", "concurrent": True, "min_grade": "C-"}, tree)

    tree = from_notation("@other{prior programming experience}")
    check("a condition keeps its words",
          tree == {"type": "condition", "kind": "other", "text": "prior programming experience"}, tree)
    check("to_notation leaves a condition's words out", to_notation(tree) == "@other")

    check("& and | compare regardless of order",
          to_notation(from_notation("B 1 & (C 2 | A 1)")) == to_notation(from_notation("(A 1 | C 2) & B 1")))
    check("groups get parentheses except at the top",
          to_notation(from_notation("(A 1 | B 1) & C 1")) == "(A 1 | B 1) & C 1")

    for text in ["MATH 3A", "MATH 3A* & (PHYS 1 | PHYS 1L[B])", "@standing & (@consent | ECON 1)",
                 "((A 1 & B 1) | C 1) & D 1"]:
        check("round trip: %s" % text, to_notation(from_notation(text)) == to_notation(from_notation(
            to_notation(from_notation(text)))), to_notation(from_notation(text)))

    check("mixing & and | without parentheses is an error", raises(from_notation, "A 1 & B 1 | C 1"))
    check("a missing ) is an error", raises(from_notation, "(A 1 & B 1"))
    check("text after a ) is an error", raises(from_notation, "A 1 & B 1)"))
    check("a malformed condition is an error", raises(from_notation, "@other{oops"))


# ---------------------------------------------------------------------------
# 2. parser.py
# ---------------------------------------------------------------------------

def test_helpers():
    check("letters_for: 0 -> a, 25 -> z, 26 -> ba",
          [letters_for(0), letters_for(25), letters_for(26)] == ["a", "z", "ba"])

    check("subject_of", [subject_of("MATH 3A"), subject_of("PHYS CS 15C"), subject_of("SPAN W 2"), subject_of("X")]
          == ["MATH", "PHYS CS", "SPAN", None])

    a, b, c = make_course("A 1"), make_course("B 1"), make_course("C 1")
    check("combine: nothing -> None", combine("and", [None, None]) is None)
    check("combine: one item -> that item", combine("or", [None, a]) is a)
    joined = combine("and", [a, combine("and", [b, c]), make_course("A 1")])
    check("combine: an and inside an and is flattened, duplicates dropped",
          to_notation(joined) == "A 1 & B 1 & C 1" and len(joined["items"]) == 3, to_notation(joined))
    check("combine: an or inside an and is kept",
          to_notation(combine("and", [a, combine("or", [b, c])])) == "(B 1 | C 1) & A 1")

    tree = from_notation("A 1[B] & (B 1 | @consent)")
    check("all_courses skips conditions", [n["code"] for n in all_courses(tree)] == ["A 1", "B 1"])
    set_grade(tree, "C")
    check("set_grade keeps a grade already there", to_notation(tree) == "(@consent | B 1[C]) & A 1[B]",
          to_notation(tree))
    set_concurrent(tree, {"B 1"})
    check("set_concurrent with codes marks only those", to_notation(tree) == "(@consent | B 1*[C]) & A 1[B]",
          to_notation(tree))


SUBJECTS = {"MATH", "ECON", "PSTAT", "ECE", "CMPSC", "CMPSCW", "PHYS", "CHEM", "CHEM W"}

# (rule, catalog text, expected notation)
CASES = [
    ("the example at the top of parser.py",
     "Economics 10A or 100A; and, Economics 5 or PSTAT 109 or PSTAT 120A.",
     "(ECON 100A | ECON 10A) & (ECON 5 | PSTAT 109 | PSTAT 120A)"),
    ("'None.' means no prerequisite", "None.", "-"),
    ("'N/A' means no prerequisite", "N/A", "-"),
    ("empty text means no prerequisite", "  ", "-"),
    ("a 'Prerequisite:' label is ignored", "Prerequisite: MATH 3A", "MATH 3A"),
    ("department names become codes", "Mathematics 3A & 3B", "MATH 3A & MATH 3B"),
    ("a bare number takes the last subject", "PHYS 3, 7B or 23", "PHYS 23 | PHYS 3 | PHYS 7B"),
    ("'(or X)' is another alternative", "MATH 3A (or 3AI)", "MATH 3A | MATH 3AI"),
    ("a shared number: 'ECE or CMPSC 181'", "ECE or CMPSC 181", "CMPSC 181 | ECE 181"),

    ("sequence 1A-B-C", "Chemistry 1A-B-C", "CHEM 1A & CHEM 1B & CHEM 1C"),
    ("sequence 1A-C", "MATH 1A-C", "MATH 1A & MATH 1B & MATH 1C"),
    ("sequence of numbers 1-3", "MATH 1-3", "MATH 1 & MATH 2 & MATH 3"),
    ("sequence 3AH-BH", "MATH 3AH-BH", "MATH 3AH & MATH 3BH"),
    ("lecture and lab 172-172L", "ECE 172-172L", "ECE 172 & ECE 172L"),
    ("a range like 105A-Z is any one course, kept as text", "MATH 105A-Z", "@other"),

    ("a slash means or", "MATH 2A/3A", "MATH 2A | MATH 3A"),
    ("a slash between a lecture and its lab means and", "PHYS 5/PHYS 5L", "PHYS 5 & PHYS 5L"),

    ("online course with a separate W subject", "CHEM W 142A", "CHEM W 142A"),
    ("online course written as one word", "CMPSC W 8", "CMPSCW 8"),

    ("a grade at the end covers the whole or-list",
     "Mathematics 2A or 3A or 34A with a grade of C or better.", "MATH 2A[C] | MATH 34A[C] | MATH 3A[C]"),
    ("'each with a minimum grade' covers every course",
     "MATH 3A, 3B, and 4A, each with a minimum grade of C.", "MATH 3A[C] & MATH 3B[C] & MATH 4A[C]"),
    ("a grade before the course", "A grade of C- or better in ECE 10A.", "ECE 10A[C-]"),
    ("a grade sentence after the courses covers them",
     "MATH 6A. Completion of all listed prerequisites with a grade of C or better.", "MATH 6A[C]"),

    ("'(may be taken concurrently)'", "MATH 4B (may be taken concurrently).", "MATH 4B*"),
    ("'Concurrent enrollment in'", "Concurrent enrollment in PHYS 1.", "PHYS 1*"),
    ("a later 'may be taken concurrently' sentence only adds the flag",
     "ECE 152A and ECE 153A. ECE 153A may be taken concurrently with ECE 188A.", "ECE 152A & ECE 153A*"),

    ("standing", "Upper-division standing.", "@standing"),
    ("consent", "Consent of instructor.", "@consent"),
    ("exam", "Exam: MATH PLACE >= 30", "@exam"),
    ("'; or' starts a new alternative", "MATH 4A; or consent of instructor.", "@consent | MATH 4A"),
    ("an exam in parentheses is an alternative",
     "MATH 3A-B (AP Calculus BC exam score of 4 or better)", "(MATH 3A & MATH 3B) | @exam"),
    ("a restriction at the end applies to every alternative",
     "MATH 4A; or MATH 4AI; open to Computer Engineering majors only.", "(MATH 4A | MATH 4AI) & @restriction"),
    ("a 'recommended' sentence is kept as text", "Prior programming experience recommended.", "@other"),
    ("prose with only bare numbers is kept as text",
     "Part of a three quarter sequence with 207B and 207C.", "@other"),
]


def test_parse():
    parser = Parser(SUBJECTS)
    for rule, text, expected in CASES:
        result = parser.parse(text)
        got = to_notation(result["requires"])
        check("parse: %s" % rule, got == expected, "%r -> %s, expected %s" % (text, got, expected))

    result = parser.parse("MATH 2B or 3B and CHEM 1A")
    check("parse: 'or' groups before 'and', and it's flagged ambiguous",
          to_notation(result["requires"]) == "(MATH 2B | MATH 3B) & CHEM 1A" and result["ambiguous"],
          result)
    check("parse: a plain list is not flagged ambiguous", not parser.parse("MATH 3A and 3B")["ambiguous"])

    result = parser.parse("Prior programming experience recommended.")
    check("parse: text kept as a condition keeps its words",
          result["requires"]["text"] == "Prior programming experience recommended", result)

    result = parser.parse("MATH 4A and PHYS 1 hello")
    check("parse: a stray word next to a course is reported, not dropped",
          result["unparsed"] == ["PHYS 1 hello"] and to_notation(result["requires"]) == "MATH 4A & PHYS 1", result)

    first = parser.parse("ECON 1; and ECON 2.")
    second = parser.parse("Consent of instructor.")
    check("parse: one call doesn't leak into the next",
          to_notation(first["requires"]) == "ECON 1 & ECON 2" and to_notation(second["requires"]) == "@consent")


# ---------------------------------------------------------------------------
# 3. The labeled answers
# ---------------------------------------------------------------------------

# Exactly right, by (group, set), when these tests were written. measure.py
# prints the current numbers; raise these when the parser gets better.
SCORE_FLOOR = {
    ("tuning", "random"): 98, ("tuning", "major"): 49,
    ("heldout", "random"): 97, ("heldout", "major"): 48,
    ("final", "random"): 89, ("final", "major"): 48,
}


def test_labels():
    from measure import load_parser
    with open("tests/test_labels.json", encoding="utf-8") as f:
        labels = json.load(f)["courses"]
    check("test_labels.json has 450 courses", len(labels) == 450, len(labels))

    unreadable = []
    for label in labels:
        try:
            from_notation(label["expected"])
        except (ValueError, AttributeError):
            unreadable.append(label["code"])
    check("every label is valid notation", not unreadable, unreadable[:10])

    parser = load_parser()
    right = {}
    for label in labels:
        if label["code"] in unreadable:
            continue
        got = to_notation(parser.parse(label["prereq_text"])["requires"])
        key = (label["group"], label["set"])
        right[key] = right.get(key, 0) + (got == to_notation(from_notation(label["expected"])))
    for key, floor in SCORE_FLOOR.items():
        check("score %s/%s is at least %d" % (key + (floor,)), right.get(key, 0) >= floor, right.get(key, 0))


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    test_notation()
    test_helpers()
    test_parse()
    test_labels()
    print("%d checks passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)
