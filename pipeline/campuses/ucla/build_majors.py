"""
build_majors.py (UCLA): turn the catalog's major records into program files.

    python pipeline/campuses/ucla/build_majors.py

Reads   data/ucla/raw/majors/*.json          (from fetch.py)
        data/ucla/raw/courses/*.json         subject ids, for the catalog's ranges
        data/ucla/raw_courses.json           the course list (from extract.py)
        data/ucla/majors_translated.json     hand translations of prose rules,
                                             by rule id (see below)
Writes  data/ucla/programs/<major>.json      one per undergraduate major
        data/ucla/programs/index.json
        data/ucla/majors_prose.json          the prose rules still to translate

A UCLA major is a tree of rule groups. Each group has a line saying what to
do and, usually, what to do it with:
    "Select one course from:"                     [COM SCI M51A, EC ENGR M16]
    "Complete 17 courses as follows:"             13 courses and two choices
    "Complete 12 units minimum from:"             [CHEM 153A, CHEM 156, …]
    "Select three courses from French 100 through 169:"
                                                  a range the catalog stores as
                                                  a search (subject, numbers)
The line decides the rule:
    "Select / Complete N … from"     -> choose N  ("N units … from" -> N units)
    "Complete … as follows / the following / all", or no line  -> all of them
The count in "Complete 17 courses as follows" includes courses inside the
choices below it, so it's not checked against the list.

Some groups are prose only ("Select two life science courses from the life
sciences course list", "seven elective courses from Computer Science 100
through CM187 except M148"). Those are written into majors_prose.json and,
once translated by hand into the same node format UCSD's majors use
(course / all / choose / units / text, plus the shorthand items "range" and
"any"), kept in majors_translated.json under the rule's catalog id, so a new
download keeps them. A prose rule without a translation stays as text.
"""

import base64
import glob
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ucsd"))
from build_majors import expand  # noqa: E402  (the same node format and shorthand as UCSD)

RAW_MAJORS = os.path.join("data", "ucla", "raw", "majors")
RAW_COURSES = os.path.join("data", "ucla", "raw", "courses")
COURSES = os.path.join("data", "ucla", "raw_courses.json")
TRANSLATED = os.path.join("data", "ucla", "majors_translated.json")
PROSE_OUT = os.path.join("data", "ucla", "majors_prose.json")
PROGRAMS_DIR = os.path.join("data", "ucla", "programs")
SITE = "https://catalog.registrar.ucla.edu"
CATALOG_YEAR = "2026-27"
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15}
COUNT = r"(\d+|" + "|".join(NUMBER_WORDS) + r")"
CHOOSE_RULE = re.compile(r"^(?:Select|Complete|Choose|Take)\s+(?:at least\s+|a minimum of\s+|any\s+)?" + COUNT +
                         r"\b(?P<what>[^:]*?)\bfrom\b", re.IGNORECASE)
UNITS_RULE = re.compile(r"^(?:Select|Complete|Take)\s+(?:at least\s+|a minimum of\s+)?(\d+(?:\.\d+)?)\s+units?\b", re.IGNORECASE)
ALL_RULE = re.compile(r"^(?:Complete|Take)\b[^:]*\b(?:as follows|the following|all)\b", re.IGNORECASE)


def plain(markup):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup or "")).strip()


def count_of(word):
    word = word.lower()
    return NUMBER_WORDS.get(word) or int(word)


def subject_ids():
    """The catalog's id for each subject -> its code (from the course records)."""
    ids = {}
    for path in glob.glob(os.path.join(RAW_COURSES, "*.json")):
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        for area in record.get("educational_area_display") or []:
            if area.get("cl_id") and area.get("code"):
                ids[area["cl_id"]] = area["code"].strip()
    return ids


