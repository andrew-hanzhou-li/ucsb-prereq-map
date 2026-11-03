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
