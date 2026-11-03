/*
  student.js: what the student brings with them, kept in this browser.

  Everything here is saved in localStorage on the student's own device and
  never sent anywhere (there's no server to send it to). Some browsers
  block localStorage, for example in private windows; every read and write
  is wrapped in try/catch so the site still works, it just forgets on close.

  This file holds:
    - credit already earned before UCSB:
        AP exams and scores        -> UCSB course equivalents, from the
                                      catalog's AP chart (data/credit.json)
        college / dual-enrollment  -> the UCSB courses the student says
                                      they have credit for
    - hasCredit(code) and creditFor(code), which the map and the planner
      use to treat that credit as done.

  Loaded before app.js; the Credit box (credit.js) edits it.
*/

const CREDIT_KEY = "ucsb-prereq-map.credit";

let creditTable = null;     // data/credit.json: the AP chart, loaded at start
let credit = loadCredit();  // { ap: { "Calculus BC": 4 }, transfer: ["CMPSC 40"] }

function loadCredit() {
  try {
    const saved = JSON.parse(localStorage.getItem(CREDIT_KEY) || "null");
    if (saved && typeof saved === "object") {
      return { ap: saved.ap || {}, transfer: Array.isArray(saved.transfer) ? saved.transfer : [] };
    }
  } catch (error) {
    // Storage unavailable or damaged: start empty.
  }
  return { ap: {}, transfer: [] };
}

function saveCredit() {
  try {
    localStorage.setItem(CREDIT_KEY, JSON.stringify(credit));
  } catch (error) {
    // Storage unavailable: credit still works until the page is closed.
  }
}

// The row of the AP chart a score earns, or null (no such exam, or a 1 or 2).
function apRow(examName, score) {
  if (!creditTable) return null;
  const exam = creditTable.ap.find(e => e.name === examName);
  if (!exam) return null;
  return exam.rows.find(r => r.scores.includes(Number(score))) || null;
}

/*
  Every UCSB course the student has credit for, with where it came from:
    "MATH 3A" -> "AP Calculus BC, score 4"
    "CMPSC 40" -> "college credit"
  An AP exam that counts as "MATH 2A, 3A or 34A" gives credit for all three,
  so a prerequisite naming any of them is satisfied.
*/
function creditSources() {
  const sources = {};
  for (const examName of Object.keys(credit.ap)) {
    const row = apRow(examName, credit.ap[examName]);
    if (!row) continue;
    for (const code of row.equivalents) {
      sources[code] = "AP " + examName + ", score " + credit.ap[examName];
    }
  }
  for (const code of credit.transfer) {
    if (!sources[code]) sources[code] = "college credit";
  }
  return sources;
}

let creditCache = null;
function creditChanged() {
  creditCache = null;
  if (typeof doneChanged === "function") doneChanged();
  saveCredit();
}

function creditFor(code) {
  if (!creditCache) creditCache = creditSources();
  return creditCache[code] || null;
}

function hasCredit(code) {
  return Boolean(creditFor(code));
}

function hasAnyCredit() {
  return Object.keys(credit.ap).length > 0 || credit.transfer.length > 0;
}

/*
  The student's plan: which quarter each course goes in, and the settings
  for the grid. One plan per browser, whatever programs are on screen, so
  switching or adding a program keeps everything already placed.

    plan.placed   { "ECON 1": "1-F" }   year number, then F/W/S/U
                                         (Fall, Winter, Spring, Summer)
    plan.units    { "ANTH 99": 2 }       units chosen for variable-unit courses
    plan.grades   { "ECON 1": "A-" }     grades (Phase 4)
    plan.auto     { "MATH 2A": true }    placed by auto-fill, not chosen by
                                         the student; only these are ever
                                         removed automatically
*/
const PLAN_KEY = "ucsb-prereq-map.plan";

function emptyPlan() {
  return {
    firstYear: 1,       // 3 for a transfer student, who starts in year 3
    years: 4,
    startYear: defaultStartYear(),
    summer: false,
    cap: 16,            // most units to place in one quarter
    placed: {},
    units: {},
    grades: {},
  };
}

// The Fall that started the current academic year: Fall 2026 for any date
// from September 2026 to August 2027. Most people using the planner are
// current students; an incoming freshman can pick next Fall.
function defaultStartYear() {
  const now = new Date();
  return now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1;
}

let plan = loadPlan();

function loadPlan() {
  try {
    const saved = JSON.parse(localStorage.getItem(PLAN_KEY) || "null");
    if (saved && typeof saved === "object") return Object.assign(emptyPlan(), saved);
  } catch (error) {
    // Storage unavailable or damaged: start empty.
  }
  return emptyPlan();
}

function savePlan() {
  // Grades may have changed what counts as done (app.js).
  if (typeof doneChanged === "function") doneChanged();
  try {
    localStorage.setItem(PLAN_KEY, JSON.stringify(plan));
  } catch (error) {
    // Storage unavailable: the plan still works until the page is closed.
  }
}
