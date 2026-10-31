# Part 5 — Website v1

> **Note:** Part 6 redesigned the map. Cytoscape and the quarter columns described below were replaced by HTML boxes laid out with dagre, with each course placed to the right of the courses it needs. See `PART6.md`. The data files, the panel and the publishing steps here are unchanged.

**Status:** done. You pick a major and see its map, with courses in columns by the earliest quarter you could take them. Clicking a course lights up everything it needs and what it unlocks, and fills a side panel. All 135 majors load, and a browser test confirms it (413 checks, all passing).

The plan's "done when" test passes: on the Economics map, clicking MATH 3A highlights and lists what it unlocks (ECON 5, ECON 10A, MATH 3B, MATH 34B).

## Files

| File | What it is |
|---|---|
| `site/index.html` | The page: header, map area, side panel, footer |
| `site/style.css` | All colors, fonts and layout. Colors are defined once at the top |
| `site/app.js` | Everything the page does (about 600 lines, many of them comments) |
| `site/lib/cytoscape.min.js` | Cytoscape.js 3.34, the library that draws boxes and arrows (MIT license, copy in `lib/`) |
| `site/data/` | The graphs from Part 4 (`build_graph.py` writes these) |
| `test_site.py` | Opens the site in a headless browser and checks every major |
| `.github/workflows/pages.yml` | Optional: publishes `site/` to GitHub Pages when you push |

The site is **static files only**: no server code, no build step, no database. That's why it can be hosted free on GitHub Pages.

## Run it on your computer

```
py -m http.server 8000 --directory site
```

Then open **http://localhost:8000** in your browser. Press Ctrl+C in the terminal to stop the server.

**Why you need the server line:** if you double-click `index.html`, the browser opens it as a `file://` page. Browsers block `file://` pages from loading other files with `fetch()`, which is how the page loads `data/majors.json`. So the map would stay empty. `http.server` is Python's built-in web server; it serves the folder the same way GitHub Pages will.

## How `app.js` works

The file is split into numbered sections that match this list:

1. **Majors list.** `start()` loads `data/majors.json` and fills the major picker. The picker is an `<input>` with a `<datalist>`, so typing filters the list with no extra code. Choosing a major sets the address to `#economics-ba`, and a `hashchange` listener loads it. That makes every map a shareable link, and the back button works.

2. **Which courses to show.** `isVisible()` applies the three **Show** checkboxes: electives, courses from other majors, and courses not offered now (off by default).

3. **Layout.** `computePositions()` decides where each box goes:
   - **x** comes straight from the column computed in Part 4: `column × 210` pixels.
   - **y** is the order within the column. It starts as required courses first, then "pick one", electives and outside courses, alphabetically within each. Then it **untangles**: going left to right, each course moves toward the average row of its prerequisites in earlier columns. This is called the *barycenter method*, and it keeps courses near what they need, so arrows are shorter and cross less.

4. **Drawing.** `draw()` hands the boxes, their positions and the arrows to Cytoscape. We use Cytoscape's `preset` layout, which means "use the positions I give you." The colors come from `style.css` (`readColors()`), so the page and the map always match. Arrows exist from the start but are hidden (`display: none`) until you click.

5. **Clicking a course.** `selectCourse()` asks Cytoscape for two sets:
   - `target.predecessors()`: every course on any path leading into the clicked one. That's its prerequisites, their prerequisites, and so on. These get **amber**.
   - `target.outgoers("edge")`: arrows going straight out, meaning what it directly **unlocks**. These get **indigo**.
   
   Everything else fades. Clicking empty space clears the selection.

6. **Side panel.** For a course, the panel shows:
   - Units and earliest quarter.
   - Where it counts in the major.
   - Its prerequisites as nested "All of / One of" lists. `treeHtml()` walks the same tree Part 2 produced, recursively.
   - The catalog's original wording, what it unlocks, and links to the course's catalog page and to ASSIST (for lower-division courses).
   
   Course names in the panel are buttons that jump to that course on the map. Everything taken from the catalog goes through `escapeHtml()`, so stray `<` or `&` characters in the data can't break the page.

**The quarter ruler.** The row of "Quarter 1, Quarter 2, …" labels sits above the map. When you pan or zoom, Cytoscape moves the boxes, so `updateRuler()` listens for Cytoscape's `viewport` event and moves each label to stay above its column.

## Design choices

- **Columns labeled by quarter** are the main idea of the page: the map reads left to right like a schedule. Everything else is kept quiet.
- **Colors:** deep teal for required courses, light teal for "pick one of a few," white for electives, and sand with a dashed border for courses from other majors. When you click a course, amber means "needs" and indigo means "unlocks." I deliberately avoided UCSB's official navy and gold, so the page doesn't look like an official university site.
- **Font:** Atkinson Hyperlegible, designed for legibility at small sizes. It suits course codes in small boxes. Without internet it falls back to the system font.
- **The upper-division section names** are shown in sentence case ("Preparation for the major") instead of the catalog's capitals.

## Tests: `test_site.py`

These tests drive a real browser:
1. The front page loads and the picker lists all 135 majors.
2. **Every major** loads with no JavaScript errors, draws exactly as many boxes as its graph file says, and opens a course in the panel when one is clicked.
3. The plan's test: Economics, click MATH 3A, and MATH 3B and ECON 10A appear as unlocked.
4. The Show checkboxes hide and restore the right courses.

To run them, first do a one-time setup:

```
py -m pip install playwright
py -m playwright install chromium
```

Then start the server in one terminal (`py -m http.server 8000 --directory site`) and run this in a second terminal:

```
py test_site.py
```

It takes about a minute and should print `413 checks passed, 0 failed`.

Writing the test found two real problems:
- **Interdisciplinary Studies has no individual courses at all.** Its only requirement is one list of about 3,000 courses, so the map is a single box. The test (and the page) now handle that case.
- **The second was a bug in the test itself.** Asking the browser to return Cytoscape's whole internal state froze the test. The lesson: return only the value you need.

## Publishing (when you're ready)

The site only exists on your computer until you publish it. When you want a public link, the included workflow does it:

1. Push the project to a GitHub repository.
2. In the repository, go to **Settings → Pages → Source** and choose **GitHub Actions**.
3. Every push to `main` then publishes the `site/` folder, at an address like `https://<your-username>.github.io/<repo-name>/`.

I couldn't test the workflow from here, since it only runs on GitHub. If the first run fails, the Actions tab shows the error; paste it to me.

## Known limits (Part 6 covers these)

- **Phones work, but awkwardly.** The panel sits below the map; Part 6 turns it into a bottom sheet.
- **Long titles are cut** to about 22 characters in the boxes. The full title is in the panel.
- **Big majors are tall.** Economics has 27 electives in one column. Part 6 collapses elective lists into one expandable box.
- **"Or" arrows can point backwards.** If a course needs "B or C" and C comes earlier, the course sits right after C, so the arrow from B points left. These are drawn dashed. About 11% of "or" arrows do this (see `PART4.md`).
- **No "mark as taken" yet.** That's Part 6.

## Try this

1. Open your own major and click a course you're taking this quarter. Do the amber courses match what you took to get there?
2. Click a course in the side panel's "Unlocks" list and watch the map jump to it.
3. Uncheck **Electives** to see just the core path through the major.
