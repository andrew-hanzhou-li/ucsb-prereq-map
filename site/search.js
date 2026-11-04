/*
  search.js: the two search boxes, "Choose a major or minor…" and
  "Find a course…".

  These used the browser's built-in suggestion list (<datalist>), which only
  matches exact text: "stats" found nothing, "cs 16" didn't find CMPSC 16,
  and a failed search just cleared the box. This is a small dropdown of our
  own instead:
    - case and spaces don't matter: "cs 16", "CMPSC16", "cmpsc 16"
    - common nicknames work: CS -> CMPSC / Computer Science, Stats ->
      PSTAT / Statistics, EE / CE, Econ, Poli Sci, Psych… (NICKNAMES)
    - arrow keys move, Enter picks, Esc closes; clicking into the box
      selects its text, so typing replaces it
    - no match: "No match for 'xyz'. Did you mean …?"
*/

// Nicknames: a word someone might type -> what it stands for. Program
// names use the words; course codes use the subject codes.
const PROGRAM_NICKNAMES = {
  cs: ["computer science"], compsci: ["computer science"], ce: ["computer engineering"],
  ee: ["electrical engineering"], ece: ["electrical", "computer engineering"], me: ["mechanical engineering"],
  mecheng: ["mechanical engineering"], cheme: ["chemical engineering"], che: ["chemical engineering"],
  econ: ["economics"], stats: ["statistics", "statistical"], stat: ["statistics", "statistical"],
  pstat: ["statistics", "statistical"], polisci: ["political science"], poli: ["political"],
  psych: ["psychological", "psychology"], bio: ["biology", "biological", "biochemistry", "biopsychology"],
  chem: ["chemistry", "chemical"], comm: ["communication"], math: ["mathematics", "mathematical"],
  phys: ["physics"], anthro: ["anthropology"], ling: ["linguistics"], hist: ["history"], soc: ["sociology"],
  env: ["environmental"], ds: ["data science"], ai: ["artificial intelligence"], geo: ["geography", "earth"],
  phil: ["philosophy"], art: ["art"], film: ["film"],
};
const COURSE_NICKNAMES = {
  cs: "cmpsc", compsci: "cmpsc", stats: "pstat", stat: "pstat", ee: "ece", ce: "ece", econ: "econ",
  polisci: "pols", poli: "pols", psych: "psy", writing: "writ", envs: "envs", env: "envs", bio: "mcdb",
};

// Lowercase letters and digits only: "PSTAT W 120A" -> "pstatw120a".
function squash(text) {
  return String(text).toLowerCase().replace(/[^a-z0-9]/g, "");
}

function words(text) {
  return String(text).toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
}

/*
  Does a program's name match what was typed? Every typed word (or one of
  its nickname's expansions) has to start some word of the name.
  "comp eng", "ce", "stats bs", "econ minor" all work.
  Returns a score (lower is better) or null.
*/
function programScore(query, name) {
  const nameWords = words(name.replace(/\./g, ""));      // "(B.S.)" -> "bs", so "cs bs" works
  let score = 0;
  for (const typed of words(query.replace(/\./g, ""))) {
    const options = [[typed]].concat((PROGRAM_NICKNAMES[typed] || []).map(words));
    let best = null;
    for (const option of options) {
      // Every word of this option must start some word of the name.
      const places = option.map(w => nameWords.findIndex(n => n.startsWith(w)));
      if (places.every(p => p >= 0)) best = best === null ? Math.max(...places) : Math.min(best, Math.max(...places));
    }
    if (best === null) return null;
    score += best;
  }
  return score + name.length / 1000;
}

