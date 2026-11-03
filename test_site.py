"""
test_site.py: open the website in a real (headless) browser and check it.

    py -m http.server 8000 -d site      (in one terminal)
    py test_site.py                      (in another)

If port 8000 is taken by something else, pick another number for both:
    py -m http.server 8765 -d site
    py test_site.py 8765

What it checks:
  1. The front page lists every major and minor, and hides the empty panel.
  2. Every major in data/majors.json:
       - shows each current course of the major exactly once; any other box
         is a course from another department that the major needs
       - steps are in order: a course's required prerequisites are in an
         earlier step (or the same step, if they can be taken at the same time)
       - nothing is wider than the screen (no sideways scrolling)
       - clicking a course fills the panel and draws its arrows, with no
         JavaScript errors
  3. Computer Engineering: ECE 139 is with the upper-division core (same step
     as ECE 152A), and ECE 152A's arrows from ECE 15A and ECE 10A are solid.
  4. Getting around: hovering previews a course; clicking empty space, Esc and
     Close clear it; Back returns to the course before; "All majors and
     minors" returns to the front page.
  5. The Show checkboxes, "Find a course", and Mark as taken (survives a reload).
  6. Links: the address follows the selected course and a course link opens
     it; programs with no map and unknown addresses show a notice.
  7. The About box and the 404 page.
  8. On a phone-sized screen, selecting a course opens the bottom sheet and
     keeps the course visible above it.
  9. The single-file version (site/ucsb-prereq-map.html, from build_single.py)
     works when opened straight from the disk.

Needs Playwright, a browser-automation library (one-time setup):
    py -m pip install playwright
    py -m playwright install chromium
"""

import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

SITE = "http://localhost:%s/" % (sys.argv[1] if len(sys.argv) > 1 else "8000")
SINGLE_FILE = pathlib.Path("site", "ucsb-prereq-map.html").resolve()
passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print("FAIL: %s %s" % (name, detail))


def box(page, code):
    return page.locator('.box[data-code="%s"]' % code)


def classes(page, code):
    return box(page, code).get_attribute("class") or ""


def find_course(page, code):
    page.fill("#course-input", code)
    page.dispatch_event("#course-input", "change")
    page.wait_for_timeout(250)


def open_major(page, base, stem, major_id):
    page.goto(base + "#" + stem)
    page.wait_for_function("id => graph && graph.major.id === id && document.querySelectorAll('.box').length > 0",
                           arg=major_id, timeout=15000)


def new_page(browser, **options):
    page = browser.new_page(**options)
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    # Skip downloading the web font: not needed for the test, and slow.
    page.route("**/fonts.googleapis.com/**", lambda route: route.abort())
    page.route("**/fonts.gstatic.com/**", lambda route: route.abort())
    return page


# Run in the page: courses whose required prerequisite is in a later step.
STEP_ORDER = """() => {
    const wrong = [];
    for (const code of Object.keys(stepOf)) {
        for (const p of prereqsOnMap(code)) {
            if (p.type !== 'required' || !stepOf[p.from]) continue;
            const ok = p.concurrent ? stepOf[p.from] <= stepOf[code] : stepOf[p.from] < stepOf[code];
            if (!ok) wrong.push(p.from + ' -> ' + code);
        }
    }
    return wrong;
}"""


