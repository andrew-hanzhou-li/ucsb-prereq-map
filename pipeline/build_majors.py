"""
build_majors.py: turn the catalog's major and minor requirements into one file each.

    py pipeline/build_majors.py

Reads   raw_programs.json       every program in the catalog, with its
                                requirements (from fetch_programs.py)
        raw_courses.json        from Part 1, to check every course exists
        program_overrides.json  hand corrections for rules stated only in notes
                                ("add" courses, "exclude" courses, or "choose"
                                one of several groups the catalog lists as all
                                required)
Writes  data/majors/<name>.json      one file per current bachelor's degree or minor,
                                e.g. data/majors/economics-ba.json, data/majors/mathematics-minor.json
        data/majors/index.json       list of all of them, for the site's major picker

Retired programs (the catalog marks them "Inactive", e.g. Geological
Sciences - BS, replaced by Earth Science) are left out. Current programs with
no course list in the catalog (College of Creative Studies majors,
Undeclared, Individual major) are listed in the index with
"structured": false and no file, so the site can explain why there's no map.

Where the data comes from
-------------------------
Unlike course prerequisites (free English that Part 2 had to parse), the
catalog stores major requirements as structured rules. For example, Economics
area D is stored as:

    {"condition": "completedAtLeastXOf", "restriction": 6,
     "value": {"condition": "courses", "values": [
         {"value": ["ECON 100C"], "logic": "and"},
         {"value": ["ECON 106"],  "logic": "and"}, ...]}}

which means "complete at least 6 of these courses". So this script doesn't
parse anything; it translates the catalog's rule types into a smaller set of
our own (below), looks up IDs, and expands named course lists.

Our requirement types
---------------------
    {"type": "course", "code": "ECON 1", "status": "active"}
    {"type": "all",    "items": [...]}                 complete every item
    {"type": "choose", "count": 6, "items": [...]}     complete at least `count` items
    {"type": "units",  "units": 16, "items": [...]}    earn at least `units` units from the items
    {"type": "text",   "text": "Level 1-6 of a language..."}   no course list; shown as words

Any node may also have "label" ("A.", "Pre-Major"), "description" and "notes"
(plain text copied from the catalog), and "from_list" (the name of a catalog
course list it was expanded from).

A course's "status" is:
    active      in the current course list (raw_courses.json)
    inactive    named in the major, but not in the current course list. Usually
                "hibernated": the catalog keeps the course but it isn't
                currently offered (e.g. ECON 141).
    unresolved  the catalog referred to it by an internal ID we couldn't look up
"""

import html
import json
import os
import re
import sys

OUTPUT_DIR = os.path.join("data", "majors")

# The catalog's rule types, and how each maps to ours.
#   completedAllOf        -> all
#   completedAnyOf        -> choose 1
#   completedAtLeastXOf   -> choose X     (X is the rule's "restriction")
#   minimumCredits        -> units N      (N is the rule's "credits")
#   allOf / anyOf         -> all / choose, over sub-rules instead of courses
#   freeformText          -> text
#   completeVariableCoursesAndVariableCredits -> choose minCourses, with a units minimum


