# UC San Diego majors

One file per undergraduate major (with each specialization that has its own
requirements), translated from the 2026–27 UC San Diego General Catalog's
program pages (`https://catalog.ucsd.edu/curric/<DEPT>-ug.html`).
`pipeline/campuses/ucsd/build_majors.py` turns them into the site's program files.

## Why by hand

UCSD's catalog states major requirements as prose ("twelve upper-division
courses, at least four of which must be…"), not as structured data, so no
parser reads them reliably. Each major was translated into requirement nodes
by following a written set of reading rules.

## How they were checked

1. **Two independent translations.** Every program page was translated twice,
   by two translators who did not see each other's work.
2. **Compare.** The two versions were compared rule by rule (course codes,
   `choose` counts, units, grouping). 90 of 180 majors agreed; those files are
   the first translation.
3. **Reconcile.** For the other 90, a third reader went through each
   difference against the page text and wrote the version the page supports.
   Where two pages describe the same major (e.g. Computer Engineering on the
   CSE and ECE pages), the offering department's page is followed and the
   other page's differences are noted in `narrative`.

4. **Audit.** Two random samples of 24 majors each were checked line by
   line against the catalog by a reader who hadn't seen the translations:
   467 of 475 requirements right in the first, 572 of 577 in the second
   (after the fixes the first one prompted). Each error that would mislead
   a student was fixed.

The site counts each course toward one requirement (narrowest group
first), so a group the catalog counts inside a larger total is written as
part of it, not beside it.

## Format

Same as UCSB's program files (`all` / `choose` / `units` / `course` / `text`,
with optional `label` and `notes`), plus three shorthand items that the build
expands from the course list:

    {"type": "tagged", "subject": "CSE", "tag": "Systems"}
    {"type": "any", "subject": "CSE", "level": "upper", "except": ["CSE 195"]}
    {"type": "range", "subject": "COGS", "from": 120, "to": 127}

## Known limits

- Rules that can't be written as nodes ("at least two different
  departments", "no more than two courses outside CSE") are `text` items or
  `notes`; the planner shows them but can't check them.
- Some approved-elective lists are kept by departments, not printed in the
  catalog (e.g. ECE technical electives, COGS specializations); those pools
  are approximate or `text`.
- Codes the catalog prints but doesn't list as a 2026–27 course (old or
  graduate courses, and a few misprints kept as printed) show as inactive.
- Combined bachelor's/master's programs and individual majors are left out.

## Open questions for a person to check

Where the catalog page itself is unclear or contradicts itself. Each file follows the reading given here; a note in the file quotes the catalog.

- INTL History focus: HIGL 114/127 placement unclear. INTL Economics focus: ECON 101/102/103/116 appear in both choose-1 lists (one course could fill both).
- PH Climate & Env: "twelve units" but only 8 listed. PH HPMS: "SOCI 109R" likely SIO 109R; core lacks R options.
- Theatre-Dance: "Five Upper-Division Courses" heading on a lower-division list (typo?); stage management has no code. EE & Society: econ data-analysis track and sociology unit counts unclear. EE technical/professional elective lists are kept by the ECE office, so the pools are approximate.
- CompE: CSE page = CSE 140 + (141 or 142), open electives units 8; ECE page says "140, 141, or 142" and differs on P/NP (4 vs 8 units). ICAM: MUS and VIS pages give different curricula (followed VIS). CBN: PSYC vs COGS pages differ (followed PSYC). Music BA: "any three from" read as three in one area.
- AI BS: CSE 151B both core option and required; ethics outside the 20 core units. CS-Bioinformatics: five electives vs "24-unit minimum". Business Economics: offering dept unclear (ECON page used). German: degree assumed BA; LTEU 137 counted as German literature?
- Japanese Studies: whether the remaining five must be nonlanguage. INTL Intl Business: "five" required but six listed. Ling Language Studies: HEA 117 -> HIEA 117 (from other pages).
- Math-Econ: ECON vs MATH pages disagree on the extra UD courses (followed MATH, MA33). Anthro: can MATH 10 and 20 series mix? Env Anthro: Field/Lab Experience required? LATI: ESD 119, UPS 130, ANAR 156-XL kept as printed.
- USP: SOCI 153 vs 153C; USP 128B cross-listed with ANTH 128A (prob. 128B). Business Psych: PSYC/MGT pages differ on MGT 174, MGT 162 units. Math-Sec Ed: do EDS practicum courses count toward 13? Media Industries: can practice courses also count as electives?
- Philosophy (all five files): the catalog lets an emphasis course also fill a core requirement. The planner counts each course once, so the files ask for the emphasis courses besides the core ones; the total is still fifteen.
- Jewish Studies, Track 1: JWSP 101–104 "may be applied toward the elective course requirement". Counting each course once, a Track 1 student may be asked for up to three more courses than they need.