def main():
    sys.stdout.reconfigure(errors="replace")
    with open("site/data/majors.json", encoding="utf-8") as f:
        listed = json.load(f)["majors"]
    majors = [m for m in listed if m["structured"]]          # the ones with a map

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = new_page(browser, viewport={"width": 1400, "height": 900})

        # 1. Front page
        page.goto(SITE)
        page.wait_for_timeout(400)
        check("front page shows the 'pick a major' message", page.is_visible("#welcome"))
        check("front page hides the empty course panel", not page.is_visible("#panel"))
        check("major picker has every major and minor",
              page.evaluate("document.querySelectorAll('#major-list option').length") == len(listed))
        check("every listed program has a map", all(m["structured"] for m in listed))
        check("Individual BA/BS and College of Creative Studies programs aren't listed",
              not any(m["name"].startswith("Individual") or "Creative Studies" in m["name"] for m in listed))
        shown = page.locator("#browse .dept li").count()
        check("front page lists all %d programs" % len(listed), shown == len(listed), "%d listed" % shown)
        departments = {m["department"] for m in listed}
        check("front page groups them into %d departments" % len(departments),
              page.locator("#browse .dept h3").count() == len(departments))
        ece = page.locator("#browse .dept", has=page.locator("h3", has_text="Electrical and Computer Engineering"))
        check("Computer Engineering is listed under Electrical and Computer Engineering",
              ece.count() == 1 and "Computer Engineering - BS" in ece.inner_text())
        open_major(page, SITE, "economics-ba", "BAECON")
        check("the chosen program is shown by name", "Economics - BA" in page.inner_text("#chosen"))
        check("the picker is empty, ready to add another program", page.input_value("#major-input") == "")

        # Phase 1: several programs at once (CE BS + Statistical Science minor)
        page.fill("#major-input", "Computer Engineering - BS")
        page.dispatch_event("#major-input", "change")
        page.wait_for_function("graph && graph.major.programs.length === 2", timeout=15000)
        check("adding a program puts both on the map", page.evaluate("location.hash") == "#economics-ba+computer-engineering-bs")
        page.click('#chosen button[data-remove="BAECON"]')
        page.wait_for_function("graph && graph.major.programs.length === 1", timeout=15000)
        check("the x takes a program off the map", page.evaluate("location.hash") == "#computer-engineering-bs")
        page.goto(SITE + "#computer-engineering-bs+statistical-science-minor")
        page.wait_for_function("graph && graph.major.programs.length === 2 && document.querySelectorAll('.box').length > 0", timeout=15000)
        both = {}
        for stem_ in ("computer-engineering-bs", "statistical-science-minor"):
            with open("site/data/%s.json" % stem_, encoding="utf-8") as f:
                both[stem_] = {n["id"] for n in json.load(f)["nodes"] if n["in_major"] and n["status"] == "active"}
        expected = both["computer-engineering-bs"] | both["statistical-science-minor"]
        boxes = page.evaluate("[...document.querySelectorAll('.box[data-code]')].map(b => b.dataset.code)")
        check("combined map: every course of both programs is there", expected <= set(boxes),
              sorted(expected - set(boxes))[:5])
        check("combined map: no course appears twice", len(boxes) == len(set(boxes)))
        check("combined map: MATH 4A, in both, says it counts toward both",
              "counts toward both" in box(page, "MATH 4A").inner_text())
        check("combined map: a course in only one program doesn't", "counts toward" not in box(page, "ECE 152A").inner_text())
        titles = page.locator(".elective-row .row-label").all_inner_texts()
        check("combined map: elective lists are labeled with their program",
              any(t.startswith("Computer Engineering BS:") for t in titles) and any(t.startswith("Statistical Science minor:") for t in titles), titles)
        box(page, "MATH 4A").click()
        page.wait_for_timeout(100)
        check("combined map: the panel says which programs a course counts toward",
              "Counts toward Computer Engineering BS and Statistical Science minor" in page.inner_text("#panel-body"))
        check("combined map: no JavaScript errors", not page.errors, page.errors)

        # 2. Every major
        for major in majors:
            stem = major["file"][:-5]
            page.errors.clear()
            open_major(page, SITE, stem, major["id"])
            with open("site/data/" + major["file"], encoding="utf-8") as f:
                graph = json.load(f)
            expected = sorted(n["id"] for n in graph["nodes"] if n["status"] == "active" and n["in_major"])
            boxes = page.evaluate("[...document.querySelectorAll('.box[data-code]')].map(b => b.dataset.code)")
            in_major = sorted(code for code in boxes if code in set(expected))
            extra = [code for code in boxes if code not in set(expected)]
            roles = {n["id"]: n["role"] for n in graph["nodes"]}
            check("%s: shows each of its %d current courses exactly once" % (stem, len(expected)),
                  in_major == expected, "%d shown" % len(in_major))
            check("%s: every other box is a course it needs from another department" % stem,
                  all(roles.get(code) == "prerequisite" for code in extra), extra[:5])
            wrong = page.evaluate(STEP_ORDER)
            check("%s: every required prerequisite is in an earlier step" % stem, not wrong, wrong[:5])
            check("%s: no sideways scrolling" % stem,
                  page.evaluate("el.map.scrollWidth <= el.map.clientWidth + 1"))

            if boxes:
                last = boxes[-1]
                box(page, last).click()
                page.wait_for_timeout(80)
                check("%s: clicking a course fills the panel" % stem, page.inner_text("#panel-body h2").strip() == last)
                arrows = page.evaluate("document.querySelectorAll('.arrow').length")
                expected_arrows = page.evaluate("code => prereqsOnMap(code).length + unlocksOf(code).length", last)
                check("%s: its arrows are drawn" % stem, arrows >= expected_arrows, "%d < %d" % (arrows, expected_arrows))
            check("%s: no JavaScript errors" % stem, not page.errors, page.errors)

        # 3. Computer Engineering
        open_major(page, SITE, "computer-engineering-bs", "BSCMPEN")
        steps = page.evaluate("[stepOf['ECE 139'], stepOf['ECE 152A'], stepOf['ECE 15A']]")
        check("CE: ECE 139 is in the same step as ECE 152A, not step 1", steps[0] == steps[1] and steps[0] > 1, steps)
        box(page, "ECE 152A").click()
        page.wait_for_timeout(150)
        solid = page.evaluate("prereqsOnMap('ECE 152A').filter(p => p.type === 'required').map(p => p.from)")
        check("CE: ECE 152A's arrows from ECE 15A and ECE 10A are solid",
              "ECE 15A" in solid and "ECE 10A" in solid, solid)
        check("CE: ECE 152A shows ECE 10A as needed", "needs" in classes(page, "ECE 10A"))
        check("CE: ECE 152A's chain reaches back to MATH 4A", "needs" in classes(page, "MATH 4A"))
        check("CE: ECE 152A shows ECE 154A as unlocked", "unlocks" in classes(page, "ECE 154A"))
        check("CE: MATH 4A (needed by ECE 10A) is on the map", box(page, "MATH 4A").count() == 1)

        # 4. Getting around
        page.click(".row-label >> nth=0")
        page.wait_for_timeout(100)
        check("clicking empty space clears the selection", page.evaluate("selected") is None and
              not page.evaluate("el.stage.classList.contains('focused')"))
        box(page, "ECE 15A").click()
        box(page, "ECE 152A").click()
        box(page, "ECE 154A").click()
        page.wait_for_timeout(100)
        check("panel shows a back link naming the course before", "back to ECE 152A" in page.inner_text(".panel-nav"))
        page.click("[data-back]")
        page.wait_for_timeout(100)
        check("Back returns to ECE 152A", page.evaluate("selected") == "ECE 152A")
        page.click("[data-back]")
        page.wait_for_timeout(100)
        check("Back again returns to ECE 15A", page.evaluate("selected") == "ECE 15A")
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        check("Esc clears the selection", page.evaluate("selected") is None)
        check("Esc puts the address back to the major", page.evaluate("location.hash") == "#computer-engineering-bs")
        box(page, "ECE 10A").click()
        page.click("[data-close]")
        page.wait_for_timeout(100)
        check("Close clears the selection", page.evaluate("selected") is None and
              page.inner_text("#panel-body h2") == "Computer Engineering - BS")
        box(page, "CMPSC 130A").hover()
        page.wait_for_timeout(300)
        check("hovering previews a course's chain",
              page.evaluate("el.stage.classList.contains('focused') && document.querySelectorAll('.arrow').length > 0"))
        scales = page.evaluate("""() => ['CMPSC 130A', 'CMPSC 130B', 'CMPSC 24', 'ECE 5']
            .map(c => boxFor(c).style.transform)""")
        check("hovering grows the course and what it unlocks, and shrinks the unrelated ones",
              scales[0] == "scale(1.05)" and scales[1] == "scale(1.05)" and scales[2] == "" and scales[3] == "scale(0.9)",
              scales)
        page.mouse.move(700, 20)
        page.wait_for_timeout(450)
        check("moving away from it clears the preview", not page.evaluate("el.stage.classList.contains('focused')"))
        check("...and every box goes back to its normal size",
              page.evaluate("[...document.querySelectorAll('.box')].every(b => !b.style.transform)"))
        box(page, "ECE 10A").click()
        page.wait_for_timeout(100)
        arrows_before = page.evaluate("document.querySelectorAll('.arrow').length")
        box(page, "CMPSC 130A").hover()
        page.wait_for_timeout(400)
        check("while a course is clicked, pointing at another doesn't change what's lit",
              page.evaluate("focus.code") == "ECE 10A" and "selected" in classes(page, "ECE 10A") and
              "selected" not in classes(page, "CMPSC 130A") and
              page.evaluate("document.querySelectorAll('.arrow').length") == arrows_before)
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(400)
        page.mouse.move(700, 500)
        page.wait_for_timeout(400)
        check("...nor does scrolling with the mouse over other courses", page.evaluate("focus.code") == "ECE 10A")
        page.keyboard.press("Escape")

        # Linked courses off screen (Anthropology: ANTH 2 unlocks courses far down the elective list)
        open_major(page, SITE, "anthropology-ba", "BAANTH")
        box(page, "ANTH 2").hover()
        page.wait_for_timeout(300)
        bar = page.locator("#offscreen-down")
        check("off-screen courses ANTH 2 unlocks are named in a bar at the bottom",
              bar.is_visible() and "ANTH 2 unlocks" in bar.inner_text(), bar.inner_text() if bar.is_visible() else "hidden")
        bar_box = bar.bounding_box()
        page.mouse.move(bar_box["x"] + 20, bar_box["y"] + bar_box["height"] / 2, steps=12)   # crosses other courses
        page.wait_for_timeout(300)
        check("moving the mouse down to the bar keeps ANTH 2's preview", page.evaluate("focus && focus.code") == "ANTH 2")
        bar.click()
        page.wait_for_timeout(900)
        check("clicking the bar selects ANTH 2", page.evaluate("selected") == "ANTH 2")
        in_view = page.evaluate("""() => {
            const v = el.map.getBoundingClientRect();
            return [...focus.unlocks].some(c => { const r = boxFor(c).getBoundingClientRect(); return r.top >= v.top && r.bottom <= v.bottom; });
        }""")
        check("...and scrolls so the courses it unlocks are in view", in_view)
        overlaps = page.evaluate("""() => {
            const r = [...document.querySelectorAll('.box.unlocks, .box.selected')].map(b => b.getBoundingClientRect());
            let n = 0;
            for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++)
                if (r[i].left < r[j].right && r[j].left < r[i].right && r[i].top < r[j].bottom && r[j].top < r[i].bottom) n++;
            return n; }""")
        check("grown boxes don't overlap each other", overlaps == 0, "%d overlaps" % overlaps)
        check("...and a bar at the top leads back to ANTH 2",
              page.is_visible("#offscreen-up") and "ANTH 2" in page.inner_text("#offscreen-up"))
        page.click("#offscreen-up")
        page.wait_for_timeout(900)
        check("clicking it scrolls back up to ANTH 2", page.evaluate("""() => {
            const v = el.map.getBoundingClientRect(); const r = boxFor('ANTH 2').getBoundingClientRect();
            return r.top >= v.top && r.bottom <= v.bottom; }"""))
        check("Anthropology's summary says 'all in step 1'", "all in step 1" in page.evaluate(
            "(clearSelection(), document.getElementById('panel-body').innerText)"))

        open_major(page, SITE, "computer-engineering-bs", "BSCMPEN")
        page.click("#all-link")
        page.wait_for_timeout(300)
        check("'All majors and minors' goes back to the front page",
              page.is_visible("#welcome") and page.locator(".box").count() == 0)

        # 5. Show checkboxes, Find a course, Mark as taken (Economics)
        open_major(page, SITE, "economics-ba", "BAECON")
        page.uncheck("#show-electives")
        page.wait_for_timeout(150)
        check("unchecking Electives hides electives", page.locator(".role-elective").count() == 0)
        page.check("#show-electives")
        before = page.locator(".box").count()
        page.check("#show-outside")
        page.wait_for_timeout(150)
        check("'Every outside course' adds more courses", page.locator(".box").count() > before)
        page.uncheck("#show-outside")
        page.check("#show-inactive")
        page.wait_for_timeout(150)
        check("'Courses not offered now' adds ECON 141", box(page, "ECON 141").count() == 1)
        page.uncheck("#show-inactive")
        find_course(page, "ECON 171")
        check("finding ECON 171 selects it", "selected" in classes(page, "ECON 171"))
        find_course(page, "ECON 10A")
        panel = page.inner_text("#panel-body")
        check("Economics: ECON 10A's panel names what it needs", "MATH" in panel.split("Needs")[1].split("Unlocks")[0])

        page.evaluate("localStorage.clear()")
        page.reload()
        open_major(page, SITE, "economics-ba", "BAECON")
        box(page, "ECON 1").click()
        page.click("[data-taken]")
        page.wait_for_timeout(150)
        check("marking ECON 1 taken marks its box", "taken" in classes(page, "ECON 1"))
        check("ECON 2 (needs only ECON 1) becomes 'can take next'", "ready" in classes(page, "ECON 2"))
        check("ECON 10A (needs more than ECON 1) does not", "ready" not in classes(page, "ECON 10A"))
        page.reload()
        open_major(page, SITE, "economics-ba", "BAECON")
        check("the mark survives a page reload", "taken" in classes(page, "ECON 1"))
        page.click("#clear-taken")
        page.wait_for_timeout(150)
        check("'Clear all marks' removes it", "taken" not in classes(page, "ECON 1"))

        # Phase 2: credit already earned (AP and college)
        page.evaluate("localStorage.clear()")
        page.reload()
        open_major(page, SITE, "economics-ba", "BAECON")
        check("credit: the map invites adding credit", "Have AP or college credit?" in page.inner_text(".map-head"))
        check("credit: MATH 3A isn't done before any credit", "taken" not in classes(page, "MATH 3A"))
        page.click("#credit-button")
        check("credit: the box opens with the AP chart",
              page.is_visible("#credit") and page.locator("#ap-list select").count() > 30)
        page.select_option('select[data-exam="Calculus BC"]', "4")
        page.wait_for_timeout(150)
        result = page.inner_text(".ap-row:has(select[data-exam='Calculus BC']) .ap-result")
        check("credit: Calculus BC 4 shows what it counts as", "MATH 3A" in result and "8 units" in result, result)
        page.select_option('select[data-exam="Chemistry"]', "5")
        page.wait_for_timeout(150)
        result = page.inner_text(".ap-row:has(select[data-exam='Chemistry']) .ap-result")
        check("credit: an exam with no UCSB equivalent says so", "no specific UCSB course" in result, result)
        page.fill("#transfer-input", "econ 1")
        page.click("#transfer-add")
        page.wait_for_timeout(150)
        check("credit: a college course can be added by code", "ECON 1" in page.evaluate("JSON.stringify(credit.transfer)"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        check("credit: AP Calculus BC counts MATH 3A as done", "taken" in classes(page, "MATH 3A"))
        check("credit: college credit counts ECON 1 as done", "taken" in classes(page, "ECON 1"))
        check("credit: ECON 2, which needs ECON 1, becomes 'next'", "ready" in classes(page, "ECON 2"))
        box(page, "MATH 3A").click()
        page.wait_for_timeout(100)
        check("credit: the course's entry says where the credit came from",
              "AP Calculus BC, score 4" in page.inner_text("#panel-body"))
        page.keyboard.press("Escape")
        page.reload()
        open_major(page, SITE, "economics-ba", "BAECON")
        check("credit: it survives a reload", "taken" in classes(page, "MATH 3A") and "taken" in classes(page, "ECON 1"))
        page.click("#credit-button")
        page.select_option('select[data-exam="Calculus BC"]', "")
        page.select_option('select[data-exam="Chemistry"]', "")
        page.click('[data-untransfer="ECON 1"], input[data-transfer="ECON 1"]')
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        check("credit: removing it undoes it", "taken" not in classes(page, "MATH 3A") and "taken" not in classes(page, "ECON 1"))
        check("credit: no JavaScript errors", not page.errors, page.errors)

        # 6. Links and notices
        box(page, "ECON 10A").click()
        page.wait_for_timeout(100)
        check("selecting a course puts it in the address", page.evaluate("location.hash") == "#economics-ba/ECON+10A",
              page.evaluate("location.hash"))
        page.goto(SITE + "404.html")
        page.goto(SITE + "#statistics-and-data-science-bs/PSTAT+120B")
        page.wait_for_function("selected === 'PSTAT 120B'", timeout=15000)
        check("a course link opens the major with that course selected",
              page.inner_text("#panel-body h2").strip() == "PSTAT 120B" and "selected" in classes(page, "PSTAT 120B"))
        check("the copy-link button is in the course panel", page.locator("[data-copy-link]").count() == 1)
        page.goto(SITE + "#computer-science-bs-college-of-creative-studies")
        page.wait_for_timeout(300)
        check("an old link to a program with no map gets the 'no map at that address' notice",
              page.is_visible("#notice") and "No map at that address" in page.inner_text("#notice") and
              page.locator(".box").count() == 0 and not page.is_visible("#panel"))
        page.goto(SITE + "#geological-sciences-bs")
        page.wait_for_timeout(300)
        check("unknown address: 'no map at that address' notice",
              page.is_visible("#notice") and "No map at that address" in page.inner_text("#notice"))
        minor = next(m for m in majors if m["kind"] == "minor" and m["courses_in_major"] > 3)
        open_major(page, SITE, minor["file"][:-5], minor["id"])
        page.locator(".box[data-code]").first.click()
        page.wait_for_timeout(100)
        check("minor: the panel says 'in this minor'", "in this minor" in page.inner_text("#panel-body"))

        # 7. About box and 404
        page.click("#about-button")
        check("About opens", page.is_visible("#about") and "About this map" in page.inner_text("#about h2"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        check("Esc closes About", not page.is_visible("#about"))
        response = page.goto(SITE + "404.html")
        check("404 page loads", response.ok and page.inner_text("h2") == "Page not found")
        check("no JavaScript errors in sections 3-7", not page.errors, page.errors)
        browser.close()

        # 8. Phone-sized screen
        browser = p.chromium.launch()
        phone = new_page(browser, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        open_major(phone, SITE, "statistics-and-data-science-bs", "BSSTSDS")
        check("phone: the sheet starts closed", not phone.evaluate("el.panel.classList.contains('open')"))
        check("phone: no sideways scrolling", phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        phone.evaluate("selectCourse('PSTAT 120B', true)")
        phone.wait_for_timeout(900)
        check("phone: selecting a course opens the sheet", phone.evaluate("el.panel.classList.contains('open')"))
        box_bottom, sheet_top = phone.evaluate("""() => [
            document.querySelector('.box[data-code="PSTAT 120B"]').getBoundingClientRect().bottom,
            el.panel.getBoundingClientRect().top]""")
        check("phone: the selected course stays visible above the sheet", box_bottom < sheet_top,
              "%d vs %d" % (box_bottom, sheet_top))
        check("phone: no JavaScript errors", not phone.errors, phone.errors)
        browser.close()

        # 9. The single file, opened from the disk
        if not SINGLE_FILE.exists():
            check("single file exists (run py build_single.py)", False)
        else:
            browser = p.chromium.launch()
            page = new_page(browser, viewport={"width": 1400, "height": 900})
            url = SINGLE_FILE.as_uri()
            page.goto(url)
            page.wait_for_timeout(1500)
            check("single file: picker has every major and minor",
                  page.evaluate("document.querySelectorAll('#major-list option').length") == len(listed))
            check("single file: no download link to itself", not page.is_visible("#footer-download"))
            open_major(page, url, "computer-engineering-bs", "BSCMPEN")
            check("single file: CE shows MATH 4A and ECE 139",
                  box(page, "MATH 4A").count() == 1 and box(page, "ECE 139").count() == 1)
            box(page, "ECE 152A").click()
            page.wait_for_timeout(150)
            check("single file: clicking shows the course", page.inner_text("#panel-body h2") == "ECE 152A")
            page.click("#credit-button")
            check("single file: the Credit box has the AP chart", page.locator("#ap-list select").count() > 30)
            page.keyboard.press("Escape")
            check("single file: course descriptions are there",
                  page.locator("#panel-body details").count() == 1)
            page.click("#all-link")
            page.wait_for_timeout(300)
            check("single file: 'All majors and minors' works", page.is_visible("#welcome"))
            check("single file: no JavaScript errors", not page.errors, page.errors)
            browser.close()

    print("%d checks passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
