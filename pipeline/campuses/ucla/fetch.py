"""
fetch.py (UCLA): download the General Catalog's course and major records.

    python pipeline/campuses/ucla/fetch.py [subjects|courses|majors|all]

Reads   https://catalog.registrar.ucla.edu/sitemap.xml        the list of pages
        https://catalog.registrar.ucla.edu/api/content/academic-item-content
                ?siteId=ucla-prod-pres&path=/course/2026/COMSCI31&siteYear=current
                                                            one record per page
Writes  data/ucla/raw/courses/<COMSCI31>.json              the records, as downloaded
        data/ucla/raw/majors/<COMPUTERSCIENCEBS>.json
        data/ucla/raw/paths.json                           the pages found
        data/ucla/subjects.json                            subject codes and names
                (from the Schedule of Classes' subject list: "Mathematics (MATH)")

UCLA's catalog runs on CourseLoop: every course and major page loads its
record from this JSON endpoint on the catalog's own site (no key needed;
robots.txt allows everything). The 2026-27 catalog has about 15,000 course
pages (graduate courses included; extract.py keeps the undergraduate ones)
and about 300 major pages.

A record already saved isn't downloaded again, so the script can be stopped
and started; delete data/ucla/raw to fetch a new catalog year. Four requests
run at a time with a pause in each, to stay gentle on the server.
"""

import concurrent.futures
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SITE = "https://catalog.registrar.ucla.edu"
API = SITE + "/api/content/academic-item-content"
SITE_ID = "ucla-prod-pres"
YEAR = "2026"                     # the 2026-27 catalog ("current")
RAW_DIR = os.path.join("data", "ucla", "raw")
WORKERS = 4
PAUSE_SECONDS = 0.25
USER_AGENT = "prereq-planner (student project)"


def download(url, attempts=4):
    """The response's text. Tries again after a growing wait if the server
    or the network fails; gives up (raises) after `attempts` tries."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, */*"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == attempts:
                raise
            print("  retrying %s (%s)" % (url, error))
            time.sleep(3 * attempt)


def catalog_paths():
    """Course and major paths of this catalog year, from the sitemaps:
    ("course", "/course/2026/COMSCI31"), ("major", "/major/2026/COMPUTERSCIENCEBS")."""
    index = download(SITE + "/sitemap.xml")
    found = []
    for sitemap in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", index):
        for url in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", download(sitemap)):
            match = re.search(r"(/(course|major)/%s/[A-Za-z0-9]+)$" % YEAR, url)
            if match:
                found.append((match.group(2), match.group(1)))
    return sorted(set(found))


SOC_HOME = "https://sa.ucla.edu/ro/public/soc"
SUBJECT_MENU = re.compile(r"SearchPanelSetup\('(\[.*?\])'")


def fetch_subjects():
    """{"MATH": "Mathematics", "C&EE": "Civil and Environmental Engineering", …}
    from the subject menu the Schedule of Classes page carries: a JSON list
    ([{"label":"Mathematics (MATH)","value":"MATH   "}, …]), HTML-escaped,
    passed to the page's SearchPanelSetup script."""
    match = SUBJECT_MENU.search(download(SOC_HOME))
    if not match:
        raise SystemExit("The Schedule of Classes page no longer has its subject menu; check " + SOC_HOME)
    subjects = {}
    for entry in json.loads(html.unescape(match.group(1))):
        code = entry["value"].strip()
        name = re.sub(r"\s*\([^()]*\)\s*$", "", entry["label"]).strip()
        if code and name:
            subjects[code] = name
    return subjects


def fetch_one(kind, path):
    """Save one record; returns "saved", "kept" (already there) or "failed: …"."""
    name = path.rsplit("/", 1)[1]
    target = os.path.join(RAW_DIR, kind + "s", name + ".json")
    if os.path.exists(target):
        return "kept"
    query = urllib.parse.urlencode({"siteId": SITE_ID, "path": path, "siteYear": "current"})
    try:
        text = download(API + "?" + query)
        record = json.loads(text)
        if not isinstance(record, dict) or not record.get("data"):
            return "failed: %s: no record" % path
    except (urllib.error.URLError, ValueError, TimeoutError, ConnectionError) as error:
        return "failed: %s: %s" % (path, error)
    with open(target + ".part", "w", encoding="utf-8") as f:
        json.dump(record["data"], f, ensure_ascii=False)
    os.replace(target + ".part", target)
    time.sleep(PAUSE_SECONDS)
    return "saved"


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("subjects", "all"):
        subjects = fetch_subjects()
        with open(os.path.join("data", "ucla", "subjects.json"), "w", encoding="utf-8") as f:
            json.dump(subjects, f, indent=1, ensure_ascii=False, sort_keys=True)
        print("%d subjects" % len(subjects))
        if which == "subjects":
            return 0
    for kind in ("courses", "majors"):
        os.makedirs(os.path.join(RAW_DIR, kind), exist_ok=True)
    paths_file = os.path.join(RAW_DIR, "paths.json")
    if os.path.exists(paths_file):
        with open(paths_file) as f:
            paths = [tuple(p) for p in json.load(f)]
    else:
        paths = catalog_paths()
        with open(paths_file, "w") as f:
            json.dump(paths, f, indent=0)
    wanted = [p for p in paths if which == "all" or p[0] + "s" == which]
    print("%d pages to read (%s)" % (len(wanted), which))
    counts = {}
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for done, result in enumerate(pool.map(lambda p: fetch_one(*p), wanted), 1):
            key = result.split(":")[0]
            counts[key] = counts.get(key, 0) + 1
            if result.startswith("failed"):
                print("  %s" % result)
            if done % 500 == 0:
                print("  %d of %d: %s" % (done, len(wanted), counts))
    print("Done: %s" % counts)
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
