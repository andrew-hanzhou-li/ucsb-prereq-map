"""
test_site.py: open the website in a real (headless) browser and check it.

    py -m http.server 8000 -d site      (in one terminal)
    py test_site.py                      (in another)

If port 8000 is taken by something else, pick another number for both:
    py -m http.server 8765 -d site
    py test_site.py 8765

What it checks:
  1. The front page loads, and the major picker shows the full list even
     after a major has been chosen.
  2. Every major in data/majors.json:
       - shows each current course of the major exactly once (in its own
         box, a shared "one of" box, or a folded elective list)
       - draws every box, with no two boxes overlapping
       - every arrow points left to right (a course is always to the right
         of the courses it needs)
       - clicking a box fills the side panel, with no JavaScript errors
  3. The plan's "done when" test: on Economics, find MATH 3A and see
     what it unlocks.
  4. The Show checkboxes hide and show the right courses.
  5. Folded elective lists open, unfold onto the map and fold back.
  6. "Find a course" works for a course folded inside a list.
  7. Mark as taken: taken and "can take next" boxes change, and the marks
     survive a page reload.
  8. On a phone-sized screen, selecting a course opens the bottom sheet and
     keeps the course visible above it.
  9. Part 7: the front page lists every major and minor; programs with no
     course list, and unknown addresses, show a notice instead of a map; the
     address bar follows the selected course and a course link opens it;
     a minor's panel says "minor"; the About and 404 pages load.

Needs Playwright, a browser-automation library (one-time setup):
    py -m pip install playwright
    py -m playwright install chromium
"""

import json
import sys

from playwright.sync_api import sync_playwright

SITE = "http://localhost:%s/" % (sys.argv[1] if len(sys.argv) > 1 else "8000")
passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print("FAIL: %s %s" % (name, detail))


def box(page, box_id):
    return page.locator('[data-box="%s"]' % box_id)


def find_course(page, code):
    page.fill("#course-input", code)
    page.dispatch_event("#course-input", "change")
    page.wait_for_timeout(250)


def open_major(page, stem, major_id):
    page.goto(SITE + "#" + stem)
    page.wait_for_function("id => graph && graph.major.id === id && document.querySelectorAll('.box').length > 0",
                           arg=major_id, timeout=10000)


