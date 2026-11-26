"""
test_graph.py: checks for build_graph.py.

    py tests/test_graph.py

Two kinds of tests:

1. Small made-up examples, one per rule in build_graph.py (AND takes the
   later column, OR the earlier, "concurrent" adds no quarter, loops get
   reported...). If one fails, the rule it's named after is broken.

2. Checks on the real graphs in site/data (run build_graph.py first):
   - every arrow for a REQUIRED prerequisite points left to right
   - every arrow starts and ends at a course in the graph
   - courses you know come in the right order (MATH 3A before 3B before 4A,
     PSTAT 120A before 120B before 120C, ...)
"""

import glob
import json
import os
import sys

# build_graph.py lives in pipeline/; tell Python to look there for it.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
from build_graph import (OFFERING_OVERRIDES, POOL_LIMIT, ColumnFinder, add_outside_prerequisites,
                         collect_major_courses, describe_rule, is_upper_division, make_edges, offered_for,
                         real_cycles, sort_key, upper_division_floor)

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print("FAIL: %s %s" % (name, detail))


# ---------------------------------------------------------------------------
# Helpers to write small prerequisite trees by hand
# ---------------------------------------------------------------------------

def course(code, concurrent=False):
    return {"type": "course", "code": code, "concurrent": concurrent, "min_grade": None}


def AND(*items):
    return {"type": "and", "items": list(items)}


def OR(*items):
    return {"type": "or", "items": list(items)}


def condition(kind):
    return {"type": "condition", "kind": kind, "text": ""}


def columns(prereq_trees, preferred=(), floor=0):
    """Run ColumnFinder on a dict like {"B": course("A")}."""
    prereqs = {code: {"requires": tree} for code, tree in prereq_trees.items()}
    finder = ColumnFinder(prereqs, preferred=preferred, upper_division_floor=floor)
    return finder, {code: finder.of(code) for code in prereq_trees}


# ---------------------------------------------------------------------------
# 1. Rules, on made-up courses
# ---------------------------------------------------------------------------

def test_rules():
    _, col = columns({"A 1": None, "A 2": course("A 1"), "A 3": course("A 2")})
    check("chain: each course one column right of its prerequisite",
          (col["A 1"], col["A 2"], col["A 3"]) == (0, 1, 2), col)

    _, col = columns({"A 1": None, "A 2": course("A 1"), "B 1": None,
                      "C 1": AND(course("A 2"), course("B 1"))})
    check("AND: the later prerequisite decides", col["C 1"] == 2, col)

    _, col = columns({"A 1": None, "A 2": course("A 1"), "B 1": None,
                      "C 1": OR(course("A 2"), course("B 1"))})
    check("OR: the earlier alternative decides", col["C 1"] == 1, col)

    _, col = columns({"A 1": None, "A 2": course("A 1"),
                      "A 2L": course("A 2", concurrent=True)})
    check("concurrent: a lab sits in the same column as its lecture",
          col["A 2L"] == col["A 2"], col)

    _, col = columns({"A 1": None, "A 2": OR(course("A 1"), condition("consent"))})
    check("OR with 'consent of instructor': the course alternative decides",
          col["A 2"] == 1, col)

    _, col = columns({"M 1": None, "M 2": course("M 1"), "H 2": None,
                      "M 3": OR(course("M 2"), course("H 2"))}, preferred={"M 2", "M 3"})
    check("OR: an alternative in the major wins over an outside one",
          col["M 3"] == 2, col)

    _, col = columns({"X 101": None, "X 5": None}, floor=3)
    check("upper-division floor applies to course numbers 100+", col["X 101"] == 3, col)
    check("upper-division floor doesn't touch lower division", col["X 5"] == 0, col)

    finder, _ = columns({"A 1": course("A 2"), "A 2": course("A 1")})
    check("a real loop is reported", len(finder.cycles) == 1, finder.cycles)

    finder, _ = columns({"A 1": course("A 1L", concurrent=True),
                         "A 1L": course("A 1", concurrent=True)})
    check("a lecture/lab 'take together' pair is not a loop", finder.cycles == [], finder.cycles)

    edges = make_edges("C 1", AND(course("A 1"), OR(course("B 1"), course("B 2"))))
    kinds = sorted((e["from"], e["type"]) for e in edges)
    check("edges: AND gives 'required', OR gives 'alternative'",
          kinds == [("A 1", "required"), ("B 1", "alternative"), ("B 2", "alternative")], kinds)
    groups = {e["group"] for e in edges if e["type"] == "alternative"}
    check("edges: alternatives of the same OR share one group", len(groups) == 1, groups)

    edges = make_edges("A 1", AND(course("A 1"), course("B 1")))
    check("edges: a course listing itself gets no arrow",
          [e["from"] for e in edges] == ["B 1"], edges)

    edges = make_edges("C 1", OR(course("A 1"), condition("consent")))
    check("edges: 'A or consent' still makes A an alternative",
          [(e["type"], e["group"]) for e in edges] == [("alternative", "C 1/or1")], edges)
    check("edges: no prerequisite, no arrows", make_edges("C 1", None) == [])


