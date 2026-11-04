# Part 9 — From prerequisite map to degree planner

**Status:** all six phases from `CLAUDE.md` are built on the `degree-planner` branch and pass the browser test (`py test_site.py`, 1,473 checks). Nothing is published yet: `main` and the live site are unchanged until you've reviewed this.

Each phase was committed separately, so `git log --oneline degree-planner` reads as the build order:

| Phase | What it adds | Main files |
|---|---|---|
| 1 | Any combination of majors and minors on one map | `app.js` (`combine`, `loadPrograms`) |
| 2 | AP and college credit, counted as done | `ap_credit.json`, `build_credit.py`, `student.js`, `credit.js` |
| 3 | The quarter-by-quarter plan | `planner.js` |
| 4 | Grades and a live GPA | `grades.js` |
| 5 | Reading a GOLD transcript in the browser | `transcript.js` |
| 6 | Target grades for a goal GPA | `grades.js` (end) |

## The big decision: one page, two views

**Map** and **Plan** are two views of the same programs, switched by the two links next to the program names. The address says which: `#economics-ba` is the map, `#plan/economics-ba` is the plan.

Why not separate pages:
- **The two views share everything:** the programs, credit, "taken" marks and grades. With one page they share the same loaded data and code; nothing is copied or kept in sync.
- **The one-file copy keeps working.** It's a single HTML page, and separate pages would need separate files.
- **The map stayed intact.** Every map test from before still passes, and each phase left the site working.

The code is split by job, one plain `<script>` per file, loaded in this order:

| File | Job |
|---|---|
| `student.js` | The student's own data, saved in this browser: credit, plan, grades |
| `app.js` | The map, the program picker, the address, switching views |
| `credit.js` | The Credit box |
| `planner.js` | The Plan view |
| `grades.js` | Grades, GPA, goal targets |
| `transcript.js` | Reading a transcript |

No framework, no modules, no build step for the code: `build_single.py` finds every `<script src>` in the page and copies it in, in order.

## Phase 1: combining programs

- **The address holds several programs**, joined by `+`: `#computer-engineering-bs+statistical-science-minor`. Old single-program links still work.
- **`combine()` merges the programs' graphs in the browser**, so the data files didn't change:
  - **Each course appears once.** Its role is the strongest one it has in any program (required beats "pick one", which beats elective), and `programs` lists every program it counts toward.
  - **Requirement sections and elective lists keep their program's name in front** ("Statistical Science minor — Upper division"), so two programs' lists can't merge by accident.
- **On the map**, a course in both programs says "counts toward both", and its entry names the programs.

## Phase 2: credit already earned

**AP.** The catalog's AP chart (2026-27) is a page of text, so I typed it into `ap_credit.json`, with its source link. Hand-copied data goes wrong quietly, so `build_credit.py` checks every course code against the current catalog. Five codes the chart names (ARTHI 1, CMPSC 4, EEMB 22, PSY 5, WRIT 2LK) aren't current courses. That's the catalog's chart naming retired courses, not a typo; they're kept and just never match a map.

- An exam that counts as "MATH 2A, 3A or 34A" gives credit for all three, so a prerequisite naming any of them is met.
- Exams only students from before 2018 could have are left out.

**College credit** (dual enrollment, community college). As CLAUDE.md says, other schools' courses aren't listed. You tick the UCSB course each one counts as: the Credit box lists the lower-division courses of the programs on screen, plus a field for any other UCSB course. It points to ASSIST.org for official equivalents.

**One rule for "done"** (`isDone` in `app.js`): ticked as taken, or AP/college credit, or a passing grade in the plan. The map's ✓ and "next" marks, the planner's prerequisite checks and auto-fill all use it.

**Where the box is:** "Credit" in the masthead, and an "Add it" line at the top of each map until some credit is entered. I chose this over a pop-up on first load, which gets in the way of someone who only wants to look at the map. Easy to change if you'd rather have a pop-up.

## Phase 3: the plan

### Where "when is it offered" comes from (open question 2)

