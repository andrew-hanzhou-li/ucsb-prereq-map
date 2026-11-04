"""
fetch.py - Part 1 of the UCSB Prereq Planner.

Downloads every course in the UCSB General Catalog (catalog.ucsb.edu) and
saves it to raw_courses.json. For each course we keep the code, title,
units, the prerequisite text exactly as the catalog writes it (cleaned of
HTML), enrollment comments, and the description.

Where the data comes from:
  catalog.ucsb.edu is built on a platform called Coursedog. When you browse
  the course list, your browser asks Coursedog's public API for the courses.
  This script sends the same request the catalog website sends.

How to run:
  py pipeline/fetch.py
No extra packages needed - only Python's standard library.

Be polite: the script waits 1 second between requests and only needs about
8 requests to get the whole catalog. Don't run it in a loop.
"""

import html
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Settings. If a new catalog year comes out, the catalog ID and date change.
# To find the new values: open catalog.ucsb.edu/courses, open your browser's
# developer tools (Network tab), go to page 2 of the results, and look for a
# request to app.coursedog.com. Copy catalogId and effectiveDatesRange from it.
# ---------------------------------------------------------------------------
SCHOOL = "ucsb"
CATALOG_ID = "friXFQMHuLvLoBthCmmV"          # 2026-27 General Catalog
EFFECTIVE_DATE = "2027-03-29"                  # a date inside that catalog year
PAGE_SIZE = 1000
OUTPUT_FILE = "data/raw_courses.json"

# The fields we ask the API to return.
COLUMNS = [
    "customFields.advisorEnrollmentComments", "customFields.quartersUsuallyOffered",
    "description", "longName", "courseNumber", "subjectCode", "code",
    "courseGroupId", "college", "departments", "credits", "requisites", "status",
]

# The same filter the catalog website uses: only courses that are currently
# active (have a description and a start term, and are not "hibernated").
FILTERS = {
    "condition": "AND",
    "filters": [{
        "id": "hCwAcIl8",
        "condition": "and",
        "filters": [
            {"id": "description-course", "condition": "field", "name": "description",
             "inputType": "text", "group": "course", "type": "isNotEmpty", "customField": False},
            {"id": "startTerm-course", "condition": "field", "name": "startTerm",
             "inputType": "text", "group": "course", "type": "isNotEmpty", "customField": False},
            {"id": "mF7cqilx", "condition": "or", "filters": [
                {"id": "hibernateTerm-course", "condition": "field", "name": "hibernateTerm",
                 "inputType": "text", "group": "course", "type": "isEmpty", "customField": True},
                {"id": "hibernateTerm-course", "condition": "field", "name": "hibernateTerm",
                 "inputType": "text", "group": "course", "type": "greaterThan", "value": "20264",
                 "customField": True},
                {"id": "hibernateTerm-course", "condition": "field", "name": "hibernateTerm",
                 "inputType": "text", "group": "course", "type": "contains", "value": " ",
                 "customField": True},
            ]},
        ],
    }],
}


def build_url(skip):
    """Build the API address for one page of results."""
    return (
        f"https://app.coursedog.com/api/v1/cm/{SCHOOL}/courses/search/%24filters"
        f"?catalogId={CATALOG_ID}&skip={skip}&limit={PAGE_SIZE}&orderBy=code"
        f"&formatDependents=false&effectiveDatesRange={EFFECTIVE_DATE}%2C{EFFECTIVE_DATE}"
        f"&ignoreEffectiveDating=false&ignoreTotalCount=false"
        f"&columns={'%2C'.join(COLUMNS)}"
    )


