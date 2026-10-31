/*
  app.js: the UCSB Prerequisite Map website.

  What happens, in order:
    1. Load the list of majors and minors (data/majors.json) into the picker
       and the lists on the front page.
    2. When one is picked, load its graph (data/<major>.json, built by
       build_graph.py in Part 4). The address bar remembers the program and
       the selected course (#economics-ba/ECON+10A), so any view can be
       shared as a link. "Major" in the code below means major or minor.
    3. Decide which boxes to draw. To keep the map readable:
         - interchangeable courses ("MATH 2A or 3A") share one box,
         - long elective lists fold into one box,
         - courses from other majors are hidden unless you ask for them;
           arrows pass through them, so the order stays right.
    4. Lay the boxes out with dagre, a library that arranges a graph in
       layers: each course sits to the right of everything it needs.
       Positions are relative to other courses, not tied to quarters.
    5. Draw each box as a real HTML button (so text is sharp at any zoom)
       and the arrows as SVG lines underneath.
    6. Clicking a box lights up everything it needs (amber) and what it
       directly unlocks (indigo), fades the rest, and fills the side panel.
    7. "Mark as taken": courses you've taken turn green, and courses whose
       prerequisites you've now met get a green outline. Your marks are saved
       in this browser.

  Libraries: dagre (lib/dagre.min.js) for the layout. Everything else is
  plain JavaScript and runs as static files: no server code, no build step.
*/

// ===========================================================================
// Settings
// ===========================================================================

const BOX_WIDTH = 172;
const LINE_HEIGHT = 18;       // height of one line of text in a box
const BOX_PADDING = 14;       // top + bottom padding inside a box
const LAYER_GAP = 46;         // horizontal space between layers
const ROW_GAP = 12;           // vertical space between boxes in a layer
const COLLAPSE_AT = 9;        // elective lists with this many courses or more start folded into one box
const CHOICE_MAX = 4;         // "pick one of" lists up to this long share one box
const SAVE_KEY = "ucsb-prereq-map.taken";   // where "taken" marks are saved in the browser
const REPO_URL = "https://github.com/andrew-hanzhou-li/ucsb-prereq-map";   // linked as "Source code" in the footer

const ROLE_NAMES = {
  required: "Required",
  choice: "Required (pick one of a few)",
  elective: "Elective",
  prerequisite: "Not in this program, but needed for a course that is",
};

// ===========================================================================
// State
// ===========================================================================

let majors = [];            // from data/majors.json (majors and minors)
let currentMajor = null;    // the entry from majors.json that's on the map
let graph = null;           // the loaded major's graph file
let loading = 0;            // counts loads, so a slow one can't replace a newer one
let nodesById = {};         // course code -> course from the graph file
let taken = loadTaken();    // course codes marked as taken (shared by all majors)
let expanded = new Set();   // elective lists the user unfolded on this major
let zoom = 1;

// Rebuilt by draw():
let boxes = {};             // box id -> box (see chooseBoxes)
let standIn = {};           // course code -> id of the box that shows it
let arrows = [];            // {from, to, type} between box ids
let selectedBox = null;     // id of the highlighted box
let selectedCourse = null;  // course code shown in the panel (may be inside a shared box)

const el = {
  majorInput: document.getElementById("major-input"),
  majorList: document.getElementById("major-list"),
  courseInput: document.getElementById("course-input"),
  courseList: document.getElementById("course-list"),
  toggles: document.getElementById("toggles"),
  showElectives: document.getElementById("show-electives"),
  showOutside: document.getElementById("show-outside"),
  showInactive: document.getElementById("show-inactive"),
  map: document.getElementById("map"),
  stage: document.getElementById("stage"),
  zoomControls: document.getElementById("zoom-controls"),
  empty: document.getElementById("empty"),
  notice: document.getElementById("notice"),
  welcome: document.getElementById("welcome"),
  browseMajors: document.getElementById("browse-majors"),
  browseMinors: document.getElementById("browse-minors"),
  legend: document.getElementById("legend"),
  panel: document.getElementById("panel"),
  panelHandle: document.getElementById("panel-handle"),
  panelBody: document.getElementById("panel-body"),
  takenStatus: document.getElementById("taken-status"),
  footerCatalog: document.getElementById("footer-catalog"),
  footerRepo: document.getElementById("footer-repo"),
  top: document.querySelector(".top"),
  optionsButton: document.getElementById("options-button"),
};

// ===========================================================================
// 1. Majors list, pickers and loading a major
// ===========================================================================

async function start() {
  try {
    const response = await fetch("data/majors.json");
    majors = (await response.json()).majors;
  } catch (error) {
    showNotice("<h2>The list of majors didn't load</h2>" +
               "<p>Check your internet connection, then refresh the page.</p>");
    return;
  }

  for (const major of majors) {
    const option = document.createElement("option");
    option.value = major.name;
    el.majorList.appendChild(option);
  }
  fillBrowseLists();

  el.majorInput.addEventListener("change", function () {
    const major = majors.find(m => m.name.toLowerCase() === el.majorInput.value.trim().toLowerCase());
    if (major) location.hash = stem(major.file);
  });

  el.courseInput.addEventListener("change", function () {
    const code = el.courseInput.value.trim().toUpperCase();
    if (nodesById[code]) {
      selectCourse(code, true);
      el.courseInput.value = "";
      el.courseInput.blur();
    }
  });

  showFullListWhenOpened(el.majorInput);
  showFullListWhenOpened(el.courseInput);

  for (const box of [el.showElectives, el.showOutside, el.showInactive]) {
    box.addEventListener("change", function () { draw(); });
  }

  // The address bar remembers the major and course (#economics-ba/ECON+10A),
  // so a map can be shared as a link and the back button works.
  window.addEventListener("hashchange", loadFromHash);
  loadFromHash();

  if (REPO_URL) el.footerRepo.innerHTML = '<a href="' + REPO_URL + '">Source code</a>';
  updateTakenStatus();
}

/*
  A text box with a suggestion list (<datalist>) only suggests entries that
  match what's already typed. Once a major is filled in, that's just the one
  major, so the list looked broken. Fix: when you click into the box, empty
  it so the whole list shows; if you leave without picking, put the old
  value back.
*/
function showFullListWhenOpened(input) {
  let previous = "";
  input.addEventListener("focus", function () {
    previous = input.value;
    input.value = "";
  });
  input.addEventListener("blur", function () {
    if (input.value.trim() === "") input.value = previous;
  });
}

function stem(fileName) {
  return fileName.replace(/\.json$/, "");
}