The catalog has a field, `quartersUsuallyOffered`, but it's filled in for only **115 of 7,973 courses**. `fetch.py` now saves it. For the rest the plan assumes **Fall, Winter and Spring**, and says so in each course's panel and in the plan's summary ("Check the Schedule of Classes on GOLD"). It's honest, but it's the weakest data in the planner; see "What's next".

Other things checked and not found: the catalog's data has **no sample four-year plans**, and there's no public record of when students actually take courses. So placement uses only prerequisites, offering and the unit cap, as CLAUDE.md asked; no invented "usual trends".

### Click to add (`earliestSlot`)

A course goes in the first quarter where:
1. **its prerequisites are done, or planned for an earlier quarter.** Prerequisites marked "may be taken at the same time" can be in the same quarter. A prerequisite that isn't in the plan at all doesn't block it, but the course is flagged with "!".
2. **it's usually offered.** Summer only if "plan summer quarters" is ticked.
3. **the quarter stays under the unit cap** (16 by default, adjustable).

That gives CLAUDE.md's example exactly: ECON 1 → Fall, ECON 2 → Winter, ECON 10A → Spring.

### Auto-fill

1. **The courses to add:** every required course not done or planned, plus the courses from other departments they need. That's the same list the map draws, from `chooseShown`, which now takes its settings as an argument so the map's checkboxes don't change the plan.
2. **"Take one of" requirements:** keep an option already done or planned. Otherwise take the first one the catalog still offers (CMPSC 189A's "48 or 56 or …" skips the retired CMPSC 48).
3. **Order: each course after the ones it needs.** This is a topological sort (`prerequisiteOrder`), the CS 24 idea. My first version ordered by the map's "column" instead, and the test found a bug: in CE + Statistical Science minor, the two programs' columns disagree, and ECE 10A landed before MATH 4B. A final pass (`repairOrder`) re-places anything that still ends up ahead of a prerequisite.
4. **Elective slots:** for each elective list still short, labeled slots ("Area D electives", 4 units each) go in from year 3. Click a slot to pick its course from the list.

### Choose-N and electives (open question 3)

Requirements are trees (Part 3): `all`, `choose N`, `N units from`, `course`, `text`. Progress is worked out on the tree (`progress`):
- **a course:** 1 needed, 1 had if done or planned.
- **all of:** the sum of its parts.
- **choose N:** N needed; had = parts complete, plus elective slots.
- **N units:** units done or planned among its courses (sequences included), plus slots × 4.

The requirements column shows this per section and per group. Groups longer than 8 courses fold up, and so does progress inside a "one of" option you didn't take (it read like something was missing).

### The slim panel

Clicking a course in the plan shows:
- name, units and when it's usually offered;
- where it's planned;
- earlier / later / remove buttons;
- its grade;
- the catalog link.

**Prerequisites appear only when they're not met where the course is planned**, under "Needs first", with the catalog's wording.

### Moving courses

Drag a course to another quarter, or use "earlier"/"later" in its panel. Phone browsers don't support drag-and-drop, so the buttons are the phone's way.

### Extras kept from the Econ planner

- **Share link:** the plan itself is packed into the address (JSON → base64), so it works with no server. **Grades are left out.**
- **Download:** a CSV that opens in Excel, Sheets or Numbers.
- **Clear plan.**
- **Transfer student:** the plan starts in year 3 with two years.
- **Add a year** (up to 8).

## Phase 4: grades and GPA

- **Grades:** A+ through F, P, NP or In Progress, per course in the plan.
- **The scale is checked against the catalog's grading page:** A+ and A are 4.0, A− 3.7, … D− 0.7, F 0. P/NP and In Progress don't count toward GPA.
- **GPA** = Σ(points × units) ÷ Σ units over letter grades. Units come from the catalog. For **variable-unit courses** (fetch.py now saves ranges like ANTH 99's "1-4"), the panel has a units menu.
- **A passing grade counts as done** (P, or D− and up). Minimum grades in prerequisites ("C or better") aren't checked; the map's course entry shows them.

## Phase 5: transcript upload

- **Privacy:** the file is read by JavaScript in the student's browser, never uploaded, never stored. Only the courses the student approves are kept, in their plan. No GOLD login, ever.
- **PDF or pasted text.** A PDF is read with pdf.js, loaded from cdnjs only when someone opens a PDF. That downloads the library's code; nothing about the file is sent. Pasting the text works offline, including in the one-file copy.
- **How it reads:**
  - A line naming a quarter and year starts a term.
  - A line starting with a real UCSB subject code (the catalog's 139, saved by `build_credit.py`) and a course number is a course.
  - On a course line, the last grade-like word is the grade and the first number from 0.5 to 12 is the units. No grade means In Progress.
  - A course taken twice keeps its latest attempt.
- **A review table comes first:** fix units and grades, or untick courses, before "Apply". Courses then go in their quarters, and the plan's start moves to the first term on the transcript.
- **Tested with:** a sample transcript, both pasted and as a real PDF made in the test.
- **⚠ Not yet tested on a real GOLD transcript.** I don't have one. A redacted copy of yours (names and ID removed) would let me match its exact layout.

## Phase 6: target grades

You enter a goal GPA and a year. The needed average is:

> (goal × (graded units + remaining units) − grade points so far) ÷ remaining units

"Remaining" counts planned courses up to that year with no final grade (In Progress included), plus elective slots at 4 units. It's shown with the letter grade that meets it, and it says when a goal is out of reach or already secured.

**Spreading the target by course difficulty is not built yet.** It needs historical grade distributions. CLAUDE.md points at the Daily Nexus's public-records data, but its terms of use need checking before using it, and that's your call. The page says these targets are rough guidance and that grades vary a lot by instructor.

## Data refreshed along the way

- `fetch.py` also saves quarters usually offered and variable-unit ranges. Re-downloading showed the catalog had changed since early October: 34 courses added, 9 removed, 20 prerequisites reworded. Everything was rebuilt; the parser's held-out score is unchanged (89% / 96%).
- `fetch_programs.py` had already started saving department names (Part 8).

## What's next (my suggestions)

1. **A real GOLD transcript** (redacted) to tune `transcript.js`.
2. **Better "when offered" data.** The best public source is past quarters' class schedules; a script could record which quarters each course actually ran in the last 2–3 years. It's worth checking how UCSB's public class search may be used first.
3. **Keeping the catalog current (open question 4):** a `compare_catalog.py` that re-downloads into a temporary folder and lists what changed (courses added and removed, prerequisites reworded, programs changed) before anything is overwritten. The manual diff I did for this part is what it would automate.
4. **Difficulty-weighted targets**, once there's a grade-distribution source you're comfortable with.
5. **Phones:** the plan works (one year at a time, with earlier/later buttons), but a long requirements list sits above the grid. A tab for "requirements / plan" would help.
6. **Choices I made that you may want to change:**
   - Credit is reached from a masthead link, not a pop-up on first load.
   - The default unit cap is 16.
   - Elective slots start in year 3.
   - Share links leave out grades.

## Revision 1 (after your review)

### The transcript reader, rebuilt from real GOLD transcripts

Two real "Unofficial Transcript - Printable Version" pages showed why it missed about half the courses and got units wrong:

| What GOLD does | What the reader does now |
|---|---|
| Long titles wrap ("HIST 202 -HISTORICAL" / "METHODS"), and the grade and units sit halfway between the two lines, so a PDF has **three separate lines** per course | A course is its first line **plus the lines after it**, up to the next course, term, total or page header |
| Columns: Grade, EnrlCd (5 digits), Att Unit, Comp Unit, GPA Unit, Points, Additional Info | The grade is the word right **before the EnrlCd**; the units are **Att Unit, right after it** |
| "HIST 202 -HISTORICAL" but also "HIST 295LA-WORKSHOP" (no space), "RG ST 251B" (two-word subject) | A course is a subject, a number and a dash. Any capital-letter subject counts there, since old transcripts have codes the catalog has dropped |
| Grades S and U (graduate), W, I; "No Credit" under Additional Info | S → P, U → NP, I → In Progress. W and No Credit are listed but **unticked**, with the reason shown |
| A course in progress has no grade | In Progress |

The tests use a **made-up transcript in GOLD's exact layout**, not the real ones (those have students' names and perm numbers):
- **As pasted text:** every row on one line.
- **As a PDF:** a table with a narrow Course column, drawn by Chromium. It reproduces the three-lines-per-course problem; the test prints the PDF's lines, and the grade really is on its own line.
- **Both are read exactly:** all 11 courses, with units (including a 2-unit ANTH 99 and 1-unit courses) and grades.
- **Privacy is checked:** the name, perm number and enrollment codes are never saved.

Also fixed: a course from outside the programs on screen used to fall back to 4 units after a transcript was read; it now keeps the transcript's units, so the GPA is right.

### The column beside the plan

- **Your AP and college credit** is now the first thing in the column, with a button to check off exams. In the Credit box, each AP exam has a **checkbox**. Ticking it fills in a score of 3 (the lowest that earns credit) and shows what it counts as; change the score if yours differs. A course flagged for a missing prerequisite also offers "Add your credit" in its panel. With AP Calculus AB ticked, MATH 3B is no longer flagged for MATH 3A.
- **One requirement area open at a time.** Preparation, Upper division and the rest are folds; opening one closes the others. It starts on the first area that isn't complete.
- **"Needed first, from other departments"** lists the courses the requirements need from outside the program: CMPSC 8 for Computer Engineering, the calculus for Economics.
- **Auto-fill prefers the "one of" option you've partly done.** With AP Calculus AB, it adds MATH 2B or 3B, not a whole new sequence.

## Revision 2: a calmer sidebar

- **Course codes only** in the requirements column (MATH 2A, not "MATH 2A Calculus with Algebra and Trigonometry"). Pointing at a code still shows its title.
- **No "add a slot" in Pre-major or Preparation for the major**, in the column or from auto-fill (`slotsAllowed`). Students take specific courses there. Upper-division electives keep their slots.
- **Click a line to collapse a group, as in a Reddit thread.** Every group inside an area hangs off a thin vertical line. Clicking the line, or the group's heading, collapses the whole group to one line ("All of 0 of 2 · 2 courses"); clicking the heading opens it again. Long lists start collapsed. This replaced the triangle folds inside areas, so every group works the same way.

## Revision 3: the IMPROVEMENTS.md list

Each item below has a test that fails without the fix (test_site.py or test_graph.py). Commits are on the `improvements` branch, one per item or small group.

### P0: wrong plans

1. **Computer Engineering capstone is "one of two sequences".** program_overrides.json gets a `choose` override (with a `why` quoting the department sheet): CMPSC 189A–B *or* ECE 189A–C. build_majors.py learned the new `choose` kind.
2. **Class standing counts.** "Senior standing" puts a course in year 4 at the earliest, "junior standing" or upper division in year 3, "sophomore"/"not open to freshmen" in year 2 (`standingYear`). A course placed too early is flagged.
3. **Upper-division courses start in year 2 or later** (`placementYear`).
4. **The start year defaults to the current academic year** (Fall of this year from September, else last year), and the label reads "First quarter at UCSB: Fall 2026".
5. **Reading a transcript into a plan no longer scrambles it.** Nothing is auto-placed before the quarter after your last graded course (`firstOpenIndex`); courses the transcript covers come out of the plan (`pruneCovered`), and the rest of the auto-filled plan is laid out again (`rebuildAfterTranscript`). Courses you placed by hand stay where you put them.
6. **Completed courses aren't flagged.** A course that's done (taken, credit, passed, or implied by a later course you passed) has no missing prerequisites.
7. **AP credit takes covered courses out of the plan,** and the message updates instead of going stale.
8. **Link previews.** og:image and Twitter card tags, with site/preview.png made by the new build_preview.py.

### P1: confusing or missing

9. **Search boxes** (new site/search.js) replace the browser's `<datalist>`, which only matched exact text:
   - Case and spaces don't matter ("cs 16", "MATH4A"), and common nicknames work (cs, stats, econ, ee, poli sci, psych…).
   - Arrow keys and Enter; clicking into a box selects its text.
   - No match says so and offers the nearest name: "No match for 'economcs'. Did you mean Economics (B.A.)?"
   - **Course search works on the front page.** Its panel lists every program that uses the course, each linking straight to it on that map. The data is site/data/course-index.json (233 KB, loaded the first time the box is used), built by build_graph.py.
10. **When courses are offered.** build_graph.py reads it from hand corrections (new offering_overrides.json), then the catalog's field, then phrases in course text: 121 courses in all. ECE 139 is Spring only, from the department's 4-year plan. Everything else is assumed Fall/Winter/Spring and marked with a faint "?" in the plan. UCSB's public API has real quarter data, but it needs an API key; that's your call.
11. **Repeated courses on a transcript.** Every attempt is listed; earlier ones are unticked ("earlier attempt, replaced by B"), as GOLD's repeat rule works.
12. **GPA label:** "GPA of graded courses in this plan", with a note that GOLD's own GPA is the official one.
13. **Online twins share a card:** "PSTAT 120A (or online PSTATW 120A)". Taking either counts for both.
14. **No empty condition text.** The hand overrides in overrides.json now carry the catalog's words (`@other{significant prior programming experience}`); test_graph.py fails on any empty one.
15. **Small phones (checked at 375×667, iPhone SE size).**
   - Plan view: the settings fold behind **Settings** and the five plan links behind a **⋯** menu. The grid starts about 180px down instead of about 400.
   - Map: one intro line with **How to read this** for the key.
   - The header **shrinks once you scroll** (tagline and the add-a-program box go) and comes back at the top.
16. **Wording:** "All of these", "One of these", "Choose 2 of these", and progress as "0/2 done".

### P2: polish

17. **One name format:** "Computer Engineering (B.S.)", "Statistical Science (minor)", "Anthropology (B.A., Archaeology Emphasis)" (`displayName` in app.js), everywhere a program is named.
18. **The Show checkboxes are hidden on the front page** until a program is open.
19. **AP box: a score dropdown only** ("—" = not taken; nothing set by default) and a **filter box** for the ~40 exams. Exams with a score stay in view while filtering.
20. **Elective slots spread evenly.** Each goes in the quarter (year 3 on) with the fewest units so far. Computer Engineering's year 4 went from Fall 15 / Winter 12 / Spring 0 units to 11 / 12 / 8.
21. **pdf.js 3.11.174 → 4.10.38** (CVE-2024-4367 is fixed from 4.2.67). Version 4 is a JavaScript module only, and a module loaded with `import()` can't carry an integrity hash, so transcript.js downloads each file with `fetch()` and an SRI hash, then runs it from a local `blob:` copy; a file that doesn't match is refused. `isEvalSupported: false` is set. Tested on the site and in the one-file copy opened from disk.
22. **Privacy text vs. analytics:** no change, since the site has no analytics.
23. **The one-file copy's size** (8.7 MB) shows next to both links to it; build_single.py keeps the number current.
24. **Program count:** no change needed (the list checked it).
25. **ECE 139 vs PSTAT 120A:** the 2026–27 catalog data for Computer Engineering lists ECE 139 only and doesn't mention PSTAT 120A, so no override was added. The department's pages blocked automated access (403), so it's worth asking the CE advisor whether PSTAT 120A is still accepted.

### Also fixed along the way

- **The one-file copy crashed when opened straight at a program** ("passedCourse is not defined"): it started before the later scripts had loaded. It now starts on DOMContentLoaded.
- **build_graph.py's cleanup deleted credit.json**, emptying the Credit box until build_credit.py ran again. It now keeps that file (`KEEP_IN_DATA`).
