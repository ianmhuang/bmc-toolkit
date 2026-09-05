# bmc-toolkit

Claude Code plugin. Layout: `.claude-plugin/` (manifest, marketplace),
`skills/<name>/` (SKILL.md plus a launcher under `scripts/`), `bmc_toolkit/`
(the Python package the launchers import), `hooks/` (SessionStart dependency
install), `tests/`.

- Code, comments, commit messages and docs are in English.
- Run `ruff check .`, `ruff format --check .` and `python -m pytest -q` before
  committing; GitHub Actions runs the same three.
- `bmc_toolkit/` core logic is standard library only; `curl_cffi` and
  `pdfplumber` are imported lazily inside the commands that need them.

## How changes land

The maintainer's changes go through revali: acceptance criteria approved by
the owner before any code, an independent review with its own tests, and a
sandbox validation, then a squash merge. Contributors without that tooling
open a pull request; the checks in `.github/workflows/test.yml` and the
rules in CONVENTIONS.md are what a review looks for.

@CONVENTIONS.md
