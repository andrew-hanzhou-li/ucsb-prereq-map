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
  planChanged();
  if (graph) draw();      // the map's ✓ and "next" marks follow grades too
});