/*
  Does a course code (or title) match? "cs 16" -> "cmpsc16" starts
  "cmpsc16"; "pstat w120a" -> "pstatw120a"; "linear alg" matches a title.
*/
function courseScore(query, code, title) {
  const typed = squash(query);
  if (!typed) return null;
  const tries = [typed];
  const lead = query.trim().toLowerCase().match(/^([a-z]+)\s*(.*)$/);
  if (lead && COURSE_NICKNAMES[lead[1]]) tries.push(COURSE_NICKNAMES[lead[1]] + squash(lead[2]));
  const compact = squash(code);
  for (const t of tries) {
    if (compact === t) return 0;
    if (compact.startsWith(t)) return 1 + compact.length / 100;
  }
  const titleWords = words(title || "");
  if (words(query).length && words(query).every(w => titleWords.some(t => t.startsWith(w)))) return 5;
  return null;
}

// How different two short texts are (edits needed): for "Did you mean".
function editDistance(a, b) {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let previous = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const here = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, previous + (a[i - 1] === b[j - 1] ? 0 : 1));
      previous = here;
    }
  }
  return row[b.length];
}

/*
  Turn a text box into a search box with a dropdown.
    find(query)   -> [{ value, label, hint }] best first
    pick(item)    called when one is chosen
    suggest(query) -> an item to offer as "Did you mean", or null
*/
function makeSearch(input, find, pick, suggest) {
  const list = document.createElement("ul");
  list.className = "search-list";
  list.hidden = true;
  list.setAttribute("role", "listbox");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.parentElement.classList.add("search");
  input.parentElement.appendChild(list);
  let items = [];
  let active = 0;

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
  }

  function show() {
    const query = input.value.trim();
    if (!query) {
      close();
      return;
    }
    items = find(query).slice(0, 12);
    active = 0;
    if (!items.length) {
      const guess = suggest ? suggest(query) : null;
      list.innerHTML = '<li class="search-none">No match for “' + escapeHtml(query) + "”." +
        (guess ? ' Did you mean <button type="button" class="text-button" data-guess>' + escapeHtml(guess.label) + "</button>?" : "") + "</li>";
      list.querySelector("[data-guess]") && (list.querySelector("[data-guess]").onmousedown = function (event) {
        event.preventDefault();
        choose(guess);
      });
    } else {
      list.innerHTML = items.map((item, i) =>
        '<li role="option" data-i="' + i + '"' + (i === active ? ' class="active" aria-selected="true"' : "") + ">" +
        escapeHtml(item.label) + (item.hint ? ' <span class="search-hint">' + escapeHtml(item.hint) + "</span>" : "") + "</li>").join("");
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function choose(item) {
    close();
    input.value = "";
    input.blur();
    pick(item);
  }

  function highlight(i) {
    active = (i + items.length) % items.length;
    list.querySelectorAll("li[data-i]").forEach((li, j) => {
      li.classList.toggle("active", j === active);
      li.setAttribute("aria-selected", j === active ? "true" : "false");
    });
  }

  input.addEventListener("input", show);
  input.addEventListener("focus", function () {
    input.select();
    if (input.value.trim()) show();
  });
  input.addEventListener("blur", function () { setTimeout(close, 150); });
  input.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown" && items.length) {
      event.preventDefault();
      highlight(active + 1);
    } else if (event.key === "ArrowUp" && items.length) {
      event.preventDefault();
      highlight(active - 1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (list.hidden) show();
      if (items.length) choose(items[active]); else show();
    } else if (event.key === "Escape") {
      close();
    }
  });
  // mousedown (not click), so the box doesn't lose focus and close first.
  list.addEventListener("mousedown", function (event) {
    const li = event.target.closest("li[data-i]");
    if (!li) return;
    event.preventDefault();
    choose(items[Number(li.dataset.i)]);
  });
}

// ---------------------------------------------------------------------------
// The two boxes
// ---------------------------------------------------------------------------

let courseIndex = null;      // every course in any program: { code: [title, [places in majors]] }

function findPrograms(query) {
  return majors.map(m => ({ m: m, score: programScore(query, displayName(m.name)) }))
    .filter(x => x.score !== null)
    .sort((a, b) => a.score - b.score)
    .map(x => ({ value: x.m.id, label: displayName(x.m.name), program: x.m }));
}

