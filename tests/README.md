# tests

Run from the repo root.

- `test_graph.py`: data checks over every program's graph. Run with `py tests/test_graph.py`.
- `test_parser.py`: checks for the prerequisite parser and notation, plus a floor on its score against `test_labels.json`. Run with `py tests/test_parser.py`.
- `test_pipeline.py`: checks for `build_majors.py`, `fetch.py` and `build_credit.py` on made-up data. Run with `py tests/test_pipeline.py`.
- `test_site.py`: browser tests with Playwright. Serve `site/` first, then run `py tests/test_site.py`.
- `test_labels.json`: 450 courses with AI-generated answers that `pipeline/measure.py` scores the parser against.
