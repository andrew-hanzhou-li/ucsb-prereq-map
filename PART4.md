# Part 4 — The graph

**Status:** done. `build_graph.py` joins each major (Part 3) with course prerequisites (Part 2) and writes one ready-to-draw file per major into `site/data/`. It covers all 135 majors and takes about a second to run. `test_graph.py` runs 25,770 checks; all pass. Along the way, the checks found two real parser bugs, both now fixed.

## What a graph file contains

`site/data/economics-ba.json` has four parts:

| Part | What it is | Economics |
|---|---|---|
| `nodes` | one per course, with its column | 77 major courses + 14 outside |
| `edges` | one arrow per prerequisite | 156 |
| `pools` | huge elective lists, kept as one box | 0 |
| `major` | the requirement tree from Part 3, for the side panel | |

Each **node** has: `id`, `title`, `units`, `status` (active / inactive), `in_major`, `role`, `groups` (which requirement it counts for), `column`, `prereq_text`, `requires` (the Part 2 tree), `ambiguous` and `description`.

The `role` field is one of:

| Role | Meaning | Example |
|---|---|---|
| `required` | you must take it | ECON 1 |
| `choice` | one of a short list of interchangeable courses | MATH 2A *or* 3A |
| `elective` | part of a "choose N" or "N units from" list | ECON area D |
| `prerequisite` | not in the major, but a major course needs it | MATH 4A for Economics |

Each **edge** has `from` (take first), `to`, `type`, `group`, `concurrent` and `min_grade`. The `type` is either:
- `required`: needed no matter what.
- `alternative`: one option in an "or". Arrows from the same "or" share a `group`, so the site can say "one of these."

## Run it (Windows)

The parser changed (see the end of this file), so rebuild Part 2's output first:

```
py build_prereqs.py
py build_graph.py
py test_graph.py
```

`build_graph.py economics-ba` builds just one major and prints its summary.

## How it works, in four steps

### 1. The major's courses

The script walks the requirement tree from Part 3 and gives each course a role.

- **`required` vs `choice`.** A course is `required` when only "complete ALL" lies between it and its section. Inside a "choose 1" of up to 4 courses, it's a `choice`. "PSTAT 120A or PSTATW 120A" is really one requirement, so those count as near-required.
- **Pools.** An elective list longer than 100 courses becomes a single box. An example is "any upper-division course in Letters & Science" (about 3,000 courses). Computer Engineering's 70-course elective list is drawn in full.

### 2. Outside prerequisites

Next, it follows prerequisites outward until nothing new appears. Economics never lists MATH 4A, but PSTAT 120A needs it, so MATH 4A joins the graph as a `prerequisite` node. Every alternative is included, because a student might take any of them.

### 3. Arrows

One edge per course in each prerequisite tree. A course that lists itself gets no arrow; some multi-part courses do this.

### 4. Columns (the interesting part)

**Column = the earliest quarter you could take the course**, counting how many quarters of prerequisites must come first.

| Prerequisite | Rule | Why |
|---|---|---|
| none | column 0 | |
| A needs B | column(B) + 1 | B takes a quarter |
| A needs B, concurrently | column(B) | same quarter is allowed |
| A needs B **and** C | **max** | you wait for the later one |
| A needs B **or** C | **min** | you take whichever comes first |

Worked example (Statistics & Data Science BS):

```
MATH 3A    no course prerequisite                  0
MATH 3B    needs 3A                     0 + 1  =   1
MATH 4A    needs 2B or 3B         min(1, 1) + 1 =   2
PSTAT 10   needs 2B or 3B                         2
MATH 6A    needs 4A                     2 + 1  =   3
PSTAT 120A needs 4A or 6A or ...  min(2, 3) + 1 =   3
PSTAT 120B needs 120A                   3 + 1  =   4
PSTAT 126  needs 10 and 120B      max(2, 4) + 1 =   5
PSTAT 131  needs 120A, 120B, 126  max(3, 4, 5) + 1 = 6
```

This is the topological-sort idea from CS 24: you can only place a course after everything it depends on. It's computed with recursion plus memoization: `ColumnFinder.of()` works out each course's column once and saves it.