function guessProgram(query) {
  const typed = squash(query);
  let best = null;
  for (const m of majors) {
    for (const w of words(m.name)) {
      const d = editDistance(typed, w);
      if (d <= Math.max(1, Math.floor(w.length / 3)) && (!best || d < best.d)) best = { d: d, m: m };
    }
  }
  return best ? { value: best.m.id, label: displayName(best.m.name), program: best.m } : null;
}

function pickProgram(item) {
  const programs = currentPrograms.filter(p => p.id !== item.program.id).concat([item.program]);
  location.hash = currentView === "plan" ? planHashFor(programs) : hashFor(programs, null);
}

// On a map: the courses in its graph. On the front page: every course in
// any program (data/course-index.json, loaded the first time it's needed).
function findCourses(query) {
  const pool = graph
    ? Object.keys(nodesById).map(code => [code, nodesById[code].title])
    : Object.keys(courseIndex || {}).map(code => [code, courseIndex[code][0]]);
  return pool.map(([code, title]) => ({ code: code, title: title, score: courseScore(query, code, title) }))
    .filter(x => x.score !== null)
    .sort((a, b) => (a.score - b.score) || bySortKey(a.code, b.code))
    .map(x => ({ value: x.code, label: x.code, hint: x.title }));
}

function guessCourse(query) {
  const typed = squash(query);
  const pool = graph ? Object.keys(nodesById) : Object.keys(courseIndex || {});
  let best = null;
  for (const code of pool) {
    const d = editDistance(typed, squash(code));
    if (d <= 2 && (!best || d < best.d)) best = { d: d, code: code };
  }
  return best ? { value: best.code, label: best.code } : null;
}

function pickCourse(item) {
  if (graph && nodesById[item.value]) selectCourse(item.value, true);
  else showIndexedCourse(item.value);
}

async function loadCourseIndex() {
  if (courseIndex) return;
  try {
    courseIndex = window.EMBEDDED ? window.EMBEDDED.courseIndex : await (await fetch("data/course-index.json")).json();
  } catch (error) {
    courseIndex = {};
  }
}

/*
  A course looked up from the front page: which programs list it, each a
  link straight to that course on that program's map.
*/
function showIndexedCourse(code) {
  const entry = (courseIndex || {})[code];
  if (!entry) return;
  const programs = entry[1].map(i => majors[i]).filter(Boolean);
  let html = '<div class="panel-nav"><button type="button" class="nav-button" data-close>close</button></div>';
  html += "<h2>" + escapeHtml(code) + "</h2>";
  html += '<p class="course-title">' + escapeHtml(entry[0]) + "</p>";
  html += "<h3>In these programs</h3><ul>" + programs.map(m =>
    '<li><a href="' + hashFor([m], code) + '">' + escapeHtml(displayName(m.name)) + "</a></li>").join("") + "</ul>";
  html += '<p class="note">Open one to see what ' + escapeHtml(code) + " needs and what it unlocks there.</p>";
  html += '<p><a href="https://catalog.ucsb.edu/courses/' + encodeURIComponent(code) + '" target="_blank" rel="noopener">This course in the UCSB catalog</a></p>';
  el.panel.hidden = false;
  setPanel(html, code + "  " + entry[0]);
  openSheet();
}

function startSearch() {
  makeSearch(el.majorInput, findPrograms, pickProgram, guessProgram);
  makeSearch(el.courseInput, findCourses, pickCourse, guessCourse);
  // On the front page the course list loads the first time the box is used;
  // once it's here, search again for whatever was typed meanwhile.
  el.courseInput.addEventListener("focus", function () {
    if (courseIndex) return;
    loadCourseIndex().then(function () {
      if (document.activeElement === el.courseInput && el.courseInput.value.trim()) el.courseInput.dispatchEvent(new Event("input"));
    });
  });
}
