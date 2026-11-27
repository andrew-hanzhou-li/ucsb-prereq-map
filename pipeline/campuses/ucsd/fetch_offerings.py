"""
fetch_offerings.py (UC San Diego): download which courses ran in recent quarters.

    python pipeline/campuses/ucsd/fetch_offerings.py

Reads   https://act.ucsd.edu/scheduleOfClasses/  the Schedule of Classes
        data/ucsd/raw_courses.json             the subject codes to search
Writes  data/ucsd/raw/soc/<TERM>/<SUBJECT>-<page>.html
        (pages stop at the first one holding only graduate courses: results
        are in course-number order)

UCSD's catalog states the usual quarters for only a few dozen courses, so
the planner learns them from the quarters each course actually ran: the last
two academic years (Fall 2024 to Spring 2026) and the 2025 summer sessions.

The search takes one subject at a time and shows results a page at a time
(the next pages need the same session cookie). One request a second, a
plain user agent, and a page already saved isn't downloaded again, so a
stopped run picks up where it left off.
"""

import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

SEARCH = "https://act.ucsd.edu/scheduleOfClasses/scheduleOfClassesStudentResult.htm"
TERMS = ["FA24", "WI25", "SP25", "S125", "S225", "S325", "FA25", "WI26", "SP26"]
COURSES = os.path.join("data", "ucsd", "raw_courses.json")
OUT_DIR = os.path.join("data", "ucsd", "raw", "soc")
PAUSE_SECONDS = 1.0
USER_AGENT = "prereq-planner (student project)"
PAGE_COUNT = re.compile(r"Page\s+\(\d+(?:&nbsp;|\s)+of(?:&nbsp;|\s)+(\d+)\)")
COURSE_NUMBER = re.compile(r'class="crsheader">\s*([0-9]+[A-Z]*)\s*<')


def only_graduate(page_html):
    """True when every course on the page is numbered 200 or up. Results are
    in course-number order, so later pages are graduate courses too."""
    numbers = [int(re.match(r"\d+", n).group()) for n in COURSE_NUMBER.findall(page_html)]
    return bool(numbers) and min(numbers) >= 200


def opener_with_cookies():
    """A fresh session: the result pages after the first need its cookie."""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener.addheaders = [("User-Agent", USER_AGENT)]
    return opener


def fetch(opener, url, data=None, attempts=3):
    for attempt in range(1, attempts + 1):
        try:
            with opener.open(url, data=data, timeout=60) as response:   # nosec B310 - fixed https URL
                return response.read().decode("utf-8", errors="replace")
        except OSError as error:
            if attempt == attempts:
                raise
            print("  %s failed (%s); trying again" % (url, error))
            time.sleep(5 * attempt)
    return ""


def save(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def fetch_subject(term, subject):
    """All result pages for one subject in one term. Returns pages downloaded."""
    folder = os.path.join(OUT_DIR, term)
    first_path = os.path.join(folder, "%s-1.html" % subject.replace(" ", "_"))
    opener = opener_with_cookies()
    downloaded = 0
    if os.path.exists(first_path):
        with open(first_path, encoding="utf-8") as f:
            first = f.read()
    else:
        time.sleep(PAUSE_SECONDS)
        form = urllib.parse.urlencode({"selectedTerm": term, "selectedSubjects": subject, "tabNum": "tabs-sub"}).encode()
        first = fetch(opener, SEARCH, form)
        save(first_path, first)
        downloaded += 1
    match = PAGE_COUNT.search(first)
    pages = int(match.group(1)) if match else 1
    if only_graduate(first):
        return downloaded
    session_ready = downloaded == 1
    for page in range(2, pages + 1):
        path = os.path.join(folder, "%s-%d.html" % (subject.replace(" ", "_"), page))
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if only_graduate(f.read()):
                    break
            continue
        if not session_ready:            # resuming: start the search again for this session
            time.sleep(PAUSE_SECONDS)
            form = urllib.parse.urlencode({"selectedTerm": term, "selectedSubjects": subject, "tabNum": "tabs-sub"}).encode()
            fetch(opener, SEARCH, form)
            session_ready = True
        time.sleep(PAUSE_SECONDS)
        text = fetch(opener, SEARCH + "?page=%d" % page)
        save(path, text)
        downloaded += 1
        if only_graduate(text):
            break           # the rest are graduate courses
    return downloaded


def main():
    with open(COURSES, encoding="utf-8") as f:
        subjects = sorted({c["subject"] for c in json.load(f)["courses"]})
    terms = sys.argv[1:] or TERMS
    for term in terms:
        total = 0
        for subject in subjects:
            total += fetch_subject(term, subject)
        print("%s: %d pages downloaded" % (term, total), flush=True)


if __name__ == "__main__":
    main()
