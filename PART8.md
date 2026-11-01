# Part 8 — Flowchart layout, getting back, and one self-contained file

**Status:** done and published. The browser test passes (`1386 checks passed, 0 failed`).

You asked for four things after looking at Computer Engineering next to the department's own chart ([web.ece.ucsb.edu/~yoga/ce_prereq_flowchart.html](https://web.ece.ucsb.edu/~yoga/ce_prereq_flowchart.html)):

| You asked | What changed |
|---|---|
| Why is ECE 139 off to the side? | It's now in **Step 5, with ECE 152A and CMPSC 130A**. See "ECE 139" below |
| Use the whole page; the text is too small | Boxes wrap to fill the width and the page scrolls down. No zoom: text is full size (about 17 px course codes, up from about 10 px) |
| List every course and its prerequisites, like the department chart | Nothing is folded or hidden: every course has its own box, plus the outside courses the core needs (MATH 4A, PHYS 7A–D for CE). Point at or click any course to trace its whole chain |
| Go back without the browser's Back button | Esc, Close, a Back button in the panel, clicking empty space, and an "All majors and minors" link |
| One file that opens in any browser | `site/ucsb-prereq-map.html`: the whole site (190 maps) in one 8 MB file. The footer links to it |

## What we kept from the department chart, and what we didn't

Kept:
- **Every course listed**, in rows, with electives in their own blocks.
- **No arrows until you point at a course.** Then amber arrows lead into it from everything it needs, all the way back, and blue arrows lead to what it unlocks. Everything else fades. This is what makes it readable: 135 courses with all their arrows at once would be a tangle.

Didn't keep:
- **The dark theme and low-contrast text** (gray on near-black at 7–10 px). We kept our light colors and made the text larger.
- **Hand-placed rows.** The department places each course by hand for one major. Ours places courses automatically for all 190 programs, so steps come from the prerequisites themselves.
- **Hover-only details.** A tooltip disappears when the mouse moves and doesn't work on phones. Hovering previews; clicking keeps the course selected and opens the panel.

## The new layout

```
Step 1 · no prerequisites in this major
[ECE 1A] [ECE 1B] [ECE 5] [ECE 15A] [MATH 2A] [MATH 3A] [CMPSC 8]
Step 2
[CMPSC 16] [PHYS 7A] [MATH 2B] [MATH 3B]
...
Step 5
[CMPSC 130A] [ECE 10B] [ECE 10BL] [ECE 139] [ECE 152A] [ENGR 101] [PHYS 7D]
...
Computer Engineering electives · 56 courses · earn at least 36 units
[ECE 122A] [ECE 122B] ...
```

- **Steps** hold the required courses ("pick one of a few" too) and the outside courses they need. A course's prerequisites are always in an earlier step, or the same step for "may be taken at the same time". The test checks this in all 190 programs.
- **Electives** come after the steps, one block per elective list, with the list's rule. Inside a block, courses that need fewer earlier courses come first.
- **Colors** are the same as before: dark teal required, light teal "pick one" (the box says "or MATH 3A"), white elective, sand with a dashed border for another department's course. The Key is now a row at the top of the map instead of a box in the corner.

### How steps are worked out (`assignSteps()` in `app.js`)

1. Start from each course's `column` in the graph file (Part 4). That's the number of quarters of prerequisites before it. Upper-division courses are never placed before the major's first upper-division core course.
2. Then push each course below the prerequisites the map actually shows. The column for "MATH 4A or 4AI" counts whichever comes first, which is 4AI, the honors version with no prerequisites. The map shows MATH 4A, so without this step MATH 4B could land beside MATH 4A. The test caught this in 12 programs.

### Which outside courses appear (`chooseShown()`)

Outside courses appear when a required course needs them. For a "one of", nothing is added if the major already has an option. CMPSC 130A needs "ECE 139 or PSTAT 120A", and ECE 139 is in CE, so PSTAT 120A isn't added. If no option is in the major, the first one the catalog lists is added. "Every outside course" in the Show options adds all the rest. CE gains one outside course this way (CMPSC 8); its math and physics are already part of the major.

### Solid vs dashed arrows (`prereqsOnMap()`)

Dashed means "one of several options, take any one". An option only counts if it's on the map. ECE 152A needs "ECE 15A and 10A/10AL, or CMPSC 30 or 64". CMPSC 30 isn't offered now and CMPSC 64 isn't in CE, so for a CE student ECE 15A and 10A are the way, and those arrows are solid.

## ECE 139

The catalog lists **no course prerequisites** for ECE 139, only "Open to Electrical Engineering, Computer Engineering and pre-Computer Engineering majors only". The department chart says the same: "No formal course prereq." The old map put every course with no prerequisites in the first column, so ECE 139 sat beside first-quarter courses like ECE 5.

The data already had a rule for this: upper-division courses are never placed before the major's first upper-division core course (ECE 152A for CE). The old layout ignored that rule; the new steps use it. The panel now also says "No courses are required first, only the condition above" for courses like this.

## Getting around (the edge cases)

