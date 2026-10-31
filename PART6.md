# Part 6 — Mark as taken, polish, mobile (and the map redesign)

**Status:** the code is done. One item is yours: show the site to 3 classmates on their phones and fix the first thing each one gets confused by. The browser test runs 970 checks, all passing.

Part 6 shipped in two rounds. The first round added marking courses taken, folded elective lists and the phone layout. After you tried it, you raised four problems, so the second round redesigned the map:

| Your feedback | What changed |
|---|---|
| The major dropdown does nothing once a major is filled in | Clicking into the box now empties it, so the full list shows. If you click away without choosing, the old major comes back |
| Course boxes still look blurry | The boxes are now real HTML text instead of a picture painted on a canvas, so they're sharp at any zoom and any display scaling |
| Columns labeled "Quarter 1, 2, …" don't fit transfers or major switchers, and quarter 1 had 10 courses in Computer Engineering | No more quarters. Each course just sits **to the right of the courses it needs**. Position shows order, not a schedule |
| Too cluttered; hard to tell what goes where | Fewer boxes and fewer arrows (details below). Computer Engineering now shows its 92 courses in 38 boxes with 41 arrows |

## The new map, in one paragraph

Every box is a course (or a small group of courses). An arrow from A to B means "A unlocks B." A course with no prerequisites in the major sits at the far left. Every other course sits as far left as it can while still being to the right of everything it needs. Courses that aren't connected to anything sit in their own row underneath, labeled as such. Click a course: the courses it needs turn amber, the ones it unlocks turn blue, and everything else fades.

## How the layout works

The code is in section 4 of `app.js`, `layout()`. It uses **dagre** (`site/lib/dagre.min.js`, MIT license), a small library that arranges boxes and arrows in layers.

1. **Layers.** dagre puts every box in a layer (a column) so that all arrows point the same way, left to right.
2. **Left-justified.** By default dagre pushes a course as close as possible to the course it unlocks, which put no-prerequisite courses like ECE 15A far to the right. The fix is a trick: we give dagre the arrows **reversed** and ask for right-to-left (`rankdir: "RL"`, `ranker: "longest-path"`). Flipping twice gives left to right, with each course as far left as it can go.
3. **Order within a column.** dagre orders boxes in each column to keep arrows from crossing.
4. **Unlinked courses** (no prerequisites here, nothing here needs them) are taken out before layout and wrapped into a row at the bottom.

## How the clutter came down

| Change | Where in `app.js` | Effect |
|---|---|---|
| **"One of" boxes.** When the major says "take one of MATH 2A or MATH 3A", both go in a single box | `findChoiceSets()` | One box instead of two, and it's clear you need only one |
| **Folded elective lists.** Lists of 9+ electives become one box ("Computer Engineering electives, 48 courses") | `chooseBoxes()`, `COLLAPSE_AT` | Click it to see the list and its rule; unfold it onto the map if you want |
| **Outside courses hidden by default.** Courses from other majors that are needed first (MATH 4A for Economics) are off unless you tick "Courses from other majors" | `buildArrows()` | Arrows walk *through* a hidden course, so the order stays right: if ECON 10A needs MATH 4A, which needs MATH 3B, you see MATH 3B → ECON 10A |
| **No shortcut arrows.** If MATH 3A → MATH 3B → MATH 4B, a direct arrow MATH 3A → MATH 4B is dropped, because you can follow the chain | `removeShortcuts()` | This is called a *transitive reduction*. It removed most of the long arrows that crossed the map |
| **No loops.** See below | `removeLoops()` | Every arrow points left to right |
| **Key closed by default** | `index.html` | Click "Key" to open it; it remembers your choice |

### Loops from folding

Folding courses into a shared box can create a loop. In Mathematics, a course in list A needs a course in list B, and a different course in B needs one in A. That gives A → B and B → A, and no left-to-right order fits both. Sixteen majors had one such loop.

`removeLoops()` adds arrows one at a time, most trustworthy first: required arrows between single courses, then arrows touching a folded list, then "one of several options" arrows. It skips any arrow that would close a loop. The panel still lists every prerequisite in full, so nothing is lost there.

## Why the text is sharp now

