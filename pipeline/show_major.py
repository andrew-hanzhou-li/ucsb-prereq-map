"""
show_major.py: print a major's requirements as an indented outline, so you can
check a data/majors/*.json file against the catalog page by eye.

    py pipeline/show_major.py economics-ba
    py pipeline/show_major.py statistics-and-data-science-bs
    py pipeline/show_major.py --list              (every available major)

Long lists of single courses are printed on one line. Courses marked
[inactive] are named in the major but not currently offered; [+] marks a
course added by program_overrides.json.
"""

import json
import sys


def describe(node):
    if node["type"] == "all":
        return "Complete ALL of:"
    if node["type"] == "choose":
        text = "Complete at least %d of:" % node["count"]
        if node.get("units"):
            text += " (at least %s units)" % node["units"]
        return text
    if node["type"] == "units":
        return "Earn at least %s units from:" % node["units"]
    return ""


def course_text(node):
    text = node.get("code") or ("unknown course " + node.get("catalog_id", ""))
    if node["status"] != "active":
        text += " [%s]" % node["status"]
    if node.get("added_by_override"):
        text += " [+]"
    return text


def show(node, depth):
    pad = "    " * depth
    label = (node.get("label") + "  ") if node.get("label") else ""

    if node["type"] == "course":
        print(pad + course_text(node))
        return
    if node["type"] == "text":
        print(pad + label + "(text) " + node["text"].replace("\n", " "))
        return

    print(pad + label + describe(node))
    items = node["items"]
    if len(items) > 6 and all(i["type"] == "course" for i in items):
        source = items[0].get("from_list")
        if source:
            print(pad + "    from the catalog list '%s' (%d courses):" % (source, len(items)))
        print(pad + "    " + ", ".join(course_text(i) for i in items))
        return
    for item in items:
        show(item, depth + 1)


def main():
    sys.stdout.reconfigure(errors="replace")
    with open("data/majors/index.json", encoding="utf-8") as f:
        index = json.load(f)["majors"]

    if len(sys.argv) < 2 or sys.argv[1] == "--list":
        for entry in index:
            if entry["structured"]:
                print("%-60s %s" % (entry["name"], entry["file"][:-5]))
        return

    name = sys.argv[1].removesuffix(".json")
    with open("data/majors/%s.json" % name, encoding="utf-8") as f:
        major = json.load(f)

    print("%s  (%s catalog)" % (major["name"], major["catalog_year"]))
    print(major["source"])
    for section in major["sections"]:
        print()
        print("== " + section["name"])
        show(section["requirement"], 0)
    if major.get("overrides_applied"):
        print()
        print("Hand corrections applied:")
        for why in major["overrides_applied"]:
            print("  - " + why)


if __name__ == "__main__":
    main()
