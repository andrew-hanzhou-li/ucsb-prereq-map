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

import datetime
import json
import os
import pathlib
import re
import sys

from playwright.sync_api import sync_playwright

# A made-up transcript in the layout of GOLD's "Unofficial Transcript -
# Printable Version" (no real student's data). Each row: course, grade,
# EnrlCd, Att/Comp/GPA units, points, additional info. It covers what real
# transcripts showed: titles that wrap, "295LA-TITLE" with no space before
# the dash, two-word subjects, S and W grades, "No Credit", a variable-unit
# course, and courses in progress (no grade yet).
TRANSCRIPT_TERMS = [
    ("Fall 2024", [
        ("CMPSC 16 -PROBLEM SOLVING I", "A", "30111", "4.0", "4.0", "4.0", "16.00", ""),
        ("ECE 15A -FUND OF LOGIC DESIGN", "A-", "30222", "4.0", "4.0", "4.0", "14.80", ""),
        ("MATH 4A -LINEAR ALGEBRA W APPLIC", "B+", "30333", "4.0", "4.0", "4.0", "13.20", ""),
        ("ECE 1A -COMPUTER ENGR SEMINAR", "P", "30444", "1.0", "1.0", "0.0", "0.00", ""),
    ]),
    ("Winter 2025", [
        ("PSTAT 5E -STAT ECON BUS APPL", "A", "40111", "5.0", "0.0", "0.0", "0.00", "No Credit"),
        ("ECE 10A -FOUND ANALOG DIG CIRC", "B", "40222", "3.0", "3.0", "3.0", "9.00", ""),
        ("ANTH 99 -INDEPENDENT STUDIES", "A", "40333", "2.0", "2.0", "2.0", "8.00", ""),
        ("HIST 295LA-WORKSHOP LATIN AM", "S", "40444", "1.0", "1.0", "0.0", "0.00", ""),
        ("RG ST 148B -ADVANCED ARABIC", "W", "40555", "4.0", "0.0", "0.0", "0.00", ""),
    ]),
    ("Spring 2025", [
        ("ECE 10B -FOUND ANALOG DIG CIRC II", "", "50111", "3.0", "0.0", "0.0", "0.00", ""),
        ("MATH 6A -VECTOR CALCULUS", "", "50222", "4.0", "0.0", "0.0", "0.00", ""),
    ]),
]
TRANSCRIPT_EXPECTED = [
    # code, units, grade, used
    ("CMPSC 16", 4, "A", True), ("ECE 15A", 4, "A-", True), ("MATH 4A", 4, "B+", True), ("ECE 1A", 1, "P", True),
    ("PSTAT 5E", 5, "A", False), ("ECE 10A", 3, "B", True), ("ANTH 99", 2, "A", True), ("HIST 295LA", 1, "P", True),
    ("RG ST 148B", 4, "IP", False), ("ECE 10B", 3, "IP", True), ("MATH 6A", 4, "IP", True),
]


def transcript_text():
    """As copied from GOLD's page: one line per row."""
    lines = ["University of California, Santa Barbara", "Unofficial Transcript", "TEST STUDENT", "Perm Number: 0000000"]
    for term, rows in TRANSCRIPT_TERMS:
        lines += [term, "Course Grade EnrlCd Att Unit Comp Unit GPA Unit Points Additional Info"]
        lines += [" ".join(x for x in row if x) for row in rows]
        lines.append("Quarter Total (Ugrad) GPA 3.50 13.0 13.0 13.0 45.50")
    return "\n".join(lines)


def transcript_html():
    """As GOLD prints it: a table whose narrow Course column wraps long
    titles, with the other cells centered between the two lines."""
    html = ["<style>body{font:13px serif} td,th{padding:2px 6px;vertical-align:middle} td.c{width:150px}</style>",
            "<p>University of California, Santa Barbara</p><h3>Unofficial Transcript</h3><p>TEST STUDENT<br>Perm Number: 0000000</p>"]
    for term, rows in TRANSCRIPT_TERMS:
        html.append("<h4>%s</h4><table><tr><th>Course</th><th>Grade</th><th>EnrlCd</th><th>Att<br>Unit</th>"
                    "<th>Comp<br>Unit</th><th>GPA<br>Unit</th><th>Points</th><th>Additional Info</th></tr>" % term)
        for row in rows:
            html.append("<tr><td class='c'>%s</td>" % row[0] + "".join("<td>%s</td>" % x for x in row[1:]) + "</tr>")
        html.append("<tr><td><b>Quarter Total (Ugrad)</b></td><td><b>GPA 3.50</b></td><td></td><td>13.0</td></tr></table>")
    return "".join(html)


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


def online_base(code, codes):
    """'PSTATW 120A' -> 'PSTAT 120A' if that's in codes (the site's rule, app.js onlineBase)."""
    match = re.match(r"^(.+?)\s?W (\S+)$", code)
    if not match:
        return None
    base = match.group(1) + " " + match.group(2)
    return base if base in codes else None


def box(page, code):
    return page.locator('.box[data-code="%s"]' % code)


def classes(page, code):
    return box(page, code).get_attribute("class") or ""