| You do | What happens |
|---|---|
| Point at a course (mouse) | Preview: its chain lights up. Move away and whatever you clicked comes back |
| Click a course | It stays selected and the panel shows it |
| Click another course | Switches to it. The panel's **← Back to …** returns to the one before (up to 50 back) |
| Click empty space, press **Esc**, or **✕ Close** | Back to the whole map, with the major's summary in the panel |
| **All majors and minors** (next to the pickers) | Back to the front page |
| Browser Back | Goes to the previous major or page, not the previous course, so it doesn't fill up with every click |

## Growing, shrinking, and courses off screen

When a course is lit up (pointed at or clicked):
- **It and the courses it unlocks grow 5%.** The courses it needs stay at normal size (they're already amber), and everything unrelated shrinks to 90% and fades. Sizes are set in one place, `SCALE` in `app.js`; above 5%, two grown boxes side by side would touch.
- **A bar names the linked courses that are scrolled out of view**, e.g. "↓ Further down: ANTH 2 unlocks ANTH 102, ANTH 113, ANTH 115 and 10 more". Growing alone couldn't fix Anthropology: all 13 courses ANTH 2 unlocks are in an 80-course elective list, the nearest about 800 px below the screen. **Click the bar** to select the course and scroll to them; a bar at the top then leads back ("↑ Back to ANTH 2"). On phones, the bottom bar sits above the course sheet.
- **The mouse can travel to the bar** without the preview jumping to every course it crosses: once one course is previewed, another has to be pointed at for about a tenth of a second to take over.

The arrows end exactly on the resized boxes. They're worked out from where each box will end up, not measured mid-animation.

## The single file

`py build_single.py` writes `site/ucsb-prereq-map.html`. It's the same page, styles and code, with every major inside it, so it opens by double-clicking, with no internet and no server. The website links to it in the footer ("Download the whole site as one file").

The 190 graph files repeat each course's details (title, description, prerequisites) in every major that uses it, 18 MB in all. The single file stores each of the 4,654 courses once, plus each major's own facts about them (role, step, status). `app.js` puts the two back together when you open a major. Result: 8.2 MB.

Things that differ in the single file:
- The web font needs the internet. Offline, it falls back to the system font.
- Marks ("taken") are saved per file location in some browsers. Moving the file can lose them.
- "Copy a link to this course" explains that links work on the website, since a link to a file on your computer is no use to anyone else.

**After changing anything in `site/`, run `py build_single.py` before committing**, or the download will be out of date.

## Also removed

- `site/about.html`: About is now a box over the page, so it works in the single file too.
- `site/lib/dagre.min.js`: the step layout is plain CSS. Also removed: `site/lib/cytoscape.min.js`, which nothing had used since Part 6.
- Zoom buttons, dragging, folded elective lists and "one of" boxes.

## Tests

`test_site.py` (run as before: server in one terminal, `py test_site.py 8765` in another) now checks:

- **Every program:**
  - Each current course appears exactly once.
  - Every other box is an outside course the major needs.
  - Every required prerequisite is in an earlier step.
  - Nothing scrolls sideways.
  - Clicking a course fills the panel and draws its arrows.
  - No JavaScript errors.
- **CE:**
  - ECE 139 is in ECE 152A's step.
  - ECE 152A's arrows from ECE 15A and 10A are solid.
  - Its chain reaches MATH 4A, and it unlocks ECE 154A.
- **Getting around:** hover preview and moving away, clicking empty space, Esc, Close, Back twice, and "All majors and minors".
- **The single file, opened from disk:** every program is listed, CE works, details and descriptions are there, and there are no errors.
- Everything from earlier parts: checkboxes, Find a course, Mark as taken, links, notices, About, 404, phone.

## The look: a catalog page

The first version of this layout looked like a generic web app: a grid of identical rounded cards with soft shadows, a teal/amber palette, a floating pill button, swatch chips for the key, and gray "← Back" / "✕ Close" buttons. Three directions were mocked up on the same slice of the CE map (`design-directions.html`): **A. Catalog page**, **B. Transit map**, **C. Plain web page**. You picked A.

What it looks like now:

- **Type:** one serif, Libre Caslon Text, used the way a printed catalog uses it. Small capitals for section heads ("Step five", "Needs"), italics for notes, bold course codes.
- **Paper and ink:** warm off-white paper, near-black ink, a double rule under the masthead. No rounded corners, no shadows, no gradients anywhere.
- **Courses are entries in a ruled list**, each over a dotted rule, not boxes. A course from another department gets a dagger (†) and a footnote-style explanation at the top of the map, as a catalog would.
- **Two pencil colors.** Red for the chosen course and everything it needs; blue for what it unlocks. Lines are thin pencil strokes.
- **Taken is a tick:** "I've taken this course" is a checkbox, taken courses get a ✓ in green, and courses you can take next say "next".
- **The entry beside the map** reads like a catalog entry: code, title, "5 units · step five on this map", then **Needs**, **Unlocks**, **In this major** as run-in small-caps heads. Back and close are plain italic links.
- **The off-screen lines** ("↓ Further down: ANTH 2 unlocks …") are italic underlined text at the map's edge, not a floating button.
- **The tab icon** is a ruled page with a red pencil line.

Colors are set once at the top of `style.css` (`--paper`, `--ink`, `--red`, `--blue`, `--green`).
