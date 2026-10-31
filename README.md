# UCSB Prereq Planner

A tool that draws the prerequisite map for any UCSB major or minor, built from the official General Catalog.

**Live at https://andrew-hanzhou-li.github.io/ucsb-prereq-map/**

**Status:** Parts 1–8 done (data, prerequisite parser, major requirements, graph, website, mark-as-taken and mobile, launch with minors, flowchart layout and single-file version). Next: test with classmates (end of `PART7.md`).

## Project map

| Part | What it does | Main files | Guide |
|---|---|---|---|
| 1 | Download every course in the catalog | `fetch.py` → `raw_courses.json` | this file, below |
| 2 | Turn prerequisite English into logic trees | `parser.py`, `build_prereqs.py`, `measure.py` → `prereqs.json` | `PART2.md` |
| 3 | Major requirements, from the catalog's structured data | `fetch_programs.py`, `build_majors.py`, `show_major.py` → `majors/` | `PART3.md` |
| 4 | One ready-to-draw graph per major | `build_graph.py`, `test_graph.py` → `site/data/` | `PART4.md` |
| 5 | The website | `site/index.html`, `site/style.css`, `site/app.js`, `test_site.py` | `PART5.md` |
| 6 | Mark as taken, folded elective lists, phone layout; map redesigned (relative layout with dagre, sharp HTML text) | same files, plus `site/lib/dagre.min.js` | `PART6.md` |
| 7 | Minors, retired programs left out, front-page lists, links to a course, About and 404 pages | same files, plus `site/404.html` | `PART7.md` |
| 8 | Flowchart layout (every course, in steps; arrows on hover or click), Back/Close/Esc, the whole site as one file | same files, plus `build_single.py` → `site/ucsb-prereq-map.html` | `PART8.md` |

To rebuild everything from scratch (Windows):

```
py fetch.py
py fetch_programs.py
py build_prereqs.py
py build_majors.py
py build_graph.py
py measure.py --quiet
py test_graph.py
py build_single.py
```

`build_single.py` makes `site/ucsb-prereq-map.html`, the whole site in one file. Run it after changing anything in `site/`.

To see the site, run `py -m http.server 8000 --directory site` and open http://localhost:8000. If port 8000 is already in use, use another number, such as 8765.

To run the browser test, keep that server running and in a second terminal run `py test_site.py` (or `py test_site.py 8765` for another port).

The two `fetch` steps download from the catalog (about 40 requests total). Every data file they produce is already included, so you can skip them and start at `build_prereqs.py`.

## Part 1 — Getting the data

### What's here

| File | What it is |
|---|---|
| `fetch.py` | Downloads every course in the UCSB catalog and saves it to `raw_courses.json` |
| `raw_courses.json` | The result: 7,948 courses from 138 subjects (2026–27 catalog) |

### Where the data comes from

[catalog.ucsb.edu](https://catalog.ucsb.edu/courses) runs on a platform called Coursedog. When you scroll through the course list, your browser quietly asks Coursedog's public API for each page of courses. `fetch.py` sends the same request the website sends, so we get exactly what the catalog shows — no scraping of web pages needed.

It takes 8 requests (1,000 courses each), with a 1-second pause between them.

### Run it yourself

```
python fetch.py
```

Only Python's standard library is used, so there's nothing to install. Run it once per catalog year; when a new catalog comes out, update `CATALOG_ID` and `EFFECTIVE_DATE` at the top of the file (the comment there says how to find the new values).

### What each course looks like

```json
{
 "code": "ECON 100B",
 "subject": "ECON",
 "number": "100B",
 "level": "upper",
 "title": "Intermediate Microeconomic Theory",
 "units": "4",
 "prereq_text": "Economics 10A or 100A; and, Economics 5 or PSTAT 109 or PSTAT 120A.",
 "comments": "No credit will be given to students who have taken Economics 104B.",
 "description": "Economic theory relating to imperfectly competitive product markets, ...",
 "college": "College of Letters and Science",
 "departments": ["ECON"]
}
```

- `level` is `lower` (1–99), `upper` (100–199) or `graduate` (200+).
- `prereq_text` is the catalog's wording with HTML removed (`&amp;` → `&`, `<p>` tags stripped). It's still plain English — turning it into logic is Part 2.
- 6,214 courses have prerequisite text; the rest have none.

### Checks

- **No HTML left** in any prerequisite text.
- **10 random courses checked against their catalog pages** (CHEM 109C, CHEM 115A, CHEM 126, CHEM 176, ECE 10CL, ECE 152A, ECON 135, MATH 6A, PHYS 103, PSTAT 172A): 10/10 prerequisite texts match exactly.
- The departments the first three majors need are all present: ECE 179 courses, CHEM 168, ECON 141, CMPSC 126, MATH 126, PHYS 122, PSTAT 94, ENGR 9.

### Things Part 2 will have to handle

From reading the data:

- **Subject names vary.** The same department is written as "Mathematics", "Math" or "MATH"; "Computer Science", "CS" or "CMPSC". The parser needs a name-to-code table.
- **Subjects are often implied.** "ECE 132 and 134" means ECE 134.
- **Hyphenated sequences.** "Chemistry 113A-B-C" means 113A, 113B and 113C.
- **Non-course conditions** mixed in: "open to EE majors only", "consent of instructor", "upper-division standing", minimum grades, "may be taken concurrently".
