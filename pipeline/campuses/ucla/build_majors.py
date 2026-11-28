"""
build_majors.py (UCLA): turn the catalog's major records into program files.

    python pipeline/campuses/ucla/build_majors.py

Reads   data/ucla/raw/majors/*.json          (from fetch.py)
        data/ucla/raw/courses/*.json         subject ids, for the catalog's ranges
        data/ucla/raw_courses.json           the course list (from extract.py)
        data/ucla/majors_translated.json     hand translations of prose rules,
                                             by rule id (see below)
Writes  data/ucla/programs/<major>.json      one per undergraduate major
        data/ucla/programs/index.json
        data/ucla/majors_prose.json          the prose rules still to translate

A UCLA major is a tree of rule groups. Each group has a line saying what to
do and, usually, what to do it with:
    "Select one course from:"                     [COM SCI M51A, EC ENGR M16]
    "Complete 17 courses as follows:"             13 courses and two choices
    "Complete 12 units minimum from:"             [CHEM 153A, CHEM 156, …]
    "Select three courses from French 100 through 169:"
                                                  a range the catalog stores as
                                                  a search (subject, numbers)
The line decides the rule:
    "Select / Complete N … from"     -> choose N  ("N units … from" -> N units)
    "Complete … as follows / the following / all", or no line  -> all of them
The count in "Complete 17 courses as follows" includes courses inside the
choices below it, so it's not checked against the list.

Some groups are prose only ("Select two life science courses from the life
sciences course list", "seven elective courses from Computer Science 100
through CM187 except M148"). Those are written into majors_prose.json and,
once translated by hand into the same node format UCSD's majors use
(course / all / choose / units / text, plus the shorthand items "range" and
"any"), kept in majors_translated.json under the rule's catalog id, so a new
download keeps them. A prose rule without a translation stays as text.
"""

import base64
import glob
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ucsd"))
from build_majors import expand  # noqa: E402  (the same node format and shorthand as UCSD)

RAW_MAJORS = os.path.join("data", "ucla", "raw", "majors")
RAW_COURSES = os.path.join("data", "ucla", "raw", "courses")
COURSES = os.path.join("data", "ucla", "raw_courses.json")
TRANSLATED = os.path.join("data", "ucla", "majors_translated.json")
PROSE_OUT = os.path.join("data", "ucla", "majors_prose.json")
PROGRAMS_DIR = os.path.join("data", "ucla", "programs")
SITE = "https://catalog.registrar.ucla.edu"
CATALOG_YEAR = "2026-27"
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15}
COUNT = r"(\d+|" + "|".join(NUMBER_WORDS) + r")"
CHOOSE_RULE = re.compile(r"^(?:(?:Select|Complete|Choose|Take)\s+)?(?:at least\s+|a minimum of\s+|any\s+|a total of\s+)?" + COUNT +
                         r"\b(?P<what>[^:]*?)\b(?:from|of the following)\b", re.IGNORECASE)
# "two courses from each of the following principles", "one course from each of three of the four areas"
EACH_RULE = re.compile(r"\bfrom (?:each of\s+(?:(?P<areas>\d+|" + "|".join(NUMBER_WORDS) + r")\s+of\b)?|"
                       r"(?P<some>\d+|" + "|".join(NUMBER_WORDS) + r")\s+of the following\s+(?:\w+\s+)?"
                       r"(?:areas|groups|categories|lists|tracks)\b)", re.IGNORECASE)
# A rule group the catalog offers but doesn't require: honors, specializations,
# field quarters, substitutions ("Chemistry 20AH may be substituted for 20A"),
# petitions and recommendations.
OPTIONAL_TITLE = re.compile(r"honors|departmental scholar|specialization$|optional|substitut|petition|"
                            r"biology quarter|recommended", re.IGNORECASE)
OPTIONAL_LINE = re.compile(r"\bmay be substituted\b|\bmay substitute\b|\bby petition\b|\boptional\b|"
                           r"\bhonors (?:students|program)\b|\bfor honors\b|"
                           r"\bmay not be applied toward the major\b", re.IGNORECASE)
