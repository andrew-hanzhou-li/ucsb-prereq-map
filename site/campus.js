/*
  campus.js: which UC campus this page shows, and everything that depends
  on it: where its data is, where its saved marks and plans are kept, and
  the campus screen ("Choose your university").

  Loaded before every other script, so they can all use CAMPUS.

  Addresses start with the campus:
    #ucsb/economics-ba                 a map
    #ucsb/plan/economics-ba            a plan
    #campus                            the campus screen
  An address with no campus in front (#economics-ba) is a link from before
  campuses were added: those were all UCSB, so it opens as UCSB.

  CAMPUS is fixed for the life of the page. Opening another campus reloads
  the page, so no data, marks or plan from one campus can mix with another's.
*/

// The site's name. A placeholder until Andrew picks one; it's also written
// in index.html and 404.html.
const SITE_NAME = "Prereq";

// UC's own order. "ready": its data is on the site. "next": being built
// (hasData: its data is on the site, for the preview). "later": not started.
const CAMPUSES = [
  { id: "ucb", name: "UC Berkeley", short: "Berkeley", terms: "Semesters", status: "later" },
  { id: "ucd", name: "UC Davis", short: "Davis", terms: "Quarters", status: "later" },
  { id: "uci", name: "UC Irvine", short: "Irvine", terms: "Quarters", status: "later" },
  { id: "ucla", name: "UCLA", short: "Los Angeles", terms: "Quarters", status: "next" },
  { id: "ucm", name: "UC Merced", short: "Merced", terms: "Semesters", status: "later" },
  { id: "ucr", name: "UC Riverside", short: "Riverside", terms: "Quarters", status: "later" },
  { id: "ucsd", name: "UC San Diego", short: "San Diego", terms: "Quarters", status: "next", hasData: true },
  { id: "ucsb", name: "UC Santa Barbara", short: "Santa Barbara", terms: "Quarters", status: "ready" },
  { id: "ucsc", name: "UC Santa Cruz", short: "Santa Cruz", terms: "Quarters", status: "later" },
];

// What differs between campuses in the site's words and links.
//   catalog       the catalog's name, as the footer and links say it
//   courseUrl     a course's catalog page from its code, when the catalog has
//                 one page per course; otherwise the data gives each course's
//                 own address (UCSD: one page per department)
//   program(s)    what a student picks: UCSB has majors and minors; UCSD,
//                 until its majors are read, has departments
//   examples      [address, name] for the front page's "For example"
const CAMPUS_DETAILS = {
  ucsb: {
    catalog: "UCSB General Catalog", catalogHome: "https://catalog.ucsb.edu/",
    courseUrl: code => "https://catalog.ucsb.edu/courses/" + encodeURIComponent(code),
    program: "major or minor", programs: "majors and minors", apChart: true, exampleCourse: "CMPSC 40",
    examples: [["economics-ba", "Economics (B.A.)"], ["statistics-and-data-science-bs", "Statistics and Data Science (B.S.)"],
               ["computer-engineering-bs", "Computer Engineering (B.S.)"]],
  },
  ucsd: {
    catalog: "UC San Diego General Catalog", catalogHome: "https://catalog.ucsd.edu/",
    courseUrl: null,
    program: "department", programs: "departments", apChart: true, exampleCourse: "CSE 12",
    examples: [["computer-science-and-engineering", "Computer Science and Engineering"], ["mathematics", "Mathematics"],
               ["biological-sciences", "Biological Sciences"]],
  },
};

function campusDetails() {
  return CAMPUS_DETAILS[CAMPUS] || CAMPUS_DETAILS.ucsb;
}

// "This course in the UCSB General Catalog", linked. `url` is the course's
// own address from the data, when there is one; only https links are used.
function catalogLinkFor(code, url) {
  const details = campusDetails();
  let href = url && /^https:\/\//.test(url) ? url : null;
  if (!href) href = details.courseUrl ? details.courseUrl(code) : details.catalogHome;
  return '<a href="' + escapeCampusText(href) + '" target="_blank" rel="noopener">This course in the ' +
         escapeCampusText(details.catalog) + "</a>";
}

const CAMPUS_SCREEN = "campus";               // the address of the campus screen
const REMEMBERED_CAMPUS_KEY = "prereq.campus";
// Every address before campuses were added was UCSB's.
const CAMPUS_OF_OLD_LINKS = "ucsb";

function campusById(id) {
  return CAMPUSES.find(c => c.id === id) || null;
}

// Preview: opening the site with "?preview" in the address also opens the
// "Coming next" campuses, to check them before they're marked ready. It's
// remembered on this device until "?preview=off".
const PREVIEW_KEY = "prereq.preview";
const PREVIEW = (function () {
  const asked = new URLSearchParams(location.search).get("preview");
  try {
    if (asked !== null) {
      if (asked === "off") localStorage.removeItem(PREVIEW_KEY);
      else localStorage.setItem(PREVIEW_KEY, "1");
    }
    return localStorage.getItem(PREVIEW_KEY) === "1";
  } catch (error) {
    return asked !== null && asked !== "off";     // storage blocked: this page only
  }
})();

function isReady(id) {
  const campus = campusById(id);
  // The one-file copy carries only UCSB's data.
  if (window.EMBEDDED) return id === "ucsb";
  if (!campus) return false;
  return campus.status === "ready" || (PREVIEW && campus.status === "next" && campus.hasData === true);
}

function decodedHash() {
  try {
    return decodeURIComponent(location.hash.slice(1));
  } catch (error) {
    return "";              // a mangled link: treat it as no address
  }
}

