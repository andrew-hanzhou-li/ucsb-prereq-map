"""
build_graph.py: combine a major (Part 3) with course prerequisites (Part 2)
into one ready-to-draw file per major.

    py build_graph.py                      every major in majors/
    py build_graph.py economics-ba         just one

Reads   majors/*.json         what each major requires          (Part 3)
        prereqs.json          what each course requires         (Part 2)
        raw_courses.json      titles, units, descriptions       (Part 1)
Writes  site/data/<major>.json   one graph per major
        site/data/majors.json    list of majors, for the site's picker

What's in a graph
-----------------
nodes   one per course: the major's own courses, plus every outside course
        they need (Economics needs MATH 4A for some electives even though the
        major never lists it). Each node has a "column": how many quarters of
        prerequisites must come before it. The site lays courses out left to
        right by column.
edges   one arrow per prerequisite: from the course you take first to the
        course it unlocks.
pools   very large elective lists ("any upper-division L&S course") shown as
        one box instead of thousands of courses.

How "column" is computed (the earliest quarter you could take a course)
-----------------------------------------------------------------------
Think of it as: column = the number of quarters that must come before it.

    a course with no prerequisites              column 0
    A requires B                                column(A) = column(B) + 1
    A requires B, and B may be taken
      at the same time ("concurrently")          column(A) = column(B)
    A requires B AND C                          the LATER of the two:   max
    A requires B OR C                           the EARLIER of the two: min

So MATH 3A is column 0, MATH 3B (requires 3A) is 1, MATH 4A (requires 3B) is
2. For "ECON 10A or 100A", the earlier alternative decides.

This is the topological-sort idea from CS 24 (process a course only after
everything it depends on), with min for OR and max for AND. It's computed by
recursion with memoization: each course's column is worked out once and saved.

Upper-division floor
--------------------
Many upper-division courses list only "upper-division standing" (junior
year) instead of course prerequisites, which would put them in column 0. So
upper-division courses are never placed left of the major's first required
upper-division course that has real course prerequisites. This is a display
rule, not a catalog rule; see upper_division_floor().

Cycle check
-----------
Real prerequisites can't go in a circle. A cycle (A needs B, B needs A) almost
always means a parsing mistake, so the script reports every one. The only
allowed loops are lecture/lab pairs that must be taken together (each lists
the other as "concurrent enrollment"); those don't add a quarter, so they
can't make the columns wrong.
"""

import json
import os
import re
import sys

from parser import all_courses

MAJORS_DIR = "majors"
OUTPUT_DIR = os.path.join("site", "data")

# An elective list longer than this becomes one "pool" box. Computer
# Engineering's elective list (~70 courses) is drawn in full; "any upper-division
# course in Letters and Science" (~3,000) is not.
POOL_LIMIT = 100

# Files in site/data written by other scripts, which the cleanup leaves alone
# (credit.json is the AP chart, from build_credit.py).
KEEP_IN_DATA = {"credit.json"}


# ===========================================================================
# Step 1: the major's own courses
# ===========================================================================