// The front page's lists of every major and minor.
function fillBrowseLists() {
  for (const kind of ["major", "minor"]) {
    const list = kind === "major" ? el.browseMajors : el.browseMinors;
    const items = majors.filter(m => m.kind === kind);
    list.innerHTML = items.map(function (m) {
      const name = kind === "minor" ? m.name.replace(/\s*-\s*Minor\s*$/, "") : m.name;
      return '<li><a href="#' + escapeHtml(stem(m.file)) + '">' + escapeHtml(name) + "</a>" +
             (m.structured ? "" : ' <span class="note">(no map)</span>') + "</li>";
    }).join("");
    document.getElementById("browse-" + kind + "s-title").textContent =
      (kind === "major" ? "Majors" : "Minors") + " (" + items.length + ")";
  }
}

/*
  The address: "#economics-ba" is a major; "#economics-ba/ECON+10A" is a
  major with a course selected ("+" stands for the space in a course code).
*/
function readHash() {
  let raw = "";
  try {
    raw = decodeURIComponent(location.hash.slice(1));
  } catch (error) {
    // A mangled link: treat it as no address.
  }
  const slash = raw.indexOf("/");
  if (slash < 0) return { stem: raw, course: null };
  return { stem: raw.slice(0, slash), course: raw.slice(slash + 1).replace(/\+/g, " ").toUpperCase() || null };
}

function hashFor(major, code) {
  return "#" + stem(major.file) + (code ? "/" + code.replace(/ /g, "+") : "");
}

// Keep the address bar in step with the selection, so copying it shares this
// exact view. replaceState changes the address without adding a Back step
// for every click, and without firing "hashchange".
function rememberInAddress() {
  if (!currentMajor) return;
  const target = hashFor(currentMajor, selectedCourse);
  if (location.hash !== target) history.replaceState(null, "", target);
}

async function loadFromHash() {
  const wanted = readHash();
  if (!wanted.stem) {
    showHome();
    return;
  }
  const major = majors.find(m => stem(m.file) === wanted.stem);
  if (!major) {
    showHome();
    showNotice("<h2>No map at that address</h2>" +
               "<p>That link doesn't match a current major or minor. The program may have been renamed or " +
               "retired from the catalog. Pick one from the lists below.</p>");
    return;
  }
  if (!major.structured) {
    showHome();
    el.majorInput.value = major.name;
    showNotice(noMapMessage(major));
    return;
  }
  if (!currentMajor || currentMajor.id !== major.id) {
    if (!(await loadMajor(major))) return;
  }
  if (wanted.course && nodesById[wanted.course]) {
    if (wanted.course !== selectedCourse) selectCourse(wanted.course, true);
  } else if (selectedBox || selectedCourse) {
    clearSelection();
  }
}

// Programs listed in the catalog with no course list (build_majors.py).
function noMapMessage(major) {
  let why = "The UCSB catalog doesn't list required courses for this program, so there's nothing to map.";
  if (/Creative Studies/.test(major.name)) {
    why = "The UCSB catalog doesn't list required courses for College of Creative Studies programs. " +
          'CCS describes its majors on <a href="https://ccs.ucsb.edu/" target="_blank" rel="noopener">its own site</a>.';
  } else if (/^Undeclared/.test(major.name)) {
    why = "Undeclared isn't a major with its own courses. Browse the majors below to see what each one takes.";
  } else if (/^Individual/.test(major.name)) {
    why = "An individual major is designed with an advisor, so the catalog has no fixed course list for it.";
  }
  return "<h2>" + escapeHtml(major.name) + "</h2><p>There's no map for this one. " + why + "</p>" +
         '<p><a href="' + escapeHtml(major.source) + '" target="_blank" rel="noopener">See it in the UCSB catalog</a></p>';
}

// A message at the top of the front page, in place of the welcome text.
function showNotice(html) {
  el.notice.innerHTML = html;
  el.notice.hidden = false;
  el.welcome.hidden = true;
  el.empty.hidden = false;
  el.empty.scrollTop = 0;
}

// Back to the front page: no map, the welcome text and the lists.
function showHome() {
  loading += 1;           // any load still in progress is no longer wanted
  currentMajor = null;
  graph = null;
  nodesById = {};
  boxes = {};
  standIn = {};
  arrows = [];
  selectedBox = null;
  selectedCourse = null;
  el.stage.innerHTML = "";
  el.stage.style.width = "0px";
  el.stage.style.height = "0px";
  el.stage.classList.remove("focused");
  el.courseList.innerHTML = "";
  el.majorInput.value = "";
  el.empty.hidden = false;
  el.notice.hidden = true;
  el.welcome.hidden = false;
  el.legend.hidden = true;
  el.zoomControls.hidden = true;
  el.toggles.disabled = true;
  el.courseInput.disabled = true;
  el.footerCatalog.textContent = "Built from the UCSB General Catalog.";
  document.title = "UCSB Prerequisite Map";
  el.panelBody.className = "panel-empty";
  el.panelBody.innerHTML = "<p>Click any course to see its prerequisites, what it unlocks and where it counts in the major.</p>";
  el.panelHandle.textContent = "Course details";
  el.panel.hidden = true;           // nothing to show until a map is open
  closeSheet();
}

// Load a major's graph and draw it. Returns false if it didn't load.
async function loadMajor(major) {
  const ticket = ++loading;
  el.majorInput.value = major.name;
  el.majorInput.blur();
  let loaded;
  try {
    loaded = await (await fetch("data/" + major.file)).json();
  } catch (error) {
    if (ticket !== loading) return false;
    showHome();
    showNotice("<h2>" + escapeHtml(major.name) + " didn't load</h2>" +
               "<p>Check your internet connection, then refresh the page.</p>");
    return false;
  }
  if (ticket !== loading) return false;     // another major was picked meanwhile
  currentMajor = major;
  graph = loaded;

  nodesById = {};
  for (const node of graph.nodes) nodesById[node.id] = node;
  selectedBox = null;
  selectedCourse = null;
  expanded = new Set();
  el.empty.hidden = true;
  el.notice.hidden = true;
  el.panel.hidden = false;
  el.legend.hidden = false;
  el.zoomControls.hidden = false;
  el.toggles.disabled = false;
  el.courseInput.disabled = false;
  el.footerCatalog.textContent = "Built from the " + graph.major.catalog_year + " UCSB General Catalog. ";
  const source = document.createElement("a");
  source.href = graph.major.source;
  source.textContent = "Official requirements for " + graph.major.name;
  el.footerCatalog.appendChild(source);
  document.title = graph.major.name + " | UCSB Prerequisite Map";

  zoom = 1;
  draw();
  startView();
  showMajorSummary();
  closeSheet();
  return true;
}

// ===========================================================================
// 2. "Taken" marks
// ===========================================================================

