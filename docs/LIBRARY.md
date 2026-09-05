# Library layout

What `bmcspec.py` writes under the Library (`~/.bmc-specs/` unless
`BMC_SPEC_LIBRARY` says otherwise), so you can open the files yourself.
The commands that produce them are in [COMMANDS.md](COMMANDS.md).

Each document version sits at
`specs/<family>/<document>/<version>/original.<pdf|zip>` next to a
`meta.json` that records where it came from and its SHA-256. After
`extract` the same directory holds `extract.txt` (one `=== page N ===`
marker per physical page, layout preserved), `outline.json` (section
titles with pages, from PDF bookmarks or from the contents pages; Word
cross-reference anchors among the bookmarks, `Ref_DSP0236`, `OLE_LINK1`,
are dropped, and two or more bookmarks that all point at one page of a
longer document count as none),
`linemap.json` (DMTF printed line numbers: per physical page, the first
and last number and a map from each line's 0-based index within the page
block to its printed number) and `extract.json` (extractor version,
timing, what was found). Outline entries parsed from a contents page whose
page offset could not be confirmed carry `"approximate": true`.
`figures.json` lists, per page that has one, the figure regions (raster
images and vector drawings with the paths that overlap them, in PDF points)
and the indices of the text lines lying inside them; `renders/page-N.png`
holds pages rendered on request. `tables.json` holds the Logical Tables
read so far (a format version, `pages_done`, and per table the page range,
caption, section, how it is drawn, column edges, parts, rows and the page
each row starts on). For a ZIP bundle, `extract` writes `schemas/`
instead (DSP8010, and the profile schema of DSP8013): the JSON Schema
files, flat, and `extract.json` with `"kind": "schemas"` and the file and
resource counts; for the registries bundle DSP8011 it writes
`registries/`, the newest file of each message registry, and
`extract.json` with `"kind": "registries"`.
Code Trees live beside `specs/`, under `code/<repo>/<commit>/`, each with
a `.bmc-tree.json`.

While a command writes several files it holds `.lock` in the version
directory (`code/<repo>/.lock` for a clone): a small JSON file with the
holder's `pid`, `host`, `command` and `started` time, touched every 30
seconds while the holder is alive; one untouched for 5 minutes is stale
and the next command takes it over. Single files are written as
`<name>.<pid>-<token>.part` beside their target and renamed into place, and
a clone is built in `code/<repo>/.tmp-<pid>-<token>/` before it is renamed
to its commit. A `.part` or `.tmp-*` entry you find is a leftover of a
failed run; `prune` lists and removes them along with stale locks.