# (A line that says what to complete is a requirement, whatever else it says:
# "Select four courses (… may be substituted for some)".)
IMPERATIVE = re.compile(r"^(?:Complete|Select|Choose|Take|Students must)\b", re.IGNORECASE)
# "Mathematics 33B is highly recommended" (but not "Complete four courses. It is
# strongly recommended that they be taken early").
RECOMMENDED_LINE = re.compile(r"^(?!(?:Complete|Select|Choose|Take)\b).*\brecommended\b", re.IGNORECASE)
UNITS_RULE = re.compile(r"^(?:Select|Complete|Take)\s+(?:at least\s+|a minimum of\s+)?(\d+(?:\.\d+)?)\s+units?\b", re.IGNORECASE)
COUNT_ONLY = re.compile(r"^(?:Select|Complete|Choose|Take)\s+(?:at least\s+|a minimum of\s+|any\s+|a total of\s+)?" + COUNT +
                        r"\s+(?!units?\b)(?:[\w-]+\s+){0,4}?(?:courses?|sequences?|series|options?|concentrations?)\b", re.IGNORECASE)
# "Select eight courses total, four in one area of concentration and two in …"
TOTAL_RULE = re.compile(r"^(?:Select|Complete)\s+" + COUNT + r"\s+courses\s+total\b", re.IGNORECASE)
ONE_OF_ANYWHERE = re.compile(r"\b(?:(?:complete|select|choose|take)\s+|from\s+)one of the following\b", re.IGNORECASE)
# "Complete a minimum of five courses from the following tracks": one track.
TRACKS = re.compile(r"\b(?:from|for) the following (?:tracks|concentrations|pathways)\b", re.IGNORECASE)
# "It is preferred that the three additional upper-division courses … are selected from:"
PREFERRED = re.compile(r"\b" + COUNT + r"\s+(?:additional\s+)?(?:[\w-]+\s+){0,2}courses\b[^:]*\bselected from\b", re.IGNORECASE)
# A rule given only as a range: "Select from Mathematics 106 through 199."
RANGE_TEXT = re.compile(r"^(?:Select|Choose)\s+(?:courses\s+)?from\s+([A-Za-z ,&]+?)\s+(\d+)\s+(?:through|to)\s+(\d+)\.?$", re.IGNORECASE)
ONE_SEQUENCE = re.compile(r"^(?:Select|Complete)\s+one\b[^:.]*\bsequence\b", re.IGNORECASE)
UPPER_RULE = re.compile(r"^(?:Complete|Select)\s+" + COUNT + r"\s+(?:additional\s+)?upper-division\s+([A-Za-z ,&]+?)\s+courses\b", re.IGNORECASE)
SOME_UNITS = re.compile(r"\band\s+(\d+(?:\.\d+)?)\s+units\s+from\s+([^:]*)", re.IGNORECASE)
UNITS_OF = re.compile(r"^Complete\b[^:]*?\(?(\d+(?:\.\d+)?)\s+units\)?\s+of\b", re.IGNORECASE)
ONE_MUST = re.compile(r"^(?:At least )?one of the\b[^.]*\bmust\b", re.IGNORECASE)
ONLY_ONE = re.compile(r"^Only one (?:course|of these courses) may (?:apply|be applied)\.?$", re.IGNORECASE)
SPLIT_RULE = re.compile(r"^Select\b[^:]*?\b" + COUNT + r"\s+courses?\b[^:]*?\band\s+" + COUNT + r"\s+courses?\b", re.IGNORECASE)
ALL_RULE = re.compile(r"^(?:Complete|Take)\b[^:]*\b(?:as follows|the following|all)\b", re.IGNORECASE)


def plain(markup):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup or "")).strip()


def count_of(word):
    word = word.lower()
    return NUMBER_WORDS.get(word) or int(word)


def subject_ids():
    """The catalog's id for each subject -> its code (from the course records)."""
    ids = {}
    for path in glob.glob(os.path.join(RAW_COURSES, "*.json")):
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        for area in record.get("educational_area_display") or []:
            if area.get("cl_id") and area.get("code"):
                ids[area["cl_id"]] = area["code"].strip()
    return ids


