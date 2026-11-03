/*
  grades.js: grades and a live GPA.

  Each course in the plan can have a grade: a letter (A+ … F), P or NP
  (Passed / Not Passed), or IP (In Progress). Grades are kept in plan.grades
  (student.js), in this browser only, and are never put in a share link.

  GPA, as the UCSB catalog defines it
  -----------------------------------
    grade points per unit:  A+ 4.0  A 4.0  A- 3.7
                            B+ 3.3  B 3.0  B- 2.7
                            C+ 2.3  C 2.0  C- 1.7
                            D+ 1.3  D 1.0  D- 0.7   F 0
    GPA = (sum of grade points x units) / (sum of units), letter grades only.
    P, NP and In Progress don't count toward GPA.
  Units come from the catalog (or the student's choice, for a variable-unit
  course), so the student never types them.

  A passing grade (D- or better, or P) counts as "done" for prerequisites,
  like a ticked course or credit. F and NP don't. Minimum grades in
  prerequisites ("C or better") aren't checked; the course's entry on the
  map shows them.
*/

const GRADE_POINTS = {
  "A+": 4.0, "A": 4.0, "A-": 3.7,
  "B+": 3.3, "B": 3.0, "B-": 2.7,
  "C+": 2.3, "C": 2.0, "C-": 1.7,
  "D+": 1.3, "D": 1.0, "D-": 0.7,
  "F": 0,
};
const OTHER_GRADES = { P: "P (Passed)", NP: "NP (Not Passed)", IP: "In Progress" };

// Passed: a letter grade other than F, or P.
function passedCourse(code) {
  const grade = plan.grades[code];
  if (!grade) return false;
  if (grade === "P") return true;
  return grade in GRADE_POINTS && grade !== "F";
}

/*
  The GPA over the courses with letter grades, optionally only those
  planned up to a quarter (for "GPA at the end of year 2"). Returns
  { gpa, units, points } (gpa null if nothing's graded yet).
*/
function gpaOf(untilSlotIndex) {
  let units = 0;
  let points = 0;
  for (const code of Object.keys(plan.grades)) {
    const grade = plan.grades[code];
    if (!(grade in GRADE_POINTS)) continue;
    if (untilSlotIndex !== undefined) {
      const slot = plan.placed[code];
      if (slot && slotIndex(slot) > untilSlotIndex) continue;
    }
    const u = unitsOf(code);
    units += u;
    points += GRADE_POINTS[grade] * u;
  }
  return { gpa: units ? points / units : null, units: units, points: points };
}

function formatGpa(gpa) {
  return gpa === null ? "—" : gpa.toFixed(2);
}

// The grade menu in a course's panel (planner.js, showPlanCourse).
function gradeHtml(code) {
  const current = plan.grades[code] || "";
  const options = ['<option value="">no grade yet</option>']
    .concat(Object.keys(GRADE_POINTS).map(g => '<option value="' + g + '"' + (current === g ? " selected" : "") + ">" + g + "</option>"))
    .concat(Object.keys(OTHER_GRADES).map(g => '<option value="' + g + '"' + (current === g ? " selected" : "") + ">" + OTHER_GRADES[g] + "</option>"));
  return '<p class="grade-row"><label>Grade <select data-plan-grade="' + escapeHtml(code) + '">' + options.join("") + "</select></label></p>";
}

// The GPA line in the plan's summary.
function gpaSummaryHtml() {
  const result = gpaOf();
  const graded = Object.keys(plan.grades).length;
  if (!graded) return '<p class="note">Add grades to courses you\'ve finished (click a course in the plan) to see your GPA.</p>';
  const inProgress = Object.values(plan.grades).filter(g => g === "IP").length;
  return '<h3>GPA</h3><p class="gpa"><strong>' + formatGpa(result.gpa) + "</strong> over " + result.units +
         " graded units" + (inProgress ? ", " + inProgress + " in progress" : "") + ".</p>" +
         '<p class="note">P/NP and In Progress don\'t count toward GPA.</p>';
}

el.panelBody.addEventListener("change", function (event) {
  if (currentView !== "plan" || !event.target.dataset.planGrade) return;
  const code = event.target.dataset.planGrade;
  if (event.target.value) plan.grades[code] = event.target.value;
  else delete plan.grades[code];
  delete (plan.auto || {})[code];          // graded: definitely the student's
  pruneCovered();
  planChanged();
  if (graph) draw();      // the map's ✓ and "next" marks follow grades too
});

