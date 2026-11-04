# tests

Run from the repo root.

- `test_graph.py`: data checks over every program's graph. Run with `py tests/test_graph.py`.
- `test_site.py`: browser tests with Playwright. Serve `site/` first, then run `py tests/test_site.py`.
- `test_labels.json`: 450 hand-labeled courses that `pipeline/measure.py` scores the parser against.
