# Part 3 — Major requirements

**Status:** done, and it went further than planned. The plan was to hand-write 3 major files. Instead, the catalog turned out to store major requirements as structured data, so a script converts **all 135 bachelor's degrees that have structured requirements**. Your four (Economics BA, Statistics & Data Science BA and BS, Computer Engineering BS) were checked against the live catalog pages and match.

## The key finding

Part 2 was hard because course prerequisites are free English. Major requirements are different. When you open a major's "Program Requirements" tab, the catalog downloads rules like this (Economics area D):

```json
{"condition": "completedAtLeastXOf", "restriction": 6,
 "value": {"condition": "courses", "values": [
     {"value": ["ECON 100C"], "logic": "and"},
     {"value": ["ECON 106"],  "logic": "and"}, ...]}}
```

That already means "complete at least 6 of these courses." So Part 3 doesn't parse anything. It **translates** the catalog's rule types into a smaller set of our own, and fills in a few gaps.

| | Part 2 (prerequisites) | Part 3 (majors) |
|---|---|---|
| Source | free English | structured rules |
| Main job | parsing | translating + verifying |
| Hard part | ambiguity | gaps the structure can't express |
| How it's checked | 450 hand-labeled courses | comparing to the live catalog pages |

That contrast is worth saying in an interview: you looked for structure before writing a parser, and found it.

## Files

| File | What it is |
|---|---|
| `fetch_programs.py` | Downloads every program and its rules → `raw_programs.json` |
| `raw_programs.json` | All 606 catalog programs (majors, minors, grad degrees), as downloaded |
| `build_majors.py` | Converts the rules → one file per bachelor's degree in `majors/` |
| `program_overrides.json` | 4 hand corrections for rules the catalog only states in notes |
| `majors/*.json` | 135 major files, e.g. `majors/economics-ba.json` |
| `majors/index.json` | List of every bachelor's degree, for the site's major picker |
| `show_major.py` | Prints a major as a readable outline, to check by eye |

## Run it (Windows)

Put everything in your project folder, next to `raw_courses.json`. The `majors` folder goes in as a folder.

```
py build_majors.py
py show_major.py economics-ba
py show_major.py --list
```

`build_majors.py` should print 233 bachelor's programs, 135 with structured requirements, and 7 unresolved catalog IDs (none in your majors; see Known limits). `raw_programs.json` is included, so you don't need to download anything. To refresh it for a new catalog year, run `py fetch_programs.py` (about 30 requests, one per second).

## How the data is downloaded

`fetch_programs.py` sends the same three kinds of requests the catalog website sends:

1. **Programs.** Every program with its rules. Two requests of 400.
2. **Course lists.** Some rules say "16 units from *Upper Division Statistics Courses*" and refer to that list by an ID. There are 79 such lists, downloaded 20 at a time.
3. **Course IDs.** Some rules name a course by an internal ID (`3bqcxdGsNgF83jgVOQYD`) instead of its code. We look up all 526 and get back codes (`PHYS 7A`) for 508 of them. In your four majors, these were PHYS 7A–7D, PHYS 7L, CMPSC 41, ECE 157C, ECE 184, ECON 157 and ECON 187.

I found these endpoints the same way as Part 1: by opening the catalog in a browser and watching which requests it makes.

## How the rules are translated

The catalog uses 8 rule types. They map onto 5 of ours:

| Catalog rule | Ours | Example |
|---|---|---|
| `completedAllOf` | `all` | Pre-major: ECON 1, 2, 10A |
| `completedAnyOf` | `choose`, count 1 | ECON 5 or PSTAT 120A |
| `completedAtLeastXOf` | `choose`, count X | 6 of the area D electives |
| `minimumCredits` | `units` | 36 units of CE electives |
| `allOf` / `anyOf` | `all` / `choose` over sub-rules | Stats BS areas A–D |
| `freeformText` | `text` | "Level 1-6 of a language other than English" |

Inside a rule, each entry is a group of courses joined by `and` (a sequence: MATH 2A **and** 2B) or `or` (CMPSC 9 **or** 16). Single courses become `course` nodes.

