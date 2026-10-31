# Part 2 — The prerequisite parser

**Status:** done. On 150 courses it had never seen, labeled by hand before it ran, the parser gets **90% exactly right** (88% of 100 random catalog courses, 94% of 50 ECON/PSTAT/MATH/ECE/CMPSC/PHYS courses). Counting only the course logic that draws arrows on the map, it's **95% / 94%**. The plan's target was 85%.

## What it does

It turns the catalog's English into a logic tree the website can draw.

**Before** (catalog text for PHYS 137):

```
Physics 5 or 25 or 115A with a minimum grade of C-, Physics 104 (may be taken concurrently)
```

**After** (in short notation):

```
(PHYS 5[C-] | PHYS 25[C-] | PHYS 115A[C-]) & PHYS 104*
```

That reads: one of PHYS 5, 25 or 115A with a C- or better, **and** PHYS 104, which you may take at the same time.

## Files

| File | What it is |
|---|---|
| `parser.py` | The parser. Start reading here; the top of the file explains the whole approach. |
| `subjects.py` | Table of the ways departments are written ("Mathematics", "Math") → official code (MATH). |
| `notation.py` | The one-line notation above: tree → text and text → tree. Used by tests and overrides. |
| `build_prereqs.py` | Parses all 7,948 courses and writes `prereqs.json` (what Part 4 reads). |
| `measure.py` | Scores the parser against the hand-labeled answers. |
| `test_labels.json` | 450 hand-labeled answers (see "How it was tested"). |
| `overrides.json` | 8 hand corrections for text the parser gets wrong. |

Put these in the same folder as `fetch.py` and `raw_courses.json` from Part 1.

## Run it (Windows)

```
py build_prereqs.py
py measure.py --quiet
py measure.py final
```

1. `build_prereqs.py` should print 7,948 courses, 6,214 with text, 2,462 requiring at least one course, and "Wrote prereqs.json".
2. `measure.py --quiet` prints the score table.
3. `measure.py final` also prints every miss, with the text, the right answer and what the parser said.

Everything uses only Python's standard library.

## How it works

### The tree

Every answer is built from four kinds of pieces:

| Piece | Example | Meaning |
|---|---|---|
| course | `{"type": "course", "code": "PHYS 104", "concurrent": true, "min_grade": null}` | one course, with its flags |
| condition | `{"type": "condition", "kind": "restriction", "text": "open to EE majors only"}` | anything that isn't a course |
| and | `{"type": "and", "items": [...]}` | need all of these |
| or | `{"type": "or", "items": [...]}` | need one of these |

Condition kinds: `standing` (upper-division, graduate…), `consent` (instructor or department approval), `restriction` (majors only, admission to a program), `exam` (AP/IB scores), `other` (everything else, with the original words kept).

### The three passes, traced on PHYS 137

**Pass 1 — Protect.** Some phrases contain "or", "and" or commas but are one unit. If we split first, "a grade of C **or** better" would become two alternatives. So these phrases get swapped for placeholders, and department names become codes:

```
Physics 5 or 25 or 115A with a minimum grade of C-, Physics 104 (may be taken concurrently)
PHYS 5 or 25 or 115A §a§ , PHYS 104 §b§

§a§ = grade C-
§b§ = may be taken concurrently
```

Doing department names here matters too: "Film **and** Media Studies 96" would otherwise be split on its "and."

**Pass 2 — Split, biggest separator first.** Each level becomes one layer of the tree:

| Level | Split on | How the pieces join |
|---|---|---|
| sentences | `.` | AND |
| clauses | `;` | AND, but a clause starting with "or" begins a new alternative |
| segments | `,` | list rules (below) |
| words | `or`, `and`, `/` | "or" groups before "and": "A or B and C" = (A or B) and C |
| atoms | — | one course, a sequence like `113A-B-C`, or a condition |

PHYS 137 has one sentence, one clause, and two comma segments:

```
segment 1:  PHYS 5 or 25 or 115A §a§     ->  PHYS 5 | PHYS 25 | PHYS 115A
segment 2:  PHYS 104 §b§                 ->  PHYS 104
joined:     no "and"/"or" after the comma, so AND
```

The bare "25" becomes PHYS 25 because the parser remembers the last subject it saw.

**Pass 3 — Apply markers.** Each placeholder attaches to the courses it describes. `§a§` sits in segment 1, so all three courses there get C-. `§b§` sits in segment 2, so only PHYS 104 is concurrent.

### Comma list rules

| Text | Reading | Why |
|---|---|---|
| `A, B, and C` | A and B and C | the last connector covers the list |
| `A, B, or C` | A or B or C | same |
| `A or B, and C` | (A or B) and C | the comma separates groups |
| `PHYS 3, 7B or 23` | PHYS 3 or 7B or 23 | single items + one connector = one list |
| `CHEM 142A or W142A, 142B-C` | (142A or W142A) and 142B and 142C | no connector after the comma = AND |

### How far a marker reaches (scope rules)

| Marker | Where it sits | Reaches |
|---|---|---|
| grade | in a middle comma segment | that segment |
| grade | in the clause's last segment ("A, B, and C with a C") | the whole clause |
| grade with "each/all/both" | anywhere | everything before it in the sentence, but not across "; or" |
| grade | its own sentence ("Completion of all listed prerequisites with a grade of C") | every course |
| "(may be taken concurrently)" | after a course or group | that segment |
| "(MCDB 108C may be taken concurrently)" | names a course | only that course |
| "Concurrent enrollment in …" | before the courses | the whole clause |
| "open to … majors only" | after "; or" alternatives | all alternatives |

### Smaller rules worth knowing