def search_terms(entry):
    """A stored search's conditions: ([(field, value)] it must match, [(field, value)] it must not).
    field is the last part of the name ("codeNumber"); a range gives ("codeNumber", (low, high))."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(entry.get("encodedURL", "")).query).get("appliedFilters", [""])[0]
    try:
        search = json.loads(base64.b64decode(query + "=" * (-len(query) % 4)).decode("utf-8"))
        bool_query = search["search"]["es"]["query"]["bool"]
    except (ValueError, UnicodeDecodeError, KeyError, TypeError):
        return None

    def terms(clauses):
        found = []
        for clause in clauses or []:
            if "query_string" in clause:
                field = clause["query_string"]["fields"][0].rsplit(".", 1)[-1]
                found.append((field, clause["query_string"]["query"]))
            elif "range" in clause:
                field, bounds = next(iter(clause["range"].items()))
                found.append((field.rsplit(".", 1)[-1], (bounds.get("gte"), bounds.get("lte"))))
        return found
    return terms(bool_query.get("must")), terms(bool_query.get("must_not"))


def code_parts(code):
    """"HIST M187A" -> ("M", 187, "A")."""
    match = re.search(r" ([A-Z]*)(\d+)([A-Z]*)$", code)
    return (match.group(1), int(match.group(2)), match.group(3)) if match else ("", -1, "")


def dynamic_range(entry, ids, catalog):
    """A stored search ("French 100 through 169", "Economics 105 to 199"
    without the labs, "Lower-Division History Courses (except History 19,
    89, 99)") -> a range item over the subject's numbers, with the courses
    the search leaves out in "except"; or None."""
    found = search_terms(entry)
    if not found:
        return None
    must, must_not = found
    subject = next((ids[v] for f, v in must if f == "educationalArea" and v in ids), None)
    if not subject:
        return None
    numbers = next((v for f, v in must if f == "codeNumber" and isinstance(v, tuple)), None)
    digits = lambda v, default: int(v) if v and str(v).isdigit() else default
    exact = next((v for f, v in must if f == "codeNumber" and not isinstance(v, tuple) and str(v).isdigit()), None)
    if numbers:
        low, high = digits(numbers[0], 0), digits(numbers[1], 199)
    elif exact:                                                        # "History 97A through 97O"
        low = high = int(exact)
    else:
        words = (entry.get("description") or "").lower()
        low, high = (1, 99) if "lower-division" in words else (100, 199) if "upper-division" in words else (0, 199)
    suffixes = {v for f, v in must if f == "codeSuffix" and not isinstance(v, tuple)}
    letters = next((v for f, v in must if f == "codeSuffix" and isinstance(v, tuple)), None)   # "60A through 60Z"
    skip_codes = {re.sub(r"\s+", " ", v).strip() for f, v in must_not if f == "code"}
    skip_numbers = {v for f, v in must_not if f == "codeNumber" and not isinstance(v, tuple)}
    skip_suffixes = {v for f, v in must_not if f == "codeSuffix"}
    skip_prefixes = {v for f, v in must_not if f == "codePrefix"}
    left_out = []
    for code, info in catalog.items():
        if info["subject"] != subject:
            continue
        prefix, number, suffix = code_parts(code)
        if not low <= number <= high:
            continue
        if (code in skip_codes or str(number) in skip_numbers or (suffix and suffix in skip_suffixes) or
                (prefix and prefix in skip_prefixes) or (suffixes and suffix not in suffixes) or
                (letters and not (letters[0] or "A") <= (suffix or "") <= (letters[1] or "Z"))):
            left_out.append(code)
    item = {"type": "range", "subject": subject, "from": low, "to": high}
    if left_out:
        item["except"] = sorted(left_out)
    return item


class Converter:
    def __init__(self, ids, translated, catalog):
        self.ids = ids
        self.catalog = catalog
        with open(os.path.join("data", "ucla", "subjects.json"), encoding="utf-8") as f:
            self.subject_names = json.load(f)
        self.translated = translated
        self.prose = []          # rules with no list, for translating

    def text_range(self, text):
        """"Select from Mathematics 106 through 199." -> a range item, or None."""
        found = RANGE_TEXT.match(text.strip())
        if not found or not self.subject_code(found.group(1)):
            return None
        return {"type": "range", "subject": self.subject_code(found.group(1)),
                "from": int(found.group(2)), "to": int(found.group(3))}

    def subject_code(self, words):
        """"Latin" -> "LATIN" (a subject's name, any case), or None."""
        words = words.strip().lower()
        for code, name in self.subject_names.items():
            if name.lower() == words:
                return code
        return None

    def group(self, container, major):
        """One rule group -> a node (UCSD's format, shorthand allowed)."""
        rule_id = container.get("cl_id")
        if rule_id in self.translated:
            node = self.translated[rule_id]["node"]
            if node["type"] == "text" and (ranged := self.text_range(node.get("text", ""))):
                return dict(ranged, label=node.get("label") or (container.get("title") or "").strip())
            return node
        line = plain(container.get("description"))
        title = (container.get("title") or "").strip()
        parts = []
        for item in sorted((container.get("relationship") or []) + (container.get("container") or []) +
                           (container.get("dynamic_relationship") or []), key=lambda x: int(x.get("order") or 0)):
            if item.get("academic_item_code"):
                parts.append({"type": "course", "code": re.sub(r"\s+", " ", item["academic_item_code"]).strip()})
            elif item.get("encodedURL"):
                found = dynamic_range(item, self.ids, self.catalog)
                parts.append(found or {"type": "text", "text": item.get("description") or "a course list"})
            elif "description" in item and ("container" in item or "relationship" in item):
                node = self.group(item, major)
                if node:
                    node = dict(node)
                    node["_plain"] = not plain(item.get("description"))     # a list with no rule of its own
                    node["_line"] = plain(item.get("description"))
                    parts.append(node)
        parts = one_of_kind(parts, line)
        node = None
        units = UNITS_RULE.match(line)
        choose = CHOOSE_RULE.match(line)
        if not parts:
            if line:
                self.prose.append({"major": major, "rule_id": rule_id, "title": title, "text": line})
                node = {"type": "text", "text": line}
        elif units and re.search(r"\bfrom\b", line, re.IGNORECASE):
            node = {"type": "units", "units": float(units.group(1)), "items": parts}
        elif ONE_MUST.match(line) and parts:
            # "One of the 16 courses for the preparation and major must be in history
            # before 1700 CE": one of these, which also counts where it's listed.
            node = {"type": "choose", "count": 1, "items": lists_joined(parts), "may_share": True}
        elif (total := TOTAL_RULE.match(line)) and count_of(total.group(1)) <= len(lists_joined(parts)):
            # (before "from each of": "eight courses total, four in one area and two from each of the others")
            node = {"type": "choose", "count": count_of(total.group(1)), "items": lists_joined(parts)}
        elif TRACKS.search(line) and len(parts) > 1 and all(p["type"] != "course" and not p.get("_plain") for p in parts):
            node = {"type": "choose", "count": 1, "items": parts}
        elif (preferred := PREFERRED.search(line)) and count_of(preferred.group(1)) < len(parts):
            node = {"type": "choose", "count": count_of(preferred.group(1)), "items": parts}
        elif (alternatives := line_alternatives(parts, line)):
            # "Select Bioengineering 177A and 177B (8 units) or Bioengineering 177C (12 units)."
            node = {"type": "choose", "count": 1, "items": alternatives}
        elif ONE_OF_ANYWHERE.search(line) and len(parts) > 1:
            # "… Students must complete one of the following four capstone options."
            node = {"type": "choose", "count": 1, "items": parts}
        elif ONE_SEQUENCE.search(line) and all(p["type"] == "course" for p in parts) and len({subject_of(p) for p in parts}) > 1:
            # "Select one intermediate sequence in one Asian language": the listed
            # courses, one sequence per language.
            by_subject = {}
            for part in parts:
                by_subject.setdefault(subject_of(part), []).append(part)
            node = {"type": "choose", "count": 1,
                    "items": [{"type": "all", "label": subject, "items": courses} for subject, courses in by_subject.items()]}
        elif choose and EACH_RULE.search(line) and all(p["type"] != "course" for p in parts):
            # Each list gives N; "from each of three of the four" asks for three lists.
            each = [{"type": "choose", "count": count_of(choose.group(1)), "items": unwrapped(p),
                     **({"label": p["label"]} if p.get("label") else {})} for p in parts]
            # ("one course from three of the following four areas": three areas, one course each)
            areas = EACH_RULE.search(line).group("areas") or EACH_RULE.search(line).group("some")
            node = {"type": "choose", "count": count_of(areas), "items": each} if areas else {"type": "all", "items": each}
        elif choose and (re.search(r"\bcourses?\b", choose.group("what"), re.IGNORECASE) or
                         not re.search(r"\bunits?\b", choose.group("what"), re.IGNORECASE)):
            # "Select one course from either group": the groups' courses are
            # one list (a group of courses isn't a single option). A list of
            # series ("Select one of the following series") stays as options.
            node = {"type": "choose", "count": count_of(choose.group(1)), "items": parts}
            # (Unless the parts have rules of their own that share the count out.)
            # ("Select one group of courses from:" chooses a group, not a course.)
            if (re.search(r"\bcourses?\b", choose.group("what"), re.IGNORECASE) and counted_across(node)["type"] == "choose"
                    and not re.search(r"\b(?:groups?|series|sets?|sequences?|pairs?)\b", choose.group("what"), re.IGNORECASE)):
                node["items"] = lists_joined(parts)
        elif ((counted := COUNT_ONLY.match(line)) and count_of(counted.group(1)) == len(or_pairs(parts, line))
              and len(or_pairs(parts, line)) < len(parts)):
            # "Complete four courses. Select either Mathematics 131B or 132." over five listed.
            node = {"type": "all", "items": or_pairs(parts, line)}
        elif ((counted := COUNT_ONLY.match(line)) and not ALL_RULE.match(line)
              and count_of(counted.group(1)) < sum(50 if p["type"] in ("range", "any") else 1 for p in lists_joined(parts))
              # (not "Complete 13 required courses, 12 units of technical breadth, …")
              and not re.search(r"\brequired\b", counted.group(0)) and not line[counted.end():].startswith(",")):
            # "Select three courses:" / "Complete seven elective courses" over a longer list
            node = {"type": "choose", "count": count_of(counted.group(1)), "items": lists_joined(parts)}
        elif (upper := UPPER_RULE.match(line)) and self.subject_code(upper.group(2)) and \
                count_of(upper.group(1)) > sum(1 for p in parts if p["type"] == "course") and \
                not any(p["type"] in ("all", "choose", "units") and not p.get("optional") for p in parts):
            # "Complete seven upper-division Latin courses, including course 110":
            # the courses named, and the rest from any upper-division Latin course.
            named = [p for p in parts if p["type"] == "course"]
            subject = self.subject_code(upper.group(2))
            rest = {"type": "choose", "count": count_of(upper.group(1)) - len(named), "label": "Other upper-division courses",
                    "items": [{"type": "any", "subject": subject, "level": "upper", "except": [p["code"] for p in named]}]}
            node = {"type": "all", "items": named + [rest] + [p for p in parts if p["type"] != "course"]}
        elif (some := SOME_UNITS.search(line)) and all(p["type"] == "course" for p in parts) and \
                len(numbered(parts, some.group(2))) >= 2:
            # "Complete the following six required courses and 4 units from
            # Theater 50A, 50B, 50C, or 50D": the six, and 4 units of the four.
            pool = numbered(parts, some.group(2))
            node = {"type": "all", "items": [p for p in parts if p not in pool] +
                    [{"type": "units", "units": whole(float(some.group(1))), "items": pool}]}
        elif (years := UNITS_OF.search(line)) and all(p["type"] == "course" for p in parts) and len(parts) > 1 \
                and not COUNT_ONLY.match(line):
            # "Complete two years (12 units) of performance organizations": 12 units of the listed ones.
            node = {"type": "units", "units": whole(float(years.group(1))), "items": parts}
        elif ONLY_ONE.match(line):
            node = {"type": "choose", "count": 1, "items": parts}
        elif (split := SPLIT_RULE.match(line)) and all(p["type"] == "all" for p in parts):
            # "Select a concentration of four courses in one area listed and two
            # courses in a second area": six courses from the areas (the spread is in the notes).
            node = {"type": "choose", "count": count_of(split.group(1)) + count_of(split.group(2)),
                    "items": lists_joined(parts)}
        else:
            node = {"type": "all", "items": or_pairs(parts, line)}
        if node is not None and node["type"] == "choose":
            node = counted_across(node)
        for part in parts:
            part.pop("_plain", None)
            part.pop("_line", None)
        if node is not None and node["type"] in ("all", "choose", "units"):
            # Optional groups count only where the major requires them as a whole:
            # inside a choice, "the honors series" is one of the ways to meet it.
            for part in node["items"]:
                if node["type"] != "all" and part.get("optional"):
                    del part["optional"]
        if node is not None and node["type"] != "text" and (OPTIONAL_TITLE.search(title) or
                                                       (not IMPERATIVE.match(line) and OPTIONAL_LINE.search(line)) or
                                                       RECOMMENDED_LINE.search(line)):
            node["optional"] = True
        if node is None:
            return None
        if node["type"] != "text" and title:
            node["label"] = title
        if node["type"] != "text" and line and not ALL_RULE.match(line):
            node["notes"] = line
        if node["type"] == "units" and float(node["units"]).is_integer():
            node["units"] = int(node["units"])
        return node


def pruned(node):
    """The node without lists that match no course (Philosophy's "graduate
    courses 201-219": graduate courses aren't in the undergraduate list), so
    a requirement isn't left that nothing can meet. None if nothing is left."""
    if node["type"] not in ("all", "choose", "units"):
        return node
    items = [kept for kept in (pruned(i) for i in node["items"]) if kept is not None]
    if not items:
        return None
    if node["type"] == "all" and len(items) == 1 and not node.get("optional") and items[0]["type"] != "course":
        # (A list holding one list: the inner one, under the outer one's name.)
        inner = dict(items[0])
        if node.get("label") and not inner.get("label"):
            inner["label"] = node["label"]
        return inner
    return dict(node, items=items)


def one_concentration(sections):
    """Chemistry BS lists "Chemistry Concentration" and "Physical Chemistry
    Concentration" as two sections; a student completes one. Two or more
    sections named "... Concentration" (or Option, Track) become one section,
    "Concentration", that's a "one of"."""
    named = re.compile(r"\b(?:concentration|option|track)$", re.IGNORECASE)
    picks = [s for s in sections if named.search(s["name"]) and not s.get("optional")]
    if len(picks) < 2:
        return sections
    choice = {"type": "choose", "count": 1, "label": "One concentration",
              "items": [dict(s["requirement"], label=s["name"]) for s in picks]}
    at = sections.index(picks[0])
    rest = [s for s in sections if s not in picks]
    return rest[:at] + [{"name": "Concentration", "requirement": choice}] + rest[at:]


def whole(number):
    """12.0 -> 12; 2.5 stays."""
    return int(number) if float(number).is_integer() else number


def line_alternatives(parts, line):
    """"Select course 191, or two courses from 198A and 198B, or 199A and 199B":
    the listed courses as options (each a course or an "all"), if the line's
    "or" splits them cleanly (every course in exactly one option); else None."""
    if len(parts) < 2 or any(p["type"] != "course" for p in parts) or not re.search(r"\bor\b", line):
        return None
    words = re.sub(r"\([^)]*\)", "", line.split(":")[0])
    chunks = re.split(r",?\s+or\s+", words)
    # ("Mathematics 31A or 31AL and Mathematics 31B" is a pair and a course:
    # or_pairs. Here the "or" must be the loosest: after a comma, or after an "and".)
    if len(chunks) < 2 or not (re.search(r",\s+or\b", words) or re.search(r"\band\b", chunks[0])):
        return None
    by_number = {p["code"].rsplit(" ", 1)[-1]: p for p in parts}
    options, used = [], set()
    for chunk in chunks:
        found = [by_number[n] for n in re.findall(r"\b([A-Z]{0,2}\d+[A-Z]*)\b", chunk) if n in by_number]
        if not found or any(p["code"] in used for p in found):
            return None
        used.update(p["code"] for p in found)
        options.append(found[0] if len(found) == 1 else {"type": "all", "items": found})
    return options if len(used) == len(parts) else None


def numbered(parts, words):
    """The courses in `parts` whose numbers the words name ("Theater 50A, 50B, or 50D")."""
    numbers = set(re.findall(r"\b([A-Z]{0,2}\d+[A-Z]*)\b", words))
    return [p for p in parts if p["type"] == "course" and p["code"].rsplit(" ", 1)[-1] in numbers]


def subject_of(course):
    return course["code"].rsplit(" ", 1)[0]


def courses_needed(node):
    """About how many courses a node asks for (units at 4 a course)."""
    if node["type"] in ("course", "range", "any"):
        return 1
    if node["type"] == "text" or node.get("optional") or "items" not in node:
        return 0
    if node["type"] == "choose":
        return node["count"]
    if node["type"] == "units":
        return max(1, round(node["units"] / 4))
    return sum(courses_needed(i) for i in node["items"])


def courses_in(node):
    """Every course (or course range) inside a node."""
    if node["type"] in ("course", "range", "any"):
        return [node]
    return [c for i in node.get("items", []) for c in courses_in(i)]


def counted_across(node):
    """"Complete nine courses from the following tracks and one capstone",
    "Select seven courses" over "three from group 1" and "three from group 2":
    the count is spread over parts that each have a rule of their own. A
    "choose" counts whole parts, so that could never be met. If the parts
    ask for the count between them, all of them are needed; if they ask for
    fewer, all of them plus the rest from any of their courses."""
    parts = [p for p in node["items"] if p["type"] != "text"]
    # (Lists with no rule of their own are one list, not parts with counts: see lists_joined.)
    if (not parts or any(p["type"] in ("course", "range", "any") or p.get("_plain") for p in parts)
            or node["count"] <= len(parts)):
        return node
    asked = sum(courses_needed(p) for p in parts)
    if asked >= node["count"]:
        return {k: v for k, v in dict(node, type="all").items() if k != "count"}
    extra = {"type": "choose", "count": node["count"] - asked, "label": "Additional courses",
             "items": [dict(c) for c in courses_in({"type": "all", "items": parts})]}
    out = {k: v for k, v in dict(node, type="all").items() if k != "count"}
    out["items"] = node["items"] + [extra]
    return out


def one_of_kind(parts, line):
    """A student completes one minor, one plan: "For the Conservation Biology
    minor, … is also required", "Plan I—Research Immersion" and "Plan II—
    Advanced Independent Research". Two or more such parts become one "one of"."""
    def kind(part):
        label = (part.get("label") or "").strip()
        own = part.get("_line") or ""
        if re.search(r"\bminor$", label, re.IGNORECASE) or re.match(r"(?:For|Required for) the [^,]* minor\b", own, re.IGNORECASE) \
                or re.match(r"Required for the .* minor", label, re.IGNORECASE):
            return "minor"
        if re.match(r"(?:Plan|Option|Pathway)\s+(?:[IVX]+|\d+|[A-Z])\b", label):
            return "plan"
        return None
    for which in ("minor", "plan"):
        picked = [p for p in parts if p["type"] != "course" and not p.get("optional") and kind(p) == which]
        if len(picked) < 2 or (which == "plan" and len(picked) != len([p for p in parts if p["type"] != "text"])):
            continue
        choice = {"type": "choose", "count": 1, "label": "One " + which, "items": picked}
        at = parts.index(picked[0])
        parts = [p for p in parts if p not in picked]
        parts.insert(at, choice)
    return parts


def lists_joined(parts):
    """For "N courses from" these lists: the courses of every plain list
    (an "all" that isn't a series), as one list. "Economics 104/104L" or
    "Physics 1 series" stay whole: one of them is one choice."""
    joined = []
    for part in parts:
        series = re.search(r"series|sequence|/", part.get("label") or "", re.IGNORECASE)
        if part["type"] == "all" and not series and not part.get("optional"):
            joined.extend(lists_joined(part["items"]))
        else:
            joined.append(part)
    return joined


def unwrapped(node):
    """A plain "all" list's items (for joining into a list above it); else the node itself."""
    return list(node["items"]) if node["type"] == "all" else [node]


def or_pairs(parts, line):
    """"Complete Mathematics 31A or 31AL and Mathematics 31B" lists all three
    courses; the line says 31A and 31AL are one choice. Courses the line joins
    with "or" become a "one of"."""
    pairs = re.findall(r"\b([A-Z]{0,2}\d+[A-Z]*)\s+or\s+(?:[A-Z][a-z]+\s+)*([A-Z]{0,2}\d+[A-Z]*)\b", line)
    by_number = {}
    for part in parts:
        if part["type"] == "course":
            by_number.setdefault(part["code"].rsplit(" ", 1)[-1], part)
    out = list(parts)
    for left, right in pairs:
        a, b = by_number.get(left), by_number.get(right)
        if b is None and a is not None:
            # (The catalog's "31A or 31L" means 31AL: the number of the left one, the right one's letter.)
            near = [p for n, p in by_number.items() if n != left and n.startswith(re.match(r"[A-Z]*\d+", left).group(0))
                    and n.endswith(re.sub(r"^[A-Z]*\d+", "", right) or "#")]
            b = near[0] if len(near) == 1 else None
        if a is None or b is None or a is b or a not in out or b not in out:
            continue
        at = out.index(a)
        out.remove(b)
        out[at] = {"type": "choose", "count": 1, "items": [a, b]}
    return out


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main():
    with open(COURSES, encoding="utf-8") as f:
        catalog = {c["code"]: c for c in json.load(f)["courses"]}
    translated = {}
    if os.path.exists(TRANSLATED):
        with open(TRANSLATED, encoding="utf-8") as f:
            translated = json.load(f)
    converter = Converter(subject_ids(), translated, catalog)
    os.makedirs(PROGRAMS_DIR, exist_ok=True)
    for old in glob.glob(os.path.join(PROGRAMS_DIR, "*.json")):
        os.remove(old)
    listing, problems = [], []
    for path in sorted(glob.glob(os.path.join(RAW_MAJORS, "*.json"))):
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        if "Undergraduate" not in json.dumps(record.get("degree_level")):
            continue
        # "Computer Science BS" -> "Computer Science - BS", the form the site
        # shows as "Computer Science (B.S.)" (as UCSB's and UCSD's names).
        name = re.sub(r"\s+(BA|BS|BFA|BM|BMus|BArch)$", r" - \1", record["title"].strip())
        department = (record.get("academic_org") or {}).get("value", "") if isinstance(record.get("academic_org"), dict) else ""
        sections = []
        for top in (record.get("curriculumStructure") or {}).get("container") or []:
            node = converter.group(top, name)
            if node is None:
                continue
            here = []
            requirement = pruned(expand(node, catalog, here, name + " / " + (top.get("title") or "")))
            problems.extend(here)
            if requirement is None:
                continue
            section = {"name": (top.get("title") or "Requirements").strip(), "requirement": requirement}
            parts = requirement.get("items") if requirement["type"] == "all" else None
            if requirement.get("optional") or (parts and all(p.get("optional") for p in parts)):
                section["optional"] = True
            sections.append(section)
        sections = one_concentration(sections)
        # (Optional sections, such as an honors program, after the required ones.)
        sections.sort(key=lambda section: bool(section.get("optional")))
        page = os.path.basename(path)[:-5]
        program = {"id": "UCLA-" + page, "name": name, "kind": "major", "type": "Bachelor's Degree",
                   "catalog_year": CATALOG_YEAR, "source": SITE + "/major/2026/" + page,
                   "sections": sections, "narrative": []}
        target = slug(name) + ".json"
        with open(os.path.join(PROGRAMS_DIR, target), "w", encoding="utf-8") as f:
            json.dump(program, f, indent=1, ensure_ascii=False)
        codes = set(re.findall(r'"code": "([^"]+)"', json.dumps(sections)))
        listing.append({"id": program["id"], "name": name, "kind": "major", "department": department,
                        "file": target, "source": program["source"], "structured": True, "courses": len(codes),
                        "inactive": sum(1 for p in problems if "isn't in the catalog" in p and p.startswith(name)),
                        "unresolved": 0})
    with open(os.path.join(PROGRAMS_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"majors": listing}, f, indent=1, ensure_ascii=False)
    with open(PROSE_OUT, "w", encoding="utf-8") as f:
        json.dump(converter.prose, f, indent=1, ensure_ascii=False)
    print("Wrote %d majors to %s; %d prose rules not yet translated (%s)"
          % (len(listing), PROGRAMS_DIR, len(converter.prose), PROSE_OUT))
    print("%d codes not in the course list" % sum(1 for p in problems if "isn't in the catalog" in p))


if __name__ == "__main__":
    main()