def dynamic_range(entry, ids):
    """A stored search ("French 100 through 169") -> a range item, or None."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(entry.get("encodedURL", "")).query).get("appliedFilters", [""])[0]
    try:
        search = json.loads(base64.b64decode(query + "=" * (-len(query) % 4)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    text = json.dumps(search)
    area = re.search(r'"educationalArea"\], "query": "([0-9a-f]{32})"', text)
    numbers = re.search(r'"codeNumber": \{"gte": "(\d+)", "lte": "(\d+)"\}', text)
    if not area or area.group(1) not in ids or not numbers:
        return None
    return {"type": "range", "subject": ids[area.group(1)], "from": int(numbers.group(1)), "to": int(numbers.group(2))}


class Converter:
    def __init__(self, ids, translated):
        self.ids = ids
        self.translated = translated
        self.prose = []          # rules with no list, for translating

    def group(self, container, major):
        """One rule group -> a node (UCSD's format, shorthand allowed)."""
        rule_id = container.get("cl_id")
        if rule_id in self.translated:
            return self.translated[rule_id]["node"]
        line = plain(container.get("description"))
        title = (container.get("title") or "").strip()
        parts = []
        for item in sorted((container.get("relationship") or []) + (container.get("container") or []) +
                           (container.get("dynamic_relationship") or []), key=lambda x: int(x.get("order") or 0)):
            if item.get("academic_item_code"):
                parts.append({"type": "course", "code": re.sub(r"\s+", " ", item["academic_item_code"]).strip()})
            elif item.get("encodedURL"):
                found = dynamic_range(item, self.ids)
                parts.append(found or {"type": "text", "text": item.get("description") or "a course list"})
            elif "description" in item and ("container" in item or "relationship" in item):
                node = self.group(item, major)
                if node:
                    parts.append(node)
        node = None
        units = UNITS_RULE.match(line)
        choose = CHOOSE_RULE.match(line)
        if not parts:
            if line:
                self.prose.append({"major": major, "rule_id": rule_id, "title": title, "text": line})
                node = {"type": "text", "text": line}
        elif units and re.search(r"\bfrom\b", line, re.IGNORECASE):
            node = {"type": "units", "units": float(units.group(1)), "items": parts}
        elif choose and (re.search(r"\bcourses?\b", choose.group("what"), re.IGNORECASE) or
                         not re.search(r"\bunits?\b", choose.group("what"), re.IGNORECASE)):
            node = {"type": "choose", "count": count_of(choose.group(1)), "items": parts}
        else:
            node = {"type": "all", "items": parts}
        if node is None:
            return None
        if node["type"] != "text" and title:
            node["label"] = title
        if node["type"] != "text" and line and not ALL_RULE.match(line):
            node["notes"] = line
        if node["type"] == "units" and float(node["units"]).is_integer():
            node["units"] = int(node["units"])
        return node


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main():
    with open(COURSES, encoding="utf-8") as f:
        catalog = {c["code"]: c for c in json.load(f)["courses"]}
    translated = {}
    if os.path.exists(TRANSLATED):
        with open(TRANSLATED, encoding="utf-8") as f:
            translated = json.load(f)
    converter = Converter(subject_ids(), translated)
    os.makedirs(PROGRAMS_DIR, exist_ok=True)
    for old in glob.glob(os.path.join(PROGRAMS_DIR, "*.json")):
        os.remove(old)
    listing, problems = [], []
    for path in sorted(glob.glob(os.path.join(RAW_MAJORS, "*.json"))):
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        if "Undergraduate" not in json.dumps(record.get("degree_level")):
            continue
        # "Computer Science BS" -> "Computer Science - BS", the form the site
        # shows as "Computer Science (B.S.)" (as UCSB's and UCSD's names).
        name = re.sub(r"\s+(BA|BS|BFA|BM|BMus|BArch)$", r" - \1", record["title"].strip())
        department = (record.get("academic_org") or {}).get("value", "") if isinstance(record.get("academic_org"), dict) else ""
        sections = []
        for top in (record.get("curriculumStructure") or {}).get("container") or []:
            node = converter.group(top, name)
            if node is None:
                continue
            here = []
            requirement = expand(node, catalog, here, name + " / " + (top.get("title") or ""))
            problems.extend(here)
            sections.append({"name": (top.get("title") or "Requirements").strip(), "requirement": requirement})
        page = os.path.basename(path)[:-5]
        program = {"id": "UCLA-" + page, "name": name, "kind": "major", "type": "Bachelor's Degree",
                   "catalog_year": CATALOG_YEAR, "source": SITE + "/major/2026/" + page,
                   "sections": sections, "narrative": []}
        target = slug(name) + ".json"
        with open(os.path.join(PROGRAMS_DIR, target), "w", encoding="utf-8") as f:
            json.dump(program, f, indent=1, ensure_ascii=False)
        codes = set(re.findall(r'"code": "([^"]+)"', json.dumps(sections)))
        listing.append({"id": program["id"], "name": name, "kind": "major", "department": department,
                        "file": target, "source": program["source"], "structured": True, "courses": len(codes),
                        "inactive": sum(1 for p in problems if "isn't in the catalog" in p and p.startswith(name)),
                        "unresolved": 0})
    with open(os.path.join(PROGRAMS_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"majors": listing}, f, indent=1, ensure_ascii=False)
    with open(PROSE_OUT, "w", encoding="utf-8") as f:
        json.dump(converter.prose, f, indent=1, ensure_ascii=False)
    print("Wrote %d majors to %s; %d prose rules not yet translated (%s)"
          % (len(listing), PROGRAMS_DIR, len(converter.prose), PROSE_OUT))
    print("%d codes not in the course list" % sum(1 for p in problems if "isn't in the catalog" in p))


if __name__ == "__main__":
    main()
