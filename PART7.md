# Part 7 — Launch prep, minors, and the majors that wouldn't load

**Status:** done and live at **https://andrew-hanzhou-li.github.io/ucsb-prereq-map/** (source: https://github.com/andrew-hanzhou-li/ucsb-prereq-map). The browser test passes (`1373 checks passed, 0 failed`). What's left is yours: show it to classmates (see "Launch" at the end).

Part 7 did three things:

| | Before | After |
|---|---|---|
| Programs with a map | 135 majors | **134 majors + 56 minors** |
| Programs in the picker with no map | 98 (silently missing) | 35, each with a note saying why |
| Retired programs | mixed in | 66 left out |
| Front page | 3 example links | every major and minor, listed |
| Links | to a major | to a major **and a course** (`#economics-ba/ECON+10A`) |
| Pages | the map | the map, an About page, a 404 page |

## The 98 majors that "had no structured requirements"

Part 3 said 98 bachelor's programs only described their requirements in paragraphs, so loading them would need a new parser. That turned out to be wrong. They had **no requirements at all** in the download, not even paragraphs. Checking them on the live catalog showed why:

| Group | How many | What they are | What the site does now |
|---|---|---|---|
| **Retired** | 62 | The catalog marks them `Inactive`: Geological Sciences (now Earth Science), Business Economics, Pharmacology, Psychology BA, Statistical Science and others | Left out |
| **No course list in the catalog** | 35 | 33 College of Creative Studies programs, Individual BA/BS, Undeclared. Their catalog pages have no Program Requirements tab | Listed, marked "(no map)", with a note and a catalog link |
| **Updated since the download** | 1 | Global Studies BA. The catalog added its requirements after the Oct 2 download | Has a map now |

Two programs that *did* have requirements are also retired: Aquatic Biology BA and an old History of Art and Architecture BA code. They're left out too. That also removed the duplicate History of Art and Architecture file, whose name had an old program code attached.

**Lesson worth telling in an interview:** the plan said "write a parser." Looking at what the 98 actually contained showed there was nothing to parse. It's the same move as Part 3: check what the data really is before building for it.

### How it's done

- `fetch_programs.py` now also saves each program's `status` (`Active` / `Inactive`).
- `build_majors.py` reads bachelor's degrees **and minors**, skips `Inactive` ones, and adds `kind` (`major` or `minor`) and `source` (catalog link) to `majors/index.json`. It deletes old files in `majors/` first, so retired programs don't linger.
- `build_graph.py` does the same cleanup in `site/data/`. It writes programs with no course list into `majors.json` with `"structured": false`, so the site can list them.

`py build_majors.py` now prints:

```
Current majors in catalog:          169
  with structured requirements:   134  (written to majors/)
  no course list in the catalog:  35
Current minors in catalog:          56
  with structured requirements:   56  (written to majors/)
  no course list in the catalog:  0
Retired programs left out:        66
```

Unresolved catalog IDs went from 7 to 8, because minors added one. They still show as "not in the current catalog" in the panel.

## Minors

Minors are stored by the catalog exactly like majors, so `build_majors.py` needed no new translation code. The site calls everything a "major" internally. Where the page says it out loud ("In this minor", "Unlocks in this minor") it uses `programWord()` in `app.js`.

The checkbox that used to say "Courses from other majors" now says **"Prerequisites from outside"**, since it also applies to minors.

## The front page

Below the welcome text are two lists: **Majors (169)** and **Minors (56)**. Every name is a link. Programs with no map say "(no map)". On phones the lists become one column with bigger tap targets. The side panel stays hidden until a map is open, since it has nothing to show before that.

## Notices instead of a blank page

`showNotice()` in `app.js` puts a message box at the top of the front page for:

- **A program with no map** (`noMapMessage()`): says why (CCS, Individual or Undeclared) and links to the catalog page.
- **An address that matches nothing**, for example an old link to a retired program.
- **A failed download** (offline): the major list, or one major's file.

## Links to a course

The address bar now follows what you select: `#economics-ba` → click ECON 10A → `#economics-ba/ECON+10A` (`+` stands for the space). Opening that link selects ECON 10A straight away. It uses `history.replaceState`, so clicking around doesn't fill the Back button with every course.

The course panel also has a **Copy a link to this course** button. Browsers only allow copying on `https` pages or `localhost`. GitHub Pages is `https`, so it works once published.

## New pages and files

| File | What it is |
|---|---|
| `site/about.html` | How to read the map, the color key, privacy (marks stay on the device), where the data comes from, what it can't check, the "unofficial" notice |
| `site/404.html` | GitHub Pages shows this for addresses that don't exist |
| `site/favicon.svg` | The browser-tab icon: three boxes and arrows in the map's colors |

`index.html` also gained link-preview tags (`og:title`, `og:description`), so a link texted to someone shows a title and a description. There's no preview *image*: that needs the site's final web address, so it's a small job for after publishing.

## Tests

`test_site.py` adds these checks:

- The front page lists every major and minor and hides the empty panel.
- Every one of the **190** maps passes the Part 6 checks (each course once, no overlaps, every arrow left to right, clicking works).
- Selecting a course puts it in the address; clearing takes it out; a course link opens with that course selected; the copy button is there.
- A CCS program shows the notice, the catalog link, no map and no panel; an unknown address shows "No map at that address"; an empty address goes back to the welcome text.
- A minor's panel says "In this minor".
- The About and 404 pages load.

**New: a port option.** On your computer, something else was already using port 8000 (a `uvicorn main:app` server, which looks like your dining-hall project). So the test now takes a port number:

```
py -m http.server 8765 --directory site
py test_site.py 8765
```

It should print `1373 checks passed, 0 failed`. `py test_graph.py` should print `30427 checks passed, 0 failed`.

## Data freshness

`raw_programs.json` was downloaded again on Oct 31. `raw_courses.json` is still the early-October copy. That's fine unless the catalog changes a course mid-year. To refresh everything, run the full rebuild in the README, starting with `py fetch.py`.

## Launch

Done:

1. **Repository:** https://github.com/andrew-hanzhou-li/ucsb-prereq-map (public). Commits use your GitHub "noreply" email, so your personal email isn't shown.
2. **Pages:** turned on with GitHub Actions as the source. `.github/workflows/pages.yml` republishes `site/` on every push to `main`, which takes about a minute. The first run failed because it started before Pages was on; the re-run worked.
3. **`REPO_URL`** in `site/app.js` points at the repository, so the footer shows a "Source code" link.
4. **Checked live:** the front page lists 169 majors and 56 minors, a course link opens that course, the About page loads, a mistyped address shows the 404 page, and there are no JavaScript errors. Checked on desktop and phone sizes.

To publish a change: commit and `git push`. The Actions tab on GitHub shows each run.

Yours: **show it to 3 classmates on their phones** (from Part 6). Text them the link, don't explain anything, and note where each one hesitates. Bring those notes back.
