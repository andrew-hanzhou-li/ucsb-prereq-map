/*
  app.js: the UCSB Prerequisite Map website.

  What happens, in order:
    1. Load the list of majors and minors into the picker and the lists on
       the front page.
    2. When one is picked, load its graph (built by build_graph.py in Part 4).
       The address bar remembers the program and the selected course
       (#economics-ba/ECON+10A), so any view can be shared as a link.
       "Major" in the code below means major or minor.
    3. Decide which courses to show: every course in the major, plus the
       courses from other departments that its required courses need
       (MATH 4A for Computer Engineering's ECE 10A).
    4. Lay them out like a department flowchart:
         - required courses in rows called "steps": a course's
           prerequisites are always in an earlier step (or the same step,
           for "may be taken at the same time"),
         - each elective list in its own block underneath.
       Boxes wrap to fill the screen's width; the page scrolls down.
    5. No arrows until you point at or click a course. Then amber arrows
       trace everything it needs, all the way back, blue arrows show what
       it unlocks, and everything else fades.
    6. "Mark as taken": courses you've taken turn green, and courses whose
       prerequisites you've now met get a green outline. Marks are saved in
       this browser.

  The same code runs two ways:
    - as the website, loading each major's file from data/ when needed,
    - as one self-contained file (built by build_single.py), where every
      major is already inside the page in window.EMBEDDED.
  Everything is plain JavaScript: no libraries, no server code.
*/

// ===========================================================================
// Settings
// ===========================================================================

const SAVE_KEY = "ucsb-prereq-map.taken";   // where "taken" marks are saved in the browser
const REPO_URL = "https://github.com/andrew-hanzhou-li/ucsb-prereq-map";   // linked as "Source code" in the footer
const BACK_LIMIT = 50;        // how many earlier courses the panel's Back button remembers

const ROLE_NAMES = {
  required: "Required",
  choice: "Required (pick one of a few)",
  elective: "Elective",
  prerequisite: "Not in this program, but needed for a course that is",
};

// ===========================================================================
// State
// ===========================================================================

let majors = [];            // majors and minors (data/majors.json)
let currentMajor = null;    // the entry from majors.json that's on the map
let graph = null;           // the loaded major's graph
let loading = 0;            // counts loads, so a slow one can't replace a newer one
let nodesById = {};         // course code -> course from the graph
let taken = loadTaken();    // course codes marked as taken (shared by all majors)

// Rebuilt by draw():
let shown = new Set();      // course codes that have a box on the map
let stepOf = {};            // course code -> step number (core courses only)
let partners = {};          // course code -> the other options in its "pick one" requirement
let prereqCache = {};       // course code -> its prerequisites that are on the map

let selected = null;        // course code (or pool id) that's selected
let previous = [];          // courses selected before this one, for the Back button
let hoverTimer = null;

const el = {
  majorInput: document.getElementById("major-input"),
  majorList: document.getElementById("major-list"),
  courseInput: document.getElementById("course-input"),
  courseList: document.getElementById("course-list"),
  allLink: document.getElementById("all-link"),
  toggles: document.getElementById("toggles"),
  showElectives: document.getElementById("show-electives"),
  showOutside: document.getElementById("show-outside"),
  showInactive: document.getElementById("show-inactive"),
  map: document.getElementById("map"),
  stage: document.getElementById("stage"),
  empty: document.getElementById("empty"),
  offUp: document.getElementById("offscreen-up"),
  offDown: document.getElementById("offscreen-down"),
  notice: document.getElementById("notice"),
  welcome: document.getElementById("welcome"),
  browseMajors: document.getElementById("browse-majors"),
  browseMinors: document.getElementById("browse-minors"),
  panel: document.getElementById("panel"),
  panelHandle: document.getElementById("panel-handle"),
  panelBody: document.getElementById("panel-body"),
  takenStatus: document.getElementById("taken-status"),
  footerCatalog: document.getElementById("footer-catalog"),
  footerRepo: document.getElementById("footer-repo"),
  footerDownload: document.getElementById("footer-download"),
  about: document.getElementById("about"),
  top: document.querySelector(".top"),
  optionsButton: document.getElementById("options-button"),
};

// ===========================================================================
// 1. Majors list, pickers and loading a major
// ===========================================================================