def main():
    sys.stdout.reconfigure(errors="replace")
    with open("site/data/majors.json", encoding="utf-8") as f:
        listed = json.load(f)["majors"]
    majors = [m for m in listed if m["structured"]]          # the ones with a map
    no_map = [m for m in listed if not m["structured"]]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # Skip downloading the web font: not needed for the test, and slow.
        page.route("**/fonts.googleapis.com/**", lambda route: route.abort())
        page.route("**/fonts.gstatic.com/**", lambda route: route.abort())

        # 1. Front page and the major picker
        page.goto(SITE)
        page.wait_for_timeout(400)
        check("front page shows the 'pick a major' message", page.is_visible("#empty"))
        check("front page hides the empty course panel", not page.is_visible("#panel"))
        check("major picker has every major and minor",
              page.evaluate("document.querySelectorAll('#major-list option').length") == len(listed))
        for kind in ("major", "minor"):
            expected = sum(m["kind"] == kind for m in listed)
            shown = page.locator("#browse-%ss li" % kind).count()
            check("front page lists all %d %ss" % (expected, kind), shown == expected, "%d listed" % shown)
        open_major(page, "economics-ba", "BAECON")
        page.focus("#major-input")
        check("clicking into a filled-in picker empties it, so the full list shows",
              page.input_value("#major-input") == "")
        page.focus("#course-input")
        check("leaving it without choosing puts the major back",
              page.input_value("#major-input") == "Economics - BA")

        # 2. Every major
        for major in majors:
            stem = major["file"][:-5]
            errors.clear()
            open_major(page, stem, major["id"])
            with open("site/data/" + major["file"], encoding="utf-8") as f:
                graph = json.load(f)
            expected = sorted(n["id"] for n in graph["nodes"]
                              if n["status"] == "active" and n["role"] != "prerequisite")
            shown = sorted(page.evaluate("Object.keys(standIn)"))
            check("%s: shows each of its %d current courses exactly once" % (stem, len(expected)),
                  shown == expected, "%d shown" % len(shown))

            result = page.evaluate("""() => {
                const list = Object.values(boxes);
                const drawn = document.querySelectorAll('.box').length;
                let overlaps = 0;
                for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
                    const a = list[i], b = list[j];
                    if (a.x < b.x + BOX_WIDTH && b.x < a.x + BOX_WIDTH && a.y < b.y + b.height && b.y < a.y + a.height) overlaps++;
                }
                const backwards = arrows.filter(a => !(boxes[a.from].x < boxes[a.to].x)).length;
                const dangling = arrows.filter(a => !boxes[a.from] || !boxes[a.to]).length;
                return [list.length, drawn, overlaps, backwards, dangling];
            }""")
            total, drawn, overlaps, backwards, dangling = result
            check("%s: draws all %d boxes" % (stem, total), drawn == total, "drew %d" % drawn)
            check("%s: no two boxes overlap" % stem, overlaps == 0, "%d overlaps" % overlaps)
            check("%s: every arrow points left to right" % stem, backwards == 0, "%d backwards" % backwards)
            check("%s: every arrow connects two boxes" % stem, dangling == 0)

            first = page.evaluate("document.querySelector('.box').dataset.box")
            box(page, first).click()
            page.wait_for_timeout(100)
            check("%s: clicking a box fills the panel" % stem, page.inner_text("#panel-body h2").strip() != "")
            check("%s: no JavaScript errors" % stem, not errors, errors)

        # 3. The plan's test: what does MATH 3A unlock in Economics?
        open_major(page, "economics-ba", "BAECON")
        find_course(page, "MATH 3A")
        panel = page.inner_text("#panel-body")
        check("Economics: the panel shows MATH 3A", panel.startswith("MATH 3A"))
        for code in ("MATH 3B", "ECON 10A"):
            check("Economics: MATH 3A's panel says it unlocks %s" % code, code in panel.split("Unlocks")[1])
        check("Economics: ECON 10A's box is highlighted as unlocked",
              "unlocks" in box(page, "ECON 10A").get_attribute("class"))

        # 4. Show checkboxes
        page.uncheck("#show-electives")
        page.wait_for_timeout(150)
        check("unchecking Electives hides electives and elective lists",
              page.locator(".role-elective, .kind-group").count() == 0)
        page.check("#show-electives")
        page.check("#show-outside")
        page.wait_for_timeout(150)
        check("checking 'courses from other majors' shows them (MATH 4A)", box(page, "MATH 4A").count() == 1)
        page.uncheck("#show-outside")
        page.check("#show-inactive")
        page.wait_for_timeout(150)
        check("checking 'not offered now' adds inactive courses (ECON 141)",
              page.evaluate("'ECON 141' in standIn"))
        page.uncheck("#show-inactive")

        # 5. Folded elective lists (Economics area D)
        group = page.evaluate("Object.keys(boxes).find(id => boxes[id].kind === 'group' && boxes[id].courses.includes('ECON 100C'))")
        check("Economics: area D is folded into one box", bool(group))
        check("Economics: ECON 100C isn't its own box while folded", box(page, "ECON 100C").count() == 0)
        box(page, group).click()
        check("clicking the list box shows its rule", "at least 6" in page.inner_text("#panel-body"))
        page.click("[data-unfold]")
        page.wait_for_timeout(200)
        check("'Show these courses on the map' unfolds the list", box(page, "ECON 100C").count() == 1)
        page.click("[data-fold]")
        page.wait_for_timeout(200)
        check("'Fold back' folds it again", box(page, "ECON 100C").count() == 0)

        # 6. Find a course that's folded inside a list
        find_course(page, "ECON 171")
        check("finding ECON 171 unfolds its list and selects it",
              box(page, "ECON 171").count() == 1 and "selected" in box(page, "ECON 171").get_attribute("class"))

        # 7. Mark as taken
        page.evaluate("localStorage.clear()")
        page.reload()
        open_major(page, "economics-ba", "BAECON")
        box(page, "ECON 1").click()
        page.click("[data-taken]")
        page.wait_for_timeout(150)
        check("marking ECON 1 taken marks its box", "taken" in box(page, "ECON 1").get_attribute("class"))
        check("ECON 2 (needs only ECON 1) becomes 'can take next'", "ready" in box(page, "ECON 2").get_attribute("class"))
        check("ECON 10A (needs more than ECON 1) does not",
              "ready" not in box(page, "ECON 10A").get_attribute("class"))
        page.reload()
        open_major(page, "economics-ba", "BAECON")
        check("the mark survives a page reload", "taken" in box(page, "ECON 1").get_attribute("class"))
        page.click("#clear-taken")
        page.wait_for_timeout(150)
        check("'Clear all marks' removes it", "taken" not in box(page, "ECON 1").get_attribute("class"))

        # 9. Part 7
        # The address bar follows the selection...
        box(page, "ECON 10A").click()
        page.wait_for_timeout(100)
        check("selecting a course puts it in the address", page.evaluate("location.hash") == "#economics-ba/ECON+10A",
              page.evaluate("location.hash"))
        page.evaluate("clearSelection()")
        check("clearing the selection takes it back out", page.evaluate("location.hash") == "#economics-ba")
        # ...and a link with a course opens straight to it, even from another page.
        page.goto(SITE + "about.html")
        page.goto(SITE + "#statistics-and-data-science-bs/PSTAT+120B")
        page.wait_for_function("selectedCourse === 'PSTAT 120B'", timeout=10000)
        check("a course link opens the major with that course selected",
              page.inner_text("#panel-body h2").strip() == "PSTAT 120B" and
              "selected" in box(page, "PSTAT 120B").get_attribute("class"))
        check("the copy-link button is in the course panel", page.locator("[data-copy-link]").count() == 1)

        # A program with no course list shows a notice and no map.
        ccs = next(m for m in no_map if "Creative Studies" in m["name"])
        page.goto(SITE + "#" + ccs["file"][:-5])
        page.wait_for_timeout(300)
        check("no-list program: notice is shown", page.is_visible("#notice") and "no map" in page.inner_text("#notice"))
        check("no-list program: it links to the catalog", page.locator("#notice a[href*='catalog.ucsb.edu']").count() == 1)
        check("no-list program: the old map is cleared", page.locator(".box").count() == 0)
        check("no-list program: the course panel is hidden", not page.is_visible("#panel"))
        check("no-list program: the picker shows its name", page.input_value("#major-input") == ccs["name"])

        # An address that matches nothing.
        page.goto(SITE + "#geological-sciences-bs")
        page.wait_for_timeout(300)
        check("unknown address: 'no map at that address' notice",
              page.is_visible("#notice") and "No map at that address" in page.inner_text("#notice"))
        page.goto(SITE + "#")
        page.wait_for_timeout(300)
        check("empty address: back to the welcome text", page.is_visible("#welcome") and not page.is_visible("#notice"))

        # A minor's panel says "minor".
        minor = next(m for m in majors if m["kind"] == "minor" and m["courses_in_major"] > 3)
        open_major(page, minor["file"][:-5], minor["id"])
        course = page.evaluate("Object.keys(boxes).find(id => boxes[id].kind === 'course')")
        box(page, course).click()
        page.wait_for_timeout(100)
        check("minor: the panel says 'In this minor'", "In this minor" in page.inner_text("#panel-body"))

        # About and 404 pages.
        response = page.goto(SITE + "about.html")
        check("About page loads", response.ok and page.inner_text("h2") == "About this site")
        response = page.goto(SITE + "404.html")
        check("404 page loads", response.ok and page.inner_text("h2") == "Page not found")
        check("no JavaScript errors in the Part 7 checks", not errors, errors)
        browser.close()

        # 8. Phone-sized screen
        browser = p.chromium.launch()
        phone = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        phone.route("**/fonts.googleapis.com/**", lambda route: route.abort())
        open_major(phone, "statistics-and-data-science-bs", "BSSTSDS")
        check("phone: the sheet starts closed", not phone.evaluate("el.panel.classList.contains('open')"))
        phone.evaluate("selectCourse('PSTAT 120B', true)")
        phone.wait_for_timeout(800)
        check("phone: selecting a course opens the sheet", phone.evaluate("el.panel.classList.contains('open')"))
        box_bottom, sheet_top = phone.evaluate("""() => [
            document.querySelector('[data-box="PSTAT 120B"]').getBoundingClientRect().bottom,
            el.panel.getBoundingClientRect().top]""")
        check("phone: the selected course stays visible above the sheet", box_bottom < sheet_top,
              "%d vs %d" % (box_bottom, sheet_top))
        browser.close()

    print("%d checks passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
