"""
build_single.py: put the whole website into one HTML file that opens in any
browser, even offline, by double-clicking it.

    py build_single.py

Reads   site/index.html, site/style.css, site/app.js, site/favicon.svg
        site/data/majors.json and every major's graph in site/data/
Writes  site/ucsb-prereq-map.html     (published with the site, so the
                                      footer's download link works)

Why a build step
----------------
The website loads each major's file from data/ only when you pick it. A
browser won't load files that way from a page opened straight from your
computer (file://), so the single file carries every major inside it, in
window.EMBEDDED. app.js checks for that and uses it instead of downloading.

Keeping it small
----------------
The 190 graph files repeat the same course details (title, description,
prerequisites) in every major that uses the course: 18 MB in all. Here each
course's details are stored once, in "courses", and each major keeps only
its own facts about a course (role, step, status). app.js puts the two back
together when a major is opened. Result: about 8 MB.
"""

import base64
import json
import re
import os
import sys

SITE = "site"
OUTPUT = os.path.join(SITE, "ucsb-prereq-map.html")

# Course details shared by every major (stored once).
SHARED = ("title", "units", "offered", "level", "prereq_text", "requires", "ambiguous", "description")
# A major's own facts about each of its courses.
PER_MAJOR = ("id", "status", "in_major", "role", "groups", "column")


def read(path):
    with open(os.path.join(SITE, path), encoding="utf-8") as f:
        return f.read()


def script_json(value):
    """JSON that's safe inside a <script> tag ("</script>" in a course
    description would otherwise end the script early)."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/")


def replace_once(text, old, new):
    if text.count(old) != 1:
        sys.exit("build_single.py: expected exactly one %r in index.html; did it change?" % old)
    return text.replace(old, new)


def main():
    sys.stdout.reconfigure(errors="replace")
    with open(os.path.join(SITE, "data", "majors.json"), encoding="utf-8") as f:
        majors = json.load(f)["majors"]

    courses = {}
    programs = {}
    for major in majors:
        if not major["structured"]:
            continue
        with open(os.path.join(SITE, "data", major["file"]), encoding="utf-8") as f:
            graph = json.load(f)
        for node in graph["nodes"]:
            courses.setdefault(node["id"], {key: node[key] for key in SHARED})
        programs[major["file"]] = {
            "major": graph["major"],
            "pools": graph["pools"],
            "stats": {"courses_in_major": graph["stats"]["courses_in_major"]},
            "nodes": [{key: node[key] for key in PER_MAJOR} for node in graph["nodes"]],
        }

    # The AP chart for the Credit box (build_credit.py).
    with open(os.path.join(SITE, "data", "credit.json"), encoding="utf-8") as f:
        credit_table = json.load(f)

    with open(os.path.join(SITE, "data", "course-index.json"), encoding="utf-8") as f:
        course_index = json.load(f)
    embedded = {"majors": majors, "courses": courses, "programs": programs, "credit": credit_table,
                "courseIndex": course_index}
    icon = "data:image/svg+xml;base64," + base64.b64encode(read("favicon.svg").encode("utf-8")).decode("ascii")

    page = read("index.html")
    page = replace_once(page, '<link rel="stylesheet" href="style.css">', "<style>\n" + read("style.css") + "</style>")
    page = replace_once(page, 'href="favicon.svg"', 'href="' + icon + '"')

    # Every script the page loads from site/ (student.js, app.js, credit.js…),
    # in the same order, copied into the page. The data goes in first, so
    # the scripts find window.EMBEDDED when they start.
    scripts = re.findall(r'<script src="([\w-]+\.js)"></script>', page)
    if not scripts:
        sys.exit("build_single.py: no <script src=...> tags found in index.html")
    for i, name in enumerate(scripts):
        inline = "<script>\n" + read(name) + "</script>"
        if i == 0:
            inline = "<script>window.EMBEDDED = " + script_json(embedded) + ";</script>\n" + inline
        page = replace_once(page, '<script src="%s"></script>' % name, inline)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(page)
    size = "(%.1f MB)" % (os.path.getsize(OUTPUT) / 1e6)
    print("Wrote %s: %s, %d programs, %d courses" % (OUTPUT, size, len(programs), len(courses)))

    # The links to this file say how big it is, so someone on a phone isn't
    # surprised. index.html carries the size from the last build; update it
    # if it changed (run this script again to carry it into the copy too).
    index = read("index.html")
    sized = re.sub(r'<span class="file-size">\([^)]*\)</span>', '<span class="file-size">%s</span>' % size, index)
    if sized != index:
        with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(sized)
        print("Updated the file size in index.html to %s" % size)


if __name__ == "__main__":
    main()