/*
  Marks are saved in the browser's localStorage, so they survive a page
  refresh but stay on this computer. Some browsers block localStorage (for
  example in private windows); then marks just last until the page closes.
*/
function loadTaken() {
  try {
    return new Set(JSON.parse(localStorage.getItem(SAVE_KEY) || "[]"));
  } catch (error) {
    return new Set();
  }
}

function saveTaken() {
  try {
    localStorage.setItem(SAVE_KEY, JSON.stringify(Array.from(taken)));
  } catch (error) {
    // Storage unavailable: marks still work until the page is closed.
  }
}

function toggleTaken(code) {
  if (taken.has(code)) taken.delete(code); else taken.add(code);
  saveTaken();
  updateTakenStatus();
  applyProgress();
  if (selectedCourse) showDetails(selectedCourse);
}

function clearTaken() {
  taken = new Set();
  saveTaken();
  updateTakenStatus();
  applyProgress();
  if (selectedCourse) showDetails(selectedCourse); else showMajorSummary();
}

/*
  Have the prerequisites in a tree (from Part 2) been met?
    course     met if you've marked it taken
    all of     met if every part is met
    one of     met if any part is met
    condition  ("consent of instructor", "upper-division standing") can't be
               checked here, so it counts as met; the panel reminds you.
               (Except as an option in "one of": see below.)
*/
function isMet(node) {
  if (!node) return true;
  if (node.type === "course") return taken.has(node.code);
  if (node.type === "condition") return true;
  if (node.type === "and") return node.items.every(isMet);
  // "One of": a condition option like "or an AP exam score" can't be checked,
  // so when there are course options, only a taken course counts.
  const courseOptions = node.items.filter(hasCourses);
  return (courseOptions.length ? courseOptions : node.items).some(isMet);
}

function hasCourses(node) {
  if (!node) return false;
  if (node.type === "course") return true;
  if (node.type === "condition") return false;
  return node.items.some(hasCourses);
}

// "Can take next": not taken yet, has course prerequisites, and they're all
// met. (Courses with no course prerequisites would always qualify, which
// isn't useful to highlight.)
function canTakeNext(course) {
  return !taken.has(course.id) && hasCourses(course.requires) && isMet(course.requires);
}

// A box's progress: for a shared box, "taken" once any one option is fully
// taken, "ready" if any course in it can be taken next.
function boxProgress(box) {
  if (box.kind === "course") {
    const course = nodesById[box.courses[0]];
    if (taken.has(course.id)) return "taken";
    return canTakeNext(course) ? "ready" : "";
  }
  if (box.kind === "choice") {
    if (box.options.some(option => option.every(code => taken.has(code)))) return "taken";
    return box.courses.some(code => canTakeNext(nodesById[code])) ? "ready" : "";
  }
  return "";
}

function applyProgress() {
  for (const box of Object.values(boxes)) {
    const button = el.stage.querySelector('[data-box="' + cssEscape(box.id) + '"]');
    if (!button) continue;
    button.classList.remove("taken", "ready");
    const progress = boxProgress(box);
    if (progress) button.classList.add(progress);
    button.innerHTML = boxInnerHtml(box);
  }
}

function updateTakenStatus() {
  if (taken.size === 0) {
    el.takenStatus.innerHTML = "";
    return;
  }
  el.takenStatus.innerHTML = "You've marked " + taken.size + (taken.size === 1 ? " course" : " courses") +
    ' as taken. <button type="button" class="text-button" id="clear-taken">Clear all marks</button>';
  document.getElementById("clear-taken").addEventListener("click", clearTaken);
}

// ===========================================================================
// 3. Which boxes to draw
// ===========================================================================

function isVisible(course) {
  if (course.status !== "active" && !el.showInactive.checked) return false;
  if (course.role === "elective" && !el.showElectives.checked) return false;
  if (course.role === "prerequisite" && !el.showOutside.checked) return false;
  return true;
}

// Which requirement an elective belongs to, e.g. "UUPPER-DIVISION MAJOR: D."
function groupKey(course) {
  return course.groups[0] || "Electives";
}

/*
  "Pick one of a few" requirements from the major's requirement tree
  (Part 3), e.g. "MATH 2A or 3A", or "MATH 2A-B, 3A-B or 34A-B". Each option
  is a list of courses (one course, or a sequence you take all of).
  Returns a list of option lists.
*/
function findChoiceSets() {
  const sets = [];
  function codesOf(item) {
    if (item.type === "course") return item.code ? [item.code] : null;
    if (item.type === "all" && item.items.every(i => i.type === "course" && i.code)) {
      return item.items.map(i => i.code);
    }
    return null;
  }
  function visit(node) {
    if (node.type === "choose" && node.count === 1 && node.items.length >= 2 && node.items.length <= CHOICE_MAX) {
      const options = node.items.map(codesOf);
      if (options.every(Boolean)) {
        sets.push(options);
        return;
      }
    }
    for (const item of node.items || []) visit(item);
  }
  for (const section of graph.major.sections) visit(section.requirement);
  return sets;
}

/*
  Builds three things:
    boxes    every box to draw. Kinds: "course" (one course), "choice"
             (interchangeable courses), "group" (a folded elective list),
             "pool" (a huge list kept as one box from Part 4)
    standIn  for every course on the map, the box that shows it
    arrows   which box needs which, with "alternative" for one-of options
*/
function chooseBoxes() {
  boxes = {};
  standIn = {};
  const shown = graph.nodes.filter(isVisible);
  const shownCodes = new Set(shown.map(c => c.id));
  let counter = 0;

  // a) interchangeable courses share one box
  for (const options of findChoiceSets()) {
    const visibleOptions = options
      .map(option => option.filter(code => shownCodes.has(code) && !standIn[code]))
      .filter(option => option.length);
    if (visibleOptions.length < 2) continue;
    counter += 1;
    const box = { id: "choice-" + counter, kind: "choice", options: visibleOptions, courses: visibleOptions.flat() };
    boxes[box.id] = box;
    for (const code of box.courses) standIn[code] = box.id;
  }

  // b) long elective lists fold into one box
  const electivesByGroup = {};
  for (const course of shown) {
    if (course.role === "elective" && !standIn[course.id]) {
      (electivesByGroup[groupKey(course)] = electivesByGroup[groupKey(course)] || []).push(course.id);
    }
  }
  for (const key of Object.keys(electivesByGroup)) {
    const codes = electivesByGroup[key];
    if (codes.length < COLLAPSE_AT || expanded.has(key)) continue;
    counter += 1;
    const box = { id: "group-" + counter, kind: "group", key: key, courses: codes, rule: describeGroupRule(key) };
    boxes[box.id] = box;
    for (const code of codes) standIn[code] = box.id;
  }

  // c) everything else gets its own box
  for (const course of shown) {
    if (!standIn[course.id]) {
      boxes[course.id] = { id: course.id, kind: "course", courses: [course.id] };
      standIn[course.id] = course.id;
    }
  }

  // d) huge lists from Part 4
  if (el.showElectives.checked) {
    for (const pool of graph.pools) {
      boxes[pool.id] = { id: pool.id, kind: "pool", pool: pool, courses: [] };
    }
  }

  arrows = buildArrows();
}

