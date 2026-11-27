"""
test_ucsd.py: checks on UC San Diego's catalog reader and its parser rules.

    py tests/test_ucsd.py

Each case is a real catalog line (or a short made-up one) whose reading went
wrong once. Needs data/ucsd/raw_courses.json (from extract.py) for UCSD's
subject codes.
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, "pipeline")
sys.path.insert(0, os.path.join("pipeline", "campuses", "ucsd"))

import build_prereqs   # noqa: E402
import extract         # noqa: E402
from notation import to_notation   # noqa: E402
from parser import Parser          # noqa: E402

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print("FAIL: %s %s" % (name, detail))


def test_name_lines():
    cases = {
        "CSE 100": ["CSE 100"],
        "CSE 256/LING 256": ["CSE 256", "LING 256"],
        "AAS/ANSC 185": ["AAS 185", "ANSC 185"],
        "HIEU 160/260": ["HIEU 160", "HIEU 260"],
        "DSC 10/R": ["DSC 10", "DSC 10R"],
        "POLI 30 or 30D": ["POLI 30", "POLI 30D"],
        "MATH 20A-B-C": ["MATH 20A", "MATH 20B", "MATH 20C"],
        "ECE 145AL-BL-CL": ["ECE 145AL", "ECE 145BL", "ECE 145CL"],
        "VIS 128A–E": ["VIS 128A", "VIS 128B", "VIS 128C", "VIS 128D", "VIS 128E"],
        "EDS 128 A-B": ["EDS 128A", "EDS 128B"],
        "GSS 21-22-23": ["GSS 21", "GSS 22", "GSS 23"],
        "HITO 193/POLI 194/COM GEN 194": ["HITO 193", "POLI 194", "COM GEN 194"],
    }
    for text, expected in cases.items():
        got = extract.expand_codes(text)
        check("name line %r" % text, got == expected, got)
    match = extract.NAME_LINE.match("POLI 30 or 30D. Political Inquiry (4)")
    check("name line: 'or' doesn't end up in the title", match and match.group("title") == "Political Inquiry",
          match and match.group("title"))
    check("units of a sequence", extract.split_units("4-4-4", 3) == ["4", "4", "4"])


def test_notes_split():
    cases = [
        ("CSE 8B or CSE 11; restricted to undergraduates. Graduate students will be allowed as space permits.",
         "CSE 8B or CSE 11; restricted to undergraduates."),
        ("upper-division standing. Will not receive credit for SOCI 152 and SOCC 152.", "upper-division standing."),
        ("BIBC 100. Note: Students may not receive credit for both BIBC 102 and CHEM 114B.", "BIBC 100."),
        ("CSE 100; bioinformatics majors only. (S).", "CSE 100; bioinformatics majors only."),
        ("ECON 100A. Enrollment limited to majors in the Department of Economics.",
         "ECON 100A. Enrollment limited to majors in the Department of Economics."),
        ("AP Chemistry score of 4. Recommended: a physics course. Concurrent enrollment in MATH 20A.",
         "AP Chemistry score of 4. Concurrent enrollment in MATH 20A."),
        ("EDS 140, department approval. This form provides the instructor with information; EDS 139 must be taken "
         "as a corequisite.", "EDS 140, department approval. EDS 139 must be taken as a corequisite."),
    ]
    for text, expected in cases:
        got = extract.split_prereq_text(text)[0]
        check("notes split: %r" % text[:50], got == expected, got)


def test_recommendations():
    cases = {
        "CHEM 40B or 140B (a grade of C or higher in CHEM 40B or 140B is strongly recommended).": "CHEM 40B or 140B.",
        "upper-division standing and background in development psychology is recommended.": "upper-division standing.",
        "consent of instructor, MUS 171 recommended.": "consent of instructor.",
        "BILD 1, BILD 2 recommended.": "BILD 1.",
        "MUS 172; MUS 4, 8–10, or 120 recommended.": "MUS 172;",
    }
    for text, expected in cases.items():
        got = build_prereqs.without_recommendations(text)
        check("recommended: %r" % text[:40], got == expected, got)


def test_readings(parser):
    cases = [
        ("CSE 12", "CSE 8B or CSE 11; restricted to undergraduates.", "(CSE 11 | CSE 8B) & @restriction"),
        ("COMM 127", "COMM 10 and one from COMM 100A, 100B, 100C.", "(COMM 100A | COMM 100B | COMM 100C) & COMM 10"),
        ("MATH 104A", "MATH 100B or MATH 103B. Students who have not completed the listed prerequisite(s) may enroll "
                      "with consent of instructor.", "@consent | MATH 100B | MATH 103B"),
        ("SIO 121", "BILD 1, BILD 2, BILD 3, or consent of instructor.", "@consent | BILD 1 | BILD 2 | BILD 3"),
        ("MAE 175A", "senior standing; MAE 143B; and MAE 170, or consent of instructor.",
         "(@standing & MAE 143B & MAE 170) | @consent"),
        ("CSE 21", "CSE 20 or MATH 15A; students who have completed MATH 154 previously may not receive credit for "
                   "CSE 21; restricted to undergraduates.", "(CSE 20 | MATH 15A) & @restriction"),
        ("CHEM 43A", "CHEM 7L or 7LM and 40A, 40AH, or 41A.", "(CHEM 40A | CHEM 40AH | CHEM 41A) & (CHEM 7L | CHEM 7LM)"),
        ("DSC 40AR", "DSC 10/R and MATH 18.", "(DSC 10 | DSC 10R) & MATH 18"),
        ("ECE 190", "department stamp is required to enroll in ECE 190.", "@consent"),
        ("VIS 60", "none. Open to visual arts majors and minors.", "@restriction"),
        ("CHIN 165A", "any one of the following or department approval through placement interview: CHIN 100CM, "
                      "CHIN 100CN.", "@consent | CHIN 100CM | CHIN 100CN"),
        ("LIIT 1B", "LIIT 1A with a grade of C– or better, or equivalent and LIIT 1AX with a grade of D or better, or "
                    "equivalent.", "(@other | LIIT 1AX[D]) & (@other | LIIT 1A[C-])"),
        # Brackets group, and the subject carries into and out of them
        ("ASTR 122", "PHYS 2A/2AR-B-C-D or 4A-B-C-D-E.",
         "((PHYS 2A | PHYS 2AR) & PHYS 2B & PHYS 2C & PHYS 2D) | (PHYS 4A & PHYS 4B & PHYS 4C & PHYS 4D & PHYS 4E)"),
        ("DSC 97", "(MATH 20C or MATH 31BH), and (MATH 18 or MATH 31AH), and DSC 20.",
         "(MATH 18 | MATH 31AH) & (MATH 20C | MATH 31BH) & DSC 20"),
        ("X 1", "EDS (20S or 30 or 31) and EDS 117.", "(EDS 20S | EDS 30 | EDS 31) & EDS 117"),
        ("CHEM 43A", "CHEM 7L or 7LM and 40A, 40AH, or 41A.", "(CHEM 40A | CHEM 40AH | CHEM 41A) & (CHEM 7L | CHEM 7LM)"),
        ("POLI 161", "POLI/ECON 5(D) and POLI 30(D).", "(ECON 5 | ECON 5D | POLI 5 | POLI 5D) & (POLI 30 | POLI 30D)"),
        ("MUS 177", "MUS 172 (formerly MUS 161).", "MUS 172"),
        ("JAPN 140B", "previous course or consent of instructor.", "@consent | JAPN 140A"),
        ("MAE 105", "PHYS 2A and B, and MATH 20D.", "MATH 20D & PHYS 2A & PHYS 2B"),
        ("LISP 15", "LISP 1D/DX.", "LISP 1D | LISP 1DX"),
        ("EDS 130", "department approval required; EDS 139 must be taken as a corequisite.", "@consent & EDS 139*"),
        ("SIO 104", "undergraduate: BILD 3 or consent of instructor. Graduate: graduate-level standing.", "@consent | BILD 3"),
        ("PH 110", "PH 40. Restricted enrollment to sophomore, junior, and senior standing.", "@standing & PH 40"),
        ("EDS 102", "ED25 major and upper-division standing.", "@restriction & @standing"),
        ("CENG 101B", "admission to the major and a grade of C– or better in CENG 101A.", "@restriction & CENG 101A[C-]"),
        ("EDS 129A", "department approval required. Must have successfully completed EDS 135, 136, or 129A for 129B, "
                     "and 129B for 129C. EDS 129B and 129C are restricted for students applying to the program.",
         "@consent & @restriction"),
        ("EDS 129B", "Must have successfully completed EDS 135, 136, or 129A for 129B, and 129B for 129C.",
         "EDS 129A | EDS 135 | EDS 136"),
        ("LIFR 5B", "none for 5A; for 5B, two or more years of French in high school.", "@other"),
        ("LIFR 5A", "none for 5A; for 5B, two or more years of French in high school.", "-"),
        ("LISP 5D", "none for 5A; for 5B, two or more years of Spanish in high school.", "-"),
        # Chains of two-course pairs, and the or-groups they must not swallow
        ("LTWR 8B", "CAT 2 and 3 or CCE 1 and 2 or WARR 11A-B or WCWP 10A and WCWP 10B or SYN 1 and 2.",
         "(CAT 2 & CAT 3) | (CCE 1 & CCE 2) | (SYN 1 & SYN 2) | (WARR 11A & WARR 11B) | (WCWP 10A & WCWP 10B)"),
        ("COGS 150", "COGS 14A and COGS 14B or MATH 11 or PSYC 60.", "(COGS 14B | MATH 11 | PSYC 60) & COGS 14A"),
        ("MATH 20E", "MATH 18 or MATH 31AH and MATH 20C or MATH 31BH.", "(MATH 18 | MATH 31AH) & (MATH 20C | MATH 31BH)"),
        ("ECE 103", "ECE 65 and PHYS 2D or PHYS 4D and 4E.", "((PHYS 4D & PHYS 4E) | PHYS 2D) & ECE 65"),
        ("ANSC 191GS", "ANSC 121, ANSC 148, or ANTH 103, department approval required, and upper-division standing.",
         "(ANSC 121 | ANSC 148 | ANTH 103) & @consent & @standing"),
        ("PH 101", "PH 40 or FMPH 40 and PSYC 60, HDS 60, MATH 11, or COGS 14B, and upper-division standing.",
         "(COGS 14B | HDS 60 | MATH 11 | PSYC 60) & (FMPH 40 | PH 40) & @standing"),
        ("ETHN 100B", "ETHN 100A, ethnic studies major or minor, or consent of instructor.", "(@restriction & ETHN 100A) | @consent"),
        ("BENG 120", "CHEM 6A and 6B; majors only or consent of department.", "(@consent | @restriction) & CHEM 6A & CHEM 6B"),
        ("DSC 190", "department and instructor approval required to monitor enrollment. Restricted to students with "
                    "upper-division standing.", "@consent & @standing"),
        ("MATH 96", "AP Calculus AB score of 4 or more, or MATH 20A.", "@exam | MATH 20A"),
        ("BENG 187C", "BENG 187B; bioengineering, bioengineering: biotechnology, or bioengineering: bioinformatics "
                      "majors only or consent of instructor.", "(@restriction & BENG 187B) | @consent"),
        ("CLX 199", "students must meet with a faculty member for approval and to define course objectives.", "@consent"),
        ("CSE 12", "CSE 11 and CS majors only.", "@restriction & CSE 11"),
    ]
    for code, text, expected in cases:
        got = to_notation(build_prereqs.parse(parser, text, code)["requires"])
        check("reading %s" % code, got == expected, "%r -> %s" % (text[:60], got))


def test_grades_per_course():
    parser = Parser({"MATH", "PHYS", "ECE", "CHEM"})
    cases = {
        "CHEM 109A with a minimum grade of B+ or CHEM 109AH with a minimum grade of B.": "CHEM 109AH[B] | CHEM 109A[B+]",
        "MATH 3A; 4B with a grade of C and PHYS 1 with a grade of D": "MATH 3A & MATH 4B[C] & PHYS 1[D]",
        "ECE 10A; 10B with a grade of C or better and MATH 4A with a grade of B or better": "ECE 10A & ECE 10B[C] & MATH 4A[B]",
    }
    for text, expected in cases.items():
        result = parser.parse(text)
        check("grades: %r" % text[:50], to_notation(result["requires"]) == expected, to_notation(result["requires"]))
    result = parser.parse("MATH 3A extra with a grade of C and PHYS 1 with a grade of D")
    check("grades: leftover words listed once", result["unparsed"] == ["MATH 3A extra"], result["unparsed"])


def test_regex_speed():
    """Patterns that once took exponential time on long lists."""
    rule = [pattern for kind, pattern in build_prereqs.EXTRA_RULES if "majors?" in pattern][0]
    text = " or ".join("CS%02d" % i for i in range(60)) + " students"
    start = time.time()
    re.search(rule, text)
    check("major-code rule is fast on a long list", time.time() - start < 0.5, time.time() - start)
    start = time.time()
    build_prereqs.courses_for_this_course("1" * 60 + " and more", "5")
    check("'for' phrases are fast on a long run of digits", time.time() - start < 0.5, time.time() - start)


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    with open(os.path.join("data", "ucsd", "raw_courses.json"), encoding="utf-8") as f:
        ucsd_parser = build_prereqs.make_parser(json.load(f)["courses"])
    test_name_lines()
    test_notes_split()
    test_recommendations()
    test_readings(ucsd_parser)
    test_grades_per_course()
    test_regex_speed()
    print("%d checks passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)