**Course status.** Each course is marked:
- `active`: in the current course list.
- `inactive`: named in the major but not currently offered. Economics has 14 of these (e.g. ECON 141, 112B); the catalog marks them "hibernated." Part 4 can show them greyed out.

**Named course lists** are defined by a rule like "PSTAT, numbered 100–199." The catalog's stored copy of each list also includes every old course that ever matched, so we keep only courses in the current course list.

## The hand corrections

Some rules exist only as a sentence in a note, which the structured data can't express. `program_overrides.json` handles these, each with the catalog quote it comes from:

1. **Economics area D:** the note says "ECON 191AA-ZZ," so ECON 191D and 191M are added.
2. **Computer Engineering electives:** "ECE 194AA-ZZ (except 194R)" adds 10 lettered ECE 194 courses.
3. **Statistics & Data Science BA and BS:** "These courses will NOT apply to the major: PSTAT 109, 182T, 188, 190, 193." The catalog's own list includes some of them, so they're removed.

Overrides point at a rule by its catalog ID. If the catalog changes and the ID disappears, `build_majors.py` prints a warning instead of applying the correction silently.

## How it was checked

1. **Every course reference resolves, with 7 exceptions.** Across all 135 majors, only 7 course references (in 5 majors) point to IDs the catalog's own API can't look up. None are in your four majors. My first version of `build_majors.py` reported 0 here because of a counting bug: it skipped courses with no code. Checking the number against the download log caught it.

2. **Compared against 12 live catalog pages.** For your 4 majors plus 8 random others, I loaded each major's Program Requirements page and extracted every course code shown, then compared it to our file. **All 12 match.** Two kinds of apparent mismatch turned out not to be errors:
   - **Courses shown without a title** (ECON 181, a few CHEM labs) were missed by my first comparison script.
   - **Course codes that appear only inside a note.** One example is the Stats "will NOT apply" list. Another is a list of extra electives in Zoology's area E note, which is a plain paragraph on the page, not a rule. These are notes, not requirements, and our files keep them as note text.

3. **The "at least N" and "N units" numbers match the pages** for all 12.

4. **Your Stats list, checked against the course catalog.** The expanded "Upper Division Statistics Courses" list contains every current PSTAT 100–199 course except the 4 excluded by the override, and PSTAT 133 (see below).

## Known limits

- **98 of 233 bachelor's programs have no structured requirements.** Their catalog pages describe requirements only in paragraphs. They're listed in `majors/index.json` with `"structured": false` and no file. Converting those would need a Part-2-style parser, so they're a post-launch job.
- **Rules that live in notes are kept as notes, not logic.** Examples:
  - CE electives "must include at least 2 sequences."
  - Econ area E courses need ECON 3A-B.
  - "A maximum of 4 units of Economics 199."
  
  These show up in the side panel as text.
- **7 unresolved course references** in Anthropology (Archaeology and Cultural emphases), Artificial Intelligence BS, English BA and Theater BA. The catalog's API returns nothing for those IDs even with date filtering off. They're kept as `"status": "unresolved"` with the ID, so the site can show "unknown course" instead of silently dropping them.
- **PSTAT 133 is missing from the catalog's Upper Division Statistics list,** even though it matches the list's own rule. I left it out, since the catalog does. Worth asking a PSTAT advisor.
- **Section names are copied exactly,** including the catalog's typo "UUPPER-DIVISION MAJOR" in Economics.

## What Part 4 will use

From each major file:
- `sections` → the requirement tree, for the side panel and the legend colors (pre-major, preparation, upper-division).
- `courses` → every course in the major, once, with its status and section. These become the map's boxes.

Part 4 then joins those courses with `prereqs.json` from Part 2 to draw the arrows and compute the columns.

## Try this

Run `py show_major.py statistics-and-data-science-bs` and compare it to [the catalog page](https://catalog.ucsb.edu/programs/BSSTSDS). You know this major better than any script does, so if anything looks wrong, that's a real bug worth fixing.