/*
  An arrow goes from box A to box B when a course in B lists a course in A
  as a prerequisite. If that prerequisite is hidden (say MATH 4A, a math
  course outside the Economics major), we keep walking back through ITS
  prerequisites until we reach courses that are on the map, so the order
  stays right even with outside courses hidden.
*/
function buildArrows() {
  const found = {};
  function addArrow(fromBox, toBox, type) {
    if (!fromBox || fromBox === toBox) return;
    const key = fromBox + ">" + toBox;
    if (!found[key] || type === "required") found[key] = { from: fromBox, to: toBox, type: type };
  }
  function walk(node, toBox, insideOr, visited) {
    if (!node) return;
    if (node.type === "course") {
      if (standIn[node.code]) {
        addArrow(standIn[node.code], toBox, insideOr ? "alternative" : "required");
      } else if (nodesById[node.code] && !visited.has(node.code)) {
        visited.add(node.code);
        walk(nodesById[node.code].requires, toBox, insideOr, visited);   // hidden: look further back
      }
      return;
    }
    if (node.type === "and" || node.type === "or") {
      for (const item of node.items) walk(item, toBox, insideOr || node.type === "or", visited);
    }
  }
  for (const code of Object.keys(standIn)) {
    walk(nodesById[code].requires, standIn[code], false, new Set([code]));
  }
  return removeShortcuts(removeLoops(Object.values(found)));
}

/*
  Folding courses into shared boxes can create a loop. Say a course in list
  A needs a course in list B, and a different course in B needs one in A:
  now A -> B and B -> A, and no left-to-right order fits both. We add the
  arrows one at a time, most trustworthy first (required arrows between
  single courses), and skip any arrow that would close a loop. The panel
  still lists every prerequisite in full, so nothing is lost there.
*/
function removeLoops(list) {
  function trust(arrow) {
    let score = arrow.type === "required" ? 0 : 2;
    if (boxes[arrow.from].kind === "group" || boxes[arrow.to].kind === "group") score += 1;
    return score;
  }
  const ordered = list.slice().sort((a, b) => trust(a) - trust(b));
  const out = {};
  function reaches(from, target) {
    const seen = new Set();
    const stack = [from];
    while (stack.length) {
      const current = stack.pop();
      if (current === target) return true;
      if (seen.has(current)) continue;
      seen.add(current);
      for (const next of out[current] || []) stack.push(next);
    }
    return false;
  }
  const kept = [];
  for (const arrow of ordered) {
    if (reaches(arrow.to, arrow.from)) continue;     // would close a loop
    (out[arrow.from] = out[arrow.from] || []).push(arrow.to);
    kept.push(arrow);
  }
  return kept;
}

/*
  Drop "shortcut" arrows. If MATH 3A -> MATH 3B -> MATH 4A, an arrow straight
  from MATH 3A to MATH 4A adds nothing you can't already see by following
  the chain, but it adds a long line across the map. (This is called a
  "transitive reduction".) For each arrow A -> B, we look for another way
  to get from A to B; if there is one, the direct arrow goes.
*/
function removeShortcuts(list) {
  const out = {};
  for (const arrow of list) (out[arrow.from] = out[arrow.from] || []).push(arrow.to);

  function reachableWithout(from, target, skipDirect) {
    const seen = new Set();
    const stack = (out[from] || []).filter(next => !(skipDirect && next === target));
    while (stack.length) {
      const current = stack.pop();
      if (current === target) return true;
      if (seen.has(current)) continue;
      seen.add(current);
      for (const next of out[current] || []) stack.push(next);
    }
    return false;
  }
  return list.filter(arrow => !reachableWithout(arrow.from, arrow.to, true));
}

function groupTitle(key) {
  // "UUPPER-DIVISION MAJOR: D." -> "Area D"; "...: Computer Engineering electives" -> that.
  const parts = key.split(": ");
  const label = parts.length > 1 ? parts.slice(1).join(": ") : readable(parts[0]);
  if (label.length <= 3) return "Area " + label.replace(".", "") + " electives";
  return label;
}

// The rule behind an elective list ("Complete at least 6 courses"), found in
// the major's requirement tree the same way build_graph.py labeled the groups.
function describeGroupRule(key) {
  let found = "";
  function visit(node, section, label) {
    if (found || node.type === "course" || node.type === "text") return;
    const here = node.label || label;
    const name = section + (here && here !== section ? ": " + here : "");
    if (name === key && (node.type === "choose" || node.type === "units")) {
      found = node.type === "units"
        ? "Earn at least " + node.units + " units from this list."
        : "Complete at least " + node.count + (node.count === 1 ? " course" : " courses") + " from this list.";
      return;
    }
    for (const item of node.items || []) visit(item, section, here);
  }
  for (const section of graph.major.sections) visit(section.requirement, section.name, "");
  return found;
}

// ===========================================================================
// 4. Layout
// ===========================================================================