The old map used Cytoscape, which paints the map onto a `<canvas>`, like a picture. Pictures blur when stretched, for example by Windows display scaling at 125%. The new map is ordinary HTML: each course is a `<button>`, and the arrows are an SVG drawing underneath. Zoom uses the CSS `zoom` property, which makes the browser redraw the text at the new size instead of stretching it. So the text is as sharp as any web page.

Zooming: the − / Fit / + buttons, or Ctrl + mouse wheel. Drag the background to move around.

## The dropdown fix

A `<datalist>` (the browser's built-in suggestion list) only shows entries that match what's already typed. With "Economics - BA" filled in, it showed only that one entry, so clicking the arrow looked like it did nothing. `showFullListWhenOpened()` empties the box when you click into it (so every major shows) and puts the old value back if you leave without choosing.

## How "Mark as taken" works

The code is in section 2 of `app.js`.

**Where the marks live.** They're stored in the browser's `localStorage`, a small per-site storage area. It survives a refresh but **stays on that computer**; nobody else can see it, and nothing is sent anywhere. Some browsers block it, for example in private windows. If so, the `try`/`catch` blocks let marks still work until the page closes.

**"Can take next".** `isMet()` walks a course's prerequisite tree from Part 2:

| Part of the tree | Met when |
|---|---|
| a course | you've marked it taken |
| All of | every part is met |
| One of | any **course** option is met (options like "or AP exam" are ignored when there are course options, otherwise every course with an AP alternative would always look ready) |
| a condition ("consent of instructor", "upper-division standing") | always, since the site can't check it |

A course gets the green outline when it isn't taken, it has at least one course prerequisite, and `isMet()` says they're all met. A "one of" box counts as taken when any one of its options is.

**What it doesn't check:** grades ("C or better" assumes you got one) and "may be taken concurrently" (it waits for you to mark the course taken). Both are stated in the panel.

## How the phone layout works

The phone styles are in `style.css`, in the `@media (max-width: 800px)` block at the end:

- **The panel becomes a sheet.** It's fixed to the bottom of the screen and pushed down so only its handle shows. Selecting a course slides it up to 62% of the screen. Tapping the handle toggles it.
- **The selected course stays visible.** `scrollToBox()` scrolls the map so the selected box sits in the strip above the sheet. The map has extra empty room at the bottom on phones (`.map::after`) so even the lowest course can be scrolled up that far.
- **The header shrinks.** "Find a course" and the checkboxes move behind an **Options** button.
- **The footer moves** into the panel's major summary.

## Tests

`test_site.py` checks, among other things:
- The major picker empties when clicked and restores itself.
- **Every one of the 135 majors:** each current course appears exactly once (own box, "one of" box or folded list), all boxes are drawn, no two overlap, **every arrow points left to right**, no arrow points at a missing box, and clicking a box works with no JavaScript errors.
- Economics: MATH 3A unlocks MATH 3B and ECON 10A.
- The checkboxes, folding and unfolding a list, and "Find a course" unfolding ECON 171's list.
- Mark as taken, reload, and clear.
- Phone: the sheet opens and the selected course stays above it.

Run it the same way as in Part 5 (server in one terminal, `py test_site.py` in another). It should print `970 checks passed, 0 failed`.

## Your part: 3 classmates

The plan's "done when" is that 3 classmates use it on their phones without asking you how. Two ways to get it onto their phones:

- **Easiest:** publish it (the GitHub Pages steps in `PART5.md`) and text them the link.
- **Without publishing:** have them use it on your laptop. That tests the desktop version, not the phone one.

When you watch them, don't explain anything. Write down the first place each person hesitates or asks a question. Bring me those notes and we'll fix them.

## Small settings you can change

All are at the top of `app.js`:

| Setting | Now | What it does |
|---|---|---|
| `BOX_WIDTH` | 172 | Box width in pixels |
| `LAYER_GAP`, `ROW_GAP` | 46, 12 | Space between columns, and between boxes in a column |
| `COLLAPSE_AT` | 9 | Elective lists this long or longer start folded |
| `CHOICE_MAX` | 4 | "One of" lists up to this long share a box |
| `REPO_URL` | empty | Put your GitHub repository's address here to show a "Source code" link in the footer |
