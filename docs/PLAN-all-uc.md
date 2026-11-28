# Plan: the prerequisite map for every UC

Status: plan only. Nothing is built until Andrew answers the open questions at the end.

## Goal

Turn the UCSB prerequisite map into one site for all nine undergraduate UC campuses. Like UCPath, you **choose your university first**, then everything after it (majors, courses, plan, credit) belongs to that campus.

For each campus, a student can:
- **see every major's prerequisite chain** as a map;
- **build a quarter-by-quarter plan** (semesters at Berkeley and Merced) with AP and transfer credit;
- **share the plan as a link**;
- **find any course's page** from a web search.

## Who it's for, and what already exists

- **Current UC students** choosing classes and planning a major. Official tools (GOLD, Schedule of Classes, degree audits) show requirements, but not the chain of prerequisites as a map or plan.
- **Transfer students** come later (phase 6). ASSIST and UC TAP are the official tools, and TransferPlanner and Plan My Transfer already exist, so we don't start there.
- **Other student tools** are mostly one campus each, and mostly grades or schedules (e.g. Berkeleytime). I found nothing UC-wide with prerequisite maps per major. That gap is ours.

## What stays the same (from the current site)

- **No backend, no accounts, no logins.** Plans live in the browser and in the share link.
- **Unofficial and honest:** every course links to its official catalog entry.
- **Plain Python pipeline + plain JavaScript site.** No framework.
- **Everything works offline**, once loaded.

## What the campus research showed

Every UC runs a different catalog system, so each campus needs its own fetcher and its own prerequisite parser.

| Campus | Catalog | Plan |
|---|---|---|
| UCSB | Coursedog API | Already done |
| UCSD | Plain HTML pages | Next: easiest to parse |
| UCLA | Custom site (Next.js) | Next: largest audience; read its page data |
| UC Merced | Acalog (Modern Campus) | One adapter; Acalog is common |
| UCSC | Custom catalog | Its own adapter |
| UC Berkeley, UC Riverside | The catalog address redirects to a registrar page; course data lives elsewhere | Research first |
| UC Irvine, UC Davis | Didn't answer from the cloud machine | Check from a home connection |

Majors (degree requirements) are much harder than courses: most catalogs write them as prose. So each new campus ships in two steps:
1. **Courses and prerequisites:** every course's chain, a map per department, course pages.
2. **Majors:** a map and plan per major, only where requirements can be read reliably. Otherwise a major page links to the catalog, and the student adds its courses by hand.

## Design: UCPath-style flow

```
┌───────────────────────────────────────────────────────────┐
│  [name]                                  About   Help     │   <- plain bar, no tagline
├───────────────────────────────────────────────────────────┤
│  Choose your university                                   │
│                                                           │
│  Berkeley     Davis       Irvine      Los Angeles         │   <- plain list, campus names
│  Merced       Riverside   San Diego   Santa Barbara       │      in UC's own order; campuses
│  Santa Cruz                                               │      not ready yet are greyed,
│                                                           │      with "coming" beside them
│  [ remember my choice ]                                   │
└───────────────────────────────────────────────────────────┘
               │
               ▼
┌───────────────────────────────────────────────────────────┐
│  [name] / UC Santa Barbara ▾          Credit  About       │   <- campus is always visible
│  Major or minor: [ Computer Science B.S.        ▾ ]       │      and switchable, like
│  Map | Plan                                               │      UCPath's institution context
├───────────────────────────────────────────────────────────┤
│  (the map or the plan, as today)                          │
└───────────────────────────────────────────────────────────┘
```

**Addresses carry the campus:** `/#/ucsb/computer-science-bs/plan`. Old UCSB links keep working, because they redirect to `/ucsb/`.

**Plans and credit are saved per campus.** Switching campus never mixes or loses data.

## Design: not looking machine-made

The current masthead ("The Prerequisite Map", a tagline, "· unofficial") is one of the patterns these checklists flag. The redesign follows a merged checklist from Anthropic's frontend-design skill (Apache-2.0), unslop-ui-skill (MIT), avoid-ai-design (MIT) and anti-slop (MIT). For this site, the rules that matter most:

1. **The product's own artifact leads,** not a marketing hero: the first screen is the campus list, and then the map or plan.
2. **A real name as a plain wordmark.** No "The X Map", no tagline, no middot strings.
3. **Type:** one or two deliberate faces. Not Inter, Roboto, Geist or the Space Grotesk / Instrument Serif set. Numbers in plans and tables use tabular figures.
4. **Color:** a few named colors chosen for this product, with one accent used sparingly. No gradients, glass or purple; not cream and terracotta. Body text near-black. Light by default.
5. **Components:**
   - cards only for real separate objects, never nested;
   - a mix of square and rounded corners;
   - borders instead of identical soft shadows.
6. **Copy:**
   - sentence case;
   - buttons name the action ("Add to plan", "Share this plan");
   - no puffery or em-dash labels;
   - empty screens say what to do next.
7. **Motion:** only in answer to a click. No fade-ins, and reduced motion is respected.
8. **Process:**
   - write a one-page design brief (colors, type, layout) first;
   - mock up 3 clearly different directions as screenshots for Andrew to pick from;
   - check the chosen one with the "silhouette test" (could this be anyone's site?) and the checklist;
   - add an automatic scan in CI.
9. **No UC logos, seals or campus marks** (trademarks). Plain campus names only, and "unofficial" said once, in About.

## Architecture

```
pipeline/
  common/        schema, the prerequisite tree format, graph building (moved from today's scripts)
  campuses/
    ucsb/        fetch.py + parse rules (today's code, moved)
    ucsd/        fetch.py + parse rules
    ...
  build_site.py  builds site/data/<campus>/... for every campus that's ready
site/
  index.html     the campus list, then the app
  data/<campus>/ courses, prerequisite trees, programs, credit tables
  <campus>/course/<code>.html   one static page per course, for search engines
  sitemap.xml
```

- **One shared course format,** so the map, planner and credit code don't care which campus the data came from. Only the fetcher and the prerequisite-sentence rules differ per campus.
- **Term system per campus:** quarters everywhere except Berkeley and Merced (semesters). The planner grid reads this from the campus's settings.
- **AP credit tables per campus:** each UC publishes its own.

## Quality bar (a campus ships only when it passes)

1. **Parser accuracy:** at least 95% of a hand-checked sample of 300 courses parse into the right prerequisite tree. The sample is in the repo, as UCSB's `test_labels.json` is today.
2. **Data checks:** like today's `test_graph.py` (30,000+ checks), run per campus.
3. **Browser checks for the campus flow:**
   - pick a campus;
   - switch campus without losing plans;
   - old links redirect;
   - share links;
   - phone width.
4. **The UCSB checks keep passing** (1,563 today), so nothing gets worse for existing users.
5. **Review rounds after each phase:** correctness, dead code, security, design checklist, and an independent review.

## Phases

| Phase | What | Done when |
|---|---|---|
| 0 | Design brief, 3 directions, Andrew picks one | Picked direction written down |
| 1 | Campus-first shell; UCSB moved under `/ucsb/` with the new design | All UCSB checks pass; old links redirect |
| 2 | UCSD: courses and prerequisites, then majors | Quality bar met |
| 3 | UCLA: same | Quality bar met |
| 4 | Static course pages + sitemap for every ready campus | Pages validate, sitemap submitted |
| 5 | Remaining campuses, in the order their data proves readable | Quality bar per campus |
| 6 | Transfer view: which community college courses count (ASSIST) | Only after checking ASSIST's terms |

## Risks

- **Catalog terms of use:** each catalog is read the way its own site loads it, politely (cached, a few requests), and attributed. Check each campus's terms before shipping it.
- **Catalogs change yearly:** the pipeline runs each year, and checks fail loudly if a format changes.
- **Accuracy:** wrong prerequisites hurt students. That's why there's a quality bar per campus, links to the official catalog everywhere, and "unofficial" in About.
- **Scope:** nine campuses is a lot. Phases ship one campus at a time; a campus that isn't ready shows "coming", never a half-working map.

## Decisions (Andrew, 2026-11-27)

1. **Repository:** grow `ucsb-prereq-map`, on a branch (`all-uc`). Rename later if wanted.
2. **Name:** decided later. The mock-ups use a placeholder, and Andrew picks when he sees them.
3. **Campus order:** UCSB, then UCSD, then UCLA.
4. **Majors on new campuses:** courses and prerequisite maps first; majors later.
5. **Design:** direction C, "Timetable" (Andrew asked for my recommendation). See `docs/design-brief.md`.
6. **Catalog text:** publish titles and descriptions for every campus, as for UCSB today. Andrew accepted the risk under UCSD's terms (a takedown request is possible; if one comes, fall back to codes and links only).

## UCSD research (2026-11-27)

- **Data:** no API or feed. 85 static department pages (`catalog.ucsd.edu/courses/<DEPT>.html`), about 86 requests per run. Each course is a `p.course-name` + `p.course-descriptions` pair; prerequisites follow the text "Prerequisites:". Quarters offered are never stated.
- **Parser differences from UCSB:** "or" binds tighter than "and" by default; bare numbers carry the subject forward ("ECON 1 or 100B"); ranges ("CHEM 6A-B-C"); enrollment comments run on after the prerequisites; new phrasings (corequisites, "none.", "two courses out of", placement exams, "with a grade of C– or better").
- **Majors:** prose and lists, several majors per page, tag-based electives. Harder than UCSB.
- **Blocker for Andrew:** ucsd.edu's terms forbid copying or republishing site material without explicit permission (one personal copy excepted). ucsd.edu's robots.txt disallows `/catalog/` on its main host; catalog.ucsd.edu has no robots.txt. Before UCSD ships, decide: ask UCSD for permission, or publish only prerequisite structure (codes and links, no titles or descriptions). The same check applies to UCLA.

## Phase 1 work plan

Decisions I made (simplest option that fits the plan):

- **Addresses:** `#ucsb/economics-ba/ECON+10A` (map) and `#ucsb/plan/economics-ba/<packed plan>` (plan). An address with no campus in front is an old UCSB link: it opens as UCSB and the address is rewritten in place (no extra Back step).
- **Campus screen:** shows for `#campus`, and for an empty address when no campus is remembered. With a remembered campus, an empty address opens that campus's home page.
- **Changing campus** reloads the page, so no data from one campus can leak into another.
- **Data:** `site/data/ucsb/` (was `site/data/`). The campus list is a constant in `site/campus.js` (no extra request).
- **Storage:** keys `prereq.ucsb.taken`, `prereq.ucsb.credit`, `prereq.ucsb.plan`, and `prereq.campus`. On first load, values under the old `ucsb-prereq-map.*` keys are copied over (and left in place, so going back to an old version loses nothing).
- **Single-file copy:** UCSB only. No campus screen and no "change" link.
- **Pipeline:** only the output folder changes now (`site/data/ucsb/`). Splitting the code into `common/` and `campuses/ucsb/` waits for Phase 2, when a second campus shows which parts are really shared.
- **Name:** "Prereq" is a placeholder in one place. This branch must not reach `main` until Andrew picks the name.

Steps, each ending with all checks passing (`test_graph.py`, `test_site.py`, single file):
1. Campus-aware data paths, addresses, storage and old-link handling.
2. The campus screen (direction C).
3. Restyle the whole site to direction C (`docs/design-brief.md`).
4. Browser checks for the new flow: pick, switch, old links, per-campus storage, phone width.
5. Review rounds: correctness, dead code, security, design checklist, then an independent review.

## Phase 2 work plan: UC San Diego, courses first

UCSD has no majors at first (Andrew's call: courses first). So its "programs" are **departments**: one map per department, with every course in it in prerequisite order, plus the courses from other departments they need. The planner works the same way (add courses by hand); "Auto-fill" is off for departments, since a department isn't a list of requirements.

Steps, each checked before the next:
1. **Fetch** (`pipeline/campuses/ucsd/fetch.py`): the course index and every department page, saved to `data/ucsd/raw/`. One request a second, a plain user agent, and a page already saved isn't fetched again.
2. **Extract** (`pipeline/campuses/ucsd/extract.py`): each course's code, title, units, level, description and prerequisite text, into `data/ucsd/raw_courses.json`. Cross-listed courses appear on several pages: kept once, under each code. Enrollment comments after the prerequisites ("restricted to…", "students may not receive credit…") are split off as notes.
3. **Label first:** 300 courses chosen at random (fixed seed, spread over departments), with the correct prerequisite tree typed by hand into `tests/ucsd_labels.json`, *before* tuning the parser, so the score is honest.
4. **Parse** with the shared parser (`pipeline/parser.py`), given UCSD's subject codes and a few UCSD rules (en-dash grades "C–", "MATH 20 C", ranges "CHEM 6A-B-C", "Corequisite(s):", "none."). Score on the labels; ship only at 95% or better. Courses the parser can't read with confidence keep the catalog's own words on screen, as at UCSB.
5. **Build** `site/data/ucsd/`: one graph per department, the course index, and an empty credit table (UCSD's AP chart comes later).
6. **Site:** "departments" wording where UCSB says "majors and minors"; mark UCSD "Ready" in `campus.js`.
7. **Checks:** data checks per campus (`test_graph.py` loops over campuses), browser checks for a UCSD department map and plan, then the review rounds.

The pipeline split into `pipeline/common/` and `pipeline/campuses/<id>/` happens in step 4, once it's clear which parts both campuses use.

### UCSD parser scores (2026-11-27)

| Group | Courses | Exactly right | Note |
|---|---|---|---|
| final (first honest score) | 100 | 84 | parser frozen in c35e32e; misses then used |
| final2 (second honest score) | 100 | 85 (82% random, 91% major) | parser frozen in 6e241c7; labels kept exactly as written |
| final3 (third honest score) | 100 | 91 (91% random, 91% major) | double-labeled (labelers agreed on all 100); parser frozen in fb24dd6 |
| final4 (fourth honest score) | 100 | 90 (88% random, 94% major) | double-labeled (agreed on all 100); parser frozen in c954c01 |
| final5 (fifth honest score) | 100 | 94 (94% random, 94% major) | double-labeled (agreed on all 100); parser frozen in 9c12166 |
| final6 (sixth honest score) | 100 | **97** (96% random, 100% major); 93/96 without 4 courses seen in sweeps | double-labeled (agreed on all 100); parser frozen in dcd6420 |
| UCSB, for comparison | 150 | 89% random, 96% major | its own "final" group |

The 95% bar is met: the latest honest score is 97% (96.9% without the four courses seen earlier). Marking UCSD "Ready" is Andrew's call. Most remaining misses are long-tail phrasings ("PHYS 2A/2AR-B-C-D", "POLI 5(D)", "previous course") and two readings where labelers differ (whether "or consent of instructor" covers only its own sentence).

## UCSD completion plan: offerings, AP credit, majors (2026-11-27)

"Ready" means changing UCSD's status in `site/campus.js` from "next" to "ready", so it can be picked on the campus screen without `?preview`. Andrew's rule: it's ready when a review pass finds nothing left to really improve. **Marked ready on 2026-11-28** after that pass (Auto-fill completes 169 of 180 majors; the 10 left each require a course the 2026–27 catalog doesn't list; every map opens without errors). Nothing is public until `all-uc` is merged to `main`.

### 1. When each course is offered
- **Source:** UCSD's Schedule of Classes (act.ucsd.edu, robots.txt allows it). The catalog states quarters for only 76 courses.
- **Method:** `pipeline/campuses/ucsd/fetch_offerings.py` searches one subject at a time for each of the last two academic years' quarters (FA24–SP26) plus summer 2025, with a 1-second pause, a plain user agent, and saved pages so it can resume. `extract_offerings.py` records each course's quarters; a course is "offered" in a quarter it ran in either year.
- **Checks:** counts per term look plausible; spot-check 10 well-known courses (CSE 8A, MATH 20A …) by hand; the planner's "assumed" marker disappears for courses with data.

### 2. AP credit chart
- **Source:** the catalog's PDF, `_files/advanced-placement-credit-chart-2026.pdf`. Only the second column ("UC San Diego course exemptions, for use on major") matters for prerequisites; college GE columns are left out.
- **Method:** pdftotext gives the column text; it's typed into `data/ucsd/ap_credit.json` in UCSB's format (exam, scores, units, equivalent courses), as UCSB's was. `build_credit.py --campus ucsd` checks every code against the catalog and writes `site/data/ucsd/credit.json`.
- **Checks:** every equivalent is a real course; a second pass compares each exam row with the PDF text; browser check that the Credit box shows UCSD's chart.

### 3. Majors
- **Source:** the catalog's undergraduate program pages (`curric/<DEPT>-ug.html`), about 70 pages, several majors each, written as prose and lists.
- **Method:** per major, translate the requirements into UCSB's requirement format (all / choose N / units / course / text), and keep the catalog's prose as notes. Each major is translated twice, independently, from the page text; differences are settled from the text. Every code must exist in the catalog; anything that can't be expressed stays as a text item, never dropped.
- **Checks:** program file validation (codes, counts possible); data checks on the built graphs; a sample of majors compared by hand against the catalog page; browser checks for a UCSD major map and plan (with Auto-fill).
- **Site:** UCSD lists majors (and keeps department maps for browsing courses).

Order: offerings fetch runs in the background (slow but simple) while the AP chart is typed, then majors.

**Done (2026-11-27):** AP chart (40 exams); offerings from the Schedule of Classes (3,128 of 4,655 courses have quarters); 180 majors, each translated twice and the 90 that differed reconciled from the page text (see data/ucsd/majors/README.md, which lists the questions a person should check). The map now treats "placement exam, or MATH 4C" as a course you can start with, so calculus is in the first step. What's left before "Ready": Andrew's call.

## UCLA plan (2026-11-28)

Sources (surveyed and fetched 2026-11-28; robots.txt allows the catalog):
- **Catalog:** CourseLoop, with an open JSON endpoint on the catalog's own site (`/api/content/academic-item-content?siteId=ucla-prod-pres&path=/course/2026/COMSCI31&siteYear=current`). The sitemap lists every course and major page. `pipeline/campuses/ucla/fetch.py` saves each record (gitignored raw folder).
- **Prerequisites:** prose inside each course description ("Enforced requisite: course 31", "Requisites: Mathematics 31B, 32A"): "course 31" means the same subject, other subjects are spelled out ("Mathematics"), mapped to codes from the Schedule of Classes' subject list.
- **Majors:** 145 undergraduate majors, each a tree of rule groups with a verb line ("Select one course from", "Complete 12 courses") and a course list. 2,587 groups; 320 are prose only ("seven courses from Computer Science 100 through CM187 except …").
- **When offered:** Schedule of Classes (`sa.ucla.edu/ro/Public/SOC/Results?t=25F&sBy=subject&subj=COM+SCI`), past terms answer too; HTML only.
- **AP credit:** one HTML table set per school (The College, Engineering, Arts and Architecture, Nursing, Theater Film and Television); they differ.

Steps:
1. Fetch courses and majors. *(running)*
2. Extract undergraduate courses (`course_level` lower/upper division); requisite text out of the description.
3. Prerequisite parser rules for UCLA's wording; measure on a labeled sample (same method as UCSD: tuning set, then held-out sets double-labeled; bar 95%).
4. Majors: convert the rule groups directly; translate the 320 prose groups (two passes, compared, reconciled, as for UCSD); audit a random sample.
5. When offered: Schedule of Classes for the last two years.
6. AP chart: The College's table as the default; where Engineering's differs, its majors use Engineering's.
7. Site: campus details, transcript (UCLA's MyUCLA "Academic History" if a sample exists), checks; Auto-fill sweep; review pass until nothing is left to improve; then ready.

## Next campuses: survey (2026-11-28)

Fetched from here unless marked otherwise.
- **UC Irvine:** official catalogue (CourseLeaf) reset connections from here. The student-run Anteater API (anteaterapi.com) serves prerequisite text and trees, structured major trees (some dated 2023-24), terms offered back to 2006, and an AP table. Risk: third-party; cross-check against the official catalogue.
- **UC Berkeley:** Coursedog, like UCSB, with structured requisites and major rules; listing every course needs the same headers UCSB's fetcher sends (untested); schedule (classes.berkeley.edu) blocked from here and disallows /search/ in robots.txt; AP fragmented; semesters.
- **UC Santa Cruz:** SmartCatalog (HTML, with a JSON page tree of the whole catalog); majors as "All of the following / one of the following" tables; class search back to 2004 (HTML form); AP tables on degreeprogress.ucsc.edu.
- **UC Riverside:** catalog and majors only as a 653-page PDF; Banner 9 JSON schedule with structured prerequisites.
- **UC Davis:** nothing reachable from here (connection resets, 403).
- **UC Merced:** Acalog behind a WAF challenge; Banner 9 schedule.

Order after UCLA: Irvine (if the Anteater data checks out against the official catalogue), then Berkeley, then Santa Cruz.

Irvine check (2026-11-28): the official catalogue (catalogue.uci.edu) still refuses automated requests (503), but the Registrar's prerequisite pages (www.reg.uci.edu/cob/prrqcgi, `?dept=CBE&action=view_all`) answer, with each course's enforced prerequisites as structured AND/OR text with minimum grades. A sample of 8 Anteater courses: the 5 listed by the Registrar match exactly; 3 aren't listed there (no enforced prerequisite, or an older department code). Anteater's major records are for 2026-27. Plan for Irvine: prerequisites from the Registrar (official), course titles, units, descriptions and terms offered from Anteater, majors from Anteater's structured requirement trees.
