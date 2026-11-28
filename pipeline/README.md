# pipeline

Python scripts that download the UCSB catalog and build the data the website loads. Run them from the repo root, in the order shown in the main [README](../README.md).

- **Download:** `fetch.py`, `fetch_programs.py`
- **Parse prerequisites:** `parser.py`, `notation.py`, `subjects.py`, `build_prereqs.py`, scored by `measure.py`
- **Translate requirements:** `build_majors.py`, checked by eye with `show_major.py`
- **Build the site's data:** `build_graph.py`, `build_credit.py`
- **Build site extras:** `build_single.py` (one-file copy), `build_preview.py` (link preview image)

## Other campuses

Each campus has its own fetcher and rules in `campuses/<id>/`; the parser (`parser.py`) and graph builder (`build_graph.py`) are shared. UC San Diego, in order:

```
python pipeline/campuses/ucsd/fetch.py            # about 86 pages, one a second; skips pages already saved
python pipeline/campuses/ucsd/extract.py
python pipeline/campuses/ucsd/build_prereqs.py
python pipeline/campuses/ucsd/build_departments.py
python pipeline/build_graph.py --campus ucsd
python pipeline/measure.py --campus ucsd --quiet  # parser accuracy on tests/ucsd_labels.json
```