def collect_major_courses(major):
    """Walk the major's requirement tree. Returns (courses, pools).

    courses: {code: {"role": ..., "groups": [labels], "status": ...}}
    role is one of:
      required  only "complete ALL" lies between the section and the course:
                you must take it (ECON 1)
      choice    one of a short list of interchangeable courses, e.g.
                "MATH 2A or 3A", "PSTAT 120A or PSTATW 120A" -- you must
                take one of them
      elective  part of a "choose N" or "N units from" list (ECON area D)
    pools: list of big elective lists kept as one box each
    """
    courses = {}
    pools = []
    strength = {"required": 3, "choice": 2, "elective": 1}

    def visit(node, section, label, role):
        kind = node["type"]
        here = node.get("label") or label
        if kind == "course":
            code = node.get("code")
            if not code:
                return
            entry = courses.setdefault(code, {"role": role, "groups": [], "status": node["status"]})
            if strength[role] > strength[entry["role"]]:
                entry["role"] = role
            group = section + (": " + here if here and here != section else "")
            if group not in entry["groups"]:
                entry["groups"].append(group)
            return
        if kind == "text":
            return

        items = node["items"]
        course_items = [i for i in items if i["type"] == "course" and i.get("code")]
        if kind in ("choose", "units") and len(course_items) > POOL_LIMIT:
            pools.append({
                "id": "pool-%d" % (len(pools) + 1),
                "label": here or section,
                "section": section,
                "rule": describe_rule(node),
                "list_name": course_items[0].get("from_list"),
                "courses": [i["code"] for i in course_items],
            })
            return

        if kind == "all":
            next_role = role
        elif kind == "choose" and node["count"] == 1 and len(items) <= 4 and role != "elective":
            next_role = "choice"
        else:
            next_role = "elective"
        for item in items:
            visit(item, section, here, next_role)

    for section in major["sections"]:
        visit(section["requirement"], section["name"], "", "required")
    return courses, pools


def describe_rule(node):
    if node["type"] == "units":
        return "at least %s units" % node["units"]
    if node["type"] == "choose":
        return "at least %d course%s" % (node["count"], "" if node["count"] == 1 else "s")
    return "all"


# ===========================================================================
# Step 2: add the outside courses they need
# ===========================================================================

def add_outside_prerequisites(codes, prereqs):
    """Follow prerequisites outward until nothing new appears.

    Every alternative is included ("ECON 5 or PSTAT 109 or PSTAT 120A" adds
    all three), because the student might take any of them."""
    seen = set(codes)
    to_visit = list(codes)
    while to_visit:
        code = to_visit.pop()
        for course in all_courses(requires_of(code, prereqs)):
            if course["code"] not in seen:
                seen.add(course["code"])
                to_visit.append(course["code"])
    return seen - set(codes)


def requires_of(code, prereqs):
    entry = prereqs.get(code)
    return entry["requires"] if entry else None


# ===========================================================================
# Step 3: edges
# ===========================================================================

def make_edges(code, tree):
    """One edge per course in the course's prerequisite tree.

    type "required"     the course is needed no matter what (only ANDs above it)
    type "alternative"  it's one option of an OR; edges from the same OR share
                        a "group" so the site can say "one of these"
    """
    edges = []
    counter = [0]

    def visit(node, or_group):
        if node is None:
            return
        if node["type"] == "course":
            if node["code"] == code:          # a course listing itself (multi-part courses)
                return
            edges.append({
                "from": node["code"],
                "to": code,
                "type": "alternative" if or_group else "required",
                "group": or_group,
                "concurrent": node.get("concurrent", False),
                "min_grade": node.get("min_grade"),
            })
        elif node["type"] in ("and", "or"):
            group = or_group
            if node["type"] == "or" and any(all_courses(i) for i in node["items"]):
                counter[0] += 1
                group = "%s/or%d" % (code, counter[0])
            for item in node["items"]:
                visit(item, group)

    visit(tree, None)
    return edges


# ===========================================================================
# Step 4: columns
# ===========================================================================

