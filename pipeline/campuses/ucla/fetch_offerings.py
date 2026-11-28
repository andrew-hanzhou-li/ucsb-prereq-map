"""
fetch_offerings.py (UCLA): the Schedule of Classes for recent terms.

    python pipeline/campuses/ucla/fetch_offerings.py

Reads   https://sa.ucla.edu/ro/Public/SOC/Results?t=25F&sBy=subject&subj=COM+SCI
        (then .../Results/CourseTitlesView?…&pageNumber=2 for each further page)
Writes  data/ucla/raw/soc/<TERM>/<SUBJECT>-<page>.html   the pages, as downloaded

The Schedule of Classes lists 25 courses a page for one subject and term,
each as a button titled "M51A - Logic Design of Digital Systems". The first
page says how many pages there are (pageCount); the rest come from the
page's own "CourseTitlesView" request, which wants the search as JSON and
the X-Requested-With header the page sends. Past terms still answer.

Terms: the last two years, with summer (25F = Fall 2025, 261 = Summer 2026).
A page already saved isn't downloaded again; two requests run at a time,
with a pause in each.
"""

import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

RESULTS = "https://sa.ucla.edu/ro/Public/SOC/Results"
SUBJECTS = os.path.join("data", "ucla", "subjects.json")
SOC_DIR = os.path.join("data", "ucla", "raw", "soc")
TERMS = ["24F", "25W", "25S", "251", "25F", "26W", "26S", "261", "26F"]
WORKERS = 2
PAUSE_SECONDS = 0.5
USER_AGENT = "prereq-planner (student project)"


def download(url, ajax=False, attempts=4):
    headers = {"User-Agent": USER_AGENT}
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == attempts:
                raise
            print("  retrying %s (%s)" % (url[:90], error))
            time.sleep(4 * attempt)


def file_name(term, subject, page):
    return os.path.join(SOC_DIR, term, re.sub(r"[^A-Za-z0-9]+", "_", subject) + "-%d.html" % page)


def fetch_subject(term, subject):
    """Every page of one subject in one term; returns how many pages."""
    first = file_name(term, subject, 1)
    if os.path.exists(first):
        with open(first, encoding="utf-8") as f:
            text = f.read()
    else:
        text = download(RESULTS + "?" + urllib.parse.urlencode({"t": term, "sBy": "subject", "subj": subject}))
        with open(first, "w", encoding="utf-8") as f:
            f.write(text)
        time.sleep(PAUSE_SECONDS)
    count = re.search(r"pageCount\s*=\s*parseInt\('(\d+)'\)", text)
    pages = int(count.group(1)) if count else 1
    model = {"subj_area_cd": subject, "search_by": "Subject", "term_cd": term,
             "ActiveEnrollmentFlag": "n", "HasData": "True"}
    for page in range(2, pages + 1):
        target = file_name(term, subject, page)
        if os.path.exists(target):
            continue
        query = urllib.parse.urlencode({"search_by": "subject", "model": json.dumps(model),
                                        "pageNumber": page, "filterFlags": "{}"})
        with open(target, "w", encoding="utf-8") as f:
            f.write(download(RESULTS + "/CourseTitlesView?" + query, ajax=True))
        time.sleep(PAUSE_SECONDS)
    return pages


def main():
    with open(SUBJECTS, encoding="utf-8") as f:
        subjects = sorted(json.load(f))
    jobs = [(term, subject) for term in TERMS for subject in subjects]
    for term in TERMS:
        os.makedirs(os.path.join(SOC_DIR, term), exist_ok=True)
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(fetch_subject, *job): job for job in jobs}
        for done, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                future.result()
            except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
                failed += 1
                print("  failed %s %s: %s" % (futures[future] + (error,)))
            if done % 200 == 0:
                print("  %d of %d" % (done, len(jobs)))
    print("Done: %d subject-terms, %d failed" % (len(jobs), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