**Three adjustments**, each found by looking at real output:

1. **"Or" prefers courses in the major.** MATH 4A needs "2B or 3B or 3BI." MATH 3BI is an honors course the catalog lists with no prerequisites, so pure "min" put MATH 4A one column too early. Now, alternatives that are part of the major win over outside ones.

2. **"Or consent of instructor" is ignored** when there's a course to take instead. Otherwise every "X or consent" course would sit in column 0.

3. **Upper-division floor.** Many upper-division courses list only "upper-division standing" or "majors only," with no course prerequisites. ECE 139 and ECON 145 are examples. By prerequisites alone they'd sit in column 0, next to MATH 3A. So no upper-division course goes left of the earliest required course in the major's upper-division section that has real prerequisites. In Economics that's ECON 100B, 101 and 140A (column 3); in Statistics it's PSTAT 120A (column 3). This is a **display rule, not a catalog rule**, and each file records it as `stats.upper_division_floor`.

**Lecture/lab pairs.** Labs like CH ST 162L and 162 each list the other as "concurrent enrollment," which is a loop. The recursion stops when it comes back around, so one of the pair could end up a column early. A cleanup pass then pushes every course right of each course it requires, until nothing moves.

## Cycle check

Real prerequisites can't go in a circle, so a loop means a parsing bug. Across the whole catalog there were 12 loops:

- **10 are lecture/lab pairs** that must be taken together (Chicano Studies, Political Science, Theater). They're legitimate: each side says "concurrent enrollment in the other," so they don't add a quarter. The check ignores loops made only of "concurrent" links.
- **2 were a real bug.** PSTAT 207A's text says "Part of a three quarter sequence with 207B and 207C." The parser split that on "and" and read "207C" as a requirement, so 207A needed 207C, which needed 207B, which needed 207A. The parser now treats a sentence of prose whose only course numbers have no subject as text, keeping any conditions inside it.

After the fix, all 135 majors have **no loops**.

## Tests: `test_graph.py`

1. **13 rule tests on made-up courses.** There's one per rule: chain, AND = max, OR = min, concurrent, consent ignored, major preferred, floor, loop reported, lab pair not a loop, edge types, self-arrows.
   
   To make sure these tests can actually fail, I temporarily changed OR from `min` to `max`. The OR test failed, as it should. Interestingly, the real-data checks below didn't notice, which is why both kinds of test exist.

2. **Real-data checks on all 135 majors:**
   - Every required arrow points left to right (or level, for concurrent).
   - Every arrow starts and ends at a course in the graph.
   - Node IDs are unique.
   - There are no loops.
   - Known sequences come out in order, e.g. PHYS 7A < 7B < 7C < 7D and PSTAT 120A < 120B < 120C < … < 131.
   - Each ECE 10 lecture shares a column with its lab.

**Alternative arrows can point backwards.** If a course needs "B or C" and C comes much earlier, the course sits right after C, so the arrow from B points left. That's 11% of alternative arrows. It's expected, and Part 5 should draw alternative arrows faded or only on click.

## The second parser fix

Online courses have their own subject codes, written two ways in the catalog: "CHEM W 142A" (subject `CHEM W`) but "CMPSCW 8" (subject `CMPSCW`). The parser always wrote "SUBJ W NUM," so "CMPSC W 8" matched nothing. It now uses whichever form exists. This showed up as an unknown course in the Stats graph.

Neither fix was aimed at the test set. On the final test group, the parser now scores 89% / 96% instead of 88% / 94%, but **quote 88% / 94%**: the final group already had its one clean run.

## For Part 5

The website needs only these files:
- `site/data/majors.json` for the major picker (name, file, course count).
- `site/data/<major>.json` for each map.

Graph files are 4–450 KB each, small enough to load on demand.

## Try this

```
py build_graph.py statistics-and-data-science-ba
```

Then open `site/data/statistics-and-data-science-ba.json` in VS Code. Press Ctrl+F, search for `"id":"PSTAT 126"`, and check its column and role. Ask yourself whether it's right given what you know about when people take it.