async function start() {
  try {
    majors = window.EMBEDDED ? window.EMBEDDED.majors : (await (await fetch("data/majors.json")).json()).majors;
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
  // The single file doesn't need a link to download itself.
  if (window.EMBEDDED) el.footerDownload.hidden = true;
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
  let before = "";
  input.addEventListener("focus", function () {
    before = input.value;
    input.value = "";
  });
  input.addEventListener("blur", function () {
    if (input.value.trim() === "") input.value = before;
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
  const code = selected && nodesById[selected] ? selected : null;
  const target = hashFor(currentMajor, code);
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
    if (wanted.course !== selected) selectCourse(wanted.course, true);
  } else if (selected) {
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
  shown = new Set();
  selected = null;
  previous = [];
  focus = null;
  el.offUp.hidden = true;
  el.offDown.hidden = true;
  el.stage.innerHTML = "";
  el.courseList.innerHTML = "";
  el.majorInput.value = "";
  el.empty.hidden = false;
  el.notice.hidden = true;
  el.welcome.hidden = false;
  el.allLink.hidden = true;
  el.toggles.disabled = true;
  el.courseInput.disabled = true;
  el.footerCatalog.textContent = "Built from the UCSB General Catalog.";
  document.title = "UCSB Prerequisite Map";
  el.panel.hidden = true;           // nothing to show until a map is open
  closeSheet();
}

// One major's graph: from the page itself (single file) or from data/.
async function fetchMajor(major) {
  if (!window.EMBEDDED) return (await fetch("data/" + major.file)).json();
  // The single file stores each course's details once (in "courses") and
  // each major's own facts about it (role, step...) separately. Put the two
  // back together into the same shape as a data/ file.
  const program = window.EMBEDDED.programs[major.file];
  const courses = window.EMBEDDED.courses;
  return Object.assign({}, program, {
    nodes: program.nodes.map(n => Object.assign({}, courses[n.id], n)),
  });
}

// Load a major's graph and draw it. Returns false if it didn't load.
async function loadMajor(major) {
  const ticket = ++loading;
  el.majorInput.value = major.name;
  el.majorInput.blur();
  let loaded;
  try {
    loaded = await fetchMajor(major);
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
  selected = null;
  previous = [];
  el.empty.hidden = true;
  el.notice.hidden = true;
  el.panel.hidden = false;
  el.allLink.hidden = false;
  el.toggles.disabled = false;
  el.courseInput.disabled = false;
  el.footerCatalog.textContent = "Built from the " + graph.major.catalog_year + " UCSB General Catalog. ";
  const source = document.createElement("a");
  source.href = graph.major.source;
  source.textContent = "Official requirements for " + graph.major.name;
  el.footerCatalog.appendChild(source);
  document.title = graph.major.name + " | UCSB Prerequisite Map";

  draw();
  el.map.scrollTo(0, 0);
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
  if (selected) showDetails(selected);
}

function clearTaken() {
  taken = new Set();
  saveTaken();
  updateTakenStatus();
  applyProgress();
  if (selected) showDetails(selected); else showMajorSummary();
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

function progressOf(code) {
  if (taken.has(code)) return "taken";
  return canTakeNext(nodesById[code]) ? "ready" : "";
}

function applyProgress() {
  for (const button of el.stage.querySelectorAll(".box[data-code]")) {
    const code = button.dataset.code;
    button.classList.remove("taken", "ready");
    const progress = progressOf(code);
    if (progress) button.classList.add(progress);
    button.innerHTML = boxInnerHtml(code);
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
// 3. Which courses to show
// ===========================================================================

function isActiveEnough(course) {
  return course.status === "active" || el.showInactive.checked;
}

/*
  The courses on the map:
    - every course in the major (electives only if "Electives" is ticked;
      courses not offered now only if that box is ticked),
    - courses from other departments that the major's required courses need.
      For "one of" prerequisites, nothing extra is added if the major already
      has one of the options (CMPSC 130A needs ECE 139 or PSTAT 120A; ECE 139
      is in Computer Engineering, so PSTAT 120A isn't added). If none of the
      options is in the major, the first one the catalog lists is added.
      "Every outside course" adds all the rest.
*/
function chooseShown() {
  const result = new Set();
  for (const course of graph.nodes) {
    if (!course.in_major || !isActiveEnough(course)) continue;
    if (course.role === "elective" && !el.showElectives.checked) continue;
    result.add(course.id);
  }
  if (el.showOutside.checked) {
    for (const course of graph.nodes) {
      if (!course.in_major && course.status === "active") result.add(course.id);
    }
    return result;
  }

  const needed = [];
  function want(code) {
    const course = nodesById[code];
    if (!course || result.has(code) || course.status !== "active") return;
    result.add(code);
    needed.push(code);
  }
  function walk(node) {
    if (!node) return;
    if (node.type === "course") {
      want(node.code);
    } else if (node.type === "and") {
      node.items.forEach(walk);
    } else if (node.type === "or") {
      const options = node.items.filter(hasCourses);
      if (!options.length) return;
      const covered = options.some(option => coursesIn(option).some(code => result.has(code)));
      if (!covered) walk(options[0]);
    }
  }
  for (const course of graph.nodes) {
    if (course.in_major && result.has(course.id) && (course.role === "required" || course.role === "choice")) {
      walk(course.requires);
    }
  }
  // Outside courses can need outside courses of their own (PHYS 7B needs PHYS 7A).
  while (needed.length) walk(nodesById[needed.pop()].requires);
  return result;
}

function coursesIn(node) {
  if (!node) return [];
  if (node.type === "course") return [node.code];
  if (node.type === "condition") return [];
  return node.items.flatMap(coursesIn);
}

/*
  "Pick one of a few" requirements from the major's requirement tree
  (Part 3), e.g. "MATH 2A or 3A". Returns, for each course in one, the
  other options, so its box can say "or MATH 2A".
*/
function findPartners() {
  const result = {};
  function codesOf(item) {
    if (item.type === "course") return item.code ? [item.code] : null;
    if (item.type === "all" && item.items.every(i => i.type === "course" && i.code)) {
      return item.items.map(i => i.code);
    }
    return null;
  }
  function visit(node) {
    if (node.type === "choose" && node.count === 1 && node.items.length >= 2 && node.items.length <= 4) {
      const options = node.items.map(codesOf);
      if (options.every(Boolean)) {
        options.forEach(function (option, i) {
          const others = options.filter((_, j) => j !== i).map(joinCodes);
          for (const code of option) result[code] = others;
        });
        return;
      }
    }
    for (const item of node.items || []) visit(item);
  }
  for (const section of graph.major.sections) visit(section.requirement);
  return result;
}

/*
  A course's prerequisites that are on the map: {from, type, concurrent}.
  type "required" or "alternative" (one option of a "one of"). If a
  prerequisite isn't on the map (an outside course you didn't ask for), we
  look further back through ITS prerequisites, so the chain stays unbroken.

  A "one of" only counts as a choice if more than one of its options is on
  the map. ECE 152A needs "ECE 15A and 10A, or CMPSC 30 or 64"; with
  CMPSC 30 and 64 off the map, ECE 15A and 10A are what this major takes,
  so their arrows are solid, not dashed. (An option that only reaches the
  map by looking back through a hidden course doesn't count while another
  option is on the map itself.)
*/
function prereqsOnMap(code) {
  if (prereqCache[code]) return prereqCache[code];
  const visited = new Set([code]);
  function walk(node) {
    if (!node) return [];
    if (node.type === "course") {
      if (node.code === code) return [];
      if (shown.has(node.code)) {
        return [{ from: node.code, type: "required", concurrent: Boolean(node.concurrent), throughHidden: false }];
      }
      if (nodesById[node.code] && !visited.has(node.code)) {
        visited.add(node.code);
        // Hidden: look further back.
        return walk(nodesById[node.code].requires).map(p => Object.assign({}, p, { throughHidden: true }));
      }
      return [];
    }
    if (node.type === "and") return node.items.flatMap(walk);
    if (node.type === "or") {
      let options = node.items.map(walk).filter(found => found.length);
      const onMapItself = options.filter(found => found.some(p => !p.throughHidden));
      if (onMapItself.length) options = onMapItself;
      if (options.length <= 1) return options[0] || [];
      return options.flat().map(p => Object.assign({}, p, { type: "alternative" }));
    }
    return [];
  }
  const found = {};
  for (const p of walk(nodesById[code] && nodesById[code].requires)) {
    if (!found[p.from] || p.type === "required") found[p.from] = { from: p.from, type: p.type, concurrent: p.concurrent };
  }
  prereqCache[code] = Object.values(found);
  return prereqCache[code];
}

// Everything on the map that leads to a course, all the way back.
function ancestorsOf(code) {
  const result = new Set();
  const stack = [code];
  while (stack.length) {
    for (const p of prereqsOnMap(stack.pop())) {
      if (!result.has(p.from)) {
        result.add(p.from);
        stack.push(p.from);
      }
    }
  }
  return result;
}

// Courses on the map that list this one as a prerequisite.
function unlocksOf(code) {
  return Array.from(shown).filter(other => prereqsOnMap(other).some(p => p.from === code));
}

// ===========================================================================
// 4. Building the page
// ===========================================================================

function bySortKey(a, b) {
  return a.localeCompare(b, "en", { numeric: true });
}

/*
  Steps start from each course's "column" in the graph file (Part 4): the
  number of quarters of prerequisites before it, with upper-division courses
  never placed before the major's first upper-division core course (that's
  what puts ECE 139, which has no course prerequisites, with ECE 152A).

  The column for "MATH 4A or 4AI" counts the earlier of the two, but the map
  may show only MATH 4A. So each course is then pushed below the
  prerequisites it actually shows (to the same step, for "may be taken at
  the same time"). Only steps that have a course in them are numbered.
*/
function assignSteps(codes) {
  const level = {};
  for (const code of codes) level[code] = nodesById[code].column;
  for (let pass = 0; pass < codes.length; pass++) {
    let moved = false;
    for (const code of codes) {
      for (const p of prereqsOnMap(code)) {
        if (p.type !== "required" || level[p.from] === undefined) continue;
        const needed = level[p.from] + (p.concurrent ? 0 : 1);
        if (level[code] < needed) {
          level[code] = needed;
          moved = true;
        }
      }
    }
    if (!moved) break;
  }
  return level;
}

function core() {
  return Array.from(shown).filter(code => nodesById[code].role !== "elective");
}

function electiveGroups() {
  const groups = {};
  for (const code of shown) {
    const course = nodesById[code];
    if (course.role !== "elective") continue;
    const key = course.groups[0] || "Electives";
    (groups[key] = groups[key] || []).push(code);
  }
  return groups;
}

function draw() {
  shown = chooseShown();
  partners = findPartners();
  prereqCache = {};

  const coreCodes = core();
  const level = assignSteps(coreCodes);
  const columns = Array.from(new Set(coreCodes.map(code => level[code]))).sort((a, b) => a - b);
  stepOf = {};
  for (const code of coreCodes) stepOf[code] = columns.indexOf(level[code]) + 1;

  let html = '<svg class="arrows" aria-hidden="true"><defs>' +
             arrowHead("head-needs") + arrowHead("head-chain") + arrowHead("head-unlocks") + "</defs></svg>";
  html += mapHeader();

  columns.forEach(function (column, i) {
    const codes = coreCodes.filter(code => level[code] === column)
      .sort((a, b) => (roleRank(a) - roleRank(b)) || bySortKey(a, b));
    const label = i === 0 ? "Step 1 · no prerequisites in this " + programWord() : "Step " + (i + 1);
    html += '<section class="row step-row"><h3 class="row-label">' + escapeHtml(label) + "</h3>" +
            '<div class="grid">' + codes.map(boxHtml).join("") + "</div></section>";
  });

  const groups = electiveGroups();
  for (const key of Object.keys(groups).sort(bySortKey)) {
    const codes = groups[key].sort((a, b) => (nodesById[a].column - nodesById[b].column) || bySortKey(a, b));
    const rule = describeGroupRule(key);
    html += '<section class="row elective-row"><h3 class="row-label">' + escapeHtml(groupTitle(key)) +
            ' <span class="row-count">· ' + codes.length + " courses" + (rule ? " · " + escapeHtml(rule) : "") +
            "</span></h3>" + '<div class="grid">' + codes.map(boxHtml).join("") + "</div></section>";
  }

  // Huge lists ("any upper-division course in Letters and Science") from
  // Part 4 stay as one card each.
  if (el.showElectives.checked && graph.pools.length) {
    html += '<section class="row elective-row"><h3 class="row-label">Open-ended electives</h3><div class="grid">';
    for (const pool of graph.pools) {
      html += '<button type="button" class="box kind-pool" data-pool="' + escapeHtml(pool.id) + '">' +
              '<span class="line strong">' + escapeHtml(pool.list_name || pool.label) + "</span>" +
              '<span class="line">Choose from ' + pool.courses.length + " courses</span></button>";
    }
    html += "</div></section>";
  }
  if (!shown.size && !graph.pools.length) {
    html += '<p class="map-note">Nothing to show with these settings. Tick "Electives" or "Courses not offered now" above.</p>';
  }

  el.stage.innerHTML = html;

  // The course finder suggests every course on the map.
  el.courseList.innerHTML = "";
  for (const code of Array.from(shown).sort(bySortKey)) {
    const option = document.createElement("option");
    option.value = code;
    option.label = nodesById[code].title;
    el.courseList.appendChild(option);
  }

  if (selected && (shown.has(selected) || nodesById[selected])) {
    focusOn(selected);
  } else if (selected && selected.startsWith("pool-")) {
    focusOn(null);
  } else {
    selected = null;
    focusOn(null);
  }
}

function mapHeader() {
  return '<div class="map-head">' +
    '<p class="map-hint"><span class="wide-only">Point at or click a course to trace what it needs and what it unlocks. <kbd>Esc</kbd> clears it.</span>' +
    '<span class="narrow-only">Tap a course to trace what it needs and what it unlocks.</span></p>' +
    '<ul class="key-row" aria-label="Key">' +
    '<li><span class="swatch required"></span>Required</li>' +
    '<li><span class="swatch choice"></span>Pick one of a few</li>' +
    '<li><span class="swatch elective"></span>Elective</li>' +
    '<li><span class="swatch outside"></span>Other department, needed first</li>' +
    (el.showInactive.checked ? '<li><span class="swatch inactive"></span>Not offered now</li>' : "") +
    '<li><span class="swatch taken"></span>Taken</li>' +
    '<li><span class="swatch ready"></span>Can take next</li>' +
    '<li><span class="key-line needs"></span>Needs</li>' +
    '<li><span class="key-line unlocks"></span>Unlocks</li>' +
    "</ul></div>";
}

function roleRank(code) {
  const order = { required: 0, choice: 1, elective: 2, prerequisite: 3 };
  return order[nodesById[code].role];
}

function boxHtml(code) {
  return '<button type="button" class="' + boxClasses(code) + '" data-code="' + escapeHtml(code) + '">' +
         boxInnerHtml(code) + "</button>";
}

function boxInnerHtml(code) {
  const course = nodesById[code];
  let html = '<span class="line strong">' + (taken.has(code) ? "✓ " : "") + escapeHtml(code) + "</span>" +
             '<span class="line title">' + escapeHtml(course.title || "") + "</span>";
  let tag = "";
  if (course.status !== "active") tag = "not offered now";
  else if (course.role === "choice" && partners[code]) tag = "or " + partners[code].join(" or ");
  else if (course.role === "prerequisite") tag = "needed first";
  if (tag) html += '<span class="line tag">' + escapeHtml(tag) + "</span>";
  return html;
}

function boxClasses(code) {
  const course = nodesById[code];
  const classes = ["box", "role-" + course.role];
  if (course.status !== "active") classes.push("inactive");
  const progress = progressOf(code);
  if (progress) classes.push(progress);
  return classes.join(" ");
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

function groupTitle(key) {
  // "UUPPER-DIVISION MAJOR: D." -> "Area D electives"; "...: Computer Engineering electives" -> that.
  const parts = key.split(": ");
  const label = parts.length > 1 ? parts.slice(1).join(": ") : readable(parts[0]);
  if (label.length <= 3) return "Area " + label.replace(".", "") + " electives";
  return label;
}

// The rule behind an elective list ("complete at least 6"), found in the
// major's requirement tree the same way build_graph.py labeled the groups.
function describeGroupRule(key) {
  let found = "";
  function visit(node, section, label) {
    if (found || node.type === "course" || node.type === "text") return;
    const here = node.label || label;
    const name = section + (here && here !== section ? ": " + here : "");
    if (name === key && (node.type === "choose" || node.type === "units")) {
      found = node.type === "units"
        ? "earn at least " + node.units + " units"
        : "complete at least " + node.count;
      return;
    }
    for (const item of node.items || []) visit(item, section, here);
  }
  for (const section of graph.major.sections) visit(section.requirement, section.name, "");
  return found;
}

// ===========================================================================
// 5. Highlighting and arrows
// ===========================================================================

function boxFor(code) {
  return el.stage.querySelector('.box[data-code="' + cssEscape(code) + '"]');
}

// While a course is lit up, the courses it unlocks grow a little and the
// unrelated ones shrink a little, so the ones that matter stand out. (More
// than 1.05 and two grown boxes side by side would touch; see .grid's gap.)
const SCALE = { selected: 1.05, unlocks: 1.05, needs: 1, other: 0.9 };

let focus = null;           // the lit-up course (hovered or clicked) and its relatives

/*
  Light up one course: it, everything that leads to it (amber) and what it
  directly unlocks (blue); fade and shrink the rest; draw the arrows.
  focusOn(null) clears it. Hovering calls this too, then puts the clicked
  course back.
*/
function focusOn(code) {
  const svg = el.stage.querySelector(".arrows");
  if (!svg) return;
  svg.querySelectorAll("path.arrow").forEach(p => p.remove());

  const onMap = code && shown.has(code);
  el.stage.classList.toggle("focused", Boolean(onMap));
  const needs = onMap ? ancestorsOf(code) : new Set();
  const unlocks = onMap ? new Set(unlocksOf(code)) : new Set();
  focus = onMap ? { code: code, needs: needs, unlocks: unlocks } : null;
  function scaleOf(c) {
    if (!onMap) return 1;
    if (c === code) return SCALE.selected;
    if (unlocks.has(c)) return SCALE.unlocks;
    if (needs.has(c)) return SCALE.needs;
    return SCALE.other;
  }
  for (const button of el.stage.querySelectorAll(".box[data-code]")) {
    const c = button.dataset.code;
    button.classList.toggle("selected", c === code);
    button.classList.toggle("needs", needs.has(c));
    button.classList.toggle("unlocks", unlocks.has(c));
    const scale = scaleOf(c);
    button.style.transform = scale === 1 ? "" : "scale(" + scale + ")";
  }
  updateOffscreen();
  if (!onMap) return;

  // The svg covers the whole map, so arrows can join boxes in any rows.
  svg.setAttribute("width", el.stage.scrollWidth);
  svg.setAttribute("height", el.stage.scrollHeight);
  // Where each box ends up once it has grown or shrunk (from its center).
  // Worked out from the layout rather than measured on screen, because the
  // boxes are still animating to their new size at this moment.
  const rects = {};
  function rect(c) {
    if (!rects[c]) {
      const box = boxFor(c);
      if (!box) return null;
      const s = scaleOf(c);
      const w = box.offsetWidth;
      const h = box.offsetHeight;
      rects[c] = { x: box.offsetLeft + w * (1 - s) / 2, y: box.offsetTop + h * (1 - s) / 2, w: w * s, h: h * s };
    }
    return rects[c];
  }
  let paths = "";
  function arrow(from, to, cls) {
    const a = rect(from);
    const b = rect(to);
    if (a && b) paths += '<path class="arrow ' + cls + '" d="' + curve(a, b) + '"/>';
  }
  // Farther back first, so the selected course's own arrows end up on top.
  for (const ancestor of needs) {
    for (const p of prereqsOnMap(ancestor)) arrow(p.from, ancestor, "chain" + (p.type === "alternative" ? " alternative" : ""));
  }
  for (const p of prereqsOnMap(code)) arrow(p.from, code, "needs" + (p.type === "alternative" ? " alternative" : ""));
  for (const u of unlocks) arrow(code, u, "unlocks");
  svg.insertAdjacentHTML("beforeend", paths);
}

/*
  Linked courses that are off screen. In a long list (Anthropology's 80
  electives), the courses ANTH 2 unlocks can all be far below. A bar at the
  bottom (or top) edge of the map names them, and clicking it scrolls there.
*/
function updateOffscreen() {
  for (const bar of [el.offUp, el.offDown]) bar.hidden = true;
  if (!focus) return;
  const view = visibleArea();
  const groups = { up: { self: false, unlocks: [], needs: [] }, down: { self: false, unlocks: [], needs: [] } };
  function place(c, kind) {
    const box = boxFor(c);
    if (!box) return;
    const r = box.getBoundingClientRect();
    const side = r.bottom < view.top + 8 ? "up" : r.top > view.bottom - 8 ? "down" : null;
    if (!side) return;
    if (kind === "self") groups[side].self = true; else groups[side][kind].push({ code: c, top: r.top });
  }
  place(focus.code, "self");
  focus.unlocks.forEach(c => place(c, "unlocks"));
  focus.needs.forEach(c => place(c, "needs"));

  for (const side of ["up", "down"]) {
    const g = groups[side];
    // "↓ Further down: ANTH 2 unlocks ANTH 105BW, ANTH 106 and 11 more"
    const parts = [];
    if (g.unlocks.length) parts.push("unlocks " + listCodes(g.unlocks));
    if (g.needs.length) parts.push("needs " + listCodes(g.needs));
    const arrowSign = side === "up" ? "↑ " : "↓ ";
    let text;
    if (parts.length) {
      text = arrowSign + (side === "up" ? "Further up: " : "Further down: ") + focus.code + " " + parts.join("; ");
      if (g.self) text += " · and " + focus.code + " itself";
    } else if (g.self) {
      text = arrowSign + "Back to " + focus.code;
    } else {
      continue;
    }
    const bar = side === "up" ? el.offUp : el.offDown;
    bar.textContent = text;
    bar.hidden = false;
  }
  // On phones, keep the bottom bar above the course sheet when it's open.
  el.offDown.style.bottom = (view.coveredBelow + 10) + "px";
}

// "ANTH 105BW, ANTH 106, ANTH 120MJ and 10 more", nearest first.
function listCodes(items) {
  const codes = items.sort((a, b) => a.top - b.top).map(i => i.code);
  const first = codes.slice(0, 3).join(", ");
  return codes.length > 3 ? first + " and " + (codes.length - 3) + " more" : first;
}

// The part of the map you can see (in screen coordinates), and how much of
// its bottom the phone's course sheet covers.
function visibleArea() {
  const map = el.map.getBoundingClientRect();
  let bottom = map.bottom;
  if (isPhone() && el.panel.classList.contains("open")) bottom = Math.min(bottom, el.panel.getBoundingClientRect().top);
  return { top: map.top, bottom: bottom, coveredBelow: Math.max(0, map.bottom - bottom) };
}

// Clicking a bar keeps the course selected (if it was only hovered) and
// scrolls to the nearest of the linked courses in that direction.
function jumpOffscreen(side) {
  if (!focus) return;
  const code = focus.code;
  if (selected !== code) selectCourse(code, false);
  const view = visibleArea();
  const targets = [code, ...focus.unlocks, ...focus.needs]
    .map(c => boxFor(c))
    .filter(Boolean)
    .map(box => box.getBoundingClientRect())
    .filter(r => side === "up" ? r.bottom < view.top + 8 : r.top > view.bottom - 8);
  if (!targets.length) return;
  // Down: the nearest one below goes near the top, so the ones after it show too.
  // Up: the nearest one above goes near the bottom.
  const target = side === "down"
    ? targets.reduce((a, b) => (b.top < a.top ? b : a))
    : targets.reduce((a, b) => (b.bottom > a.bottom ? b : a));
  const shift = side === "down" ? target.top - view.top - 70 : target.bottom - view.bottom + 70;
  el.map.scrollTo({ top: el.map.scrollTop + shift, behavior: "smooth" });
}

for (const [bar, side] of [[document.getElementById("offscreen-up"), "up"], [document.getElementById("offscreen-down"), "down"]]) {
  bar.addEventListener("click", function () { jumpOffscreen(side); });
  // Moving the mouse from a hovered course to the bar keeps the preview.
  bar.addEventListener("pointerenter", function () { clearTimeout(hoverTimer); });
  bar.addEventListener("pointerleave", function (event) {
    if (event.pointerType !== "mouse") return;
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(function () { focusOn(selected); }, 250);
  });
}

let scrollFrame = null;
el.map.addEventListener("scroll", function () {
  if (scrollFrame) return;
  scrollFrame = requestAnimationFrame(function () { scrollFrame = null; updateOffscreen(); });
});

/*
  A curved arrow from box a to box b. Going down the page (the usual case:
  an earlier step to a later one), it leaves a's bottom and enters b's top.
  Going up, the reverse. Within one row, it goes side to side.
*/
function curve(a, b) {
  let x1, y1, x2, y2;
  if (b.y >= a.y + a.h - 2) {
    x1 = a.x + a.w / 2; y1 = a.y + a.h; x2 = b.x + b.w / 2; y2 = b.y;
  } else if (b.y + b.h <= a.y + 2) {
    x1 = a.x + a.w / 2; y1 = a.y; x2 = b.x + b.w / 2; y2 = b.y + b.h;
  } else {
    const right = a.x < b.x;
    x1 = right ? a.x + a.w : a.x; y1 = a.y + a.h / 2;
    x2 = right ? b.x : b.x + b.w; y2 = b.y + b.h / 2;
    const bend = Math.max(24, Math.abs(x2 - x1) * 0.35) * (right ? 1 : -1);
    return "M" + x1 + "," + y1 + " C" + (x1 + bend) + "," + y1 + " " + (x2 - bend) + "," + y2 + " " + x2 + "," + y2;
  }
  const bend = Math.max(Math.abs(y2 - y1) * 0.4, 20) * (y2 > y1 ? 1 : -1);
  return "M" + x1 + "," + y1 + " C" + x1 + "," + (y1 + bend) + " " + x2 + "," + (y2 - bend) + " " + x2 + "," + y2;
}

function arrowHead(id) {
  return '<marker id="' + id + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
         '<path d="M0,0 L10,5 L0,10 z"/></marker>';
}

// Boxes move when the window is resized, so redraw the arrows.
let resizeTimer = null;
window.addEventListener("resize", function () {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(function () { if (graph) focusOn(selected); }, 120);
});

// ===========================================================================
// 6. Selecting, hovering and getting back
// ===========================================================================

el.stage.addEventListener("click", function (event) {
  const button = event.target.closest(".box");
  if (!button) {
    if (selected) clearSelection();       // a click on empty space clears
    return;
  }
  if (button.dataset.pool) selectPool(button.dataset.pool);
  else selectCourse(button.dataset.code, false);
});

/*
  Pointing at a course with a mouse previews its chain; moving off puts back
  whatever was clicked. (Touch screens have no hover; tapping selects.)
  While one preview is showing, the next course has to be pointed at for a
  moment before it takes over, so the mouse can cross other courses on its
  way to the "Further down" bar without losing the preview.
*/
el.stage.addEventListener("pointerover", function (event) {
  if (event.pointerType !== "mouse") return;
  const button = event.target.closest(".box[data-code]");
  if (!button) return;
  const code = button.dataset.code;
  clearTimeout(hoverTimer);
  if (focus && focus.code === code) return;
  hoverTimer = setTimeout(function () { focusOn(code); }, focus ? 120 : 0);
});
el.stage.addEventListener("pointerout", function (event) {
  if (event.pointerType !== "mouse") return;
  if (event.relatedTarget && event.relatedTarget.closest && event.relatedTarget.closest(".box[data-code]")) return;
  clearTimeout(hoverTimer);
  hoverTimer = setTimeout(function () { focusOn(selected); }, 250);
});

// Select a course by its code (from a click, the finder or a link in the
// panel). Courses that aren't on the map just show in the panel.
function selectCourse(code, scrollToIt, goingBack) {
  if (!nodesById[code]) return;
  if (!goingBack && selected && selected !== code) {
    previous.push(selected);
    if (previous.length > BACK_LIMIT) previous.shift();
  }
  selected = code;
  focusOn(code);
  if (scrollToIt && shown.has(code)) scrollToBox(code);
  showDetails(code);
  openSheet();
  rememberInAddress();
}

function selectPool(id) {
  if (selected && selected !== id) previous.push(selected);
  selected = id;
  focusOn(null);
  showDetails(id);
  openSheet();
  rememberInAddress();
}

// Back to the whole map: nothing selected, the major's summary in the panel.
function clearSelection() {
  selected = null;
  previous = [];
  focusOn(null);
  showMajorSummary();
  closeSheet();
  rememberInAddress();
}

// The panel's Back button: the course looked at before this one.
function goBack() {
  const code = previous.pop();
  if (!code) {
    clearSelection();
  } else if (code.startsWith("pool-")) {
    selected = code;
    focusOn(null);
    showDetails(code);
  } else {
    selectCourse(code, true, true);
  }
}

document.addEventListener("keydown", function (event) {
  if (event.key !== "Escape" || el.about.open) return;
  if (document.activeElement && document.activeElement.tagName === "INPUT") return;
  if (selected) clearSelection();
});

function scrollToBox(code) {
  const box = boxFor(code);
  if (!box) return;
  const map = el.map.getBoundingClientRect();
  const r = box.getBoundingClientRect();
  // On phones, keep the course in the strip above the open sheet.
  const visible = isPhone() ? el.map.clientHeight - window.innerHeight * 0.62 : el.map.clientHeight;
  const top = el.map.scrollTop + (r.top - map.top) - Math.max(16, (visible - r.height) / 2);
  el.map.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
}

el.allLink.addEventListener("click", function () {
  // href="#" empties the address, which shows the front page (loadFromHash).
  el.majorInput.value = "";
});

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

// "major" or "minor", for the page's wording.
function programWord() {
  return graph && graph.major.kind === "minor" ? "minor" : "major";
}

// A course code as a button that selects it.
function courseLink(code) {
  const course = nodesById[code];
  const text = (taken.has(code) ? "✓ " : "") + escapeHtml(code);
  if (course) {
    let note = "";
    if (course.status !== "active") note = ' <span class="note">(not offered now)</span>';
    else if (!shown.has(code)) note = ' <span class="note">(not on the map)</span>';
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

// Back and Close, at the top of the panel whenever something is selected.
function panelNav() {
  const last = previous[previous.length - 1];
  let html = '<div class="panel-nav">';
  if (last) {
    const name = last.startsWith("pool-") ? "previous list" : last;
    html += '<button type="button" class="nav-button" data-back>← Back to ' + escapeHtml(name) + "</button>";
  }
  html += '<button type="button" class="nav-button" data-close>✕ Close</button></div>';
  return html;
}

function showDetails(id) {
  if (nodesById[id]) {
    showCourse(nodesById[id]);
  } else {
    const pool = graph.pools.find(p => p.id === id);
    if (pool) showPool(pool);
  }
}

function showCourse(course) {
  const unlockList = Array.from(shown).filter(other => (other !== course.id) &&
    JSON.stringify(nodesById[other].requires || null).includes('"code":"' + course.id + '"')).sort(bySortKey);
  const isTaken = taken.has(course.id);

  let html = panelNav();
  html += "<h2>" + escapeHtml(course.id) + "</h2>";
  html += '<p class="course-title">' + escapeHtml(course.title) + "</p>";
  const facts = [];
  if (course.units) facts.push(escapeHtml(course.units) + " units");
  if (stepOf[course.id]) facts.push("Step " + stepOf[course.id] + " on this map");
  if (facts.length) html += '<p class="facts">' + facts.join(" · ") + "</p>";

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

  html += '<h3><span class="needs-key">Needs</span></h3>';
  html += course.requires ? '<ul class="tree">' + treeHtml(course.requires) + "</ul>" : "<p>No course prerequisites listed.</p>";
  if (course.requires && !hasCourses(course.requires)) {
    html += '<p class="note">No courses are required first, only the condition above.</p>';
  }
  if (course.ambiguous) {
    html += '<p class="note">The catalog wording mixes "and" and "or" without punctuation, so this reading is a best guess. Check the wording below.</p>';
  }
  if (course.prereq_text) {
    html += '<p class="catalog-text">Catalog wording: "' + escapeHtml(course.prereq_text) + '"</p>';
  }
  const chain = shown.has(course.id) ? Array.from(ancestorsOf(course.id)).sort(bySortKey) : [];
  const direct = new Set(prereqsOnMap(course.id).map(p => p.from));
  const earlier = chain.filter(code => !direct.has(code));
  if (earlier.length) {
    html += '<p class="note">Further back on the map: ' + earlier.map(courseLink).join(", ") + "</p>";
  }

  html += '<h3><span class="unlocks-key">Unlocks in this ' + programWord() + "</span></h3>";
  html += unlockList.length
    ? "<ul>" + unlockList.map(code => "<li>" + courseLink(code) + "</li>").join("") + "</ul>"
    : "<p>Nothing on this map lists it as a prerequisite.</p>";

  html += "<h3>In this " + programWord() + "</h3><p>" + ROLE_NAMES[course.role] + "</p>";
  if (course.groups.length) {
    html += "<ul>" + course.groups.map(g => "<li>" + escapeHtml(readableGroup(g)) + "</li>").join("") + "</ul>";
  }
  if (partners[course.id]) {
    html += '<p class="note">You can take ' + partners[course.id].map(escapeHtml).join(" or ") + " instead.</p>";
  }

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

function showPool(pool) {
  let html = panelNav();
  html += "<h2>" + escapeHtml(pool.list_name || pool.label) + "</h2>";
  html += '<p class="facts">' + escapeHtml(readable(pool.section)) + "</p>";
  html += "<p>Earn " + escapeHtml(pool.rule) + " from a list of " + pool.courses.length +
          " courses. The list is too long to draw, so it appears as one box.</p>";
  html += "<details><summary>Show all " + pool.courses.length + " courses</summary><p class=\"note\">" +
          pool.courses.map(escapeHtml).join(", ") + "</p></details>";
  setPanel(html, pool.list_name || pool.label);
}

function showMajorSummary() {
  if (!graph) return;
  const steps = Math.max(0, ...Object.values(stepOf));
  const outside = Array.from(shown).filter(code => !nodesById[code].in_major).length;
  let html = "<h2>" + escapeHtml(graph.major.name) + "</h2>";
  html += '<p class="facts">' + escapeHtml(graph.major.catalog_year) + " catalog</p>";
  html += "<p>" + graph.stats.courses_in_major + " courses" +
          (outside ? ", plus " + outside + " from other departments that they need" : "") + ". " +
          (steps === 1 ? "The required ones are all in step 1. "
                       : "The required ones are in " + steps + " steps: each course's prerequisites are in earlier steps. ") +
          "Electives are listed below the steps.</p>";
  html += "<p>Point at or click a course to trace what it needs and what it unlocks. Mark courses you've taken, and the ones you can take next get a green outline.</p>";

  const inMajor = graph.nodes.filter(n => n.in_major);
  const done = inMajor.filter(n => taken.has(n.id)).length;
  if (done) html += "<p>You've marked " + done + " of this " + programWord() + "'s " + inMajor.length + " courses as taken.</p>";

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

// Copies the address (which names the major and selected course) to the
// clipboard. Some browsers only allow this on secure (https) pages.
function copyLink(button) {
  function done(text) {
    button.textContent = text;
    setTimeout(function () { button.textContent = "Copy a link to this course"; }, 2500);
  }
  if (!navigator.clipboard || location.protocol === "file:") {
    done(location.protocol === "file:" ? "Links work on the website, not the downloaded file"
                                       : "Couldn't copy here; copy the address bar instead");
    return;
  }
  navigator.clipboard.writeText(location.href).then(
    function () { done("Link copied"); },
    function () { done("Couldn't copy here; copy the address bar instead"); });
}

function setPanel(html, handleText) {
  el.panelBody.className = "";
  el.panelBody.innerHTML = html;
  el.panelBody.scrollTop = 0;
  el.panel.scrollTop = 0;
  el.panelHandle.textContent = handleText;
}

// Buttons inside the panel. One listener handles them all, using the
// data-... attribute on the button that was clicked.
el.panelBody.addEventListener("click", function (event) {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.code) {
    selectCourse(button.dataset.code, true);
  } else if ("back" in button.dataset) {
    goBack();
  } else if ("close" in button.dataset) {
    clearSelection();
  } else if ("copyLink" in button.dataset) {
    copyLink(button);
  } else if (button.dataset.taken) {
    toggleTaken(button.dataset.taken);
  }
});

// ===========================================================================
// 8. Phones, and the About box
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

// About is a box over the page (not a separate page), so it also works in
// the single-file version.
document.getElementById("about-button").addEventListener("click", function () {
  el.about.showModal();
});
el.about.addEventListener("click", function (event) {
  if (event.target === el.about) el.about.close();     // a click outside the box closes it
});

start();