/*
  dagre puts every box in a "layer" so that all arrows point left to right:
  a course is always to the right of the courses it needs. Within a layer,
  it orders boxes to keep arrows from crossing. Courses with no arrows at all
  (nothing in this major needs them and they need nothing) are taken out and
  shown in a row underneath, so they don't crowd the first layer.
*/
function layout() {
  const linked = new Set();
  for (const arrow of arrows) {
    linked.add(arrow.from);
    linked.add(arrow.to);
  }

  const g = new dagre.graphlib.Graph();
  // Layers: we want every course as far LEFT as its prerequisites allow
  // (a course with no prerequisites belongs at the start, not next to the
  // late course it leads to). dagre's "longest-path" ranker does the
  // opposite: it pushes courses as far right as possible. So we hand dagre
  // the arrows reversed (course -> its prerequisite) and draw right-to-left
  // ("RL"); the two flips cancel out, and every course ends up as far left
  // as it can go.
  g.setGraph({ rankdir: "RL", ranker: "longest-path", nodesep: ROW_GAP, ranksep: LAYER_GAP, marginx: 24, marginy: 24 });
  g.setDefaultEdgeLabel(function () { return {}; });

  const loose = [];
  for (const box of Object.values(boxes)) {
    box.height = boxHeight(box);
    if (linked.has(box.id)) {
      g.setNode(box.id, { width: BOX_WIDTH, height: box.height });
    } else {
      loose.push(box);
    }
  }
  for (const arrow of arrows) g.setEdge(arrow.to, arrow.from);      // reversed, see above
  dagre.layout(g);

  let width = 0;
  let height = 0;
  for (const id of g.nodes()) {
    const n = g.node(id);
    boxes[id].x = n.x - n.width / 2;      // dagre gives centers; we want top-left corners
    boxes[id].y = n.y - n.height / 2;
    width = Math.max(width, n.x + n.width / 2);
    height = Math.max(height, n.y + n.height / 2);
  }
  for (const arrow of arrows) {
    arrow.points = g.edge(arrow.to, arrow.from).points.slice().reverse();   // back to prerequisite -> course
  }

  // The row of unlinked courses, wrapped to the map's width.
  let looseTop = null;
  if (loose.length) {
    loose.sort((a, b) => (roleRank(a) - roleRank(b)) || a.id.localeCompare(b.id, "en", { numeric: true }));
    looseTop = (g.nodes().length ? height : 0) + 56;
    const perRow = Math.max(4, Math.floor(Math.max(width, 900) / (BOX_WIDTH + ROW_GAP)));
    let rowHeight = 0;
    let y = looseTop + 30;
    loose.forEach(function (box, i) {
      if (i > 0 && i % perRow === 0) {
        y += rowHeight + ROW_GAP;
        rowHeight = 0;
      }
      box.x = 24 + (i % perRow) * (BOX_WIDTH + ROW_GAP);
      box.y = y;
      rowHeight = Math.max(rowHeight, box.height);
      width = Math.max(width, box.x + BOX_WIDTH);
      height = Math.max(height, box.y + box.height);
    });
  }
  // Extra room at the bottom so the zoom buttons and the Key, which float
  // over the map's bottom corners, never sit on top of a box you need.
  return { width: width + 24, height: height + 80, looseTop: looseTop };
}

function roleRank(box) {
  if (box.kind !== "course") return 1;
  const order = { required: 0, choice: 1, elective: 2, prerequisite: 3 };
  return order[nodesById[box.id].role];
}

function boxHeight(box) {
  return BOX_PADDING + LINE_HEIGHT * boxLines(box).length;
}

// ===========================================================================
// 5. Drawing
// ===========================================================================

// The lines of text inside a box.
function boxLines(box) {
  if (box.kind === "course") {
    const course = nodesById[box.id];
    return [{ strong: true, text: (taken.has(course.id) ? "✓ " : "") + course.id }, { text: course.title }];
  }
  if (box.kind === "choice") {
    const lines = [{ small: true, text: "One of" }];
    for (const option of box.options) {
      const done = option.every(code => taken.has(code));
      lines.push({ strong: true, text: (done ? "✓ " : "") + joinCodes(option) });
    }
    return lines;
  }
  if (box.kind === "group") {
    const done = box.courses.filter(code => taken.has(code)).length;
    return [
      { strong: true, text: groupTitle(box.key) },
      { text: box.courses.length + " courses" + (done ? ", " + done + " taken" : "") + ". Click to see them." },
    ];
  }
  return [
    { strong: true, text: box.pool.list_name || box.pool.label },
    { text: "Choose from " + box.pool.courses.length + " courses" },
  ];
}

// ["MATH 2A", "MATH 2B"] -> "MATH 2A + 2B"
function joinCodes(codes) {
  let text = codes[0];
  const subject = codes[0].replace(/\s*\S+$/, "");
  for (const code of codes.slice(1)) {
    text += " + " + (code.startsWith(subject + " ") ? code.slice(subject.length + 1) : code);
  }
  return text;
}

function boxInnerHtml(box) {
  return boxLines(box).map(function (line) {
    const cls = line.strong ? "line strong" : line.small ? "line small" : "line";
    return '<span class="' + cls + '">' + escapeHtml(line.text) + "</span>";
  }).join("");
}

function boxClasses(box) {
  const classes = ["box", "kind-" + box.kind];
  if (box.kind === "course") {
    const course = nodesById[box.id];
    classes.push("role-" + course.role);
    if (course.status !== "active") classes.push("inactive");
  }
  if (box.kind === "choice") classes.push("role-choice");
  const progress = boxProgress(box);
  if (progress) classes.push(progress);
  return classes.join(" ");
}

function draw() {
  chooseBoxes();
  const size = layout();

  let html = '<svg class="arrows" width="' + size.width + '" height="' + size.height + '" aria-hidden="true">' +
    '<defs>' + arrowHead("head-plain") + arrowHead("head-needs") + arrowHead("head-unlocks") + "</defs>";
  arrows.forEach(function (arrow, i) {
    arrow.index = i;
    html += '<path class="arrow ' + arrow.type + '" data-arrow="' + i + '" d="' + pathFor(arrow.points) + '"/>';
  });
  html += "</svg>";

  if (size.looseTop !== null) {
    html += '<p class="loose-label" style="top:' + size.looseTop + 'px">' +
            "Not linked to other courses on this map (no prerequisites here, and nothing here needs them)</p>";
  }
  for (const box of Object.values(boxes)) {
    html += '<button type="button" class="' + boxClasses(box) + '" data-box="' + escapeHtml(box.id) + '" ' +
            'style="left:' + box.x + "px;top:" + box.y + "px;width:" + BOX_WIDTH + "px;height:" + box.height + 'px">' +
            boxInnerHtml(box) + "</button>";
  }

  el.stage.style.width = size.width + "px";
  el.stage.style.height = size.height + "px";
  el.stage.innerHTML = html;
  applyZoom();

  // The course finder suggests every course on the map, including ones
  // inside shared or folded boxes.
  el.courseList.innerHTML = "";
  for (const code of Object.keys(standIn).sort((a, b) => a.localeCompare(b, "en", { numeric: true }))) {
    const option = document.createElement("option");
    option.value = code;
    option.label = nodesById[code].title;
    el.courseList.appendChild(option);
  }

  if (selectedCourse && standIn[selectedCourse]) {
    selectCourse(selectedCourse, false);
  } else if (selectedBox && boxes[selectedBox]) {
    selectBox(selectedBox, false);
  } else {
    selectedBox = null;
    selectedCourse = null;
  }
}

function arrowHead(id) {
  return '<marker id="' + id + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
         '<path d="M0,0 L10,5 L0,10 z"/></marker>';
}

