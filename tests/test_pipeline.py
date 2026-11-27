"""
test_pipeline.py: checks for the smaller pipeline scripts, on made-up data.

    py tests/test_pipeline.py

- build_majors.py: the catalog's rule types become our five requirement
  types, and hand corrections (program_overrides.json) are applied.
- fetch.py: catalog records become the flat shape in raw_courses.json.
- build_credit.py: "PSTAT 5AA-ZZ" expands to the current courses.

Nothing here reads data/ or the network.
"""

import contextlib
import io
import os
import sys

# The pipeline scripts live in pipeline/; tell Python to look there for them.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import build_credit
import build_majors
import fetch
from build_majors import Converter

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print("FAIL: %s %s" % (name, detail))


# ---------------------------------------------------------------------------
# build_majors.py
# ---------------------------------------------------------------------------

def courses_rule(condition, refs, **extra):
    """A catalog rule over a list of courses, each its own entry."""
    rule = {"condition": condition,
            "value": {"condition": "courses", "values": [{"value": [r], "logic": "and"} for r in refs]}}
    rule.update(extra)
    return rule


def converter(overrides=None):
    data = {
        "course_sets": {"set1": {"name": "Upper Division Math", "courses": ["MATH 108A", "MATH 104A", "MATH 100"]}},
        "course_group_ids": {"id123": "ECON  10A"},
    }
    return Converter(data, {"ECON 1", "ECON 2", "ECON 10A", "MATH 104A", "MATH 108A"}, overrides or {})


def codes(node):
    return [item.get("code") for item in node["items"]]


