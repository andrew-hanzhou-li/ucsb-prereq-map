/*
  planner.js: the Plan view, a quarter-by-quarter plan for the programs on
  screen.

  The page has two views of the same programs (app.js, showView):
    Map    the prerequisite map
    Plan   this file: a grid of years x quarters, and beside it the
           program's requirements with progress in each

  How a course gets placed when you click it (earliestSlot)
  ---------------------------------------------------------
  It goes in the first quarter, counting from Fall of year 1, where:
    1. its prerequisites are done (taken, or AP/college credit) or placed in
       an EARLIER quarter. "May be taken at the same time" prerequisites can
       be in the same quarter. A prerequisite that isn't in the plan at all
       doesn't hold the course back, but the course is flagged.
    2. the course is usually offered that quarter. The catalog lists this for
       only about 115 courses; the rest are assumed Fall, Winter and Spring.
       Summer is used only if "Plan summer quarters" is ticked.
    3. the quarter stays under the unit cap (16 by default).
  So ECON 1 -> Fall, ECON 2 (needs ECON 1) -> Winter, ECON 10A -> Spring.

  The catalog has no sample four-year plans in its data, and there's no
  public record of when students actually take courses, so placement uses
  only these three rules.

  Auto-fill
  ---------
  Places every required course not yet done or planned, in prerequisite
  order (the map's "column" from Part 4), plus the courses from other
  departments they need. For "take one of" requirements it uses an option
  already done or planned, or else the first one the catalog lists. Elective
  lists get labeled slots ("Elective: Area D electives"), placed from year 3
  on; click one to choose the actual course.

  Everything is saved in this browser (student.js) and can be shared as a
  link that carries the plan itself (no grades).
*/

const QUARTERS = [
  { key: "F", name: "Fall" },
  { key: "W", name: "Winter" },
  { key: "S", name: "Spring" },
  { key: "U", name: "Summer" },
];
const MAX_YEARS = 8;
const ELECTIVE_UNITS = 4;     // units assumed for an elective slot

const planEl = {
  area: document.getElementById("plan-area"),
  reqs: document.getElementById("plan-reqs"),
  grid: document.getElementById("plan-grid"),
  start: document.getElementById("plan-start"),
  transfer: document.getElementById("plan-transfer"),
  summer: document.getElementById("plan-summer"),
  cap: document.getElementById("plan-cap"),
  autofill: document.getElementById("plan-autofill"),
  share: document.getElementById("plan-share"),
  download: document.getElementById("plan-download"),
  clear: document.getElementById("plan-clear"),
  message: document.getElementById("plan-message"),
};

let planSelected = null;      // course code (or elective slot id) shown in the panel

// ===========================================================================
// 1. Quarters
// ===========================================================================

// Every quarter in the plan, in order: [{ id: "1-F", year: 1, q: "F" }, …]
function planSlots() {
  const list = [];
  for (let year = plan.firstYear; year < plan.firstYear + plan.years; year++) {
    for (const quarter of QUARTERS) {
      if (quarter.key === "U" && !plan.summer) continue;
      list.push({ id: year + "-" + quarter.key, year: year, q: quarter.key });
    }
  }
  return list;
}

function slotIndex(id) {
  return planSlots().findIndex(s => s.id === id);
}

// "1-F" -> "Fall 2026"; Winter, Spring and Summer fall in the next calendar year.
function slotName(id) {
  const [year, q] = id.split("-");
  const quarter = QUARTERS.find(x => x.key === q);
  const calendar = plan.startYear + (Number(year) - plan.firstYear) + (q === "F" ? 0 : 1);
  return quarter.name + " " + calendar;
}

function yearName(year) {
  const first = plan.startYear + (year - plan.firstYear);
  return "Year " + year + " · " + first + "–" + String(first + 1).slice(2);
}

// ===========================================================================
// 2. Facts about a course
// ===========================================================================

/*
  Courses already in the plan may come from a program that's no longer on
  screen, so the plan keeps each placed course's title and units
  (plan.info) and uses them when the course isn't in the current graph.
*/
function courseInfo(code) {
  const node = nodesById[code];
  if (node) return { title: node.title, units: node.units, offered: node.offered || [], requires: node.requires, level: node.level };
  const saved = (plan.info || {})[code] || {};
  return { title: saved.title || "", units: saved.units || "4", offered: saved.offered || [], requires: null, level: "" };
}