def find_course(page, code):
    page.fill("#course-input", code)
    page.press("#course-input", "Enter")
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
        check("major search finds every major and minor by its name",
              page.evaluate("majors.every(m => findPrograms(displayName(m.name)).some(x => x.program.id === m.id))"))
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
              ece.count() == 1 and "Computer Engineering (B.S.)" in ece.inner_text())
        # Item 17: one name format everywhere.
        check("program names read 'Name (B.S.)' / 'Name (minor)'",
              page.evaluate("[displayName('Computer Engineering - BS'), displayName('Media Arts and Design- Minor'),"
                            " displayName('Anthropology - BA - Archaeology Emphasis'), displayName('Computer Engineering (B.S.)')]")
              == ["Computer Engineering (B.S.)", "Media Arts and Design (minor)",
                  "Anthropology (B.A., Archaeology Emphasis)", "Computer Engineering (B.S.)"])
        check("the front page list uses that format",
              not any(" - " in t for t in page.locator("#browse .dept li").all_inner_texts()))
        # Item 18: the Show checkboxes stay out of the way until a program is open.
        check("front page: the Show checkboxes are hidden", not page.is_visible("#toggles"))

        # Item 9: the search boxes.
        def suggestions(selector, text):
            page.fill(selector, text)
            page.wait_for_timeout(150)
            return page.locator(selector + " ~ .search-list li").all_inner_texts()
        found = suggestions("#major-input", "stats")
        check("major search: 'stats' finds Statistics and Data Science",
              any(t.startswith("Statistics and Data Science") for t in found), found[:4])
        found = suggestions("#major-input", "cs")
        check("major search: 'cs' puts Computer Science first", found and found[0].startswith("Computer Science"), found[:3])
        found = suggestions("#major-input", "COMP eng")
        check("major search: ignores case, matches word starts", found and found[0] == "Computer Engineering (B.S.)", found[:3])
        found = suggestions("#major-input", "economcs")
        check("major search: no match says so and suggests the nearest",
              found and found[0].startswith("No match for") and "Economics" in found[0], found)
        page.click(".search-list [data-guess]")
        page.wait_for_function("graph && graph.major.programs.length === 1", timeout=15000)
        check("major search: clicking 'Did you mean' opens it", page.evaluate("location.hash").startswith("#economics"))
        page.goto(SITE)
        page.wait_for_timeout(300)
        page.fill("#major-input", "physics")
        page.locator("#major-input").blur()
        page.click("#major-input")
        check("major search: clicking into the box selects its text",
              page.evaluate("[el.majorInput.selectionStart, el.majorInput.selectionEnd]") == [0, len("physics")])
        page.fill("#major-input", "")
        check("front page: course search is on", page.is_enabled("#course-input"))
        page.click("#course-input")
        page.wait_for_function("courseIndex !== null")
        found = suggestions("#course-input", "cs 16")
        check("course search: 'cs 16' finds CMPSC 16", found and found[0].startswith("CMPSC 16"), found[:3])
        found = suggestions("#course-input", "math4a")
        check("course search: spaces don't matter", found and found[0].startswith("MATH 4A"), found[:3])
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowUp")
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)
        check("course search on the front page opens a panel listing its programs",
              page.is_visible("#panel") and page.inner_text("#panel-body h2") == "MATH 4A" and
              "Computer Engineering (B.S.)" in page.inner_text("#panel-body"))
        page.click("#panel-body a[href='#computer-engineering-bs/MATH+4A']")
        page.wait_for_function("graph && selected === 'MATH 4A'", timeout=15000)
        check("its program link opens that map with the course chosen", page.evaluate("location.hash") == "#computer-engineering-bs/MATH+4A")
        found = suggestions("#course-input", "ece 15")
        check("course search on a map: nickname-free codes still work", found and found[0].startswith("ECE 15A"), found[:3])
        found = suggestions("#course-input", "zzz 999")
        check("course search: no match says so", found and found[0].startswith("No match for"), found)
        page.keyboard.press("Escape")
        check("Esc closes the list", not page.is_visible(".search-list"))
        page.goto(SITE)
        page.wait_for_timeout(300)

        open_major(page, SITE, "economics-ba", "BAECON")
        check("the Show checkboxes appear once a program is open", page.is_visible("#toggles"))
        check("the chosen program is shown by name", "Economics (B.A.)" in page.inner_text("#chosen"))
        check("the picker is empty, ready to add another program", page.input_value("#major-input") == "")

        # Phase 1: several programs at once (CE BS + Statistical Science minor)
        page.fill("#major-input", "comp eng bs")
        page.press("#major-input", "Enter")
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
        expected = {c for c in expected if online_base(c, expected) is None}   # twins share a card
        boxes = page.evaluate("[...document.querySelectorAll('.box[data-code]')].map(b => b.dataset.code)")
        check("combined map: every course of both programs is there", expected <= set(boxes),
              sorted(expected - set(boxes))[:5])
        check("combined map: no course appears twice", len(boxes) == len(set(boxes)))
        check("combined map: MATH 4A, in both, says it counts toward both",
              "counts toward both" in box(page, "MATH 4A").inner_text())
        check("combined map: a course in only one program doesn't", "counts toward" not in box(page, "ECE 152A").inner_text())
        titles = page.locator(".elective-row .row-label").all_inner_texts()
        check("combined map: elective lists are labeled with their program",
              any(t.startswith("Computer Engineering (B.S.):") for t in titles) and any(t.startswith("Statistical Science (minor):") for t in titles), titles)
        box(page, "MATH 4A").click()
        page.wait_for_timeout(100)
        check("combined map: the panel says which programs a course counts toward",
              "Counts toward Computer Engineering (B.S.) and Statistical Science (minor)" in page.inner_text("#panel-body"))
        check("combined map: no JavaScript errors", not page.errors, page.errors)

        # 2. Every major
        for major in majors:
            stem = major["file"][:-5]
            page.errors.clear()
            open_major(page, SITE, stem, major["id"])
            with open("site/data/" + major["file"], encoding="utf-8") as f:
                graph = json.load(f)
            expected = sorted(n["id"] for n in graph["nodes"] if n["status"] == "active" and n["in_major"])
            # An online twin (PSTATW 120A) shares its base course's card (item 13).
            expected = [c for c in expected if online_base(c, expected) is None]
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
              page.inner_text("#panel-body h2") == "Computer Engineering (B.S.)")
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

        # Phase 3: the quarter-by-quarter plan
        page.evaluate("localStorage.clear()")
        page.goto(SITE + "#plan/economics-ba")
        page.reload()
        page.wait_for_function("graph && currentView === 'plan'", timeout=15000)
        page.evaluate("credit.ap = {'Calculus BC': 4}; creditChanged(); refreshPlan()")
        check("plan: the Plan view replaces the map", page.is_visible("#plan-area") and not page.is_visible(".map-area"))
        check("plan: Plan is the current view", "current" in (page.get_attribute("#view-plan", "class") or ""))
        for code, slot in (("ECON 1", "1-F"), ("ECON 2", "1-W"), ("ECON 10A", "1-S")):
            page.click('[data-plan-add="%s"]' % code)
            page.wait_for_timeout(80)
            check("plan: clicking %s places it in %s" % (code, slot), page.evaluate("c => plan.placed[c]", code) == slot,
                  page.evaluate("c => plan.placed[c]", code))
        check("plan: the slim panel shows units and when it's offered, not prerequisites",
              "units" in page.inner_text("#panel-body") and "Usually offered" in page.inner_text("#panel-body") and
              "Needs first" not in page.inner_text("#panel-body"))
        # Phase 4: grades and GPA
        for code, grade in (("ECON 1", "A"), ("ECON 2", "B+"), ("ECON 10A", "P")):
            page.click('.chip[data-plan-drag="%s"]' % code)
            page.select_option('[data-plan-grade="%s"]' % code, grade)
            page.wait_for_timeout(80)
        gpa = page.evaluate("gpaOf()")
        check("grades: GPA is (5 x 4.0 + 5 x 3.3) / 10 = 3.65, with P left out",
              abs(gpa["gpa"] - 3.65) < 1e-9 and gpa["units"] == 10, gpa)
        page.click("[data-plan-close]")
        page.wait_for_timeout(100)
        check("grades: the plan's summary shows the GPA", "3.65" in page.inner_text("#panel-body"))
        check("item 12: the GPA says which courses it covers",
              "GPA of graded courses in this plan" in page.inner_text("#panel-body") and "GOLD" in page.inner_text("#panel-body"))
        check("grades: the grade shows on the course in the grid", "A" in page.inner_text('.chip[data-plan-drag="ECON 1"]'))
        page.click('.chip[data-plan-drag="ECON 1"]')
        page.select_option('[data-plan-grade="ECON 1"]', "F")
        page.wait_for_timeout(80)
        check("grades: an F counts 0 points", abs(page.evaluate("gpaOf().gpa") - 1.65) < 1e-9)
        # (isDone would be true here anyway: ECON 2, passed, needs ECON 1; see item 6.)
        check("grades: an F isn't a pass", not page.evaluate("passedCourse('ECON 1')"))
        page.select_option('[data-plan-grade="ECON 1"]', "IP")
        page.wait_for_timeout(80)
        check("grades: In Progress doesn't count toward GPA", page.evaluate("gpaOf().units") == 5)
        page.select_option('[data-plan-grade="ECON 1"]', "A-")
        page.wait_for_timeout(80)
        check("grades: a passing grade counts as done", page.evaluate("isDone('ECON 1')"))
        # Phase 6: target grades for a goal GPA (ECON 1 A, ECON 2 B, ECON 10A ungraded, all year 1)
        page.evaluate("plan.grades = {'ECON 1': 'A', 'ECON 2': 'B'}; planChanged(); showPlanSummary()")
        page.fill('[data-goal="gpa"]', "3.5")
        page.select_option('[data-goal="year"]', "1")
        page.dispatch_event('[data-goal="gpa"]', "change")
        page.wait_for_timeout(100)
        target = page.evaluate("targetFor(3.5, 1)")
        check("goal: a 3.50 after year 1 needs (3.5 x 15 - 35) / 5 = 3.50 in ECON 10A",
              abs(target["needed"] - 3.5) < 1e-9 and target["remaining"] == 5, target)
        check("goal: the summary says what to aim for", "3.50" in page.inner_text(".target") and "A- or better" in page.inner_text(".target"),
              page.inner_text(".target"))
        page.fill('[data-goal="gpa"]', "4.0")
        page.dispatch_event('[data-goal="gpa"]', "change")
        page.wait_for_timeout(100)
        check("goal: says when a goal is out of reach", "more than straight A's" in page.inner_text(".target"))
        page.evaluate("plan.grades = {}; plan.goal = null; planChanged()")

        page.evaluate("credit.ap = {}; creditChanged(); refreshPlan()")
        check("plan: without the calculus credit, ECON 10A says what it needs first",
              any("MATH" in m for m in page.evaluate("missingPrereqs('ECON 10A')")))
        page.click("#plan-autofill")
        page.wait_for_timeout(300)
        flagged = page.evaluate("Object.keys(plan.placed).filter(c => missingPrereqs(c).length)")
        check("plan: auto-fill adds the calculus and puts no course before its prerequisites (Economics)", not flagged, flagged)
        over = page.evaluate("planSlots().filter(s => quarterUnits(s.id) > plan.cap).map(s => s.id)")
        check("plan: no quarter is over the unit cap", not over, over)
        check("plan: auto-fill adds elective slots", page.evaluate("plan.electives.length") > 0)
        check("plan: auto-fill picks one of MATH 2A or 3A, not both",
              page.evaluate("Boolean(plan.placed['MATH 2A']) !== Boolean(plan.placed['MATH 3A'])"))

        # dragging a course to another quarter
        page.drag_and_drop('.chip[data-plan-drag="ECON 2"]', '[data-plan-slot="2-W"]')
        page.wait_for_timeout(150)
        check("plan: dragging ECON 2 moves it", page.evaluate("plan.placed['ECON 2']") == "2-W")
        check("plan: ...and ECON 10A, now before it, is flagged", "warn" in (page.get_attribute('.chip[data-plan-drag="ECON 10A"]', "class") or ""))
        page.click('.chip[data-plan-drag="ECON 10A"]')
        page.wait_for_timeout(100)
        check("plan: the panel shows the unmet prerequisite only then",
              "Needs first" in page.inner_text("#panel-body") and "ECON 2" in page.inner_text("#panel-body"))
        page.click('.chip[data-plan-drag="ECON 2"]')
        page.click("[data-plan-move='-1']")
        page.wait_for_timeout(100)
        check("plan: 'earlier' moves a course back a quarter", page.evaluate("plan.placed['ECON 2']") == "2-F")

        # filling an elective slot
        first = page.evaluate("plan.electives[0].id")
        slot_quarter = page.evaluate("plan.electives[0].slot")
        page.click('.chip[data-plan-drag="%s"]' % first)
        pick = page.evaluate("document.querySelector('[data-plan-fill]').dataset.planFill")
        page.click("[data-plan-fill]")
        page.wait_for_timeout(150)
        check("plan: picking a course fills the elective slot, same quarter",
              page.evaluate("c => plan.placed[c]", pick) == slot_quarter and
              not page.evaluate("id => plan.electives.some(e => e.id === id)", first))

        # it's saved, shareable, downloadable
        placed = page.evaluate("JSON.stringify(plan.placed)")
        page.reload()
        page.wait_for_function("graph && currentView === 'plan'", timeout=15000)
        check("plan: it survives a reload", page.evaluate("JSON.stringify(plan.placed)") == placed)
        packed = page.evaluate("packPlan()")
        other = new_page(browser, viewport={"width": 1400, "height": 900})
        other.goto(SITE + "#plan/economics-ba/" + packed)
        other.wait_for_function("graph && currentView === 'plan'", timeout=15000)
        check("plan: a share link opens the same plan elsewhere", other.evaluate("JSON.stringify(plan.placed)") == placed)
        check("plan: ...and tidies the address afterwards", other.evaluate("location.hash") == "#plan/economics-ba")
        other.close()
        with page.expect_download() as download:
            page.click("#plan-download")
        check("plan: Download gives a CSV", download.value.suggested_filename == "ucsb-plan.csv")

        # transfer students start in year 3
        page.check("#plan-transfer")
        page.wait_for_timeout(150)
        years = page.locator(".plan-year").all_inner_texts()
        check("plan: transfer students start in year 3", years and years[0].startswith("Year 3"), years)
        page.uncheck("#plan-transfer")
        page.wait_for_timeout(150)

        # credit means auto-fill leaves those courses out
        page.once("dialog", lambda d: d.accept())
        page.click("#plan-clear")
        page.wait_for_timeout(150)
        check("plan: Clear empties it", page.evaluate("Object.keys(plan.placed).length") == 0)
        page.evaluate("credit.ap = {'Calculus BC': 4}; creditChanged(); refreshPlan()")
        page.click("#plan-autofill")
        page.wait_for_timeout(300)
        check("plan: with AP Calculus BC, auto-fill doesn't add MATH 2A, 2B, 3A or 3B",
              not page.evaluate("['MATH 2A','MATH 2B','MATH 3A','MATH 3B'].some(c => plan.placed[c])"))
        check("plan: ...and ECON 10A, which needs calculus, isn't flagged",
              not page.evaluate("missingPrereqs('ECON 10A').length"))
        page.evaluate("credit.ap = {}; creditChanged()")

        # Computer Engineering: a longer chain
        page.once("dialog", lambda d: d.accept())
        page.click("#plan-clear")
        page.goto(SITE + "#plan/computer-engineering-bs")
        page.wait_for_function("graph && graph.major.id === 'BSCMPEN' && currentView === 'plan'", timeout=15000)
        page.click("#plan-autofill")
        page.wait_for_timeout(500)
        flagged = page.evaluate("Object.keys(plan.placed).filter(c => missingPrereqs(c).length)")
        check("plan: auto-fill puts no course before its prerequisites (Computer Engineering)", not flagged, flagged)
        order = page.evaluate("['ECE 15A','ECE 10A','ECE 152A','ECE 154A'].map(c => slotIndex(plan.placed[c]))")
        check("plan: CE chain in order (ECE 15A, 10A before 152A before 154A)",
              min(order) >= 0 and order[0] < order[2] and order[1] < order[2] and order[2] < order[3], order)

        # The left column: credit first, one requirement area open at a time, outside courses listed
        check("plan: the credit box is at the top of the left column",
              page.locator("#plan-reqs > .req-credit [data-open-credit]").count() == 1)
        check("plan: only one requirement area is open", page.locator("#plan-reqs details.req-section[open]").count() == 1)
        areas = page.locator("#plan-reqs details.req-section")
        closed = page.locator("#plan-reqs details.req-section:not([open]) > summary").first
        closed_key = closed.evaluate("s => s.parentElement.dataset.area")
        closed.click()
        page.wait_for_timeout(100)
        check("plan: opening another area closes the first",
              page.locator("#plan-reqs details.req-section[open]").count() == 1 and
              page.evaluate("k => document.querySelector('details.req-section[data-area=\"' + k + '\"]').open", closed_key))
        check("sidebar: courses show their code only, no title",
              page.locator("#plan-reqs .req-title").count() == 0 and "Calculus with" not in page.text_content("#plan-reqs"))
        prep_slots = page.evaluate("""() => [...document.querySelectorAll('#plan-reqs details.req-section')]
            .filter(d => /pre-?major|preparation/i.test(d.querySelector('summary').textContent))
            .reduce((n, d) => n + d.querySelectorAll('[data-plan-elective]').length, 0)""")
        check("sidebar: no 'add a slot' in Pre-major or Preparation", prep_slots == 0, prep_slots)
        check("auto-fill: no elective slots for Pre-major or Preparation",
              not page.evaluate("plan.electives.some(e => /pre-?major|preparation/i.test(sectionNameForKey(e.key)))"))
        page.evaluate("document.querySelector('#plan-reqs details.req-section').open = true")
        group = page.evaluate("document.querySelector('#plan-reqs .req-group:not(.collapsed) > .req-children > .req-thread').dataset.reqToggle")
        page.click('#plan-reqs .req-thread[data-req-toggle="%s"]' % group, force=True)
        page.wait_for_timeout(100)
        check("sidebar: clicking a group's line collapses the whole group",
              page.evaluate("k => document.querySelector('[data-req-toggle=\"' + k + '\"]').closest('.req-group').classList.contains('collapsed')", group))
        page.click('#plan-reqs .req-toggle[data-req-toggle="%s"]' % group)
        page.wait_for_timeout(100)
        check("sidebar: clicking its heading opens it again",
              not page.evaluate("k => document.querySelector('[data-req-toggle=\"' + k + '\"]').closest('.req-group').classList.contains('collapsed')", group))
        outside = page.locator('#plan-reqs details[data-area="outside"]')
        check("plan: CE lists the courses it needs from other departments, including CMPSC 8",
              outside.count() == 1 and "CMPSC 8" in outside.text_content())

        # Andrew's case: MATH 3B planned, MATH 3A from AP Calculus AB
        page.evaluate("plan.placed = {'MATH 3B': '1-F'}; plan.electives = []; planChanged()")
        check("AP: MATH 3B without MATH 3A is flagged", page.evaluate("missingPrereqs('MATH 3B').length") > 0)
        page.click('.chip[data-plan-drag="MATH 3B"]')
        check("AP: the course's panel offers to add credit", page.locator("#panel-body [data-open-credit]").count() == 1)
        page.click("#panel-body [data-open-credit]")
        page.check('input[data-exam-check="Calculus AB (or the AB subscore of BC)"]')
        page.wait_for_timeout(150)
        check("AP: ticking an exam sets a score and shows what it counts as",
              "MATH 3A" in page.inner_text(".ap-row.taken .ap-result"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        check("AP: with AP Calculus AB, MATH 3B is no longer flagged", page.evaluate("missingPrereqs('MATH 3B').length") == 0)
        check("AP: the credit shows at the top of the plan", "AP Calculus AB" in page.inner_text("#plan-reqs .req-credit"))
        page.click("#credit-button")
        page.uncheck('input[data-exam-check="Calculus AB (or the AB subscore of BC)"]')
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        check("AP: unticking takes the credit away", page.evaluate("missingPrereqs('MATH 3B').length") > 0)

        # IMPROVEMENTS.md P0, items 1-4, on an empty CE plan
        page.evaluate("localStorage.clear()")
        page.goto(SITE + "#plan/computer-engineering-bs")
        page.reload()
        page.wait_for_function("graph && graph.major.id === 'BSCMPEN' && currentView === 'plan'", timeout=15000)
        today = datetime.date.today()
        fall = today.year if today.month >= 9 else today.year - 1
        check("item 4: a fresh plan starts in the current academic year (Fall %d)" % fall,
              page.evaluate("plan.startYear") == fall and page.locator(".plan-year").first.inner_text().startswith("Year 1 · %d" % fall))
        check("item 4: the label says what the year means", "First quarter at UCSB" in page.inner_text(".plan-tools"))
        page.click("#plan-autofill")
        page.wait_for_timeout(500)
        capstones = page.evaluate("['CMPSC 189A', 'ECE 189A'].filter(c => plan.placed[c])")
        check("item 1: auto-fill schedules exactly one capstone sequence", len(capstones) == 1, capstones)
        years = page.evaluate("['CMPSC 189A','CMPSC 189B','ECE 189A','ECE 189B','ECE 189C'].filter(c => plan.placed[c]).map(c => Number(plan.placed[c].split('-')[0]))")
        check("item 2: the senior-standing capstone is in year 4", years and min(years) >= 4, years)
        senior = page.evaluate("Object.keys(nodesById).filter(c => plan.placed[c] && standingYear(c) && standingYear(c).year === 4 && Number(plan.placed[c].split('-')[0]) < 4)")
        check("item 2: no senior-standing course before year 4", not senior, senior)
        early = page.evaluate("Object.keys(plan.placed).filter(c => courseInfo(c).level === 'upper' && plan.placed[c].startsWith('1-'))")
        check("item 3: no upper-division course in year 1", not early, early)
        check("item 3: ECE 139 isn't in year 1", not page.evaluate("plan.placed['ECE 139'].startsWith('1-')"))
        check("item 10: ECE 139, offered Spring only (hand correction), is planned in a Spring",
              page.evaluate("plan.placed['ECE 139'].endsWith('-S')"), page.evaluate("plan.placed['ECE 139']"))
        check("item 10: cards with assumed quarters are marked, ECE 139 isn't",
              page.locator(".chip.assumed").count() > 0 and
              "assumed" not in (page.get_attribute('.chip[data-plan-drag="ECE 139"]', "class") or ""))
        capstone = capstones[0]
        page.drag_and_drop('.chip[data-plan-drag="%s"]' % capstone, '[data-plan-slot="2-F"]')
        page.wait_for_timeout(150)
        check("item 2: dragging the capstone to year 2 shows the '!' for senior standing",
              "warn" in (page.get_attribute('.chip[data-plan-drag="%s"]' % capstone, "class") or "") and
              any("senior standing" in m for m in page.evaluate("c => missingPrereqs(c)", capstone)))
        page.goto(SITE + "#computer-engineering-bs")
        page.wait_for_function("currentView === 'map'", timeout=10000)
        check("item 1: the map shows the capstone as 'one of'", "or CMPSC 189A" in box(page, "ECE 189A").inner_text(),
              box(page, "ECE 189A").inner_text())

        # Item 13: online twins share one card
        page.goto(SITE + "#statistics-and-data-science-bs")
        page.wait_for_function("graph && graph.major.id === 'BSSTSDS' && currentView === 'map'", timeout=15000)
        check("item 13: PSTAT 120A's card names its online twin", "or online PSTATW 120A" in box(page, "PSTAT 120A").inner_text())
        check("item 13: PSTATW 120A has no card of its own", box(page, "PSTATW 120A").count() == 0)
        page.evaluate("taken.add('PSTATW 120A'); doneChanged(); draw()")
        check("item 13: taking the online twin counts for both", page.evaluate("isDone('PSTAT 120A')") and "taken" in classes(page, "PSTAT 120A"))
        page.evaluate("taken.delete('PSTATW 120A'); doneChanged(); draw()")
        page.goto(SITE + "#plan/computer-engineering-bs")
        page.wait_for_function("graph.major.id === 'BSCMPEN' && currentView === 'plan'", timeout=15000)

        # Items 5-6: reading a transcript into an auto-filled plan
        page.goto(SITE + "#plan/computer-engineering-bs")
        page.wait_for_function("currentView === 'plan'", timeout=10000)
        page.click("#plan-import")
        page.fill("#transcript-text", transcript_text())
        page.click("#transcript-read")
        page.wait_for_timeout(200)
        page.click("#transcript-apply")
        page.wait_for_timeout(500)
        used = page.evaluate("""() => { const ys = new Set(); for (const c of Object.keys(plan.placed)) ys.add(Number(plan.placed[c].split('-')[0]));
            for (const e of plan.electives) ys.add(Number(e.slot.split('-')[0])); return [...ys].sort((a, b) => a - b); }""")
        check("item 5: no empty years between the transcript and the rest of the plan",
              used == list(range(used[0], used[-1] + 1)), used)
        flagged = page.evaluate("Object.keys(plan.placed).filter(c => missingPrereqs(c).length)")
        check("item 5: nothing planned before what it needs after the import", not flagged, flagged)
        first_open = page.evaluate("firstOpenIndex()")
        check("item 5: planned courses all come after the transcript's last quarter",
              page.evaluate("i => Object.keys(plan.placed).filter(c => !plan.grades[c]).every(c => slotIndex(plan.placed[c]) >= i)", first_open))
        check("item 6: a passed course is never flagged (CMPSC 16, A)", not page.evaluate("missingPrereqs('CMPSC 16').length"))
        check("item 6: no CMPSC 8 for someone who passed CMPSC 16", not page.evaluate("plan.placed['CMPSC 8']"))

        # Item 16: wording in the sidebar and the course panel
        page.evaluate("document.querySelectorAll('#plan-reqs details.req-section').forEach(d => d.open = true)")
        side = page.text_content("#plan-reqs")
        check("item 16: groups read 'All of these' / 'One of these'", "All of these" in side and "One of these" in side)
        check("item 16: no 'All of 0 of 2' style counts", " of 0 of " not in side and "All of done" not in side)
        page.goto(SITE + "#computer-engineering-bs/MATH+4A")
        page.wait_for_function("selected === 'MATH 4A'", timeout=10000)
        check("item 16: the panel doesn't say 'Preparation for the major: Preparation'",
              "major: Preparation" not in page.inner_text("#panel-body"), page.inner_text("#panel-body")[:300])

        # Item 11: a repeated course shows both attempts
        page.goto(SITE + "#plan/computer-engineering-bs")
        page.wait_for_function("currentView === 'plan'", timeout=10000)
        rows = page.evaluate("""t => parseTranscript(t).map(r => [r.code, r.grade, r.use, r.note])""",
                             "Fall 2024\nMATH 4A -LINEAR ALGEBRA F 11111 4.0 0.0 4.0 0.00\nWinter 2025\nMATH 4A -LINEAR ALGEBRA B 22222 4.0 4.0 4.0 12.00")
        check("item 11: both attempts are listed", len(rows) == 2, rows)
        check("item 11: the earlier one is unticked and says it was replaced",
              rows[0][2] is False and "replaced by B" in rows[0][3], rows)
        check("item 11: the later one says what it replaced", rows[1][2] is True and "repeated: F replaced by B" in rows[1][3], rows)

        # Item 7: credit takes covered courses out, and the warning follows
        page.evaluate("localStorage.clear()")
        page.goto(SITE + "#plan/economics-ba")
        page.reload()
        page.wait_for_function("graph && graph.major.id === 'BAECON' && currentView === 'plan'", timeout=15000)
        page.click("#plan-autofill")
        page.wait_for_timeout(400)
        check("item 7: (setup) auto-fill planned MATH 2A and 2B", page.evaluate("Boolean(plan.placed['MATH 2A'] && plan.placed['MATH 2B'])"))
        page.click("#credit-button")
        page.select_option('select[data-exam="Calculus BC"]', "3")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        check("item 7: AP Calculus BC takes MATH 2A and 2B out of the plan",
              not page.evaluate("plan.placed['MATH 2A'] || plan.placed['MATH 2B']"))
        chips = sorted(page.evaluate("[...document.querySelectorAll('.chip.warn')].map(c => c.dataset.planDrag)"))
        summary = page.inner_text("#panel-body")
        check("item 7: the summary's warning matches the '!' marks",
              (not chips and "planned before" not in summary) or all(c in summary for c in chips), (chips, summary[:200]))
        page.evaluate("localStorage.clear()")

        # Two programs and AP credit: the case that showed ordering by column wasn't enough
        page.evaluate("localStorage.clear()")
        page.goto(SITE + "#plan/computer-engineering-bs+statistical-science-minor")
        page.reload()
        page.wait_for_function("graph && graph.major.programs.length === 2 && currentView === 'plan'", timeout=15000)
        page.evaluate("credit.ap = {'Calculus BC': 5}; creditChanged(); refreshPlan()")
        page.click("#plan-autofill")
        page.wait_for_timeout(500)
        flagged = page.evaluate("Object.keys(plan.placed).filter(c => missingPrereqs(c).length)")
        check("plan: CE + Statistical Science minor auto-fills with nothing before its prerequisites", not flagged, flagged)
        check("plan: ...and with slots for CE's 36 units of electives", page.evaluate("plan.electives.length") >= 9)
        check("plan: ...and no calculus, thanks to the AP credit",
              not page.evaluate("['MATH 2A','MATH 3A','MATH 3B'].some(c => plan.placed[c])"))
        page.evaluate("credit.ap = {}; creditChanged()")

        # back to the map
        page.click("#view-map")
        page.wait_for_function("currentView === 'map'", timeout=5000)
        check("plan: Map goes back to the map", page.is_visible(".map-area") and page.locator(".box").count() > 0)
        check("plan: no JavaScript errors", not page.errors, page.errors)

        # Phase 5: reading a transcript (pasted text, then a PDF)
        page.evaluate("localStorage.clear()")
        page.goto(SITE + "#plan/economics-ba")
        page.reload()
        page.wait_for_function("graph && currentView === 'plan'", timeout=15000)
        def read_rows():
            return page.evaluate("transcriptRows.map(r => [r.code, r.units, r.grade, r.use])")

        def expected_rows():
            return [list(r) for r in TRANSCRIPT_EXPECTED]

        page.click("#plan-import")
        page.fill("#transcript-text", transcript_text())
        page.click("#transcript-read")
        page.wait_for_timeout(200)
        rows = read_rows()
        check("transcript (pasted): every course read, with units and grades", rows == expected_rows(),
              [r for r in rows if r not in expected_rows()] or rows)
        check("transcript: shows a table to check before applying",
              page.locator(".review-table tbody tr").count() == len(TRANSCRIPT_EXPECTED))
        check("transcript: says why a row is left unticked", "no credit" in page.inner_text(".review-table") and
              "withdrawn" in page.inner_text(".review-table"))
        page.select_option('select[data-row="2"][data-field="grade"]', "A-")
        page.click("#transcript-apply")
        page.wait_for_timeout(200)
        check("transcript: courses go in their quarters (plan now starts Fall 2024)",
              page.evaluate("[plan.startYear, plan.placed['CMPSC 16'], plan.placed['ECE 10A'], plan.placed['ECE 10B']]") ==
              [2024, "1-F", "1-W", "1-S"])
        check("transcript: corrections in the table are used", page.evaluate("plan.grades['MATH 4A']") == "A-")
        check("transcript: unticked rows aren't added", not page.evaluate("plan.placed['PSTAT 5E'] || plan.placed['RG ST 148B']"))
        check("transcript: a variable-unit course keeps its units", page.evaluate("unitsOf('ANTH 99')") == 2)
        expected_gpa = (4 * 4.0 + 4 * 3.7 + 4 * 3.7 + 3 * 3.0 + 2 * 4.0) / 17
        check("transcript: grades feed the GPA (P and In Progress left out)", abs(page.evaluate("gpaOf().gpa") - expected_gpa) < 1e-9,
              page.evaluate("gpaOf()"))
        saved = page.evaluate("JSON.stringify(localStorage)")
        check("transcript: the student's name, perm number and enrollment codes aren't kept",
              "TEST STUDENT" not in saved and "0000000" not in saved and "30111" not in saved)

        # The PDF, laid out like GOLD's printout, read in the browser by pdf.js
        pdf_maker = browser.new_page()
        pdf_maker.set_content(transcript_html())
        pdf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_transcript.pdf")
        pdf_maker.pdf(path=pdf_path)
        pdf_maker.close()
        page.click("#plan-import")
        page.fill("#transcript-text", "")
        page.set_input_files("#transcript-file", pdf_path)
        page.click("#transcript-read")
        page.wait_for_function("transcriptRows.length > 0 || document.getElementById('transcript-status').textContent.includes('read')", timeout=20000)
        os.remove(pdf_path)
        rows = read_rows()
        check("transcript (PDF with wrapped titles): every course read, with units and grades", rows == expected_rows(),
              [r for r in rows if r not in expected_rows()] or rows or page.inner_text("#transcript-status"))
        page.keyboard.press("Escape")
        page.evaluate("localStorage.clear()")
        check("transcript: no JavaScript errors", not page.errors, page.errors)
        open_major(page, SITE, "economics-ba", "BAECON")

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
        check("item 8: the page has a large link-preview image",
              page.get_attribute('meta[property="og:image"]', "content").endswith("/preview.png") and
              page.get_attribute('meta[name="twitter:card"]', "content") == "summary_large_image")
        check("item 8: the preview image is there", page.request.get(SITE + "preview.png").ok)
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
            check("single file: major search finds every major and minor",
                  page.evaluate("majors.length") == len(listed) and
                  page.evaluate("majors.every(m => findPrograms(displayName(m.name)).some(x => x.program.id === m.id))"))
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
            fresh = new_page(browser, viewport={"width": 1400, "height": 900})
            fresh.goto(url + "#computer-engineering-bs/ECE+152A")
            fresh.wait_for_function("typeof selected !== 'undefined' && selected === 'ECE 152A'", timeout=15000)
            check("single file: opening it straight to a course works", not fresh.errors, fresh.errors)
            fresh.close()
            page.goto(url + "#plan/economics-ba")
            page.wait_for_function("currentView === 'plan'", timeout=15000)
            page.click('[data-plan-add="ECON 1"]')
            check("single file: the planner works offline", page.evaluate("plan.placed['ECON 1']") == "1-F")
            page.goto(url + "#computer-engineering-bs")
            page.wait_for_function("currentView === 'map' && graph.major.id === 'BSCMPEN'", timeout=15000)
            box(page, "ECE 152A").click()
            page.wait_for_timeout(150)
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
