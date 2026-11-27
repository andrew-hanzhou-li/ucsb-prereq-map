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

## UCSD research (2026-11-27)

- **Data:** no API or feed. 85 static department pages (`catalog.ucsd.edu/courses/<DEPT>.html`), about 86 requests per run. Each course is a `p.course-name` + `p.course-descriptions` pair; prerequisites follow the text "Prerequisites:". Quarters offered are never stated.
- **Parser differences from UCSB:** "or" binds tighter than "and" by default; bare numbers carry the subject forward ("ECON 1 or 100B"); ranges ("CHEM 6A-B-C"); enrollment comments run on after the prerequisites; new phrasings (corequisites, "none.", "two courses out of", placement exams, "with a grade of C– or better").
- **Majors:** prose and lists, several majors per page, tag-based electives. Harder than UCSB.
- **Blocker for Andrew:** ucsd.edu's terms forbid copying or republishing site material without explicit permission (one personal copy excepted). ucsd.edu's robots.txt disallows `/catalog/` on its main host; catalog.ucsd.edu has no robots.txt. Before UCSD ships, decide: ask UCSD for permission, or publish only prerequisite structure (codes and links, no titles or descriptions). The same check applies to UCLA.