def clean_text(text):
    """Catalog HTML -> plain text, keeping list items on their own lines."""
    if not text:
        return ""
    text = re.sub(r"<\s*(br|/p|/li)\s*/?>", "\n", text)
    text = re.sub(r"<li[^>]*>", "- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace(" ", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


class Converter:
    def __init__(self, data, active_codes, overrides):
        self.course_sets = data["course_sets"]
        self.group_ids = data["course_group_ids"]
        self.active = active_codes
        self.overrides = overrides
        self.used_rule_ids = set()

    # ------------------------------------------------------------- courses
    def course(self, ref):
        """A catalog course reference -> a course node.

        Most references are codes ("ECON 1"). Some are internal IDs
        ("3bqcxdGsNgF83jgVOQYD") that we looked up when downloading."""
        code = ref if " " in ref else self.group_ids.get(ref)
        if code is None:
            return {"type": "course", "code": None, "status": "unresolved", "catalog_id": ref}
        code = re.sub(r"\s+", " ", code).strip()
        status = "active" if code in self.active else "inactive"
        return {"type": "course", "code": code, "status": status}

    def value_items(self, value):
        """The list inside a rule's "value" -> a list of nodes.

        Each entry is a group of one or more courses joined by "and" (take
        them all, e.g. a sequence) or "or" (take any one of them)."""
        items = []
        kind = value.get("condition")
        for entry in value.get("values") or []:
            refs = entry.get("value") or []
            if kind == "courseSets":
                for set_id in refs:
                    items.extend(self.expand_set(set_id))
                continue
            courses = [self.course(ref) for ref in refs]
            if len(courses) == 1:
                items.append(courses[0])
            elif entry.get("logic") == "or":
                items.append({"type": "choose", "count": 1, "items": courses})
            else:
                items.append({"type": "all", "items": courses})
        return items

    def expand_set(self, set_id):
        """A named catalog list ("Upper Division Statistics Courses") -> its courses.

        These lists are defined by a rule (e.g. "PSTAT, numbered 100-199"), and
        the catalog's copy of the list also holds every old course that ever
        matched the rule, including long-retired ones. We keep only courses in
        the current course list, which is what the rule means today."""
        course_set = self.course_sets.get(set_id)
        if course_set is None:
            return [{"type": "text", "text": "Unknown course list " + set_id}]
        nodes = [self.course(ref) for ref in course_set["courses"]]
        nodes = [n for n in nodes if n["status"] == "active"]
        for node in nodes:
            node["from_list"] = course_set["name"]
        nodes.sort(key=lambda n: sort_key(n.get("code") or ""))
        return nodes

    # --------------------------------------------------------------- rules
    def rule(self, rule):
        """One catalog rule -> one of our requirement nodes."""
        condition = rule.get("condition")
        value = rule.get("value") if isinstance(rule.get("value"), dict) else {}
        count = rule.get("restriction")
        units = rule.get("credits")

        if rule.get("subRules") is not None:
            items = [self.rule(sub) for sub in rule["subRules"]]
            if condition == "anyOf":
                node = {"type": "choose", "count": count or 1, "items": items}
            else:
                node = {"type": "all", "items": items}
        elif condition == "freeformText":
            text = rule.get("value") if isinstance(rule.get("value"), str) else ""
            node = {"type": "text", "text": text or clean_text(rule.get("description"))}
        elif value.get("condition") in ("none", None):
            node = {"type": "text", "text": clean_text(rule.get("description")) or "See the catalog."}
        else:
            items = self.value_items(value)
            if condition == "completedAllOf":
                node = {"type": "all", "items": items}
            elif condition == "completedAnyOf":
                node = {"type": "choose", "count": 1, "items": items}
            elif condition == "completedAtLeastXOf":
                node = {"type": "choose", "count": count or 1, "items": items}
            elif condition == "minimumCredits":
                node = {"type": "units", "units": units, "items": items}
                if count:
                    node["count"] = count
            elif condition == "completeVariableCoursesAndVariableCredits":
                node = {"type": "choose", "count": rule.get("minCourses") or 1,
                        "units": rule.get("minCredits"), "items": items}
            else:
                node = {"type": "text", "text": "Unrecognized rule type: %s" % condition}

        # Units on an all/choose node (e.g. "anyOf ... credits: 40") are kept as a note.
        if units and node["type"] in ("all", "choose") and "units" not in node:
            node["units"] = units

        rule_id = rule.get("id")
        if rule_id:
            node["catalog_rule_id"] = rule_id
        for key, field in (("label", "name"), ("description", "description"), ("notes", "notes")):
            text = clean_text(rule.get(field)) if field != "name" else (rule.get(field) or "").strip()
            if text:
                node[key] = text
        return node

    # ------------------------------------------------------------ program
    def program(self, program):
        sections = []
        narrative = []
        for section in (program.get("requisites") or {}).get("requisitesSimple") or []:
            if section.get("type") == "Narrative Text" or not section.get("rules"):
                text = clean_text(section.get("notes"))
                if text:
                    narrative.append(text)
                continue
            requirement = {"type": "all", "items": [self.rule(r) for r in section["rules"]]}
            if len(requirement["items"]) == 1:
                requirement = requirement["items"][0]
            entry = {"name": (section.get("name") or "").strip(), "requirement": requirement}
            notes = clean_text(section.get("notes"))
            if notes:
                entry["notes"] = notes
            sections.append(entry)

        result = {
            "id": program["programGroupId"],
            "name": program["name"],
            "type": program["type"],
            "kind": program_kind(program),
            "departments": program.get("departments") or [],
            "catalog_year": catalog_year(program.get("effectiveStartDate")),
            "source": "https://catalog.ucsb.edu/programs/" + program["programGroupId"],
            "narrative": narrative,
            "sections": sections,
        }
        self.apply_overrides(result)
        result["courses"] = course_summary(result)
        return result

    # ----------------------------------------------------------- overrides
    def apply_overrides(self, result):
        fix = self.overrides.get(result["id"])
        if not fix:
            return
        result["overrides_applied"] = []

        for rule_id, addition in (fix.get("add") or {}).items():
            node = find_rule(result, rule_id)
            if node is None:
                print("WARNING: %s: override rule %s not found; catalog changed?" % (result["id"], rule_id))
                continue
            existing = {item.get("code") for item in node["items"]}
            for code in addition["courses"]:
                if code not in existing:
                    item = self.course(code)
                    item["added_by_override"] = True
                    node["items"].append(item)
            result["overrides_applied"].append(addition["why"])

        exclude = fix.get("exclude")
        if exclude:
            drop = set(exclude["courses"])
            remove_courses(result, drop)
            result["overrides_applied"].append(exclude["why"])

        # "choose": groups the catalog lists as all required, but students
        # take only one of (Computer Engineering's two capstone sequences).
        # The groups are taken out of the rule and put back as one
        # "choose 1" of them, so the map shows "one of" and the planner
        # schedules one.
        for rule_id, choice in (fix.get("choose") or {}).items():
            node = find_rule(result, rule_id)
            wanted = [sorted(group) for group in choice["groups"]]
            found = [item for item in (node or {}).get("items", [])
                     if sorted(c.get("code") for c in item.get("items", [item])) in wanted]
            if node is None or len(found) != len(wanted):
                print("WARNING: %s: override rule %s or its groups not found; catalog changed?" % (result["id"], rule_id))
                continue
            node["items"] = [item for item in node["items"] if item not in found]
            node["items"].append({"type": "choose", "count": 1, "items": found,
                                  "label": choice.get("label", ""), "added_by_override": True})
            result["overrides_applied"].append(choice["why"])


# =========================================================================
# Small helpers
# =========================================================================

def sort_key(code):
    """'MATH 3A' before 'MATH 108A' (number order, not text order)."""
    match = re.match(r"^(.*?)\s*(\d+)(.*)$", code)
    if not match:
        return (code, 0, "")
    return (match.group(1), int(match.group(2)), match.group(3))


def catalog_year(date):
    """'2026-09-20' -> '2026-27'."""
    if not date:
        return ""
    year = int(date[:4])
    if int(date[5:7]) < 7:
        year -= 1
    return "%d-%02d" % (year, (year + 1) % 100)


def walk(node):
    """Every node in a requirement tree, parents first."""
    yield node
    for item in node.get("items", []):
        yield from walk(item)


def find_rule(result, rule_id):
    for section in result["sections"]:
        for node in walk(section["requirement"]):
            if node.get("catalog_rule_id") == rule_id:
                return node
    return None


def remove_courses(result, codes):
    def prune(node):
        if "items" in node:
            node["items"] = [i for i in node["items"] if not (i["type"] == "course" and i.get("code") in codes)]
            for item in node["items"]:
                prune(item)
    for section in result["sections"]:
        prune(section["requirement"])


def course_summary(result):
    """Every course mentioned anywhere in the major, once, with the section it's in."""
    seen = {}
    for section in result["sections"]:
        for node in walk(section["requirement"]):
            if node["type"] != "course":
                continue
            key = node.get("code") or node.get("catalog_id")
            if key not in seen:
                seen[key] = {"code": node.get("code"), "status": node["status"], "section": section["name"]}
                if node["status"] == "unresolved":
                    seen[key]["catalog_id"] = node["catalog_id"]
    return sorted(seen.values(), key=lambda c: sort_key(c["code"] or ""))


def department_name(codes, names):
    """The program's department, by name, for grouping the site's list:
    ["ECE"] -> "Electrical & Computer Engineering". The first one listed, if
    a program belongs to several."""
    for code in codes:
        if names.get(code):
            return names[code]
    return "Other programs"


def program_kind(program):
    """"major" for a bachelor's degree, "minor" for a minor."""
    return "minor" if program.get("type") == "Minor" else "major"


def file_name(name):
    """'Economics - BA ' -> 'economics-ba.json'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ".json"


# =========================================================================

def main():
    sys.stdout.reconfigure(errors="replace")
    with open("data/raw_programs.json", encoding="utf-8") as f:
        data = json.load(f)
    with open("data/raw_courses.json", encoding="utf-8") as f:
        active = {c["code"] for c in json.load(f)["courses"]}
    with open("data/program_overrides.json", encoding="utf-8") as f:
        overrides = json.load(f)["programs"]

    converter = Converter(data, active, overrides)
    dept_names = data.get("department_names") or {}
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    undergrad = [p for p in data["programs"]
                 if "Bachelor" in (p.get("type") or "") or p.get("type") == "Minor"]
    current = [p for p in undergrad if p.get("status") != "Inactive"]
    retired = len(undergrad) - len(current)
    # A name could appear twice under different program codes (an old and a
    # new code); those files get the code added so neither overwrites the other.
    name_counts = {}
    for program in current:
        name_counts[program["name"]] = name_counts.get(program["name"], 0) + 1

    # Start clean, so files for programs that were retired since the last
    # run don't linger.
    for old in os.listdir(OUTPUT_DIR):
        if old.endswith(".json"):
            os.remove(os.path.join(OUTPUT_DIR, old))

    index = []
    for program in current:
        result = converter.program(program)
        if name_counts[program["name"]] > 1:
            name_for_file = result["name"] + " " + result["id"]
        else:
            name_for_file = result["name"]
        has_rules = bool(result["sections"])
        statuses = [c["status"] for c in result["courses"]]
        entry = {
            "id": result["id"],
            "name": result["name"],
            "kind": result["kind"],
            "department": department_name(result["departments"], dept_names),
            "file": file_name(name_for_file),
            "source": result["source"],
            "structured": has_rules,
            "courses": len(statuses),
            "inactive": statuses.count("inactive"),
            "unresolved": statuses.count("unresolved"),
        }
        index.append(entry)
        if has_rules:
            with open(os.path.join(OUTPUT_DIR, entry["file"]), "w", encoding="utf-8") as f:
                json.dump(result, f, indent=1, ensure_ascii=False)

    index.sort(key=lambda e: e["name"])
    with open(os.path.join(OUTPUT_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"catalog_id": data["catalog_id"], "fetched_at": data["fetched_at"], "majors": index},
                  f, indent=1, ensure_ascii=False)

    structured = [e for e in index if e["structured"]]
    for kind in ("major", "minor"):
        of_kind = [e for e in index if e["kind"] == kind]
        print("Current %ss in catalog:          %d" % (kind, len(of_kind)))
        print("  with structured requirements:   %d  (written to data/majors/)" % sum(e["structured"] for e in of_kind))
        print("  no course list in the catalog:  %d" % sum(not e["structured"] for e in of_kind))
    print("Retired programs left out:        %d" % retired)
    print("Courses referenced:               %d" % sum(e["courses"] for e in structured))
    print("  inactive (not offered now):     %d" % sum(e["inactive"] for e in structured))
    print("  unresolved catalog IDs:         %d" % sum(e["unresolved"] for e in structured))


if __name__ == "__main__":
    main()
