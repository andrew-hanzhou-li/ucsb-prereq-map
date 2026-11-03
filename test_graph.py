"""
test_graph.py: checks for build_graph.py.

    py test_graph.py

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

from build_graph import ColumnFinder, make_edges

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
    with open("prereqs.json", encoding="utf-8") as f:
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
    test_real_graphs()
    test_condition_text()
    print("%d checks passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)
