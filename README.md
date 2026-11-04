# UCSB Prereq Planner

A tool that draws the prerequisite map for any UCSB major or minor, built from the official General Catalog.

**Live at https://andrew-hanzhou-li.github.io/ucsb-prereq-map/**

How it's designed: [DESIGN.md](DESIGN.md) (coming soon).

To rebuild everything from scratch (Windows):

```
py fetch.py
py fetch_programs.py
py build_prereqs.py
py build_majors.py
py build_graph.py
py measure.py --quiet
py test_graph.py
py build_credit.py
py build_single.py
```

`build_single.py` makes `site/ucsb-prereq-map.html`, the whole site in one file. Run it after changing anything in `site/`.

To see the site, run `py -m http.server 8000 --directory site` and open http://localhost:8000. If port 8000 is already in use, use another number, such as 8765.

To run the browser test, keep that server running and in a second terminal run `py test_site.py` (or `py test_site.py 8765` for another port).

The two `fetch` steps download from the catalog (about 40 requests total). Every data file they produce is already included, so you can skip them and start at `build_prereqs.py`.