// A smooth line through dagre's points: straight to the first midpoint,
// then curves that bend at each point.
function pathFor(points) {
  let d = "M" + points[0].x + "," + points[0].y;
  for (let i = 1; i < points.length - 1; i++) {
    const mid = { x: (points[i].x + points[i + 1].x) / 2, y: (points[i].y + points[i + 1].y) / 2 };
    d += " Q" + points[i].x + "," + points[i].y + " " + mid.x + "," + mid.y;
  }
  const last = points[points.length - 1];
  d += " L" + last.x + "," + last.y;
  return d;
}

// Zoom uses CSS "zoom", which redraws text at the new size (sharp), unlike
// stretching a picture of it.
function applyZoom() {
  el.stage.style.zoom = zoom;
}

function setZoom(value, keepCenter) {
  const centerX = (el.map.scrollLeft + el.map.clientWidth / 2) / zoom;
  const centerY = (el.map.scrollTop + el.map.clientHeight / 2) / zoom;
  zoom = Math.min(1.6, Math.max(0.35, value));
  applyZoom();
  if (keepCenter) {
    el.map.scrollLeft = centerX * zoom - el.map.clientWidth / 2;
    el.map.scrollTop = centerY * zoom - el.map.clientHeight / 2;
  }
}

// Start with the whole map in view if that keeps text readable (zoom 0.75 or
// more); otherwise start at 0.75 at the top-left, where the first courses are.
function startView() {
  const width = parseFloat(el.stage.style.width);
  const height = parseFloat(el.stage.style.height);
  const fit = Math.min(1, el.map.clientWidth / width, el.map.clientHeight / height);
  setZoom(Math.max(isPhone() ? 0.65 : 0.75, fit), false);
  el.map.scrollTo(0, 0);
}

function fitToScreen() {
  const width = parseFloat(el.stage.style.width);
  const height = parseFloat(el.stage.style.height);
  setZoom(Math.min(1, el.map.clientWidth / width, el.map.clientHeight / height), false);
  el.map.scrollTo(0, 0);
}

document.getElementById("zoom-in").addEventListener("click", function () { setZoom(zoom * 1.2, true); });
document.getElementById("zoom-out").addEventListener("click", function () { setZoom(zoom / 1.2, true); });
document.getElementById("zoom-fit").addEventListener("click", fitToScreen);

// Ctrl + mouse wheel zooms the map (instead of the whole page).
el.map.addEventListener("wheel", function (event) {
  if (!event.ctrlKey) return;
  event.preventDefault();
  setZoom(zoom * (event.deltaY < 0 ? 1.1 : 1 / 1.1), true);
}, { passive: false });

// Drag the background with the mouse to move around. (On touch screens,
// normal finger scrolling already does this.)
let drag = null;
el.map.addEventListener("pointerdown", function (event) {
  if (event.pointerType !== "mouse" || event.target.closest(".box")) return;
  drag = { x: event.clientX, y: event.clientY, left: el.map.scrollLeft, top: el.map.scrollTop, moved: false };
});
window.addEventListener("pointermove", function (event) {
  if (!drag) return;
  const dx = event.clientX - drag.x;
  const dy = event.clientY - drag.y;
  if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
  el.map.scrollLeft = drag.left - dx;
  el.map.scrollTop = drag.top - dy;
});
window.addEventListener("pointerup", function (event) {
  if (drag && !drag.moved && !event.target.closest(".box") && event.target.closest("#map")) clearSelection();
  drag = null;
});

// ===========================================================================
// 6. Selecting a box or course
// ===========================================================================

el.stage.addEventListener("click", function (event) {
  const button = event.target.closest(".box");
  if (button) selectBox(button.dataset.box, false);
});

// Select a box (from a click on the map).
function selectBox(id, scrollToIt) {
  const box = boxes[id];
  if (!box) return;
  selectedBox = id;
  selectedCourse = box.kind === "course" ? id : null;
  highlight(id);
  if (scrollToIt) scrollToBox(id);
  showDetails(box.kind === "course" ? id : null, box);
  openSheet();
  rememberInAddress();
}

// Select a course by its code (from the finder or a link in the panel). If
// it shares a box, that box is highlighted and the panel shows the course.
function selectCourse(code, scrollToIt) {
  const folded = !standIn[code] || boxes[standIn[code]].kind === "group";
  if (folded) {
    const course = nodesById[code];
    if (course && course.role === "elective" && isVisible(course)) {
      expanded.add(groupKey(course));      // unfold its list first
      draw();
    }
  }
  const boxId = standIn[code];
  selectedCourse = code;
  selectedBox = boxId || null;
  if (boxId) {
    highlight(boxId);
    if (scrollToIt) scrollToBox(boxId);
  }
  showDetails(code);
  openSheet();
  rememberInAddress();
}

/*
  "Needs" = every box on any path leading into the selected one (walk the
  arrows backwards, then keep going). "Unlocks" = boxes one arrow forward.
*/
function highlight(id) {
  const needs = new Set();
  const stack = [id];
  while (stack.length) {
    const current = stack.pop();
    for (const arrow of arrows) {
      if (arrow.to === current && !needs.has(arrow.from)) {
        needs.add(arrow.from);
        stack.push(arrow.from);
      }
    }
  }
  const unlocks = new Set(arrows.filter(a => a.from === id).map(a => a.to));

  el.stage.classList.add("focused");
  for (const button of el.stage.querySelectorAll(".box")) {
    const boxId = button.dataset.box;
    button.classList.toggle("selected", boxId === id);
    button.classList.toggle("needs", needs.has(boxId));
    button.classList.toggle("unlocks", unlocks.has(boxId));
  }
  for (const path of el.stage.querySelectorAll(".arrow")) {
    const arrow = arrows[path.dataset.arrow];
    const onChain = (needs.has(arrow.to) || arrow.to === id) && needs.has(arrow.from);
    path.classList.toggle("needs", onChain);
    path.classList.toggle("unlocks", arrow.from === id);
  }
}

function clearSelection() {
  selectedBox = null;
  selectedCourse = null;
  el.stage.classList.remove("focused");
  for (const item of el.stage.querySelectorAll(".selected, .needs, .unlocks")) {
    item.classList.remove("selected", "needs", "unlocks");
  }
  showMajorSummary();
  closeSheet();
  rememberInAddress();
}

function scrollToBox(id) {
  const box = boxes[id];
  const visibleHeight = isPhone() ? el.map.clientHeight - window.innerHeight * 0.62 : el.map.clientHeight;
  el.map.scrollTo({
    left: (box.x + BOX_WIDTH / 2) * zoom - el.map.clientWidth / 2,
    top: (box.y + box.height / 2) * zoom - Math.max(60, visibleHeight / 2),
    behavior: "smooth",
  });
}

// ===========================================================================
// 7. The side panel (a bottom sheet on phones)
// ===========================================================================