class ColumnFinder:
    """Computes each course's column (see the top of this file)."""

    def __init__(self, prereqs, preferred=(), upper_division_floor=0):
        self.prereqs = prereqs
        self.preferred = set(preferred)     # the major's own courses
        self.floor = upper_division_floor   # see "Upper-division floor" above
        self.column = {}           # memo: code -> column, once known
        self.in_progress = set()   # courses we're in the middle of computing
        self.cycles = []           # loops found along the way

    def of(self, code, path=()):
        if code in self.column:
            return self.column[code]
        if code in self.in_progress:
            # We came back to a course we're still computing: a loop.
            self.cycles.append(list(path[path.index(code):]) + [code])
            return 0
        self.in_progress.add(code)
        value = self.evaluate(requires_of(code, self.prereqs), code, path + (code,))
        if is_upper_division(code):
            value = max(value, self.floor)
        self.in_progress.discard(code)
        self.column[code] = value
        return value

    def evaluate(self, node, code, path):
        """Column a course would get from this piece of its prerequisite tree."""
        if node is None or node["type"] == "condition":
            return 0                       # "consent of instructor" adds no quarter
        if node["type"] == "course":
            if node["code"] == code:
                return 0
            if node.get("concurrent"):
                # Same quarter is fine. Pairs that each list the other as
                # concurrent would loop forever, so don't follow those.
                if node["code"] in self.in_progress:
                    return 0
                return self.of(node["code"], path)
            return self.of(node["code"], path) + 1
        if node["type"] == "and":
            return max(self.evaluate(item, code, path) for item in node["items"])
        # "or": the earliest alternative, choosing only among the ones a
        # student in this major would actually take:
        #  - conditions ("or consent of instructor", "or an AP exam") are
        #    skipped when there's a course to take instead;
        #  - alternatives that are part of the major win over outside ones.
        #    (An alternative counts as "in the major" if any course in it is.)
        #    Without this, "MATH 3B or 3BI" would place MATH 4A by 3BI (an
        #    honors course the catalog lists with no prerequisites), one
        #    column earlier than where Economics students actually take it.
        options = [item for item in node["items"] if all_courses(item)] or node["items"]
        in_major = [item for item in options
                    if any(c["code"] in self.preferred for c in all_courses(item))]
        return min(self.evaluate(item, code, path) for item in (in_major or options))


# ===========================================================================
# Putting it together
# ===========================================================================

QUARTER_ORDER = ["Fall", "Winter", "Spring", "Summer"]
OFFERING_OVERRIDES = {}      # filled from offering_overrides.json in main()


def offered_for(code, info):
    """When a course is usually offered, from the best source there is:
      1. offering_overrides.json, hand corrections with a source;
      2. the catalog's "quarters usually offered" field;
      3. the course's own notes or description, when they say so in so many
         words ("Quarters usually offered: Spring", "Offered every fall
         quarter", "summer only"). About ten courses do.
    An empty list means nobody says; the planner then assumes Fall, Winter
    and Spring and marks the course "assumed"."""
    if code in OFFERING_OVERRIDES:
        return OFFERING_OVERRIDES[code]["offered"]
    if info.get("offered"):
        return info["offered"]
    text = " ".join([info.get("comments") or "", info.get("description") or ""])
    found = []
    match = re.search(r"quarters usually offered:\s*([A-Za-z ,]+)", text, flags=re.IGNORECASE)
    if match:
        found = [q for q in QUARTER_ORDER if q.lower() in match.group(1).lower()]
    elif re.search(r"summer( session)? only", text, flags=re.IGNORECASE):
        found = ["Summer"]
    else:
        match = re.search(r"offered every (fall|winter|spring)", text, flags=re.IGNORECASE)
        if match:
            found = [match.group(1).capitalize()]
    return found


