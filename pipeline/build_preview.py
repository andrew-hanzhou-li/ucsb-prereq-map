"""
build_preview.py: make the picture shown when the site's link is shared.

    py pipeline/build_single.py     (first, so the one-file copy is current)
    py pipeline/build_preview.py

Writes  site/preview.png   1200 x 630, the size Reddit, Discord, iMessage
                           and others use for link previews

Sites like Reddit and Discord read the page's og:image tag and show that
picture under the link. This takes a screenshot of the Computer Engineering
map with ECE 152A selected, so the preview shows what the site does: the
course, the courses it needs (red) and what it unlocks (blue).

It opens the one-file copy straight from the disk, so no server is needed.
Uses Playwright, like test_site.py.
"""

import pathlib
import sys

from playwright.sync_api import sync_playwright

SINGLE_FILE = pathlib.Path("site", "ucsb-prereq-map.html").resolve()
OUTPUT = pathlib.Path("site", "preview.png")


def main():
    if not SINGLE_FILE.exists():
        sys.exit("build_preview.py: run py pipeline/build_single.py first")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        page.goto(SINGLE_FILE.as_uri() + "#computer-engineering-bs/ECE+152A")
        page.wait_for_function("typeof selected !== 'undefined' && selected === 'ECE 152A'", timeout=20000)
        page.wait_for_timeout(1500)          # web font and arrows settle
        page.screenshot(path=str(OUTPUT))
        browser.close()
    print("Wrote %s" % OUTPUT)


if __name__ == "__main__":
    main()