// "4" -> [4, 4]; "1-4" -> [1, 4]; "" -> [4, 4] (assume 4 if the catalog has none)
function unitRange(code) {
  const text = String(courseInfo(code).units || "");
  const match = text.match(/^(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?$/);
  if (!match) return [4, 4];
  const low = Number(match[1]);
  return [low, match[2] ? Number(match[2]) : low];
}

// Units counted for a course: the student's choice for a variable-unit
// course, otherwise the catalog's (the smallest, for a range they haven't set).
function unitsOf(code) {
  const range = unitRange(code);
  const chosen = plan.units[code];
  if (chosen >= range[0] && chosen <= range[1]) return chosen;
  return range[0];
}

// The quarters a course is usually offered: the catalog's list, or
// Fall/Winter/Spring when it doesn't say. Summer only if the student plans summers.
function offeredList(code) {
  const listed = courseInfo(code).offered;
  return listed.length ? listed : ["Fall", "Winter", "Spring"];
}

function offeredIn(code, q) {
  if (q === "U") return plan.summer;
  const name = QUARTERS.find(x => x.key === q).name;
  return offeredList(code).includes(name);
}

function offeredText(code) {
  const listed = courseInfo(code).offered;
  return listed.length ? listed.join(", ") : "not listed in the catalog (assumed Fall, Winter, Spring)";
}

// ===========================================================================
// 3. Prerequisites in time
// ===========================================================================

function quarterUnits(slotId, except) {
  let total = 0;
  for (const code of Object.keys(plan.placed)) {
    if (plan.placed[code] === slotId && code !== except) total += unitsOf(code);
  }
  for (const slot of plan.electives || []) {
    if (slot.slot === slotId && slot.id !== except) total += ELECTIVE_UNITS;
  }
  return total;
}

// Done before quarter number `index`? Done means taken or credited (isDone,
// app.js); or planned for an earlier quarter (the same one, if concurrent).
function readyBy(code, index, concurrent) {
  if (isDone(code)) return true;
  const slot = plan.placed[code];
  if (!slot) return false;
  const at = slotIndex(slot);
  return at >= 0 && (concurrent ? at <= index : at < index);
}

function inPlanOrDone(code) {
  return isDone(code) || [code, onlineTwin(code), onlineBase(code)].some(c => c && plan.placed[c]);
}

// A requirement's items without online twins whose base course is listed
// too: "PSTAT 120A or PSTATW 120A" is one course for counting and listing.
function withoutTwins(items) {
  const codes = new Set(items.filter(i => i.type === "course").map(i => i.code));
  return items.filter(i => !(i.type === "course" && i.code && onlineBase(i.code) && codes.has(onlineBase(i.code))));
}

// Could this part of a prerequisite tree be met by what's done or planned?
// "ECE 15A and (ECE 2A or ECE 10A + 10AL)" can, with 15A, 10A and 10AL
// planned, even though ECE 2A isn't.
function plannable(node) {
  if (!node || node.type === "condition") return true;
  if (node.type === "course") return inPlanOrDone(node.code);
  if (node.type === "and") return node.items.every(plannable);
  return node.items.filter(hasCourses).some(plannable);
}

/*
  Are a course's prerequisites met by quarter number `index`?
  `relaxed` is for choosing where to put a course: a prerequisite that isn't
  in the plan at all doesn't stop it (it would never be met); the course is
  flagged instead (missingPrereqs).
*/
function metAt(node, index, self, relaxed) {
  if (!node) return true;
  if (node.type === "condition") return true;
  if (node.type === "course") {
    if (node.code === self) return true;
    if (relaxed && !inPlanOrDone(node.code)) return true;
    return readyBy(node.code, index, node.concurrent);
  }
  if (node.type === "and") return node.items.every(item => metAt(item, index, self, relaxed));
  // "One of": only course options count when there are some. If none of the
  // options is planned or done yet, a relaxed check lets it through.
  const options = node.items.filter(hasCourses);
  if (!options.length) return true;
  const available = options.filter(plannable);
  if (!available.length) return relaxed;
  return available.some(option => metAt(option, index, self, false));
}

// The prerequisites not met for a course where it's planned, as words:
// ["ECON 1 (not in your plan)", "MATH 3B (planned for the same quarter)"].
function missingPrereqs(code) {
  const slot = plan.placed[code];
  if (!slot) return [];
  // A course already passed (or ticked as taken, or credited) is never
  // flagged: whatever it needed, the student evidently had.
  if (isDone(code)) return [];
  const index = slotIndex(slot);
  const requires = courseInfo(code).requires;
  const missing = [];
  const standing = standingYear(code);
  if (standing && Number(slot.split("-")[0]) < standing.year) {
    missing.push(standing.words + " (year " + standing.year + " or later)");
  }
  if (metAt(requires, index, code, false)) return missing;
  function why(c) {
    if (!plan.placed[c]) return c + " (not in your plan)";
    return c + " (planned for " + slotName(plan.placed[c]) + ")";
  }
  function collect(node) {
    if (!node || node.type === "condition") return;
    if (node.type === "course") {
      if (node.code !== code && !readyBy(node.code, index, node.concurrent)) missing.push(why(node.code));
    } else if (node.type === "and") {
      node.items.forEach(collect);
    } else if (!metAt(node, index, code, false)) {
      const options = node.items.filter(hasCourses).map(option => coursesIn(option).join(" and "));
      missing.push("one of " + options.join(", or "));
    }
  }
  collect(requires);
  return missing;
}

/*
  Class standing as a year of the plan. The catalog's prerequisites include
  conditions like "senior standing" (parsed in Part 2 as kind "standing").
  UCSB counts standing by units, but for a plan it maps onto years:
    senior                                   year 4 or later
    junior, upper-division                   year 3 or later
    sophomore, "not open to freshmen"        year 2 or later
  Year numbers are the plan's, so a transfer student (who starts in year 3)
  is already a junior. Only conditions every way through the prerequisites
  need (not one option of a "one of") count. Graduate standing and
  freshman standing don't set a minimum year in a bachelor's plan.
  Returns { year, words } or null.
*/
function standingYear(code) {
  let best = null;
  (function walk(node) {
    if (!node) return;
    if (node.type === "and") return node.items.forEach(walk);
    if (node.type !== "condition" || node.kind !== "standing") return;
    const text = (node.text || "").toLowerCase();
    let found = null;
    if (/senior/.test(text)) found = { year: 4, words: "senior standing" };
    else if (/junior|upper[- ]division/.test(text)) found = { year: 3, words: "upper-division standing" };
    else if (/sophomore|not open to freshm/.test(text)) found = { year: 2, words: "sophomore standing" };
    if (found && (!best || found.year > best.year)) best = found;
  })(courseInfo(code).requires);
  return best;
}

/*
  The earliest year the planner itself puts a course in: its standing
  (above), and for an upper-division course (numbered 100 and up) no
  earlier than year 2 even without a standing condition. ECE 139 only says
  "open to EE and CE majors", but the department's 4-year plan has it in
  sophomore Spring. The student can still drag a course earlier; only a
  standing condition then shows "!".
*/
function placementYear(code) {
  const standing = standingYear(code);
  let year = standing ? standing.year : 1;
  if (courseInfo(code).level === "upper") year = Math.max(year, 2);
  return year;
}

/*
  The first quarter that's still open for planning: the one after the last
  quarter with a graded course (finished, or In Progress). Quarters up to
  then are the past, filled from a transcript or by hand; the planner
  never puts new courses there.
*/
function firstOpenIndex() {
  let last = -1;
  for (const code of Object.keys(plan.grades)) {
    if (plan.placed[code]) last = Math.max(last, slotIndex(plan.placed[code]));
  }
  return last + 1;
}

/*
  The first quarter (from `fromIndex` on) where a course fits: its
  prerequisites come earlier, it's usually offered then, it's not before
  its earliest year (placementYear), and the quarter stays under the unit
  cap. null if no quarter in the plan fits.
*/
function earliestSlot(code, fromIndex) {
  const slots = planSlots();
  const units = unitsOf(code);
  const requires = courseInfo(code).requires;
  const firstYear = placementYear(code);
  for (let i = Math.max(fromIndex || 0, firstOpenIndex()); i < slots.length; i++) {
    if (slots[i].year < firstYear) continue;
    if (!offeredIn(code, slots[i].q)) continue;
    if (quarterUnits(slots[i].id, code) + units > plan.cap) continue;
    if (!metAt(requires, i, code, true)) continue;
    return slots[i].id;
  }
  return null;
}

// Put a course in its earliest quarter, adding years if the plan is full.
// Returns the quarter, or null.
function placeCourse(code) {
  let slot = earliestSlot(code);
  while (!slot && plan.years + plan.firstYear - 1 < MAX_YEARS) {
    plan.years += 1;
    slot = earliestSlot(code);
  }
  if (!slot) return null;
  plan.placed[code] = slot;
  delete (plan.auto || {})[code];          // auto-fill marks its own afterwards
  const info = courseInfo(code);
  plan.info = plan.info || {};
  plan.info[code] = { title: info.title, units: info.units, offered: info.offered };
  return slot;
}

// ===========================================================================
// 4. Requirements and progress
// ===========================================================================

/*
  Progress through a requirement, as { have, need }:
    course           need 1; have 1 if it's done or planned
    all of           the sum of its parts
    choose N         need N; have = how many of its parts are complete
                     (or planned), plus elective slots for it, up to N
    N units from     need N units; have = units done or planned, up to N
    text             nothing to count
*/
function progress(node, key) {
  // "have" counts done or planned; "done" counts only done (taken, credit,
  // passed), so the wording can say which.
  if (node.type === "course") {
    if (!node.code) return { have: 0, done: 0, need: 1 };
    return { have: inPlanOrDone(node.code) ? 1 : 0, done: isDone(node.code) ? 1 : 0, need: 1 };
  }
  if (node.type === "text") return { have: 0, done: 0, need: 0 };
  const kept = withoutTwins(node.items);
  const parts = node.items.map((item, i) => progress(item, key + "." + i)).filter((p, i) => kept.includes(node.items[i]));
  const slots = (plan.electives || []).filter(e => e.key === key).length;
  if (node.type === "all") {
    return parts.reduce((sum, p) => ({ have: sum.have + p.have, done: sum.done + p.done, need: sum.need + p.need }),
                        { have: 0, done: 0, need: 0 });
  }
  if (node.type === "units") {
    let units = slots * ELECTIVE_UNITS;
    let done = 0;
    for (const code of coursesInRequirement(node)) {
      if (inPlanOrDone(code)) units += unitsOf(code);
      if (isDone(code)) done += unitsOf(code);
    }
    return { have: Math.min(node.units, units), done: Math.min(node.units, done), need: node.units };
  }
  // choose N
  const complete = parts.filter(p => p.need > 0 && p.have >= p.need).length + slots;
  const completeDone = parts.filter(p => p.need > 0 && p.done >= p.need).length;
  return { have: Math.min(node.count, complete), done: Math.min(node.count, completeDone), need: node.count };
}

// Every course named anywhere inside a requirement.
// Every course named anywhere inside a requirement, once (an online twin
// whose base course is also named counts as that course).
function coursesInRequirement(node) {
  if (node.type === "course") return node.code ? [node.code] : [];
  const all = (node.items || []).flatMap(coursesInRequirement);
  return all.filter(code => !(onlineBase(code) && all.includes(onlineBase(code))));
}

// "done", "planned", "0/2 done", "1/3 done or planned".
function progressText(p) {
  if (!p.need) return "";
  if (p.have >= p.need) return p.done >= p.need ? "done" : "planned";
  return p.have + "/" + p.need + (p.have > p.done ? " done or planned" : " done");
}

// A requirement tree as nested lists, each course clickable to add it.
function requirementHtml(node, key, depth, sectionName, insideChoice) {
  if (node.type === "text") {
    return '<li class="req-text">' + escapeHtml(node.text || node.description || "") + "</li>";
  }
  if (node.type === "course") {
    if (!node.code) return '<li class="req-course muted">A course the catalog doesn\'t name</li>';
    return "<li>" + requirementCourse(node.code) + "</li>";
  }
  const p = progress(node, key);
  let rule = "";
  if (node.type === "choose") rule = node.count === 1 && node.items.length <= 4 ? "One of these" : "Choose " + node.count + " of these";
  if (node.type === "units") rule = node.units + " units from these";
  if (node.type === "all") rule = depth > 0 ? "All of these" : "";
  // The catalog often repeats the section's name as a rule's label; skip that.
  const label = node.label && node.label.toLowerCase() !== (sectionName || "").split(" — ").pop().toLowerCase() ? node.label : "";
  const head = [label, rule].filter(Boolean).join(": ");
  const isChoice = node.type === "choose";
  // (Keys use each item's place in the full list, so slots stay matched.)
  const kept = withoutTwins(node.items);
  const items = node.items.map((item, i) => kept.includes(item) ? requirementHtml(item, key + "." + i, depth + 1, sectionName, isChoice) : "").join("");
  // Progress inside a "one of" option ("0 of 2") reads like something is
  // missing when the student simply took the other option, so it's left off.
  const showProgress = depth > 0 && !insideChoice;
  const canSlot = (node.type === "choose" || node.type === "units") && p.have < p.need &&
                  node.items.every(i => i.type === "course") && slotsAllowed(sectionName);
  const slotButton = canSlot
    ? ' <button type="button" class="text-button" data-plan-elective="' + escapeHtml(key) + '">add a slot</button>'
    : "";
  // The top of an area has no line of its own: the area itself folds.
  if (depth === 0) {
    return '<li class="req-group">' + (head ? '<span class="req-head">' + escapeHtml(head) + "</span> " : "") + slotButton +
           "<ul>" + items + "</ul></li>";
  }
  /*
    Inside an area, a group's courses hang off a thin vertical line, as in a
    Reddit thread: clicking the line (or the group's heading) collapses the
    whole group to one line, and clicking again opens it. Long lists start
    collapsed. What's open is remembered while the page is open (openGroups).
  */
  const collapsed = groupCollapsed(key, node);
  const count = coursesInRequirement(node).length;
  return '<li class="req-group' + (collapsed ? " collapsed" : "") + '">' +
         '<button type="button" class="req-toggle" data-req-toggle="' + escapeHtml(key) + '" aria-expanded="' + !collapsed + '">' +
         '<span class="req-head">' + escapeHtml(head || "Courses") + "</span>" +
         (showProgress && progressText(p) ? ' <span class="req-progress">· ' + progressText(p) + "</span>" : "") +
         (collapsed ? ' <span class="req-hidden">· ' + count + (count === 1 ? " course" : " courses") + "</span>" : "") +
         "</button>" + slotButton +
         '<div class="req-children"><button type="button" class="req-thread" data-req-toggle="' + escapeHtml(key) +
         '" aria-label="Collapse this group" tabindex="-1"></button><ul>' + items + "</ul></div></li>";
}

// Which groups the student has opened or closed (key -> true for open).
const openGroups = {};

function groupCollapsed(key, node) {
  if (key in openGroups) return !openGroups[key];
  return node.items.length > 8;
}

/*
  Elective slots ("a course from this list, to be chosen") belong in the
  upper-division part of a program, where students genuinely pick from a
  list. In Pre-major and Preparation for the major, students choose
  specific courses, so no slots there, in the sidebar or from auto-fill.
*/
function slotsAllowed(sectionName) {
  return !/pre-?major|preparation/i.test(sectionName || "");
}

function requirementCourse(code) {
  const info = courseInfo(code);
  let state = '<button type="button" class="text-button" data-plan-add="' + escapeHtml(code) + '">add</button>';
  if (isDone(code)) state = '<span class="req-done">✓ ' + (creditFor(code) ? "credit" : "taken") + "</span>";
  else if (plan.placed[code]) state = '<span class="req-planned">' + escapeHtml(slotName(plan.placed[code])) + "</span>";
  return '<span class="req-course" draggable="true" data-plan-drag="' + escapeHtml(code) + '">' +
         '<button type="button" class="req-code" data-plan-show="' + escapeHtml(code) + '" title="' + escapeHtml(info.title || "") + '">' +
         escapeHtml(code) + "</button></span> " + state;
}

/*
  The column beside the grid, top to bottom:
    1. Your credit: AP exams and college courses, with a button to add them.
       It's at the top because it changes everything below it (AP Calculus
       AB means MATH 3A is done, so MATH 3B isn't flagged).
    2. One fold per requirement area (Preparation for the major, Upper
       division…), with progress. Only one is open at a time, so the list
       stays short; it starts on the first area that isn't complete.
    3. "Needed first, from other departments": courses the requirements
       need that aren't in the program itself (CMPSC 8 for CMPSC 16 in
       Computer Engineering).
*/
let openArea = null;      // which fold is open ("s0", "s1"…, "outside"); null = choose one

function drawRequirements() {
  const areas = [];
  graph.major.sections.forEach(function (section, i) {
    const key = "s" + i;
    areas.push({
      key: key,
      title: readable(section.name),
      progress: progress(section.requirement, key),
      body: '<ul class="req-list">' + requirementHtml(section.requirement, key, 0, section.name, false) + "</ul>",
    });
  });
  for (const pool of graph.pools) {
    areas.push({
      key: pool.id,
      title: pool.list_name || pool.label,
      progress: { have: 0, need: 0 },
      body: '<p class="note">Earn ' + escapeHtml(pool.rule) + " from a list of " + pool.courses.length +
            " courses (too long to list here; see the map).</p>",
    });
  }
  const outside = outsideCourses();
  if (outside.length) {
    const done = outside.filter(inPlanOrDone).length;
    areas.push({
      key: "outside",
      title: "Needed first, from other departments",
      progress: { have: done, need: outside.length },
      body: '<p class="note">Not part of ' + escapeHtml(thisProgram()) + ", but courses in it need them.</p>" +
            '<ul class="req-list">' + outside.map(code => "<li>" + requirementCourse(code) + "</li>").join("") + "</ul>",
    });
  }

  if (!openArea || !areas.some(a => a.key === openArea)) {
    const first = areas.find(a => a.progress.need && a.progress.have < a.progress.need);
    openArea = first ? first.key : areas[0] && areas[0].key;
  }
  planEl.reqs.innerHTML = creditSummaryHtml() + areas.map(a =>
    '<details class="req-section" data-area="' + escapeHtml(a.key) + '"' + (a.key === openArea ? " open" : "") + "><summary><h3>" +
    escapeHtml(a.title) + ' <span class="req-progress">' + progressText(a.progress) + "</span></h3></summary>" +
    a.body + "</details>").join("");
}

// Courses from other departments that the requirements need (the same ones
// the map adds), sorted by prerequisite order.
function outsideCourses() {
  const needed = chooseShown({ electives: false, everyOutside: false, inactive: false, skipDone: true });
  return Array.from(needed).filter(code => !nodesById[code].in_major)
    .sort((a, b) => (nodesById[a].column - nodesById[b].column) || bySortKey(a, b));
}

// "Your credit": what's counted already, and the way to add more.
function creditSummaryHtml() {
  const lines = [];
  for (const exam of Object.keys(credit.ap)) {
    const row = apRow(exam, credit.ap[exam]);
    lines.push("<li>AP " + escapeHtml(exam) + " (" + credit.ap[exam] + ")" +
               (row && row.equivalents.length ? ': <span class="req-done">' + escapeHtml(row.equivalents.join(", ")) + "</span>" : "") + "</li>");
  }
  if (credit.transfer.length) {
    lines.push('<li>College credit: <span class="req-done">' + escapeHtml(credit.transfer.join(", ")) + "</span></li>");
  }
  return '<section class="req-credit"><h3>Your AP and college credit</h3>' +
         (lines.length ? '<ul class="credit-lines">' + lines.join("") + "</ul>"
                       : '<p class="note">None yet. AP exams and courses from other colleges count as done, so their prerequisites aren\'t flagged.</p>') +
         '<p><button type="button" class="credit-button" data-open-credit>' +
         (lines.length ? "Change your credit" : "Check off AP exams and college credit") + "</button></p></section>";
}

// One area open at a time: opening a fold closes the others.
planEl.reqs.addEventListener("toggle", function (event) {
  const area = event.target.closest && event.target.closest("details.req-section");
  if (!area || event.target !== area || !area.open) return;
  openArea = area.dataset.area;
  for (const other of planEl.reqs.querySelectorAll("details.req-section[open]")) {
    if (other !== area) other.open = false;
  }
}, true);

// The requirement node behind an elective slot's key ("s2.0.3").
function nodeForKey(key) {
  const parts = key.split(".");
  let node = graph.major.sections[Number(parts[0].slice(1))];
  if (!node) return null;
  node = node.requirement;
  for (const i of parts.slice(1)) {
    if (!node || !node.items) return null;
    node = node.items[Number(i)];
  }
  return node;
}

function sectionNameForKey(key) {
  const section = graph.major.sections[Number(key.split(".")[0].slice(1))];
  return section ? section.name : "";
}

// "Area D electives", named the same way as the map's elective lists
// (groupTitle, app.js), so a slot matches its list on the map.
function electiveLabel(key) {
  const node = nodeForKey(key);
  const section = sectionNameForKey(key);
  return node && node.label ? groupTitle(section + ": " + node.label) : readable(section.split(" — ").pop()) + " elective";
}

// ===========================================================================
// 5. The grid
// ===========================================================================

function drawGrid() {
  const quarters = QUARTERS.filter(q => q.key !== "U" || plan.summer);
  let html = '<table class="plan-table"><thead><tr><th></th>' +
             quarters.map(q => "<th>" + q.name + "</th>").join("") + "</tr></thead><tbody>";
  for (let year = plan.firstYear; year < plan.firstYear + plan.years; year++) {
    html += '<tr><th class="plan-year">' + escapeHtml(yearName(year)) + "</th>";
    for (const q of quarters) {
      const slotId = year + "-" + q.key;
      const codes = Object.keys(plan.placed).filter(c => plan.placed[c] === slotId).sort(bySortKey);
      const slots = (plan.electives || []).filter(e => e.slot === slotId);
      const units = quarterUnits(slotId);
      html += '<td class="plan-cell' + (units > plan.cap ? " over" : "") + '" data-plan-slot="' + slotId + '">' +
              '<span class="cell-name">' + escapeHtml(slotName(slotId)) + "</span>" +
              codes.map(chipHtml).join("") + slots.map(electiveChipHtml).join("") +
              (units ? '<span class="cell-units">' + units + " units</span>" : "") + "</td>";
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  html += '<p class="plan-years"><button type="button" class="text-button" data-plan-years="1">add a year</button>' +
          (plan.years > 1 ? ' · <button type="button" class="text-button" data-plan-years="-1">remove the last year</button>' : "") + "</p>";
  planEl.grid.innerHTML = html;
}

function chipHtml(code) {
  const problems = missingPrereqs(code);
  const classes = ["chip"];
  if (problems.length) classes.push("warn");
  if (code === planSelected) classes.push("selected");
  // A faint "?" when nobody says which quarters it's offered (assumed F/W/S).
  const assumed = !courseInfo(code).offered.length && !plan.grades[code];
  if (assumed) classes.push("assumed");
  const hover = problems.length ? "Needs first: " + problems.join("; ")
              : assumed ? "When it's offered isn't listed; assumed Fall, Winter and Spring"
              : plan.grades[code] ? "" : "Usually offered: " + courseInfo(code).offered.join(", ");
  return '<button type="button" class="' + classes.join(" ") + '" draggable="true" data-plan-show="' + escapeHtml(code) +
         '" data-plan-drag="' + escapeHtml(code) + '"' + (hover ? ' title="' + escapeHtml(hover) + '"' : "") + ">" +
         '<span class="chip-code">' + (problems.length ? "! " : "") + escapeHtml(code) + (assumed ? '<span class="chip-assumed">?</span>' : "") + "</span>" +
         '<span class="chip-units">' + (plan.grades[code] ? '<span class="chip-grade">' + escapeHtml(plan.grades[code]) + "</span> " : "") +
         unitsOf(code) + "</span></button>";
}

function electiveChipHtml(slot) {
  return '<button type="button" class="chip elective-slot' + (slot.id === planSelected ? " selected" : "") +
         '" draggable="true" data-plan-show="' + escapeHtml(slot.id) + '" data-plan-drag="' + escapeHtml(slot.id) + '">' +
         '<span class="chip-code">' + escapeHtml(electiveLabel(slot.key)) + "</span>" +
         '<span class="chip-units">' + ELECTIVE_UNITS + "</span></button>";
}

// ===========================================================================
// 6. The panel beside the plan (slim, as CLAUDE.md asks)
// ===========================================================================

/*
  Only what's needed right now: name, units, when it's usually offered,
  where it's planned. Prerequisites appear only when they're NOT met where
  the course is planned.
*/
function showPlanCourse(code) {
  planSelected = code;
  const info = courseInfo(code);
  const range = unitRange(code);
  let html = '<div class="panel-nav"><button type="button" class="nav-button" data-plan-close>close</button></div>';
  html += "<h2>" + escapeHtml(code) + "</h2>";
  html += '<p class="course-title">' + escapeHtml(info.title || "") + "</p>";
  if (range[0] !== range[1]) {
    const options = [];
    for (let u = range[0]; u <= range[1]; u++) {
      options.push('<option value="' + u + '"' + (unitsOf(code) === u ? " selected" : "") + ">" + u + "</option>");
    }
    html += '<p class="facts"><label>Units <select data-plan-units="' + escapeHtml(code) + '">' + options.join("") + "</select></label> (variable, " + range[0] + "–" + range[1] + ")</p>";
  } else {
    html += '<p class="facts">' + unitsOf(code) + " units</p>";
  }
  html += '<p class="facts">Usually offered: ' + escapeHtml(offeredText(code)) + "</p>";

  if (isDone(code)) {
    html += '<p class="credit-note">✓ ' + (creditFor(code) ? "You have credit for this: " + escapeHtml(creditFor(code)) : "Marked as taken") + ".</p>";
  }
  if (plan.placed[code]) {
    html += "<p>Planned for <strong>" + escapeHtml(slotName(plan.placed[code])) + "</strong>.</p>";
    const problems = missingPrereqs(code);
    if (problems.length) {
      html += '<h3><span class="needs-key">Needs first</span></h3><ul>' +
              problems.map(p => "<li>" + escapeHtml(p) + "</li>").join("") + "</ul>";
      html += '<p class="note">Already have one of these from an AP exam or another college? ' +
              '<button type="button" class="text-button" data-open-credit>Add your credit</button> and it counts.</p>';
      if (info.requires && courseInfo(code).requires) {
        html += '<p class="catalog-text">Catalog wording: "' + escapeHtml((nodesById[code] || {}).prereq_text || "") + '"</p>';
      }
    }
    html += '<p class="plan-actions"><button type="button" class="text-button" data-plan-move="-1">earlier</button> · ' +
            '<button type="button" class="text-button" data-plan-move="1">later</button> · ' +
            '<button type="button" class="text-button" data-plan-remove>remove from plan</button></p>';
  } else if (!isDone(code)) {
    html += '<p class="plan-actions"><button type="button" class="text-button" data-plan-add="' + escapeHtml(code) + '">add to plan</button></p>';
  }
  html += '<p><a href="https://catalog.ucsb.edu/courses/' + encodeURIComponent(code) + '" target="_blank" rel="noopener">This course in the UCSB catalog</a></p>';
  if (typeof gradeHtml === "function") html += gradeHtml(code);
  setPanel(html, code + "  " + (info.title || ""));
  openSheet();
  drawGrid();
}

// An elective slot: pick the actual course from its list.
function showElectiveSlot(id) {
  planSelected = id;
  const slot = plan.electives.find(e => e.id === id);
  const node = nodeForKey(slot.key);
  let html = '<div class="panel-nav"><button type="button" class="nav-button" data-plan-close>close</button></div>';
  html += "<h2>" + escapeHtml(electiveLabel(slot.key)) + "</h2>";
  html += '<p class="facts">' + escapeHtml(slotName(slot.slot)) + " · " + ELECTIVE_UNITS + " units assumed</p>";
  if (node && node.items) {
    const options = node.items.filter(i => i.type === "course" && i.code && !inPlanOrDone(i.code) &&
                                           (nodesById[i.code] || {}).status !== "inactive");
    html += "<p>Choose the course for this slot:</p><ul class=\"pick-list\">" + options.map(i =>
      '<li><button type="button" class="text-button" data-plan-fill="' + escapeHtml(i.code) + '">' + escapeHtml(i.code) +
      "</button> " + escapeHtml((nodesById[i.code] || {}).title || "") + "</li>").join("") + "</ul>";
  }
  html += '<p class="plan-actions"><button type="button" class="text-button" data-plan-move="-1">earlier</button> · ' +
          '<button type="button" class="text-button" data-plan-move="1">later</button> · ' +
          '<button type="button" class="text-button" data-plan-remove>remove this slot</button></p>';
  setPanel(html, electiveLabel(slot.key));
  openSheet();
  drawGrid();
}

function showPlanSummary() {
  planSelected = null;
  let total = 0;
  for (const code of Object.keys(plan.placed)) total += unitsOf(code);
  total += (plan.electives || []).length * ELECTIVE_UNITS;
  const flagged = Object.keys(plan.placed).filter(c => missingPrereqs(c).length);
  let html = "<h2>Your plan</h2>";
  html += '<p class="facts">' + escapeHtml(graph.major.name) + "</p>";
  html += "<p>" + Object.keys(plan.placed).length + " courses and " + (plan.electives || []).length +
          " elective slots planned, " + total + " units.</p>";
  if (flagged.length) {
    html += '<p class="flag">' + flagged.length + (flagged.length === 1 ? " course is" : " courses are") +
            " planned before " + (flagged.length === 1 ? "its" : "their") + " prerequisites (marked !): " +
            flagged.map(escapeHtml).join(", ") + ".</p>";
  }
  html += "<p>Click a course on the left to add it. It goes in the first quarter after its prerequisites, " +
          "when it's usually offered, under " + plan.cap + " units. Drag courses to move them, or click one for its details.</p>";
  html += '<p class="note">When a course is offered is known for only about 120 UCSB courses (the catalog, plus hand corrections). ' +
          "The rest are assumed Fall, Winter and Spring and marked with a faint ? in the plan. Check the Schedule of Classes on GOLD before you enroll.</p>";
  if (typeof gpaSummaryHtml === "function") html += gpaSummaryHtml() + goalHtml();
  html += '<p class="note">Unofficial student project. Requirements change; confirm your plan with a department advisor.</p>';
  setPanel(html, "Your plan");
  drawGrid();
}

// ===========================================================================
// 7. Opening, redrawing, settings
// ===========================================================================

// Called by app.js when the Plan view opens. `shared` is a plan from a link.
function openPlan(shared) {
  if (shared) {
    const incoming = unpackPlan(shared);
    if (incoming) {
      const hasOwn = Object.keys(plan.placed).length > 0;
      if (!hasOwn || window.confirm("Replace your saved plan with the one in this link?")) {
        plan = Object.assign(emptyPlan(), incoming, { grades: plan.grades });
        savePlan();
      }
    }
    history.replaceState(null, "", planHashFor(currentPrograms));
  }
  refreshPlan();
  showPlanSummary();
}

function refreshPlan() {
  if (!graph || currentView !== "plan") return;
  // "First quarter at UCSB": the last eight Falls and the next one.
  const thisFall = defaultStartYear();
  const years = [];
  for (let y = Math.min(plan.startYear, thisFall - 8); y <= Math.max(plan.startYear, thisFall + 1); y++) years.push(y);
  planEl.start.innerHTML = years.map(y => '<option value="' + y + '">' + y + "</option>").join("");
  planEl.start.value = plan.startYear;
  planEl.transfer.checked = plan.firstYear === 3;
  planEl.summer.checked = plan.summer;
  planEl.cap.value = plan.cap;
  drawRequirements();
  drawGrid();
  if (planSelected) {
    if ((plan.electives || []).some(e => e.id === planSelected)) showElectiveSlot(planSelected);
    else if (plan.placed[planSelected] || nodesById[planSelected]) showPlanCourse(planSelected);
    else showPlanSummary();
  } else {
    // Redrawn every time, from the same missingPrereqs that draws the "!"
    // marks, so the summary's warning can't go stale.
    showPlanSummary();
  }
}

function planChanged() {
  savePlan();
  refreshPlan();
}

/*
  After credit, grades or a transcript change what's done: take out the
  courses auto-fill placed that are now done, or no longer needed (CMPSC 8
  once CMPSC 16 is passed). Courses the student chose, moved or graded
  stay. Returns how many were removed.
*/
function pruneCovered() {
  if (!graph) return 0;
  doneChanged();
  const needed = chooseShown({ electives: false, everyOutside: false, inactive: false, skipDone: true });
  let removed = 0;
  for (const code of Object.keys(plan.placed)) {
    if (!(plan.auto || {})[code] || plan.grades[code]) continue;
    const node = nodesById[code];
    const unneeded = node && !node.in_major && !needed.has(code);
    if (isDone(code) || unneeded) {
      delete plan.placed[code];
      delete plan.auto[code];
      removed += 1;
    }
  }
  return removed;
}

/*
  After a transcript is read in: everything planned that isn't from the
  transcript is placed again, after the last quarter on it, so there's no
  gap and nothing sits before what it needs. Courses the student chose are
  kept (just moved); auto-fill's picks are dropped and auto-fill runs again.
*/
function rebuildAfterTranscript(fromTranscript) {
  const chosen = [];
  let hadAuto = false;
  for (const code of Object.keys(plan.placed)) {
    if (fromTranscript.has(code) || plan.grades[code]) continue;
    if ((plan.auto || {})[code]) hadAuto = true; else chosen.push(code);
    delete plan.placed[code];
  }
  plan.auto = {};
  const slots = (plan.electives || []).map(e => e.key);
  plan.electives = [];
  for (const code of prerequisiteOrder(chosen.filter(c => nodesById[c]))) placeCourse(code);
  for (const code of chosen.filter(c => !nodesById[c])) placeCourse(code);
  if (hadAuto) {
    autoFill(true);
  } else {
    slots.forEach(key => addElectiveSlot(key));
  }
}

function say(text) {
  planEl.message.textContent = text;
}

planEl.start.addEventListener("change", function () {
  const year = parseInt(planEl.start.value, 10);
  if (year >= 2000 && year <= 2100) plan.startYear = year;
  planChanged();
});

// A transfer student starts in year 3, with two years to plan.
planEl.transfer.addEventListener("change", function () {
  const firstYear = planEl.transfer.checked ? 3 : 1;
  const shift = firstYear - plan.firstYear;
  // Keep courses in the same position relative to the start.
  for (const code of Object.keys(plan.placed)) {
    const [year, q] = plan.placed[code].split("-");
    plan.placed[code] = (Number(year) + shift) + "-" + q;
  }
  for (const slot of plan.electives || []) {
    const [year, q] = slot.slot.split("-");
    slot.slot = (Number(year) + shift) + "-" + q;
  }
  plan.firstYear = firstYear;
  plan.years = Math.max(firstYear === 3 ? 2 : 4, plan.years);
  if (firstYear === 3) say("Transfer plan: years 3 and 4. Add your community college courses in Credit so their prerequisites count as met.");
  planChanged();
});

planEl.summer.addEventListener("change", function () {
  plan.summer = planEl.summer.checked;
  if (!plan.summer) {
    // Courses in summer quarters move to the next Fall.
    for (const code of Object.keys(plan.placed)) {
      const [year, q] = plan.placed[code].split("-");
      if (q === "U") plan.placed[code] = (Number(year) + 1) + "-F";
    }
  }
  planChanged();
});

planEl.cap.addEventListener("change", function () {
  const cap = parseInt(planEl.cap.value, 10);
  if (cap >= 4 && cap <= 30) plan.cap = cap;
  planChanged();
});

// ===========================================================================
// 8. Adding, moving and removing
// ===========================================================================

function addCourse(code) {
  if (isDone(code)) {
    say(code + " is already done (taken or credit).");
    return;
  }
  const slot = placeCourse(code);
  say(slot ? code + " goes in " + slotName(slot) + "." : "No room for " + code + " in " + MAX_YEARS + " years.");
  planChanged();
  showPlanCourse(code);
}

/*
  Auto-fill: everything required that isn't done or planned yet, in
  prerequisite order, then a slot for each elective still needed.
*/
function autoFill(quiet) {
  const needed = chooseShown({ electives: false, everyOutside: false, inactive: false, skipDone: true });
  const skip = new Set();
  // "Take one of": keep an option already done or planned, else the first
  // one the catalog still offers. A required "one of" adds that option even
  // if the map calls its courses electives.
  for (const set of pickOneSets()) {
    const options = set.options;
    const offered = option => option.every(code => nodesById[code] && nodesById[code].status === "active");
    // Prefer an option already done or planned; then the one with the
    // fewest courses still to take (with AP Calculus AB, MATH 2A-B or 3A-B
    // each need one more); then one the catalog still offers.
    const toTake = option => option.filter(code => !inPlanOrDone(code)).length;
    const ranked = options.slice().sort((a, b) => (toTake(a) - toTake(b)) || (offered(b) - offered(a)));
    const chosen = ranked.find(offered) || ranked[0];
    for (const option of options) {
      if (option !== chosen) option.forEach(code => skip.add(code));
    }
    if (set.required) chosen.forEach(code => needed.add(code));
  }
  const list = prerequisiteOrder(Array.from(needed)
    .filter(code => !skip.has(code) && !inPlanOrDone(code) && nodesById[code] && nodesById[code].status === "active"));
  let placed = 0;
  plan.auto = plan.auto || {};
  for (const code of list) {
    if (placeCourse(code)) {
      plan.auto[code] = true;
      placed += 1;
    }
  }
  repairOrder();

  // Elective slots, for lists of courses still short.
  let slots = 0;
  graph.major.sections.forEach(function (section, i) {
    (function visit(node, key) {
      if (!node.items) return;
      // A list of courses, or of short sequences ("ECE 152A + 152B"), to choose from.
      const leafList = (node.type === "choose" || node.type === "units") &&
        node.items.every(item => item.type === "course" || (item.items && item.items.every(c => c.type === "course")));
      if (leafList && !(node.type === "choose" && node.count === 1 && node.items.length <= 4)) {
        if (!slotsAllowed(section.name)) return;
        let p = progress(node, key);
        while (p.have < p.need && slots < 60) {
          if (!addElectiveSlot(key)) return;
          slots += 1;
          p = progress(node, key);
        }
        return;
      }
      node.items.forEach((item, j) => visit(item, key + "." + j));
    })(section.requirement, "s" + i);
  });
  if (!quiet) say("Auto-fill placed " + placed + " courses and " + slots + " elective slots. Electives start in year 3; click a slot to choose its course.");
  planChanged();
}

/*
  Courses in an order where each comes after the ones it needs (among the
  courses being added): a depth-first walk that adds a course only after
  its prerequisites. This is what a "topological sort" is (CS 24). Ties go
  by the map's column, then code.
*/
function prerequisiteOrder(codes) {
  const inList = new Set(codes);
  const seen = new Set();
  const order = [];
  function visit(code) {
    if (seen.has(code)) return;
    seen.add(code);
    for (const need of coursesIn(nodesById[code].requires)) {
      if (inList.has(need)) visit(need);
    }
    order.push(code);
  }
  codes.sort((a, b) => (nodesById[a].column - nodesById[b].column) || bySortKey(a, b)).forEach(visit);
  return order;
}

// A safety pass: a course that still sits before a prerequisite placed
// later (a full quarter can push a prerequisite back) is placed again.
function repairOrder() {
  for (let round = 0; round < 4; round++) {
    let moved = false;
    for (const code of Object.keys(plan.placed)) {
      if (isDone(code) || !missingPrereqs(code).length) continue;
      const before = plan.placed[code];
      const wasAuto = (plan.auto || {})[code];
      delete plan.placed[code];
      if (!placeCourse(code)) plan.placed[code] = before;
      if (wasAuto) plan.auto[code] = true;
      else if (plan.placed[code] !== before) moved = true;
    }
    if (!moved) return;
  }
}

/*
  "Take one of" lists of 2–4 options: { options: [["MATH 2A"], ["MATH 3A"]],
  required }. `required` means every rule above it is "all of", so the
  student must take one of them (not one option among electives).
*/
function pickOneSets() {
  const sets = [];
  function codesOf(item) {
    if (item.type === "course") return item.code ? [item.code] : null;
    if (item.type === "all" && item.items.every(i => i.type === "course" && i.code)) return item.items.map(i => i.code);
    return null;
  }
  (function visitAll(nodes, required) {
    for (const node of nodes) {
      if (node.type === "choose" && node.count === 1 && node.items.length >= 2 && node.items.length <= 4) {
        const options = node.items.map(codesOf);
        if (options.every(Boolean)) {
          sets.push({ options: options, required: required });
          continue;
        }
      }
      if (node.items) visitAll(node.items, required && node.type === "all");
    }
  })(graph.major.sections.map(s => s.requirement), true);
  return sets;
}

// An elective slot goes in the first quarter from year 3 on with room.
function addElectiveSlot(key) {
  plan.electives = plan.electives || [];
  const slots = planSlots();
  let from = Math.max(0, slots.findIndex(s => s.year >= 3), firstOpenIndex());
  for (;;) {
    const list = planSlots();
    for (let i = from; i < list.length; i++) {
      if (list[i].q === "U") continue;
      if (quarterUnits(list[i].id) + ELECTIVE_UNITS <= plan.cap) {
        plan.electives.push({ id: "e" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), key: key, slot: list[i].id });
        return true;
      }
    }
    if (plan.years + plan.firstYear - 1 >= MAX_YEARS) return false;
    plan.years += 1;
  }
}

// Move a course or elective slot one quarter earlier (-1) or later (+1).
function moveSelected(step) {
  const slots = planSlots();
  const elective = (plan.electives || []).find(e => e.id === planSelected);
  const current = elective ? elective.slot : plan.placed[planSelected];
  const index = slots.findIndex(s => s.id === current) + step;
  if (index < 0) return;
  if (index >= slots.length) {
    if (plan.years + plan.firstYear - 1 >= MAX_YEARS) return;
    plan.years += 1;
  }
  const target = planSlots()[index].id;
  if (elective) elective.slot = target; else plan.placed[planSelected] = target;
  planChanged();
}

function moveTo(id, slotId) {
  const elective = (plan.electives || []).find(e => e.id === id);
  if (elective) elective.slot = slotId;
  else {
    plan.placed[id] = slotId;
    delete (plan.auto || {})[id];          // moved by hand: the student's choice now
    const info = courseInfo(id);
    plan.info = plan.info || {};
    plan.info[id] = { title: info.title, units: info.units, offered: info.offered };
  }
  planChanged();
}

function removeSelected() {
  if ((plan.electives || []).some(e => e.id === planSelected)) {
    plan.electives = plan.electives.filter(e => e.id !== planSelected);
  } else {
    delete plan.placed[planSelected];
  }
  planSelected = null;
  planChanged();
  showPlanSummary();
}

// ===========================================================================
// 9. Sharing, downloading, clearing
// ===========================================================================

/*
  A share link carries the plan itself in the address, so it works with no
  server: the plan as JSON, turned into URL-safe letters (base64). Grades
  are left out; they're the student's own business.
*/
function packPlan() {
  const data = {
    f: plan.firstYear, y: plan.years, s: plan.startYear, u: plan.summer ? 1 : 0, c: plan.cap,
    p: plan.placed, v: plan.units, e: (plan.electives || []).map(e => [e.key, e.slot]),
  };
  return btoa(JSON.stringify(data)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function unpackPlan(text) {
  try {
    const data = JSON.parse(atob(text.replace(/-/g, "+").replace(/_/g, "/")));
    return {
      firstYear: data.f === 3 ? 3 : 1,
      years: Math.min(MAX_YEARS, Math.max(1, Number(data.y) || 4)),
      startYear: Number(data.s) || defaultStartYear(),
      summer: Boolean(data.u),
      cap: Number(data.c) || 16,
      placed: data.p || {},
      units: data.v || {},
      electives: (data.e || []).map((e, i) => ({ id: "e" + i, key: e[0], slot: e[1] })),
    };
  } catch (error) {
    return null;
  }
}

function shareLink() {
  const url = location.href.split("#")[0] + planHashFor(currentPrograms) + "/" + packPlan();
  if (navigator.clipboard && location.protocol !== "file:") {
    navigator.clipboard.writeText(url).then(
      () => say("Link copied. It holds your plan (not your grades); anyone who opens it gets a copy."),
      () => say("Copy this link: " + url));
  } else {
    say("Copy this link: " + url);
  }
}

// The plan as a spreadsheet file (CSV opens in Excel, Numbers or Google Sheets).
function downloadPlan() {
  const rows = [["Year", "Quarter", "Course", "Title", "Units", "Grade"]];
  for (const slot of planSlots()) {
    const codes = Object.keys(plan.placed).filter(c => plan.placed[c] === slot.id).sort(bySortKey);
    for (const code of codes) {
      rows.push([slot.year, slotName(slot.id), code, courseInfo(code).title || "", unitsOf(code), plan.grades[code] || ""]);
    }
    for (const e of (plan.electives || []).filter(e => e.slot === slot.id)) {
      rows.push([slot.year, slotName(slot.id), electiveLabel(e.key), "", ELECTIVE_UNITS, ""]);
    }
  }
  const csv = rows.map(r => r.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(",")).join("\r\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  link.download = "ucsb-plan.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  say("Downloaded ucsb-plan.csv.");
}

function clearPlan() {
  if (!window.confirm("Clear every course and elective slot from your plan? Grades and credit stay.")) return;
  plan.placed = {};
  plan.electives = [];
  planSelected = null;
  say("Plan cleared.");
  planChanged();
}

planEl.autofill.addEventListener("click", autoFill);
planEl.share.addEventListener("click", shareLink);
planEl.download.addEventListener("click", downloadPlan);
planEl.clear.addEventListener("click", clearPlan);

// ===========================================================================
// 10. Clicks and dragging
// ===========================================================================

planEl.area.addEventListener("click", function (event) {
  const target = event.target.closest("button");
  if (!target) return;
  if (target.dataset.reqToggle) {
    const group = target.closest(".req-group");
    openGroups[target.dataset.reqToggle] = group.classList.contains("collapsed");
    drawRequirements();
  } else if (target.dataset.planAdd) {
    addCourse(target.dataset.planAdd);
  } else if (target.dataset.planShow) {
    const id = target.dataset.planShow;
    if ((plan.electives || []).some(e => e.id === id)) showElectiveSlot(id); else showPlanCourse(id);
  } else if (target.dataset.planElective) {
    if (addElectiveSlot(target.dataset.planElective)) say("Added an elective slot.");
    planChanged();
  } else if (target.dataset.planYears) {
    const change = Number(target.dataset.planYears);
    const last = plan.firstYear + plan.years - 1;
    if (change < 0 && (Object.values(plan.placed).some(s => s.startsWith(last + "-")) ||
                       (plan.electives || []).some(e => e.slot.startsWith(last + "-")))) {
      say("Year " + last + " has courses in it; move them first.");
      return;
    }
    plan.years = Math.min(MAX_YEARS - plan.firstYear + 1, Math.max(1, plan.years + change));
    planChanged();
  }
});

// The panel's buttons, while the Plan view is open.
el.panelBody.addEventListener("click", function (event) {
  if (currentView !== "plan") return;
  const target = event.target.closest("button");
  if (!target) return;
  if ("planClose" in target.dataset) {
    showPlanSummary();
    closeSheet();
  } else if (target.dataset.planMove) {
    moveSelected(Number(target.dataset.planMove));
  } else if ("planRemove" in target.dataset) {
    removeSelected();
  } else if (target.dataset.planAdd) {
    addCourse(target.dataset.planAdd);
  } else if (target.dataset.planFill) {
    // Fill an elective slot with an actual course, in the same quarter.
    const slot = plan.electives.find(e => e.id === planSelected);
    plan.electives = plan.electives.filter(e => e.id !== planSelected);
    moveTo(target.dataset.planFill, slot.slot);
    showPlanCourse(target.dataset.planFill);
  }
});
el.panelBody.addEventListener("change", function (event) {
  if (currentView !== "plan" || !event.target.dataset.planUnits) return;
  plan.units[event.target.dataset.planUnits] = Number(event.target.value);
  planChanged();
});

// Drag a course (from the grid or the requirements) onto a quarter.
planEl.area.addEventListener("dragstart", function (event) {
  const item = event.target.closest("[data-plan-drag]");
  if (!item) return;
  event.dataTransfer.setData("text/plain", item.dataset.planDrag);
  event.dataTransfer.effectAllowed = "move";
});
planEl.area.addEventListener("dragover", function (event) {
  const cell = event.target.closest("[data-plan-slot]");
  if (!cell) return;
  event.preventDefault();
  cell.classList.add("drop");
});
planEl.area.addEventListener("dragleave", function (event) {
  const cell = event.target.closest("[data-plan-slot]");
  if (cell) cell.classList.remove("drop");
});
planEl.area.addEventListener("drop", function (event) {
  const cell = event.target.closest("[data-plan-slot]");
  if (!cell) return;
  event.preventDefault();
  const id = event.dataTransfer.getData("text/plain");
  if (id) moveTo(id, cell.dataset.planSlot);
});