def test_build_majors():
    c = converter()

    check("course: a code in the course list is active", c.course("ECON 1") == {"type": "course", "code": "ECON 1", "status": "active"})
    check("course: a code not in the course list is inactive", c.course("ECON 141")["status"] == "inactive")
    check("course: an internal ID is looked up and its spaces tidied", c.course("id123")["code"] == "ECON 10A")
    check("course: an unknown ID is unresolved",
          c.course("zzz") == {"type": "course", "code": None, "status": "unresolved", "catalog_id": "zzz"})

    node = c.rule(courses_rule("completedAllOf", ["ECON 1", "ECON 2"], id="r1", name=" A. "))
    check("completedAllOf -> all", node["type"] == "all" and codes(node) == ["ECON 1", "ECON 2"], node)
    check("the rule id and label are kept", node["catalog_rule_id"] == "r1" and node["label"] == "A.", node)

    node = c.rule(courses_rule("completedAnyOf", ["ECON 1", "ECON 2"]))
    check("completedAnyOf -> choose 1", node["type"] == "choose" and node["count"] == 1, node)

    node = c.rule(courses_rule("completedAtLeastXOf", ["ECON 1", "ECON 2", "ECON 10A"], restriction=2))
    check("completedAtLeastXOf -> choose X", node["type"] == "choose" and node["count"] == 2, node)

    node = c.rule(courses_rule("minimumCredits", ["ECON 1"], credits=8))
    check("minimumCredits -> units", node["type"] == "units" and node["units"] == 8 and "count" not in node, node)

    node = c.rule(courses_rule("completeVariableCoursesAndVariableCredits", ["ECON 1", "ECON 2"],
                               minCourses=2, minCredits=8))
    check("variable courses and credits -> choose with units",
          (node["type"], node["count"], node["units"]) == ("choose", 2, 8), node)

    node = c.rule({"condition": "anyOf", "credits": 40, "subRules": [
        courses_rule("completedAllOf", ["ECON 1"]), courses_rule("completedAllOf", ["ECON 2"])]})
    check("anyOf over sub-rules -> choose 1, units kept as a note",
          node["type"] == "choose" and node["count"] == 1 and node["units"] == 40 and len(node["items"]) == 2, node)
    node = c.rule({"condition": "allOf", "subRules": [courses_rule("completedAllOf", ["ECON 1"])]})
    check("allOf over sub-rules -> all", node["type"] == "all", node)

    node = c.rule({"condition": "freeformText", "value": "Level 1-6 of a language"})
    check("freeformText -> text", node == {"type": "text", "text": "Level 1-6 of a language"}, node)
    node = c.rule({"condition": "completedAllOf", "value": {"condition": "none"},
                   "description": "<p>See the department.</p>"})
    check("no course list -> the description as text", node["type"] == "text" and node["text"] == "See the department.", node)
    node = c.rule(courses_rule("somethingNew", ["ECON 1"]))
    check("an unknown rule type is shown as text, not dropped",
          node == {"type": "text", "text": "Unrecognized rule type: somethingNew"}, node)

    node = c.rule({"condition": "completedAllOf", "value": {"condition": "courses", "values": [
        {"value": ["ECON 1", "ECON 2"], "logic": "or"}, {"value": ["ECON 1", "ECON 2"], "logic": "and"}]}})
    check("an 'or' entry -> choose 1, an 'and' entry -> all",
          [(i["type"], i.get("count")) for i in node["items"]] == [("choose", 1), ("all", None)], node)

    node = c.rule({"condition": "completedAtLeastXOf", "restriction": 1,
                   "value": {"condition": "courseSets", "values": [{"value": ["set1", "nope"]}]}})
    check("a course list keeps only current courses, in number order, with its name",
          codes(node)[:2] == ["MATH 104A", "MATH 108A"] and node["items"][0]["from_list"] == "Upper Division Math", node)
    check("an unknown course list is shown as text", node["items"][2] == {"type": "text", "text": "Unknown course list nope"})

    program = {
        "programGroupId": "econ", "name": "Economics - BA", "type": "Major", "departments": ["ECON"],
        "effectiveStartDate": "2026-09-20",
        "requisites": {"requisitesSimple": [
            {"type": "Narrative Text", "notes": "<p>Read this.</p>"},
            {"name": "Preparation ", "notes": "<ul><li>One</li><li>Two</li></ul>",
             "rules": [courses_rule("completedAllOf", ["ECON 1", "ECON 2"], id="prep")]},
            {"name": "Upper Division", "rules": [courses_rule("completedAnyOf", ["ECON 10A"], id="ud"),
                                                 courses_rule("completedAllOf", ["ECON 1"])]},
        ]},
    }
    result = c.program(program)
    check("program: narrative sections become narrative text", result["narrative"] == ["Read this."], result["narrative"])
    check("program: a section with one rule is that rule",
          result["sections"][0]["requirement"]["catalog_rule_id"] == "prep" and result["sections"][0]["name"] == "Preparation")
    check("program: section notes keep list items on their own lines", result["sections"][0]["notes"] == "- One\n- Two")
    check("program: a section with several rules is 'all' of them",
          result["sections"][1]["requirement"]["type"] == "all" and len(result["sections"][1]["requirement"]["items"]) == 2)
    check("program: kind, year and source",
          (result["kind"], result["catalog_year"], result["source"]) == ("major", "2026-27", "https://catalog.ucsb.edu/programs/econ"))
    check("program: every course listed once, with its first section",
          [(s["code"], s["section"]) for s in result["courses"]] ==
          [("ECON 1", "Preparation"), ("ECON 2", "Preparation"), ("ECON 10A", "Upper Division")], result["courses"])
    check("program: no overrides, no overrides_applied", "overrides_applied" not in result)

    overrides = {"econ": {
        "add": {"ud": {"courses": ["ECON 10A", "ECON 2"], "why": "added"}, "gone": {"courses": ["ECON 1"], "why": "x"}},
        "exclude": {"courses": ["ECON 1"], "why": "excluded"},
        "choose": {"prep": {"groups": [["ECON 2"], ["ECON 1"]], "label": "One of", "why": "chosen"}},
    }}
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        result = converter(overrides).program(program)
    check("override: a rule that isn't found is a warning, not a crash",
          printed.getvalue().count("WARNING") == 2, printed.getvalue())
    ud = result["sections"][1]["requirement"]["items"][0]
    check("override add: new courses only, marked as added",
          codes(ud) == ["ECON 10A", "ECON 2"] and ud["items"][1].get("added_by_override"), ud)
    check("override exclude: the course is gone everywhere",
          "ECON 1" not in [s["code"] for s in result["courses"]], result["courses"])
    check("override choose: groups not all found (ECON 1 was excluded) leaves the rule alone",
          codes(result["sections"][0]["requirement"]) == ["ECON 2"], result["sections"][0])
    check("override: each applied correction says why",
          result["overrides_applied"] == ["added", "excluded"], result["overrides_applied"])

    overrides = {"econ": {"choose": {"prep": {"groups": [["ECON 2"], ["ECON 1"]], "label": "One of", "why": "chosen"}}}}
    prep = converter(overrides).program(program)["sections"][0]["requirement"]
    check("override choose: the groups become one 'choose 1'",
          len(prep["items"]) == 1 and prep["items"][0]["type"] == "choose" and prep["items"][0]["count"] == 1
          and codes(prep["items"][0]) == ["ECON 1", "ECON 2"] and prep["items"][0]["label"] == "One of", prep)

    check("clean_text: tags, entities and blank lines",
          build_majors.clean_text("<p>A &amp; B</p><p></p><br/>C&nbsp; D") == "A & B\nC D",
          repr(build_majors.clean_text("<p>A &amp; B</p><p></p><br/>C&nbsp; D")))
    check("clean_text: nothing -> ''", build_majors.clean_text(None) == "")
    check("catalog_year: September starts a year, March is still the last one",
          [build_majors.catalog_year(d) for d in ("2026-09-20", "2027-03-29", "2099-12-01", None)] ==
          ["2026-27", "2026-27", "2099-00", ""])
    check("file_name", build_majors.file_name("Economics - BA ") == "economics-ba.json")
    check("program_kind", [build_majors.program_kind({"type": t}) for t in ("Minor", "Major", None)] ==
          ["minor", "major", "major"])
    check("department_name: the first one with a name",
          build_majors.department_name(["XX", "ECE"], {"ECE": "Electrical & Computer Engineering"}) ==
          "Electrical & Computer Engineering")
    check("department_name: none known", build_majors.department_name(["XX"], {}) == "Other programs")