def build_major(major, prereqs, catalog):
    major_courses, pools = collect_major_courses(major)
    outside = add_outside_prerequisites(major_courses.keys(), prereqs)
    floor = upper_division_floor(major_courses, prereqs)
    finder = ColumnFinder(prereqs, preferred=major_courses.keys(), upper_division_floor=floor)

    nodes = []
    edges = []
    for code in sorted(set(major_courses) | outside, key=sort_key):
        info = catalog.get(code, {})
        entry = prereqs.get(code, {})
        in_major = code in major_courses
        status = major_courses[code]["status"] if in_major else ("active" if info else "not_in_catalog")
        nodes.append({
            "id": code,
            "title": info.get("title", ""),
            "units": info.get("units", ""),
            "offered": offered_for(code, info),
            "level": info.get("level", ""),
            "status": status,
            "in_major": in_major,
            "role": major_courses[code]["role"] if in_major else "prerequisite",
            "groups": major_courses[code]["groups"] if in_major else [],
            "column": finder.of(code),
            "prereq_text": info.get("prereq_text", ""),
            "requires": entry.get("requires"),
            "ambiguous": entry.get("ambiguous", False),
            "description": info.get("description", ""),
        })
        edges.extend(make_edges(code, entry.get("requires")))

    # Lecture/lab pairs that must be taken together list each other as
    # "concurrent", so the recursion stops at the loop and one of the pair can
    # end up a column early. One cleanup pass pushes every course right of
    # (or level with, for "concurrent") each course it REQUIRES. Repeat until
    # nothing moves; with no real loops this always stops.
    column = {n["id"]: n["column"] for n in nodes}
    for _ in range(len(nodes)):
        moved = False
        for edge in edges:
            if edge["type"] != "required":
                continue
            needed = column[edge["from"]] + (0 if edge["concurrent"] else 1)
            if column[edge["to"]] < needed:
                column[edge["to"]] = needed
                moved = True
        if not moved:
            break
    for node in nodes:
        node["column"] = column[node["id"]]

    # Columns start at the major's first course: if every course is at least
    # column 1 (e.g. all need an outside course), shift left.
    lowest = min((n["column"] for n in nodes), default=0)
    for node in nodes:
        node["column"] -= lowest

    return {
        "major": {
            "id": major["id"],
            "name": major["name"],
            "kind": major["kind"],
            "catalog_year": major["catalog_year"],
            "source": major["source"],
            "sections": major["sections"],
            "narrative": major["narrative"],
            "overrides_applied": major.get("overrides_applied", []),
        },
        "nodes": nodes,
        "edges": edges,
        "pools": pools,
        "loops": real_cycles(finder.cycles, prereqs),
        "stats": {
            "courses_in_major": len(major_courses),
            "outside_prerequisites": len(outside),
            "edges": len(edges),
            "columns": max((n["column"] for n in nodes), default=0) + 1,
            "upper_division_floor": floor,
        },
    }


def is_upper_division(code):
    """Course numbers 100 and up are upper division (200+ is graduate)."""
    match = re.search(r"(\d+)[A-Z]*$", code)
    return bool(match) and int(match.group(1)) >= 100


def upper_division_floor(major_courses, prereqs):
    """The earliest column an upper-division course is placed in.

    Many upper-division courses list no course prerequisites, only "upper-
    division standing" (about 90 units, junior year) or a major restriction.
    By prerequisites alone they'd sit in column 0, next to first-quarter
    courses, which misleads anyone planning a schedule. So upper-division
    courses never go left of the earliest required (or "choice") course in
    the major's upper-division section that has course prerequisites
    (Economics: ECON 100B, 101 and 140A; Statistics: PSTAT 120A).
    """
    finder = ColumnFinder(prereqs, preferred=major_courses.keys())
    core = {code: info for code, info in major_courses.items()
            if info["role"] in ("required", "choice") and is_upper_division(code)
            and all_courses(requires_of(code, prereqs))}
    # Prefer courses from the major's upper-division section: Economics lets
    # PSTAT 120A replace ECON 5 in its preparation, and that shouldn't pull
    # every upper-division ECON course left to where PSTAT 120A sits.
    in_ud_section = [code for code, info in core.items()
                     if any(re.search(r"upper", g, re.IGNORECASE) for g in info["groups"])]
    columns = [finder.of(code) for code in (in_ud_section or core)]
    return min(columns) if columns else 0


def sort_key(code):
    match = re.match(r"^(.*?)\s*(\d+)(.*)$", code)
    if not match:
        return (code, 0, "")
    return (match.group(1), int(match.group(2)), match.group(3))