- **Slash.** `MATH 2A/3A` means 2A or 3A. But `PHYS 5/PHYS 5L` is a lecture and its lab, so when the second course is the first one plus "L", slash means AND.
- **Sequences.** `113A-B-C` → 113A, 113B, 113C. `1A-C` → 1A, 1B, 1C. `172-172L` → 172, 172L. `Italian 1-6` → ITAL 1 through 6.
- **"Recommended"** sentences become text, not requirements, so they don't draw arrows.
- **Prose that mentions a course** ("taken with the instructor for EACS 199") becomes text, not a requirement.
- **Nothing is dropped silently.** Text with no course becomes an `other` condition holding its words. Leftover words next to a course go in `unparsed` (66 courses).
- **Ambiguity is flagged.** 121 courses mix "and" and "or" with no punctuation, where the grouping is a guess. They're marked `"ambiguous": true` so you can review them for your 3 majors.

## How it was tested

The key idea: **a parser can't be graded on the examples used to build it.** While writing rules, I read those examples, so the rules fit them. The score on them says nothing about new text. (Same reason you can't study from the exam.)

So there are three groups of 150 courses in `test_labels.json`. Each has 100 random courses with prerequisite text and 50 random lower/upper-division courses from your majors' departments. Every answer was written by hand, before the parser ran on that group.

| Group | Role | Exactly right | Course logic right |
|---|---|---|---|
| tuning | Rules were written while reading these | 98% / 98% | 98% / 98% |
| heldout | First run: 87% / 80%. Then I fixed bugs it exposed, so it's no longer clean | 97% / 96% | 97% / 96% |
| **final** | **Labeled after the parser was frozen, scored once** | **88% / 94%** | **95% / 94%** |

(Each cell is random set / major-department set.)

The heldout row is the honest story of the process: the first unseen number (87% / 80%) was much lower than the tuning number, which is what you'd expect. Fixing its misses lifted it but used up its value as a test, which is why the final group exists.

**What the 15 final misses were:**

- 7: a condition labeled `other` where `restriction` was right ("honors standing", "Must be admitted to the Professional Writing Minor"). No effect on the map.
- 3: one condition read as two, or two as one (e.g. "instructor and departmental approval required" became consent plus an `other`). No effect on the map.
- 2: catalog typos with missing spaces ("performance inEconomics 1 and 2", "minimum3.0").
- 1: an "and"/"or" mix with no punctuation (`ECE 10C and 10CL or 2C`), flagged ambiguous.
- 1: a concurrency phrase whose reach is unclear (`Physics 29 and Physics 23 (may be taken concurrently)`).
- 1: a real bug (EEMB 157A, below).

## Overrides

`overrides.json` holds hand answers for courses the parser gets wrong, written in the short notation. Each one records the catalog text it was written for. If the catalog changes that text next year, `build_prereqs.py` warns you instead of applying an outdated answer.

The plan's rule: fix the parser when a mistake is a pattern; use an override when it's a one-off. When you check your 3 majors in Part 3, add an override for any wrong course you find.

## Your first change: fix the EEMB 157A bug

Doing this once will teach you the code faster than reading it.

**The bug.** EEMB 157A's text is `MCDB 1A, and EEMB 2 and MCDB 1B, and EEMB 3; Completion of all listed prerequisites with a grade of C- or better.` The grade should reach all four courses, but the parser gives none of them a grade, and adds an `other` condition.

**Why.** The rule "a grade with no courses spreads to every course" is in `Parser.parse()`, and it only runs for a separate **sentence**. Here the catalog used a semicolon instead of a period, so that text is a **clause**, handled in `parse_sentence()`.

**Steps:**

1. Run `py measure.py final` and find EEMB 157A in the misses.
2. In `parse_sentence()`, after a clause is parsed, check whether it has no courses but does have a grade (`self.grade_in(clause)` finds it). If so, apply it to `nodes_so_far` with `set_grade`, and don't add the clause's `other` node.
3. Rerun `py measure.py`. EEMB 157A should pass and nothing else should break.

That last check is the whole point of the test set: any change you make, you rerun and see immediately whether it helped or hurt.

## For Part 4

- `prereqs.json` references 188 courses that aren't in the current catalog (old or renamed, e.g. CHEM 107A). Part 4 can show them as grey "inactive" boxes or skip them.
- A few courses list themselves (FEMST 195HA requires FEMST 195HA, a multi-part course). Drop self-arrows before the cycle check.
- Only `course` pieces become arrows. `condition` pieces go in the side panel as text.

## The 2-minute version (for interviews)

1. **Problem.** UCSB's catalog writes prerequisites as free English, with dozens of phrasings for the same thing.
2. **Approach.** A three-pass parser: protect phrases that contain "and/or," split from the biggest separator to the smallest, then attach grades and concurrency by scope rules.
3. **Measurement.** 450 hand-labeled courses in three groups, including a final group labeled after the code was frozen. 90% exactly right on that group, 95% on the course logic.
4. **What I learned.** My accuracy on examples I'd seen was 98%; on the first new set it was about 85%. Testing on data you didn't tune on is the difference between a real number and a flattering one.
5. **Next.** Ambiguous "and/or" cases are flagged for review instead of guessed silently.

## Changes after Part 2 (made during Part 4)

Part 4's checks found two parser bugs, which are now fixed. See `PART4.md` for details.

1. "Part of a three quarter sequence with 207B and 207C" was read as a requirement on PSTAT 207C, which created a loop (207A needs 207C, which needs 207A).
2. Online course codes were written "CMPSC W 8" instead of the catalog's "CMPSCW 8".

Rerunning `py measure.py` now gives 89% / 96% on the final group. Quote the original **88% / 94%**: the final group was already used once, so later scores on it are no longer a clean test.