# ---------------------------------------------------------------------------
# fetch.py
# ---------------------------------------------------------------------------

def test_fetch():
    check("clean_text: the example in its docstring",
          fetch.clean_text("<p>PHYS 5/PHYS 5L or PHYS 7D &amp; 7L.</p>") == "PHYS 5/PHYS 5L or PHYS 7D & 7L.")
    check("clean_text: a 'Comments:' label and extra spaces go",
          fetch.clean_text("Comments:  Open to<br/>majors only.") == "Open to majors only.")
    check("clean_text: nothing -> ''", fetch.clean_text(None) == "")

    check("course_level", [fetch.course_level(n) for n in ("5", "99L", "100", "199RA", "200", "", None)] ==
          ["lower", "lower", "upper", "upper", "graduate", "unknown", "unknown"])

    check("format_units: fixed", fetch.format_units({"creditHours": {"min": 4, "max": 4}}) == "4")
    check("format_units: a range", fetch.format_units({"creditHours": {"min": 1, "max": 4}}) == "1-4")
    check("format_units: variable units come from contactHours",
          fetch.format_units({"creditHours": {"min": 0, "max": 0}, "contactHours": {"min": 1, "max": 4}}) == "1-4")
    check("format_units: missing", fetch.format_units(None) == "" and fetch.format_units({}) == "")

    check("quarters_offered: in quarter order",
          fetch.quarters_offered({"quartersUsuallyOffered": ["Spring", "Fall"]}) == ["Fall", "Spring"])
    check("quarters_offered: not listed", fetch.quarters_offered({}) == [])

    raw = {"subjectCode": "MATH ", "courseNumber": " 3A", "longName": "Calculus &amp; Applications",
           "credits": {"creditHours": {"min": 4, "max": 4}},
           "requisites": {"requisitesFreeform": {"value": "<p>None.</p>"}},
           "customFields": {"quartersUsuallyOffered": ["Fall"], "advisorEnrollmentComments": "Comments: Hi"},
           "departments": [{"id": "MATH"}, "PSTAT"]}
    course = fetch.simplify(raw)
    check("simplify", course == {
        "code": "MATH 3A", "subject": "MATH", "number": "3A", "level": "lower",
        "title": "Calculus & Applications", "units": "4", "offered": ["Fall"], "prereq_text": "None.",
        "comments": "Hi", "description": "", "college": "", "departments": ["MATH", "PSTAT"]}, course)
    check("simplify: an almost empty record still works", fetch.simplify({})["code"] == " ")

    courses = [{"code": "MATH 108A", "subject": "MATH", "number": "108A", "v": 1},
               {"code": "MATH 3A", "subject": "MATH", "number": "3A", "v": 1},
               {"code": "MATH 3A", "subject": "MATH", "number": "3A", "v": 2}]
    kept = fetch.remove_duplicates(courses)
    check("remove_duplicates keeps the last copy", len(kept) == 2 and kept[1]["v"] == 2, kept)
    check("sort_key: 3A before 108A", [c["number"] for c in sorted(kept, key=fetch.sort_key)] == ["3A", "108A"])

    url = fetch.build_url(2000)
    check("build_url asks for the right page and catalog",
          "skip=2000" in url and "limit=%d" % fetch.PAGE_SIZE in url and fetch.CATALOG_ID in url, url)


# ---------------------------------------------------------------------------
# build_credit.py
# ---------------------------------------------------------------------------

def test_build_credit():
    current = {"PSTAT 5LS", "PSTAT 5AB", "PSTAT 5", "PSTAT 5LSX", "PSTAT 50AA"}
    check("expand: AA-ZZ means every current two-letter version",
          build_credit.expand("PSTAT 5AA-ZZ", current) == ["PSTAT 5AB", "PSTAT 5LS"],
          build_credit.expand("PSTAT 5AA-ZZ", current))
    check("expand: other codes are unchanged", build_credit.expand("MATH 3A", current) == ["MATH 3A"])


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="replace")
    test_build_majors()
    test_fetch()
    test_build_credit()
    print("%d checks passed, %d failed" % (passed, failed))
    sys.exit(1 if failed else 0)