def req_course(code, status="active"):
    return {"type": "course", "code": code, "status": status}


def test_major_rules():
    major = {"sections": [
        {"name": "Preparation", "requirement": {"type": "all", "items": [
            req_course("M 1"),
            {"type": "choose", "count": 1, "items": [req_course("M 2"), req_course("M 2H")]},
            {"type": "text", "text": "A language"},
            {"type": "course", "code": None, "status": "unresolved"}]}},
        {"name": "Upper Division", "requirement": {"type": "choose", "count": 2, "label": "Area A", "items": [
            req_course("M 2"), req_course("M 101"), req_course("M 102", "inactive")]}},
        {"name": "Electives", "requirement": {"type": "units", "units": 8, "items": [
            req_course("E %d" % n) for n in range(POOL_LIMIT + 1)]}},
    ]}
    courses, pools = collect_major_courses(major)
    roles = {code: info["role"] for code, info in courses.items()}
    check("major: 'all' makes a course required", roles.get("M 1") == "required", roles)
    check("major: a short 'choose 1' makes a choice", roles.get("M 2H") == "choice", roles)
    check("major: a 'choose 2' list is elective", roles.get("M 101") == "elective", roles)
    check("major: a course keeps its strongest role", roles.get("M 2") == "choice", roles)
    check("major: a course lists every group it's in",
          courses["M 2"]["groups"] == ["Preparation", "Upper Division: Area A"], courses["M 2"])
    check("major: status is kept", courses["M 102"]["status"] == "inactive")
    check("major: text and unresolved courses are skipped", None not in courses)
    check("major: a list longer than POOL_LIMIT becomes one pool",
          len(pools) == 1 and len(pools[0]["courses"]) == POOL_LIMIT + 1 and "E 0" not in courses, pools[:1])
    check("major: the pool says what it asks for", pools and pools[0]["rule"] == "at least 8 units", pools[:1])

    check("describe_rule", [describe_rule({"type": "choose", "count": 1}), describe_rule({"type": "choose", "count": 3}),
                            describe_rule({"type": "all"})] == ["at least 1 course", "at least 3 courses", "all"])

    prereqs = {"A 3": {"requires": AND(course("A 2"), condition("consent"))},
               "A 2": {"requires": OR(course("A 1"), course("B 1"))}}
    check("outside prerequisites: followed all the way, every alternative",
          add_outside_prerequisites(["A 3"], prereqs) == {"A 1", "A 2", "B 1"})

    check("upper division is 100 and up",
          [is_upper_division(c) for c in ["MATH 99", "MATH 100", "PSTAT 120A", "ECE 10AL", "X"]]
          == [False, True, True, False, False])
    check("sort_key puts 3A before 108A",
          sorted(["MATH 108A", "MATH 3B", "MATH 3A", "ECON 1"], key=sort_key) ==
          ["ECON 1", "MATH 3A", "MATH 3B", "MATH 108A"])

    core = {"U 101": {"role": "required", "groups": ["Upper Division"]},
            "U 102": {"role": "required", "groups": ["Upper Division"]},
            "P 120": {"role": "choice", "groups": ["Preparation"]},
            "L 1": {"role": "required", "groups": ["Preparation"]}}
    prereqs = {"U 101": {"requires": course("L 2")}, "L 2": {"requires": course("L 1")},
               "U 102": {"requires": condition("standing")}, "P 120": {"requires": course("L 1")}}
    check("upper-division floor: the earliest upper-division course in an upper-division section",
          upper_division_floor(core, prereqs) == 2, upper_division_floor(core, prereqs))
    check("upper-division floor: 0 when no upper-division course has prerequisites",
          upper_division_floor({"L 1": core["L 1"]}, prereqs) == 0)

    prereqs = {"A 1": {"requires": course("A 2")}, "A 2": {"requires": course("A 1")},
               "L 1": {"requires": course("L 1L", concurrent=True)},
               "L 1L": {"requires": course("L 1", concurrent=True)}}
    loops = real_cycles([["A 1", "A 2", "A 1"], ["A 1", "A 2", "A 1"], ["L 1", "L 1L", "L 1"]], prereqs)
    check("real_cycles: keeps real loops once, drops 'take together' pairs", loops == [["A 1", "A 2", "A 1"]], loops)