function readable(name) {
  if (name !== name.toUpperCase()) return name;
  const lower = name.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

function readableGroup(key) {
  const parts = key.split(": ");
  return readable(parts[0]) + (parts.length > 1 ? ": " + parts.slice(1).join(": ") : "");
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function cssEscape(text) {
  return String(text).replace(/["\\]/g, "\\$&");
}

// A course code as a button that selects it.
function courseLink(code) {
  const course = nodesById[code];
  const text = (taken.has(code) ? "✓ " : "") + escapeHtml(code);
  if (course) {
    let note = "";
    if (course.status !== "active") note = ' <span class="note">(not offered now)</span>';
    else if (!standIn[code] && course.role === "prerequisite") note = ' <span class="note">(other major)</span>';
    return '<button type="button" class="course-link" data-code="' + escapeHtml(code) + '">' + text + "</button>" + note;
  }
  return "<strong>" + text + '</strong> <span class="note">(not in the current catalog)</span>';
}

// Turn a prerequisite tree (from Part 2) into nested "All of / One of" lists.
function treeHtml(node) {
  if (!node) return "";
  if (node.type === "course") {
    let text = courseLink(node.code);
    const extras = [];
    if (node.min_grade) extras.push(node.min_grade + " or better");
    if (node.concurrent) extras.push("can be taken at the same time");
    if (extras.length) text += ' <span class="note">(' + extras.join(", ") + ")</span>";
    return "<li>" + text + "</li>";
  }
  if (node.type === "condition") {
    const names = {
      standing: "Class standing", consent: "Instructor or department approval",
      restriction: "Major or program restriction", exam: "Exam score", other: "Other",
    };
    const detail = node.text ? ": " + escapeHtml(node.text) : "";
    return '<li><span class="tree-label">' + names[node.kind] + "</span>" + detail + "</li>";
  }
  const label = node.type === "and" ? "All of:" : "One of:";
  return '<li><span class="tree-label">' + label + '</span><ul class="tree">' +
         node.items.map(treeHtml).join("") + "</ul></li>";
}

function hasConditions(node) {
  if (!node) return false;
  if (node.type === "condition") return true;
  if (node.type === "course") return false;
  return node.items.some(hasConditions);
}

// Show a course (by code), or a shared box, in the panel.
function showDetails(code, box) {
  if (code && nodesById[code]) {
    showCourse(nodesById[code]);
  } else if (box && box.kind === "choice") {
    showChoice(box);
  } else if (box && box.kind === "group") {
    showGroup(box);
  } else if (box && box.kind === "pool") {
    showPool(box.pool);
  }
}

function showCourse(course) {
  const unlocks = new Set();
  for (const other of graph.nodes) {
    if (other.requires && JSON.stringify(other.requires).includes('"code":"' + course.id + '"')) {
      unlocks.add(other.id);
    }
  }
  const unlockList = Array.from(unlocks).filter(code => standIn[code])
    .sort((a, b) => a.localeCompare(b, "en", { numeric: true }));
  const isTaken = taken.has(course.id);
  const box = boxes[standIn[course.id]];

  let html = "<h2>" + escapeHtml(course.id) + "</h2>";
  html += '<p class="course-title">' + escapeHtml(course.title) + "</p>";
  if (course.units) html += '<p class="facts">' + escapeHtml(course.units) + " units</p>";

  html += '<p class="progress-row"><button type="button" class="taken-button' + (isTaken ? " is-taken" : "") +
          '" data-taken="' + escapeHtml(course.id) + '">' +
          (isTaken ? "✓ Taken (click to undo)" : "Mark as taken") + "</button></p>";
  if (!isTaken && canTakeNext(course)) {
    html += '<p class="ready-note">You\'ve taken the courses this needs' +
            (hasConditions(course.requires) ? ", but check the other conditions below." : ".") + "</p>";
  }
  if (course.status !== "active") {
    html += '<p><span class="flag">Not offered now</span> The catalog lists this course but marks it as not currently offered.</p>';
  }

  html += "<h3>In this " + programWord() + "</h3><p>" + ROLE_NAMES[course.role] + "</p>";
  if (course.groups.length) {
    html += "<ul>" + course.groups.map(g => "<li>" + escapeHtml(readableGroup(g)) + "</li>").join("") + "</ul>";
  }
  if (box && box.kind === "choice") {
    html += '<p class="note">Shares a box on the map with the courses you can take instead: ' +
            box.options.map(joinCodes).map(escapeHtml).join(", or ") + ".</p>";
  }
  if (course.role === "elective" && expanded.has(groupKey(course))) {
    html += '<p><button type="button" class="text-button" data-fold="' + escapeHtml(groupKey(course)) +
            '">Fold this list back into one box</button></p>';
  }

  html += '<h3><span class="needs-key">Needs</span></h3>';
  html += course.requires ? '<ul class="tree">' + treeHtml(course.requires) + "</ul>" : "<p>No course prerequisites listed.</p>";
  if (course.ambiguous) {
    html += '<p class="note">The catalog wording mixes "and" and "or" without punctuation, so this reading is a best guess. Check the wording below.</p>';
  }
  if (course.prereq_text) {
    html += '<p class="catalog-text">Catalog wording: "' + escapeHtml(course.prereq_text) + '"</p>';
  }

  html += '<h3><span class="unlocks-key">Unlocks in this ' + programWord() + "</span></h3>";
  html += unlockList.length
    ? "<ul>" + unlockList.map(code => "<li>" + courseLink(code) + "</li>").join("") + "</ul>"
    : "<p>Nothing on this map lists it as a prerequisite.</p>";

  html += "<h3>More</h3><ul>";
  html += '<li><button type="button" class="text-button" data-copy-link>Copy a link to this course</button></li>';
  html += '<li><a href="https://catalog.ucsb.edu/courses/' + encodeURIComponent(course.id) +
          '" target="_blank" rel="noopener">This course in the UCSB catalog</a></li>';
  if (course.level === "lower") {
    html += '<li><a href="https://assist.org/" target="_blank" rel="noopener">Community college equivalents on ASSIST</a></li>';
  }
  html += "</ul>";
  if (course.description) {
    html += "<details><summary>Course description</summary><p class=\"note\">" + escapeHtml(course.description) + "</p></details>";
  }
  setPanel(html, course.id + "  " + course.title);
}

function showChoice(box) {
  let html = "<h2>Take one of these</h2>";
  html += "<p>These courses meet the same requirement, so they share one box on the map. Pick any one option.</p>";
  html += '<ul class="course-list">';
  for (const option of box.options) {
    html += "<li>" + option.map(code => courseLink(code) + " " + escapeHtml(nodesById[code].title)).join("<br>and ") + "</li>";
  }
  html += "</ul>";
  setPanel(html, "Take one of: " + box.options.map(joinCodes).join(", "));
}

function showGroup(box) {
  const done = box.courses.filter(code => taken.has(code)).length;
  let html = "<h2>" + escapeHtml(groupTitle(box.key)) + "</h2>";
  html += '<p class="facts">' + escapeHtml(readableGroup(box.key)) + "</p>";
  if (box.rule) html += "<p>" + escapeHtml(box.rule) + "</p>";
  html += "<p>" + box.courses.length + " courses" + (done ? ", " + done + " marked as taken" : "") + ".</p>";
  html += '<p><button type="button" class="taken-button" data-unfold="' + escapeHtml(box.key) +
          '">Show these courses on the map</button></p>';
  html += '<ul class="course-list">';
  for (const code of box.courses.slice().sort((a, b) => a.localeCompare(b, "en", { numeric: true }))) {
    const course = nodesById[code];
    let flag = "";
    if (taken.has(code)) flag = ' <span class="flag flag-taken">taken</span>';
    else if (canTakeNext(course)) flag = ' <span class="flag flag-ready">can take next</span>';
    html += "<li>" + courseLink(code) + " " + escapeHtml(course.title) + flag + "</li>";
  }
  html += "</ul>";
  setPanel(html, groupTitle(box.key));
}

function showPool(pool) {
  let html = "<h2>" + escapeHtml(pool.list_name || pool.label) + "</h2>";
  html += '<p class="facts">' + escapeHtml(readable(pool.section)) + "</p>";
  html += "<p>Earn " + escapeHtml(pool.rule) + " from a list of " + pool.courses.length +
          " courses. The list is too long to draw, so it appears as one box.</p>";
  html += "<details><summary>Show all " + pool.courses.length + " courses</summary><p class=\"note\">" +
          pool.courses.map(escapeHtml).join(", ") + "</p></details>";
  setPanel(html, pool.list_name || pool.label);
}

function showMajorSummary() {
  if (!graph) return;
  let html = "<h2>" + escapeHtml(graph.major.name) + "</h2>";
  html += '<p class="facts">' + escapeHtml(graph.major.catalog_year) + " catalog</p>";
  html += "<p>" + graph.stats.courses_in_major + " courses. Each course sits to the right of the courses it needs, " +
          "and arrows point to what it unlocks.</p>";
  html += "<p>Click a course to trace what it needs and what it unlocks. Mark courses you've taken, and the ones you can take next get a green outline. The Key in the corner of the map explains the colors.</p>";

  const inMajor = graph.nodes.filter(n => n.in_major);
  const done = inMajor.filter(n => taken.has(n.id)).length;
  if (done) html += "<p>You've marked " + done + " of this " + programWord() + "'s " + inMajor.length + " courses as taken.</p>";

  if (expanded.size) {
    html += "<h3>Unfolded elective lists</h3><ul>";
    for (const key of expanded) {
      html += "<li>" + escapeHtml(groupTitle(key)) + ' <button type="button" class="text-button" data-fold="' +
              escapeHtml(key) + '">Fold back into one box</button></li>';
    }
    html += "</ul>";
  }

  html += "<h3>Requirements</h3><ul>";
  for (const section of graph.major.sections) html += "<li>" + escapeHtml(readable(section.name)) + "</li>";
  html += "</ul>";
  if (graph.major.narrative.length) {
    html += "<details><summary>Notes from the catalog</summary>" +
            graph.major.narrative.map(t => '<p class="note">' + escapeHtml(t) + "</p>").join("") + "</details>";
  }
  html += '<p class="note">Unofficial student project, built from the ' + escapeHtml(graph.major.catalog_year) +
          ' UCSB General Catalog. Requirements change; confirm your plan with a department advisor. <a href="' +
          escapeHtml(graph.major.source) + '" target="_blank" rel="noopener">Official requirements</a></p>';
  setPanel(html, graph.major.name);
}

// "major" or "minor", for the panel's wording.
function programWord() {
  return graph && graph.major.kind === "minor" ? "minor" : "major";
}

// Copies the address (which names the major and selected course) to the
// clipboard. Some browsers only allow this on secure (https) pages.
function copyLink(button) {
  function done(text) {
    button.textContent = text;
    setTimeout(function () { button.textContent = "Copy a link to this course"; }, 2500);
  }
  if (!navigator.clipboard) {
    done("Couldn't copy here; copy the address bar instead");
    return;
  }
  navigator.clipboard.writeText(location.href).then(
    function () { done("Link copied"); },
    function () { done("Couldn't copy here; copy the address bar instead"); });
}

function setPanel(html, handleText) {
  el.panelBody.className = "";
  el.panelBody.innerHTML = html;
  el.panelHandle.textContent = handleText;
}

// Buttons inside the panel. One listener handles them all, using the
// data-... attribute on the button that was clicked.
el.panelBody.addEventListener("click", function (event) {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.code) {
    selectCourse(button.dataset.code, true);
  } else if ("copyLink" in button.dataset) {
    copyLink(button);
  } else if (button.dataset.taken) {
    toggleTaken(button.dataset.taken);
  } else if (button.dataset.unfold) {
    expanded.add(button.dataset.unfold);
    selectedBox = null;
    selectedCourse = null;
    draw();
    showMajorSummary();
  } else if (button.dataset.fold) {
    expanded.delete(button.dataset.fold);
    selectedBox = null;
    selectedCourse = null;
    draw();
    showMajorSummary();
  }
});

// ===========================================================================
// 8. Phones
// ===========================================================================

function isPhone() {
  return window.innerWidth <= 800;
}

// On phones the panel is a sheet at the bottom of the screen. Selecting a
// course opens it; the handle at its top opens and closes it.
function openSheet() { el.panel.classList.add("open"); }
function closeSheet() { el.panel.classList.remove("open"); }
el.panelHandle.addEventListener("click", function () { el.panel.classList.toggle("open"); });

// On phones, "Find a course" and the Show checkboxes sit behind an Options button.
el.optionsButton.addEventListener("click", function () {
  const open = el.top.classList.toggle("show-options");
  el.optionsButton.setAttribute("aria-expanded", open ? "true" : "false");
});

// The key starts closed so it doesn't cover the map; the major summary
// points to it. After that, the browser remembers whether you opened it.
const LEGEND_KEY = "ucsb-prereq-map.key-open";
try {
  el.legend.open = localStorage.getItem(LEGEND_KEY) === "yes";
} catch (error) {
  el.legend.open = false;
}
el.legend.addEventListener("toggle", function () {
  try { localStorage.setItem(LEGEND_KEY, el.legend.open ? "yes" : "no"); } catch (error) { /* not saved */ }
});

start();
