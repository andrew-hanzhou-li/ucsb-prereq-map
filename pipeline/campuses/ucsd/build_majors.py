"""
build_majors.py (UC San Diego): turn the translated majors into program files.

    python pipeline/campuses/ucsd/build_majors.py

Reads   data/ucsd/majors/*.json          each major's requirements, translated
                                         from the catalog's program pages (see
                                         data/ucsd/majors/README.md)
        data/ucsd/raw_courses.json       the course list (from extract.py)
        data/ucsd/programs/index.json    the department maps (build_departments.py)
Writes  data/ucsd/programs/<major>.json  one per major, in UCSB's format
        data/ucsd/programs/index.json    majors added to the list

Run build_departments.py first: it starts the programs folder fresh.

UCSD's majors are written as prose, so each was translated by hand into
requirement nodes (all / choose / units / course / text). Three shorthand
items stand for lists the catalog describes by rule; they're expanded here
from the course list:
    {"type": "tagged", "subject": "CSE", "tag": "Systems"}     courses with that tag
    {"type": "any", "subject": "CSE", "level": "upper", "except": [...]}
    {"type": "range", "subject": "COGS", "from": 120, "to": 127}
"""

import glob
import json
import os
import re
import sys

MAJORS_DIR = os.path.join("data", "ucsd", "majors")
COURSES = os.path.join("data", "ucsd", "raw_courses.json")
PROGRAMS_DIR = os.path.join("data", "ucsd", "programs")
CATALOG_YEAR = "2026-27"
RENUMBERED_TO = {}         # filled in main(): old code -> new code
NODE_TYPES = {"course", "all", "choose", "units", "text", "tagged", "any", "range"}


def number_of(code):
    match = re.search(r"(\d+)[A-Z]*$", code)
    return int(match.group(1)) if match else None


def catalog_form(code, catalog):
    """The catalog's spelling of a code: "MAE 2" is listed as "MAE 02"."""
    if code in catalog:
        return code
    match = re.match(r"(.+?) 0*(\d+)([A-Z]*)$", code)
    if match:
        for c in catalog:
            other = re.match(r"(.+?) 0*(\d+)([A-Z]*)$", c)
            if other and other.groups() == (match.group(1), match.group(2), match.group(3)):
                return c
    return code


RENUMBERED = re.compile(r"(?:Renumbered from|Formerly(?: numbered)?) ((?:[A-Z]{2,5} ?)?\d+[A-Z]*(?:(?:,| and| or|/) ?(?:[A-Z]{2,5} )?\d+[A-Z]*)*)")


def renumbered_courses(catalog):
    """Old code -> new code, from the catalog's "Renumbered from CSE 154." and
    "Formerly MATH 110A." notes. Majors pages still print some old numbers."""
    found = {}
    for code, info in catalog.items():
        text = " ".join(info.get(k) or "" for k in ("description", "comments", "prereq_text"))
        for match in RENUMBERED.finditer(text):
            for part in re.split(r",| and| or|/", match.group(1)):
                part = part.strip()
                if not part:
                    continue
                if not re.match(r"[A-Z]", part):
                    part = info["subject"] + " " + part
                found.setdefault(re.sub(r"^([A-Z]+)(\d)", r"\1 \2", part), set()).add(code)
    return {old: new.pop() for old, new in found.items() if len(new) == 1 and old not in catalog}


def required_outright(node, catalog):
    """Courses every student in the major must take: reached from a section
    only through "all" groups, never through a choice."""
    if node.get("type") == "course":
        return {catalog_form(re.sub(r"\s+", " ", node.get("code", "").strip()), catalog)}
    if node.get("type") == "all":
        return set().union(*[required_outright(item, catalog) for item in node.get("items", [])]) if node.get("items") else set()
    return set()


