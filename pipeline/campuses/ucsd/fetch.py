"""
fetch.py (UC San Diego): download the course catalog's department pages.

    python pipeline/campuses/ucsd/fetch.py

Reads   https://catalog.ucsd.edu/front/courses.html   the list of departments
        https://catalog.ucsd.edu/courses/<DEPT>.html  one page per department
Writes  data/ucsd/raw/<DEPT>.html                     the pages, as downloaded
        data/ucsd/raw/index.html

UCSD's catalog has no API or data feed; these are plain web pages, about 86
of them. A page already saved isn't downloaded again (delete data/ucsd/raw
to fetch a new catalog year), and there is a pause between requests so the
catalog's server barely notices.
"""

import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://catalog.ucsd.edu/"
INDEX_URL = BASE + "front/courses.html"
RAW_DIR = os.path.join("data", "ucsd", "raw")
PAUSE_SECONDS = 1.0
USER_AGENT = "prereq-planner (student project)"

# A department page's name in the index: "../courses/CSE.html". Only letters,
# digits and dashes, so the name is also safe as a file name.
PAGE_LINK = re.compile(r'href="\.\./courses/([A-Za-z0-9-]+)\.html"')


def download(url, attempts=3):
    """The page's text. Tries again after a short wait if the server or the
    network fails; gives up (raises) after `attempts` tries."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:   # nosec B310 - fixed https URL
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == attempts:
                raise
            print("  %s failed (%s); trying again" % (url, error))
            time.sleep(5 * attempt)
    return ""


def department_pages(index_html):
    """Department page names in the index, each once, in the index's order.
    The index links some departments twice, and a few in lowercase."""
    seen = []
    for name in PAGE_LINK.findall(index_html):
        if name not in seen:
            seen.append(name)
    return seen


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    index_path = os.path.join(RAW_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index_html = f.read()
    else:
        index_html = download(INDEX_URL)
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_html)

    pages = department_pages(index_html)
    if not pages:
        sys.exit("fetch.py: no department links found in %s; did the page change?" % INDEX_URL)

    fetched = 0
    for name in pages:
        path = os.path.join(RAW_DIR, name + ".html")
        if os.path.exists(path):
            continue
        time.sleep(PAUSE_SECONDS)
        with open(path, "w", encoding="utf-8") as f:
            f.write(download(BASE + "courses/" + name + ".html"))
        fetched += 1
    print("%d department pages (%d downloaded now) in %s" % (len(pages), fetched, RAW_DIR))


if __name__ == "__main__":
    main()