def real_cycles(cycles, prereqs):
    """Keep only loops that include at least one non-concurrent step.
    (A loop made only of "take together" links is a lecture/lab pair.)"""
    found = []
    for cycle in cycles:
        steps = list(zip(cycle, cycle[1:]))       # (course, prerequisite it needs)
        concurrent_only = True
        for course, needed in steps:
            for c in all_courses(requires_of(course, prereqs)):
                if c["code"] == needed and not c["concurrent"]:
                    concurrent_only = False
        if not concurrent_only and cycle not in found:
            found.append(cycle)
    return found


def main():
    sys.stdout.reconfigure(errors="replace")
    with open("prereqs.json", encoding="utf-8") as f:
        prereqs = {c["code"]: c for c in json.load(f)["courses"]}
    with open("raw_courses.json", encoding="utf-8") as f:
        catalog = {c["code"]: c for c in json.load(f)["courses"]}
    with open("offering_overrides.json", encoding="utf-8") as f:
        OFFERING_OVERRIDES.update(json.load(f)["courses"])
    known = sum(1 for code, info in catalog.items() if offered_for(code, info))
    print("Courses with known offering quarters: %d of %d (catalog field %d, course text %d, hand corrections %d)" % (
        known, len(catalog), sum(1 for c in catalog.values() if c.get("offered")),
        sum(1 for code, c in catalog.items() if not c.get("offered") and code not in OFFERING_OVERRIDES and offered_for(code, c)),
        len(OFFERING_OVERRIDES)))
    with open(os.path.join(MAJORS_DIR, "index.json"), encoding="utf-8") as f:
        everything = json.load(f)["majors"]
    index = [m for m in everything if m["structured"]]

    wanted = [a.removesuffix(".json") for a in sys.argv[1:]]
    if wanted:
        index = [m for m in index if m["file"][:-5] in wanted]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not wanted:
        # Start clean, so graphs for programs that were retired don't linger.
        for old in os.listdir(OUTPUT_DIR):
            if old.endswith(".json") and old not in KEEP_IN_DATA:
                os.remove(os.path.join(OUTPUT_DIR, old))
    listing = []
    for entry in index:
        with open(os.path.join(MAJORS_DIR, entry["file"]), encoding="utf-8") as f:
            major = json.load(f)
        graph = build_major(major, prereqs, catalog)
        with open(os.path.join(OUTPUT_DIR, entry["file"]), "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, separators=(",", ":"))
        listing.append({"id": entry["id"], "name": entry["name"], "kind": entry["kind"],
                        "department": entry["department"], "file": entry["file"],
                        "structured": True, **graph["stats"]})
    built = list(listing)

    if not wanted:
        # Programs with no course list in the catalog (College of Creative
        # Studies, Individual, Undeclared) are left out: the site only lists
        # programs it can draw.
        with open(os.path.join(OUTPUT_DIR, "majors.json"), "w", encoding="utf-8") as f:
            json.dump({"majors": sorted(listing, key=lambda m: m["name"])}, f, indent=1, ensure_ascii=False)

    print("Built %d graph(s) in %s (%d majors, %d minors)" % (
        len(built), OUTPUT_DIR, sum(m["kind"] == "major" for m in built), sum(m["kind"] == "minor" for m in built)))
    skipped = sum(not e["structured"] for e in everything)
    if skipped and not wanted:
        print("Left out %d with no course list in the catalog" % skipped)
    for m in built[:10] if len(built) <= 10 else []:
        print("  %-45s %3d courses + %2d outside, %3d edges, %2d columns" % (
            m["name"], m["courses_in_major"], m["outside_prerequisites"], m["edges"], m["columns"]))

    loops = []
    for m in built:
        with open(os.path.join(OUTPUT_DIR, m["file"]), encoding="utf-8") as f:
            for cycle in json.load(f)["loops"]:
                if cycle not in loops:
                    loops.append(cycle)
    if loops:
        print("Prerequisite loops found (likely parsing mistakes; add an override):")
        for cycle in loops:
            print("  " + " -> needs -> ".join(cycle))
    else:
        print("No prerequisite loops.")


if __name__ == "__main__":
    main()