def get_page(skip):
    """Ask the API for one page of courses. Returns the decoded JSON."""
    request = urllib.request.Request(
        build_url(skip),
        data=json.dumps(FILTERS).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Origin": "https://catalog.ucsb.edu",
            "Referer": "https://catalog.ucsb.edu/",
            "User-Agent": "ucsb-prereq-planner (student project)",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def clean_text(text):
    """Turn catalog text into plain text.

    The catalog sometimes stores text as HTML, e.g.
        '<p>PHYS 5/PHYS 5L or PHYS 7D &amp; 7L.</p>'
    which we turn into
        'PHYS 5/PHYS 5L or PHYS 7D & 7L.'
    """
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>|</p>", " ", text)   # line breaks become spaces
    text = re.sub(r"<[^>]+>", "", text)            # remove any other tags
    text = html.unescape(text)                      # &amp; -> &, &nbsp; -> space
    text = text.replace(" ", " ")
    text = re.sub(r"^Comments:\s*", "", text)       # a few entries start with this label
    return re.sub(r"\s+", " ", text).strip()        # collapse repeated spaces


def course_level(number):
    """Lower division is 1-99, upper division 100-199, graduate 200+."""
    digits = re.search(r"\d+", number or "")
    if not digits:
        return "unknown"
    n = int(digits.group())
    if n < 100:
        return "lower"
    if n < 200:
        return "upper"
    return "graduate"


def format_units(credits):
    """Units are stored as a min/max range; '4' or '1-4'.

    Variable-unit courses (independent study, 199s) store 0 credit hours and
    put their range in "contactHours" instead (ANTH 99: 1 to 4 units), so
    for those the range comes from there."""
    hours = (credits or {}).get("creditHours") or {}
    low, high = hours.get("min"), hours.get("max")
    if not low:
        contact = (credits or {}).get("contactHours") or {}
        if contact.get("min"):
            low, high = contact.get("min"), contact.get("max")
    if low is None:
        return ""
    if high and high != low:
        return f"{low}-{high}"
    return str(low)


def quarters_offered(custom):
    """The quarters a course is usually offered, when the catalog says
    (["Fall", "Spring"]). Most courses leave this empty, so an empty list
    means "not listed", not "never"."""
    order = ["Fall", "Winter", "Spring", "Summer"]
    listed = custom.get("quartersUsuallyOffered") or []
    return [q for q in order if q in listed]


def simplify(raw):
    """Keep only the fields the planner needs, in a simple flat shape."""
    number = (raw.get("courseNumber") or "").strip()
    subject = (raw.get("subjectCode") or "").strip()
    requisites = (raw.get("requisites") or {}).get("requisitesFreeform") or {}
    custom = raw.get("customFields") or {}
    return {
        "code": f"{subject} {number}",
        "subject": subject,
        "number": number,
        "level": course_level(number),
        "title": clean_text(raw.get("longName")),
        "units": format_units(raw.get("credits")),
        "offered": quarters_offered(custom),
        "prereq_text": clean_text(requisites.get("value")),
        "comments": clean_text(custom.get("advisorEnrollmentComments")),
        "description": clean_text(raw.get("description")),
        "college": raw.get("college") or "",
        "departments": department_ids(raw.get("departments")),
    }


def department_ids(departments):
    """The API sometimes returns full department records; keep just the IDs."""
    ids = []
    for d in departments or []:
        ids.append(d.get("id") if isinstance(d, dict) else d)
    return ids


def sort_key(course):
    """Sort like a person would: MATH 3A, MATH 4A, MATH 108A (not 108A before 3A)."""
    match = re.search(r"\d+", course["number"])
    number = int(match.group()) if match else 0
    return (course["subject"], number, course["number"])


def remove_duplicates(courses):
    """A few courses appear twice (an old and a new version). Keep the last one."""
    by_code = {}
    for course in courses:
        by_code[course["code"]] = course
    return list(by_code.values())


def main():
    courses = []
    skip = 0
    total = None
    while total is None or skip < total:
        page = get_page(skip)
        total = page.get("listLength", 0)
        batch = page.get("data") or []
        if not batch:
            break
        courses.extend(simplify(c) for c in batch)
        skip += len(batch)
        print(f"Downloaded {skip} of {total} courses")
        time.sleep(1)  # be polite to the server

    courses = remove_duplicates(courses)
    courses.sort(key=sort_key)

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "https://catalog.ucsb.edu (public Coursedog catalog API)",
        "catalog_id": CATALOG_ID,
        "course_count": len(courses),
        "courses": courses,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=1, ensure_ascii=False)
    print(f"Saved {len(courses)} courses to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
