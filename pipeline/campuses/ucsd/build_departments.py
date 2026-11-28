"""
build_departments.py (UC San Diego): one "program" per catalog department,
listing every undergraduate course on its page.

    python pipeline/campuses/ucsd/build_departments.py

Reads   data/ucsd/raw/index.html        department names (from fetch.py)
        data/ucsd/raw_courses.json      the courses (from extract.py)
Writes  data/ucsd/programs/<name>.json  one per department, in the same shape
                                        as UCSB's data/majors/*.json
        data/ucsd/programs/index.json

UCSD's majors aren't read yet (their requirements are prose), so a student
picks a department instead: its map shows all of its courses in
prerequisite order, with the outside courses they need. Every course is
listed as part of the department, lower and upper division separately.
"""

import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch   # noqa: E402  (the department list, same order as the catalog)

COURSES = os.path.join("data", "ucsd", "raw_courses.json")
INDEX_HTML = os.path.join(fetch.RAW_DIR, "index.html")
OUTPUT_DIR = os.path.join("data", "ucsd", "programs")
CATALOG_YEAR = "2026-27"

# One listing in the index:
#   <p>Anthropology <span class="courseFacLink">[ ... <a href="../courses/ANTH.html" title="Anthropology">courses</a> ...</p>
LISTING = re.compile(r"<p\b[^>]*>(?P<body>.*?)</p>", re.DOTALL)
COURSE_LINK = re.compile(r'<a href="\.\./courses/(?P<page>[A-Za-z0-9-]+)\.html"(?:\s+title="(?P<title>[^"]*)")?')


def plain(fragment):
    """Text of an HTML fragment, tags removed and spaces tidied."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def department_names(index_html):
    """{page: name}. A page can be listed under several names (CHEM.html
    under "Biochemistry and Molecular Biophysics" and "Chemistry"). The
    link's title wins when a listing's name is how it starts ("Chemistry" ->
    "Chemistry and Biochemistry"); else the first listing's name. Titles
    alone can't be trusted: some are copied from the line above ("Astronomy
    and Astrophysics" links to its courses with the title "Audiology")."""
    candidates = {}
    for listing in LISTING.finditer(index_html):
        body = listing.group("body")
        link = COURSE_LINK.search(body)
        if not link:
            continue
        name = plain(body.split("[", 1)[0])
        if name:
            candidates.setdefault(link.group("page"), []).append((name, link.group("title") or ""))
    names = {}
    for page, options in candidates.items():
        matching = [title for name, title in options if title and title.startswith(name)]
        names[page] = tidy_name(matching[0] if matching else options[0][0])
    return names


def tidy_name(name):
    """The index's inverted names, put the right way round:
        "Religion, Study of"                 -> "Study of Religion"
        "Engineering, Jacobs School of"      -> "Jacobs School of Engineering"
        "Biological Sciences, Division of"   -> "Biological Sciences"
    """
    match = re.match(r"^(?P<subject>.+), (?P<unit>[^,]+ of)$", name)
    if not match:
        return name
    if match.group("unit") == "Division of":
        return match.group("subject")
    return match.group("unit") + " " + match.group("subject")


def file_name(name):
    """"Computer Science and Engineering" -> "computer-science-and-engineering.json"."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + ".json"


def course_items(courses):
    return [{"type": "course", "code": c["code"], "status": "active"} for c in courses]


def main():
    with open(INDEX_HTML, encoding="utf-8") as f:
        index_html = f.read()
    with open(COURSES, encoding="utf-8") as f:
        courses = json.load(f)["courses"]
    names = department_names(index_html)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for old in os.listdir(OUTPUT_DIR):
        if old.endswith(".json"):
            os.remove(os.path.join(OUTPUT_DIR, old))

    listing, used_files = [], set()
    for page in fetch.department_pages(index_html):
        on_page = [c for c in courses if page.upper() in c["departments"]]
        if not on_page:
            continue                    # a graduate-only department
        name = names.get(page, page.upper())
        target = file_name(name)
        if target in used_files:        # two pages with the same name: keep both
            target = file_name(name + " " + page)
        used_files.add(target)
        sections = []
        for level, title in (("lower", "Lower division"), ("upper", "Upper division")):
            chosen = [c for c in on_page if c["level"] == level]
            if chosen:
                sections.append({"name": title, "requirement": {"type": "all", "items": course_items(chosen)}})
        program = {
            "id": "UCSD-" + page.upper(),
            "name": name,
            "kind": "department",
            "catalog_year": CATALOG_YEAR,
            "source": fetch.BASE + "courses/" + page + ".html",
            "sections": sections,
            "narrative": [],
        }
        with open(os.path.join(OUTPUT_DIR, target), "w", encoding="utf-8") as f:
            json.dump(program, f, indent=1, ensure_ascii=False)
        listing.append({"id": program["id"], "name": name, "kind": "department", "department": name,
                        "file": target, "source": program["source"], "structured": True,
                        "courses": len(on_page), "inactive": 0, "unresolved": 0})
    with open(os.path.join(OUTPUT_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"majors": listing}, f, indent=1, ensure_ascii=False)
    print("Wrote %d departments to %s" % (len(listing), OUTPUT_DIR))


if __name__ == "__main__":
    main()