/*
  Target grades for a goal GPA (Phase 6)
  --------------------------------------
  "To finish year 2 with a 3.50, what do I need from here?"

    graded so far (up to the end of that year):  U1 units, P1 grade points
    still to come (planned, no final grade yet): U2 units
      (In Progress counts as still to come; an elective slot as 4 units)
    needed average = (goal x (U1 + U2) - P1) / U2

  It's one average across the remaining courses. Spreading it by course
  difficulty (lower targets in historically harder courses) would need
  grade-distribution data, which isn't in the catalog; see PART9.md.
  Real grades depend a lot on the instructor, so this is rough guidance.
*/
function targetFor(goal, year) {
  const slots = planSlots();
  let last = -1;
  slots.forEach((s, i) => { if (s.year <= year) last = i; });
  const sofar = gpaOf(last);
  let remaining = 0;
  for (const code of Object.keys(plan.placed)) {
    const index = slotIndex(plan.placed[code]);
    if (index < 0 || index > last) continue;
    const grade = plan.grades[code];
    if (!grade || grade === "IP") remaining += unitsOf(code);
  }
  for (const e of plan.electives || []) {
    const index = slotIndex(e.slot);
    if (index >= 0 && index <= last) remaining += ELECTIVE_UNITS;
  }
  if (!remaining) return { needed: null, remaining: 0, sofar: sofar };
  const needed = (goal * (sofar.units + remaining) - sofar.points) / remaining;
  return { needed: needed, remaining: remaining, sofar: sofar };
}

// The lowest letter grade whose points reach the target: 3.62 -> "A-".
function letterFor(points) {
  const letters = Object.keys(GRADE_POINTS).filter(g => g !== "A+").reverse();     // F, D-, … A
  return letters.find(g => GRADE_POINTS[g] >= points - 1e-9) || null;
}

function targetText() {
  const goal = plan.goal || {};
  if (!goal.gpa) return "";
  const t = targetFor(goal.gpa, goal.year);
  const end = "by the end of year " + goal.year;
  if (!t.remaining) return "Nothing ungraded is planned through year " + goal.year + ", so there's nothing left to aim for there.";
  if (t.needed > 4.0) {
    return "A " + goal.gpa.toFixed(2) + " " + end + " would need a " + t.needed.toFixed(2) +
           " average over the remaining " + t.remaining + " units, more than straight A's. Try a later year or plan more units.";
  }
  if (t.needed <= 0) return "You'll have a " + goal.gpa.toFixed(2) + " " + end + " whatever grades you get in the remaining " + t.remaining + " units.";
  return "For a " + goal.gpa.toFixed(2) + " " + end + ", aim for about a <strong>" + Math.max(0, t.needed).toFixed(2) +
         "</strong> average (" + letterFor(t.needed) + " or better) across the remaining " + t.remaining + " planned units.";
}

function goalHtml() {
  const goal = plan.goal || {};
  const years = planSlots().map(s => s.year).filter((y, i, all) => all.indexOf(y) === i);
  return '<h3>Goal GPA</h3><p class="goal-row"><label>Goal <input type="number" step="0.01" min="0" max="4" data-goal="gpa" value="' +
         (goal.gpa || "") + '" placeholder="3.50"></label> <label>by the end of <select data-goal="year">' +
         years.map(y => '<option value="' + y + '"' + (Number(goal.year) === y ? " selected" : "") + ">year " + y + "</option>").join("") +
         "</select></label></p>" + (goal.gpa ? '<p class="target">' + targetText() + "</p>" : "") +
         '<p class="note">One average across the courses still to come. Grades depend a lot on the instructor, so treat this as rough guidance.</p>';
}

el.panelBody.addEventListener("change", function (event) {
  if (currentView !== "plan" || !event.target.dataset.goal) return;
  const row = event.target.closest(".goal-row");
  const gpa = parseFloat(row.querySelector('[data-goal="gpa"]').value);
  const year = Number(row.querySelector('[data-goal="year"]').value);
  plan.goal = gpa > 0 && gpa <= 4 ? { gpa: gpa, year: year } : null;
  savePlan();
  showPlanSummary();
});