def expand(node, catalog, problems, where, required=frozenset()):
    """The node with shorthand items replaced by the courses they stand for,
    and every course given a status. Problems go into `problems`.
    A shorthand list ("any upper-division ECE course") leaves out the
    courses the major already requires, which can't count twice."""
    kind = node.get("type")
    if kind not in NODE_TYPES:
        problems.append("%s: unknown node type %r" % (where, kind))
        return {"type": "text", "text": json.dumps(node)}
    if kind == "course":
        code = catalog_form(re.sub(r"\s+", " ", node.get("code", "").strip()), catalog)
        if code not in catalog and code in RENUMBERED_TO:
            return {"type": "course", "code": RENUMBERED_TO[code], "status": "active", "was": code}
        if code not in catalog:
            problems.append("%s: %s isn't in the catalog" % (where, code))
        return {"type": "course", "code": code, "status": "active" if code in catalog else "inactive"}
    if kind == "text":
        # (optional: shown, not counted, like an honors program.)
        return dict({"type": "text", "text": node.get("text", "")}, **({"optional": True} if node.get("optional") else {}))
    if kind in ("tagged", "any", "range"):
        subject = node.get("subject", "")
        if kind == "tagged":
            codes = [c for c, info in catalog.items() if info["subject"] == subject and node.get("tag") in info.get("tags", [])]
        elif kind == "any":
            # (No level: any undergraduate course of the subject.)
            low, high = {"lower": (1, 99), "upper": (100, 199)}.get(node.get("level"), (0, 199))
            skip = set(node.get("except", []))
            codes = [c for c, info in catalog.items()
                     if info["subject"] == subject and low <= (number_of(c) or -1) <= high and c not in skip]
        else:
            skip = set(node.get("except", []))
            codes = [c for c, info in catalog.items()
                     if info["subject"] == subject and node.get("from", 0) <= (number_of(c) or -1) <= node.get("to", -1)
                     and c not in skip]
        codes = [c for c in codes if c not in required]
        if not codes:
            problems.append("%s: %s matches no course" % (where, json.dumps(node)))
        return {"type": "choose", "count": 1, "items": [{"type": "course", "code": c, "status": "active"}
                                                       for c in sorted(codes, key=lambda c: (number_of(c), c))],
                "label": describe(node), "expanded_from": kind}
    items = [expand(item, catalog, problems, where, required) for item in node.get("items", [])]
    # A shorthand list inside a choose/units joins that list directly.
    flat = []
    for item in items:
        if item.get("expanded_from") and kind in ("choose", "units"):
            flat.extend(item["items"])
        else:
            flat.append(item)
    out = {"type": kind, "items": flat}
    if kind == "choose":
        out["count"] = int(node.get("count", 1))
        if out["count"] > len(flat):
            problems.append("%s: choose %d from only %d items" % (where, out["count"], len(flat)))
    if kind == "units":
        out["units"] = node.get("units", 0)
    for key in ("label", "notes", "may_share", "optional"):
        if node.get(key):
            out[key] = node[key]
    if not flat:
        problems.append("%s: an empty %s" % (where, kind))
    return out


def describe(node):
    if node["type"] == "tagged":
        return "%s courses tagged %s" % (node.get("subject"), node.get("tag"))
    if node["type"] == "any":
        level = node.get("level")
        return "any %s%s course" % (level + "-division " if level else "", node.get("subject"))
    return "%s %s–%s" % (node.get("subject"), node.get("from"), node.get("to"))


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main():
    with open(COURSES, encoding="utf-8") as f:
        catalog = {c["code"]: c for c in json.load(f)["courses"]}
    RENUMBERED_TO.update(renumbered_courses(catalog))
    index_path = os.path.join(PROGRAMS_DIR, "index.json")
    with open(index_path, encoding="utf-8") as f:
        listing = [m for m in json.load(f)["majors"] if m["kind"] != "major"]
    all_problems, built = [], 0
    for path in sorted(glob.glob(os.path.join(MAJORS_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            major = json.load(f)
        name = major["name"]
        problems = []
        required = set().union(*[required_outright(s["requirement"], catalog) for s in major.get("sections", [])])
        sections = [{"name": s["name"], "requirement": expand(s["requirement"], catalog, problems, name + " / " + s["name"],
                                                              frozenset(required))}
                    for s in major.get("sections", [])]
        program = {
            "id": "UCSD-MAJOR-" + slug(name),
            "name": name,
            "kind": "major",
            "type": major.get("type", "Bachelor's Degree"),
            "catalog_year": CATALOG_YEAR,
            "source": major.get("source", ""),
            "sections": sections,
            "narrative": major.get("narrative", []),
        }
        target = slug(name) + ".json"
        with open(os.path.join(PROGRAMS_DIR, target), "w", encoding="utf-8") as f:
            json.dump(program, f, indent=1, ensure_ascii=False)
        codes = set(re.findall(r'"code": "([^"]+)"', json.dumps(sections)))
        listing.append({"id": program["id"], "name": name, "kind": "major", "department": major.get("department", ""),
                        "file": target, "source": program["source"], "structured": True,
                        "courses": len(codes), "inactive": sum(1 for p in problems if "isn't in the catalog" in p),
                        "unresolved": 0})
        all_problems.extend(problems)
        built += 1
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"majors": listing}, f, indent=1, ensure_ascii=False)
    print("Wrote %d majors to %s" % (built, PROGRAMS_DIR))
    for problem in all_problems:
        print("  " + problem)
    return 1 if any("unknown node type" in p or "empty" in p for p in all_problems) else 0


if __name__ == "__main__":
    sys.exit(main())