def test_offered():
    check("offered: the catalog field", offered_for("X 1", {"offered": ["Fall"]}) == ["Fall"])
    check("offered: 'Quarters usually offered' in the comments",
          offered_for("X 1", {"comments": "Quarters usually offered: Winter, Fall."}) == ["Fall", "Winter"])
    check("offered: 'summer only' in the description",
          offered_for("X 1", {"description": "A field course. Summer session only."}) == ["Summer"])
    check("offered: 'Offered every spring'",
          offered_for("X 1", {"description": "Offered every spring quarter."}) == ["Spring"])
    check("offered: nothing said means an empty list", offered_for("X 1", {}) == [])
    OFFERING_OVERRIDES["X 1"] = {"offered": ["Winter"]}
    try:
        check("offered: a hand correction wins", offered_for("X 1", {"offered": ["Fall"]}) == ["Winter"])
    finally:
        del OFFERING_OVERRIDES["X 1"]


# ---------------------------------------------------------------------------
# 2. The real graphs
# ---------------------------------------------------------------------------

KNOWN_ORDER = {
    "economics-ba": [
        ["ECON 1", "ECON 2", "ECON 10A", "ECON 100B", "ECON 100C"],
        ["MATH 3A", "MATH 3B"],
        ["ECON 140A", "ECON 140B"],
    ],
    "statistics-and-data-science-bs": [
        ["MATH 3A", "MATH 3B", "MATH 4A", "MATH 6A"],
        ["PSTAT 120A", "PSTAT 120B", "PSTAT 120C"],
        ["PSTAT 120B", "PSTAT 126", "PSTAT 131"],
        ["CMPSC 8", "CMPSC 9"],
    ],
    "computer-engineering-bs": [
        ["PHYS 7A", "PHYS 7B", "PHYS 7C", "PHYS 7D"],
        ["ECE 10A", "ECE 10B", "ECE 10C"],
        ["ECE 189A", "ECE 189B", "ECE 189C"],
        ["CMPSC 16", "CMPSC 24", "CMPSC 32"],
    ],
}

SAME_COLUMN = {
    "computer-engineering-bs": [("ECE 10A", "ECE 10AL"), ("ECE 10B", "ECE 10BL"), ("ECE 10C", "ECE 10CL")],
}


def test_real_graphs():
    files = [f for f in glob.glob(os.path.join("site", "data", "*.json"))
             if not f.endswith(("majors.json", "credit.json", "course-index.json"))]   # not program graphs
    check("site/data has graphs (run build_graph.py first)", len(files) > 0)

    for path in files:
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            graph = json.load(f)
        column = {n["id"]: n["column"] for n in graph["nodes"]}
        check("%s: node ids are unique" % name, len(column) == len(graph["nodes"]))
        for edge in graph["edges"]:
            ends_ok = edge["from"] in column and edge["to"] in column
            check("%s: arrow %s -> %s ends at courses in the graph" % (name, edge["from"], edge["to"]), ends_ok)
            if not ends_ok or edge["type"] != "required":
                continue
            before, after = column[edge["from"]], column[edge["to"]]
            forward = before <= after if edge["concurrent"] else before < after
            check("%s: required arrow %s (col %d) -> %s (col %d) points right"
                  % (name, edge["from"], before, edge["to"], after), forward)
        check("%s: no prerequisite loops" % name, graph["loops"] == [], graph["loops"])

        stem = name[:-5]
        for chain in KNOWN_ORDER.get(stem, []):
            cols = [column.get(code) for code in chain]
            in_order = None not in cols and all(a < b for a, b in zip(cols, cols[1:]))
            check("%s: %s in increasing columns" % (stem, " < ".join(chain)), in_order, cols)
        for a, b in SAME_COLUMN.get(stem, []):
            check("%s: %s and its lab %s share a column" % (stem, a, b), column.get(a) == column.get(b))


def test_condition_text():
    """Every condition has the catalog's words, so the site never shows a
    blank item (IMPROVEMENTS.md item 14). Hand corrections in overrides.json
    give them as @other{...}."""
    with open("data/prereqs.json", encoding="utf-8") as f:
        courses = json.load(f)["courses"]
    empty = []

    def walk(node, code):
        if not node:
            return
        if node["type"] == "condition" and not (node.get("text") or "").strip():
            empty.append(code)
        for item in node.get("items", []):
            walk(item, code)

    for course in courses:
        walk(course.get("requires"), course["code"])
    check("no condition with empty text in prereqs.json", not empty, sorted(set(empty))[:10])


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    test_rules()
    test_major_rules()
    test_offered()
    test_real_graphs()
    test_condition_text()
    print("%d checks passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)