// "ucsb/economics-ba" -> { campus: "ucsb", rest: "economics-ba" }.
// No campus in front -> campus null, and rest is the whole address.
function splitCampus(raw) {
  const slash = raw.indexOf("/");
  const first = (slash < 0 ? raw : raw.slice(0, slash)).toLowerCase();    // "#UCSB/..." too
  if (campusById(first)) return { campus: first, rest: slash < 0 ? "" : raw.slice(slash + 1) };
  return { campus: null, rest: raw };
}

function rememberedCampus() {
  try {
    const id = localStorage.getItem(REMEMBERED_CAMPUS_KEY);
    if (isReady(id)) return id;
    // Someone who used the site before campuses were added has data under
    // the old UCSB names: they're a UCSB student.
    const oldUser = ["taken", "credit", "plan"].some(n => localStorage.getItem("ucsb-prereq-map." + n) !== null);
    return oldUser ? "ucsb" : null;
  } catch (error) {
    return null;            // storage blocked (private window): nothing remembered
  }
}

function rememberCampus(id) {
  try {
    localStorage.setItem(REMEMBERED_CAMPUS_KEY, id);
  } catch (error) {
    // Storage blocked: the campus screen shows again next time.
  }
}

/*
  Which campus the current address asks for:
    a campus id      that campus
    CAMPUS_SCREEN    the campus screen
    null             nothing chosen yet (empty address, nothing remembered)
  `current` is the campus already open, which an empty address keeps.
*/
function campusForAddress(current) {
  if (window.EMBEDDED) return "ucsb";          // the one-file copy is UCSB only
  const raw = decodedHash().replace(/\/$/, "");
  if (raw === CAMPUS_SCREEN) return CAMPUS_SCREEN;
  if (!raw) return current || rememberedCampus();
  return splitCampus(raw).campus || CAMPUS_OF_OLD_LINKS;
}

// The campus this page shows. null: the campus screen, until one is picked.
const CAMPUS = (function () {
  const wanted = campusForAddress(null);
  return wanted === CAMPUS_SCREEN ? null : wanted;
})();

// An old link (#economics-ba) is rewritten as #ucsb/economics-ba, without
// adding a Back step, so a copied address is always the new kind. Run at
// load, and by app.js when the address changes.
function updateOldLink() {
  const raw = decodedHash();
  if (raw && raw.replace(/\/$/, "") !== CAMPUS_SCREEN && !splitCampus(raw).campus) {
    history.replaceState(null, "", "#" + CAMPUS_OF_OLD_LINKS + "/" + location.hash.slice(1));
  }
}
updateOldLink();

// Where this campus's data files are on the site.
function dataUrl(fileName) {
  return "data/" + CAMPUS + "/" + fileName;
}

// The start of every address on this campus ("#ucsb/").
function campusHash() {
  return "#" + CAMPUS + "/";
}

/*
  Where this campus's marks, credit and plan are saved in the browser.
  Before campuses were added, UCSB's were saved under "ucsb-prereq-map.*";
  they're copied to the new names the first time, and the old ones are left
  in place (an older copy of the site, like a saved one-file copy, still
  reads them).
*/
function storageKey(name) {
  return "prereq." + CAMPUS + "." + name;
}

(function copyOldUcsbData() {
  if (CAMPUS !== "ucsb") return;
  for (const name of ["taken", "credit", "plan"]) {
    try {
      const old = localStorage.getItem("ucsb-prereq-map." + name);
      if (old !== null && localStorage.getItem(storageKey(name)) === null) {
        localStorage.setItem(storageKey(name), old);
      }
    } catch (error) {
      return;               // storage blocked: nothing to copy
    }
  }
})();

// ---------------------------------------------------------------------------
// The campus screen
// ---------------------------------------------------------------------------

function escapeCampusText(text) {
  return String(text).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

const STATUS_TEXT = { ready: "Ready", preview: "Preview", next: "Coming next", later: "" };

// `note`: shown above the list, e.g. when a link asked for a campus that
// isn't ready yet.
function showCampusScreen(note) {
  const screen = document.getElementById("campus-screen");
  document.body.classList.add("choosing-campus");
  document.title = SITE_NAME + " · Choose your university";
  screen.hidden = false;
  const noteBox = document.getElementById("campus-note");
  noteBox.textContent = note || "";
  noteBox.hidden = !note;
  document.getElementById("campus-list").innerHTML = CAMPUSES.map(function (campus, i) {
    const name = escapeCampusText(campus.short);
    let status = campus.status === "ready" && !isReady(campus.id) ? "later" : campus.status;   // one-file copy
    if (campus.status === "next" && isReady(campus.id)) status = "preview";
    // Only a campus that can open is a link; the rest say why they can't be picked.
    const label = isReady(campus.id)
      ? '<a class="campus-name" href="#' + campus.id + '/">' + name + "</a>"
      : '<span class="campus-name">' + name + '<span class="visually-hidden"> (not available yet)</span></span>';
    return '<li class="campus-row ' + status + (campus.id === CAMPUS ? " current" : "") + '">' +
      '<span class="campus-number" aria-hidden="true">' + (i + 1) + "</span>" + label +
      '<span class="campus-terms">' + campus.terms + "</span>" +
      '<span class="campus-status">' + STATUS_TEXT[status] + "</span></li>";
  }).join("");
}

function hideCampusScreen() {
  document.body.classList.remove("choosing-campus");
  document.getElementById("campus-screen").hidden = true;
}

// Keys 1 to 9 pick a campus while the campus screen is showing.
document.addEventListener("keydown", function (event) {
  if (!document.body.classList.contains("choosing-campus")) return;
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (document.querySelector("dialog[open]")) return;     // typing in the About box
  if (event.target.closest && event.target.closest("input, textarea, select")) return;
  const campus = CAMPUSES[Number(event.key) - 1];
  if (/^[1-9]$/.test(event.key) && campus && isReady(campus.id)) location.hash = "#" + campus.id + "/";
});
