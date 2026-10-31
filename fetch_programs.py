"""
fetch_programs.py: download every program (major, minor, degree) in the UCSB
catalog, with its requirements, and save it to raw_programs.json.

    py fetch_programs.py

This is Part 1's fetch.py, but for programs instead of courses. It sends the
same requests the catalog website sends when you open a major's
"Program Requirements" tab, in three steps:

  1. Programs.   Every program, with its requirement rules (2 requests).
  2. Course lists. Some rules say "16 units from Upper Division Statistics
                 Courses" and name the list by an ID. We download each list.
  3. Course IDs. Some rules name a course by an internal ID
                 ("3bqcxdGsNgF83jgVOQYD") instead of its code. We look those
                 up to get the code ("PHYS 7A").

About 30 requests in all, one per second. Only Python's standard library is used.
"""

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SCHOOL = "ucsb"
CATALOG_ID = "friXFQMHuLvLoBthCmmV"      # 2026-27 General Catalog (same as fetch.py)
EFFECTIVE_DATE = "2027-03-29"             # a date inside that catalog year
OUTPUT_FILE = "raw_programs.json"
API = "https://app.coursedog.com/api/v1/cm/" + SCHOOL
HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://catalog.ucsb.edu",
    "Referer": "https://catalog.ucsb.edu/",
    "User-Agent": "ucsb-prereq-planner (student project)",
}


def request(url, body=None):
    """GET (no body) or POST (with a JSON body). Returns the decoded JSON."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    method = "GET" if body is None else "POST"
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    time.sleep(1)                         # be polite to the server
    return result


# ---------------------------------------------------------------------------
# Step 1: programs
# ---------------------------------------------------------------------------

def get_programs():
    columns = ["name", "catalogDisplayName", "programGroupId", "id", "type",
               "departments", "requisites", "effectiveStartDate"]
    programs = []
    skip = 0
    while True:
        url = (API + "/programs/search/%24filters"
               + "?catalogId=" + CATALOG_ID
               + "&skip=%d&limit=400&sortBy=name" % skip
               + "&effectiveDatesRange=%s%%2C%s" % (EFFECTIVE_DATE, EFFECTIVE_DATE)
               + "&columns=" + "%2C".join(columns))
        page = request(url, {"condition": "AND", "filters": []})
        programs.extend(page["data"])
        print("  programs: %d of %d" % (len(programs), page["listLength"]))
        skip += 400
        if skip >= page["listLength"]:
            return programs


def simplify(program):
    """Keep the fields we need. Departments become just their codes."""
    return {
        "programGroupId": program["programGroupId"],
        "id": program["id"],
        "name": (program.get("catalogDisplayName") or program.get("name") or "").strip(),
        "type": program.get("type"),
        "departments": [d.get("id") or d.get("_id") for d in program.get("departments") or []],
        "effectiveStartDate": program.get("effectiveStartDate"),
        "requisites": program.get("requisites"),
    }


def find_references(programs):
    """Every course-list ID and course ID used in any rule."""
    list_ids, course_ids = set(), set()

    def walk(rules):
        for rule in rules or []:
            walk(rule.get("subRules"))
            value = rule.get("value")
            if not isinstance(value, dict):
                continue
            for entry in value.get("values") or []:
                for ref in entry.get("value") or []:
                    if value.get("condition") == "courseSets":
                        list_ids.add(ref)
                    elif " " not in ref:       # codes have a space; IDs don't
                        course_ids.add(ref)

    for program in programs:
        for section in (program["requisites"] or {}).get("requisitesSimple") or []:
            walk(section.get("rules"))
    return list_ids, course_ids


# ---------------------------------------------------------------------------
# Step 2: course lists
# ---------------------------------------------------------------------------

def get_course_lists(list_ids):
    lists = {}
    ids = sorted(list_ids)
    for i in range(0, len(ids), 20):
        url = (API + "/courseSets?courseSetGroupIds=" + ",".join(ids[i:i + 20])
               + "&effectiveDatesRange=%s,%s" % (EFFECTIVE_DATE, EFFECTIVE_DATE))
        for item in request(url).values():
            lists[item["courseSetGroupId"]] = {
                "name": item.get("name"),
                "description": item.get("description"),
                "type": item.get("type"),
                "structure": item.get("structure"),
                "courses": item.get("dynamicCourseList") or item.get("courseList") or [],
            }
    print("  course lists: %d" % len(lists))
    return lists


# ---------------------------------------------------------------------------
# Step 3: course IDs -> codes
# ---------------------------------------------------------------------------

def look_up_course_ids(course_ids):
    codes = {}
    ids = sorted(course_ids)
    for i in range(0, len(ids), 50):
        url = (API + "/courses/search/$filters?courseGroupIds="
               + urllib.parse.quote(",".join(ids[i:i + 50]), safe=",")
               + "&limit=100&effectiveDatesRange=%s%%2C%s" % (EFFECTIVE_DATE, EFFECTIVE_DATE)
               + "&formatDependents=false&returnResultsWithTotalCount=false"
               + "&columns=subjectCode,courseNumber,courseGroupId")
        for course in request(url, {})["data"]:
            codes[course["courseGroupId"]] = course["subjectCode"] + " " + course["courseNumber"]
    print("  course IDs looked up: %d of %d" % (len(codes), len(ids)))
    return codes


def main():
    print("Step 1: programs")
    programs = [simplify(p) for p in get_programs()]
    list_ids, course_ids = find_references(programs)

    print("Step 2: course lists")
    lists = get_course_lists(list_ids)
    for course_list in lists.values():
        for ref in course_list["courses"]:
            if " " not in ref:
                course_ids.add(ref)

    print("Step 3: course IDs")
    codes = look_up_course_ids(course_ids)

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "catalog_id": CATALOG_ID,
        "programs": programs,
        "course_sets": lists,
        "course_group_ids": codes,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=1, ensure_ascii=False)
    print("Wrote %s (%d programs)" % (OUTPUT_FILE, len(programs)))


if __name__ == "__main__":
    main()
