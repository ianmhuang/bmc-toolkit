# bmc-toolkit

Claude Code plugin for BMC firmware developers.

The first skill, `bmc-spec`, answers questions about BMC specifications
(IPMI, DCMI, LPC, eSPI, PWM fans, DMTF MCTP / PLDM / SPDM / NC-SI / SMBIOS,
Redfish, NVMe and NVMe-MI, OCP DC-SCM with LTPI and DC-MHS, I2C, SMBus,
PMBus, SFF-8485 SGPIO, CMIS) and about OpenBMC source
code. It keeps a local library of the documents and repositories you have
asked about, defaults to the latest published version of each document,
serves any specific version on request, and cites document, version, section
and page in every answer.

**Status: pre-release (0.9.0).** The Source Catalog covers Intel IPMI, LPC,
eSPI and the 4-wire PWM fan specification, DMTF, Redfish, NVMe, OCP DC-SCM
(with LTPI) and DC-MHS, I2C, SMBus, PMBus, SFF-8485 SGPIO and CMIS; UEFI
and ACPI are not in the catalog (uefi.org serves no scripted client) and
enter only as Drop-ins. Version 1.0.0 follows once the catalog is broader
and every document has been checked against the acceptance set in
`docs/golden-questions.md`.

## Install

```
/plugin marketplace add ianmhuang/bmc-toolkit
/plugin install bmc-toolkit@bmc-toolkit
```

Requirements: Python 3.11 or newer on `PATH` as `python` or `python3`, and
`git`. Third-party packages listed in `requirements.txt` are installed once
into the plugin's data directory by a `SessionStart` hook; in a development
checkout run `pip install -r requirements.txt` yourself.

- `curl_cffi` (MIT): HTTP client that presents a browser TLS fingerprint.
  Without it the tool falls back to `urllib`; Intel documents then come from
  the Internet Archive instead of the publisher, OCP documents still
  download directly (both verified).
- `pypdfium2` 5.x (BSD-3-Clause or Apache-2.0): PDF text with character
  positions and bookmarks; the text layer. Version 5 or newer is required
  (its bookmark API changed in 5.0); `extract` refuses an older install.
- `pdfplumber` (MIT): cell geometry and cell text of ruled tables, for
  `table`; loaded only by that command.

## Library location

Documents and code checkouts live under `~/.bmc-specs/` by default. Set
`BMC_SPEC_LIBRARY` to move it. The path is shared by every project on the
machine. Each document version sits at
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
caption, section, column edges, parts and rows). For a ZIP bundle,
`extract` writes `schemas/` instead: the JSON Schema files, flat, and
`extract.json` with `"kind": "schemas"` and the file and resource counts.
Code Trees live beside `specs/`, under `code/<repo>/<commit>/`, each with
a `.bmc-tree.json`.

## Command line

The skill drives `skills/bmc-spec/scripts/bmcspec.py`; you can run it
yourself:

```
python skills/bmc-spec/scripts/bmcspec.py catalog              # every document, one per line
python skills/bmc-spec/scripts/bmcspec.py catalog DSP0236      # one document, all versions
python skills/bmc-spec/scripts/bmcspec.py catalog --table --golden docs/golden-questions.md   # Support Level table
python skills/bmc-spec/scripts/bmcspec.py fetch DSP0236        # latest published version
python skills/bmc-spec/scripts/bmcspec.py fetch PMBUS-II --version 1.3.1   # the latest is gated: fetch names this one
python skills/bmc-spec/scripts/bmcspec.py fetch IPMI --version "2.0 rev 1.1"
python skills/bmc-spec/scripts/bmcspec.py fetch --all          # several hundred MB
python skills/bmc-spec/scripts/bmcspec.py add vendor.pdf --document DSP0236 --version 1.1.0   # --force to replace
python skills/bmc-spec/scripts/bmcspec.py scan                 # register hand-placed files
python skills/bmc-spec/scripts/bmcspec.py status
python skills/bmc-spec/scripts/bmcspec.py check DSP0236        # is the catalog behind DMTF? (no download)
python skills/bmc-spec/scripts/bmcspec.py check                # every document with a listing, plus the OpenBMC release
python skills/bmc-spec/scripts/bmcspec.py refresh --write      # maintainer: add the versions the publishers list
python skills/bmc-spec/scripts/bmcspec.py extract DSP0236      # text, outline, line map, figures
python skills/bmc-spec/scripts/bmcspec.py extract --all
python skills/bmc-spec/scripts/bmcspec.py section DSP0236 8.1  # level | title | pages, per matching entry
python skills/bmc-spec/scripts/bmcspec.py find DSP0236 "Msg tag" --context 1   # hits with page, line, section
python skills/bmc-spec/scripts/bmcspec.py page DSP0236 24 --to 25              # the pages, with a cite: line each
python skills/bmc-spec/scripts/bmcspec.py page DSP0236 --section 8.2
python skills/bmc-spec/scripts/bmcspec.py render DSP0236 --page 24             # renders/page-24.png
python skills/bmc-spec/scripts/bmcspec.py table DSP0236 --page 122             # the table(s) on the page, whole
python skills/bmc-spec/scripts/bmcspec.py extract DSP8010                       # unpack the Redfish JSON Schema
python skills/bmc-spec/scripts/bmcspec.py schema DSP8010 Chassis --property PowerState
python skills/bmc-spec/scripts/bmcspec.py repos --topic redfish                # repositories and held Code Trees
python skills/bmc-spec/scripts/bmcspec.py clone bmcweb                         # default branch, shallow
python skills/bmc-spec/scripts/bmcspec.py clone pldm --release 2.18.0          # the commit OpenBMC 2.18.0 ships
python skills/bmc-spec/scripts/bmcspec.py grep bmcweb CurrentPowerState --context 2
python skills/bmc-spec/scripts/bmcspec.py code bmcweb redfish-core/lib/chassis.hpp --lines 160-175
python skills/bmc-spec/scripts/bmcspec.py prune                # list superseded Code Trees; --yes removes them
```

Exit codes: 0 done, 1 error, 2 you need to act (the message says what).

`find` searches the latest held version (or `--version`), case-insensitively
unless `--case`, as a literal unless `--regex`; `--max` (default 50) caps the
hits. A document whose catalog entry lists `searched_with` (IPMI lists its
Specification Update) is searched together with those, their hits first;
`--only` skips them. `page` prints at most 10 pages per call
(`--max-pages`). Each printed page and each rendered page comes with a
`cite:` line: family, document and version, section, PDF page, printed
line range (or `rendered page`), origin URL or `user-provided`, and the
Library path. The Skill copies Citations from those lines and never
composes them.

`table` prints every ruled table touching the page as a Logical Table: the
pages it spans are read and joined (a table continues when it is the last
thing on its page, the next page starts with a table with the same column
edges, and only running headers, footers and page numbers lie between;
a repeated header row is dropped), and the result is a `cite:` line with
`PDF pages A-B` and `table K`, a `table:` line with the caption, and the
rows as a text grid. Tables are read on demand and kept in `tables.json`
next to the Extract, so a page is read from the PDF once; `--force` reads
it again. Tables without ruling lines are not detected.

`schema` reads a Redfish schema bundle (DSP8010): without a resource it
lists the resources and their newest schema version; with one it prints
the properties (type resolved through `anyOf` and `$ref`, read-only flag,
the version that added it, description); `--property` or `--definition`
prints one property or one named definition in full, including every
value of an enum with its description, following `$ref` into the file that
defines it. Each block starts with a `cite:` line naming the bundle
version, the schema file and the JSON pointer.

`clone` brings a repository into the Library as a Code Tree (a catalog
entry, or any `openbmc/<name>` when the catalog does not list it), a
shallow checkout at one commit under `code/<repo>/<commit>/` with a
`.bmc-tree.json` recording the URL, the commit, how it was reached (the
default branch, a `--ref` branch/tag/commit, or a `--release`) and when.
`--release L` resolves an OpenBMC release: `openbmc/openbmc` is fetched at
tag or branch L (only the `.bb` and `.inc` recipe files of every `meta-*`
layer, about 20 MB) and the component's `SRCREV` there is the commit
checked out; a repository no layer's recipe pins has no release commit,
and `clone` says so. For the `openbmc` repository itself `--release L` is
the same as `--ref L`. Several commits of one repository
coexist; `--force` on a moving name fetches again and marks the older tree
superseded rather than deleting it. `grep` (`git grep`) and `code` read a
tree: a user checkout named in `config.toml` first, then the `--ref` or
`--release` asked for, then the `config.toml` default Release, then the
default-branch tree. Every `code` output starts with a `cite:` line naming
repository, commit, provenance, path and lines.

`prune` lists every Code Tree marked superseded (an older commit of a
moving name re-fetched with `--force`) and every `.tmp-*` directory a
failed clone left behind, and removes nothing; `prune --yes` removes
them. The current tree of each name, trees reached by a commit, user
checkouts and `specs/` are never touched.

`config.toml` at the Library root (optional):

```toml
[library]
freshness_days = 30           # how old a Freshness Check may be before a note

[code]
release = "2.18.0"            # default Release for clone, grep and code

[code.checkouts]
bmcweb = "/home/me/src/bmcweb" # a checkout of your own wins over the Library
                               # (a relative path is taken from the Library root)
```

## Freshness Check

Publishers add versions faster than a catalog is maintained. `check DOC`
asks the publisher what it lists now and compares with the catalog:
`current DOC V`, or `newer DOC: catalog latest V, <publisher> lists W
(date) URL`. `check` alone does every document that has a listing (the
DMTF published-documents page, the nvmexpress.org specifications API, the
OCP wiki specification tables; Intel, NXP, SMBus and OIF have no
parseable index and are printed as `unchecked`), then, when `config.toml`
pins a release, compares it with the newest `X.Y.Z` tag of
`openbmc/openbmc` (`release: 2.18.0 (config.toml); newest openbmc tag
3.0.0 -> newer`). Nothing is downloaded and no version is switched: a
newer version enters the Library only after the catalog lists it (see
The Source Catalog below) or as a Drop-in. The outcome and the time go to
`freshness.json` at the Library root; `fetch` and `status` print a
`note:` when a document served has not been checked within
`freshness_days` (default 30), once per document until the next `check`,
and that note never touches the network.
OCP versions are mostly Google Drive links on the wiki, so `check`
reports them with `(URL to confirm by hand)`.

## What the tool does on the network and on disk

- Downloads only URLs listed in `bmc_toolkit/spec/catalog.toml`, in this
  order: the publisher's URL (with a browser TLS fingerprint through
  `curl_cffi`, which Intel's and OCP's CDNs require), then the Internet
  Archive's Wayback Machine snapshot of that URL, then it stops and prints
  the URL and the path to save the file to.
- A response that is not the expected PDF or ZIP (an HTML block page, a
  cut-off download) is discarded and never written to the Library. The same
  leading-bytes check applies to files given to `add` or found by `scan`.
- Writes only under the Library. Files placed there by hand are registered
  as Drop-ins and their origin is recorded as user-provided, never as a URL;
  `scan` also records whether the document id is in the catalog
  (`catalog_known`). Nothing already in the Library is replaced without
  `--force`.
- Replacing an original (`add --force`, `fetch --force`) removes the
  previous original and everything extracted from it, `tables.json`,
  `schemas/` and rendered pages included; so does `extract --force`.
- From a schema bundle only the JSON Schema files an answer needs leave the
  archive: every unversioned `<Name>.json` and the newest
  `<Name>.vX_Y_Z.json` per resource (452 files, 7.4 MB on disk, out of
  DSP8010 2026.1's 6890 JSON Schema files and 234 MB); CSDL, OpenAPI,
  dictionaries and the PDFs stay in the ZIP. Member paths that would
  escape `schemas/` are refused, and a base name that appears twice is
  written once.
- `check` and `refresh` read listing pages only: `https://www.dmtf.org/standards/published_documents` and `https://www.dmtf.org/dsp/<DSP>`, `https://nvmexpress.org/wp-json/vtm/v1/specifications`, and `https://www.opencompute.org/w/index.php?title=<page>` for the pages named in the catalog's `listing` keys. They download no document.
- Runs `git` as a subprocess for `clone` (shallow, one commit; `--filter=blob:none --sparse` for the `openbmc` repository), `grep` and `code` (reading `HEAD` of a user checkout), and `git ls-remote --tags` on the `openbmc` repository for `check`; `gh search code` for `repos --search`. Nothing else is executed, and nothing is re-uploaded or redistributed.
- `clone` writes only under the Library's `code/` directory: `code/<repo>/<commit>/` plus a temporary `.tmp-<pid>` directory that is removed on failure. A user checkout named in `config.toml` is only read. `prune --yes` removes superseded trees and `.tmp-*` leftovers under `code/`, nothing else.
- `check` writes `freshness.json` at the Library root; `fetch` and `status` stamp the reminder there (`reminded_at`) when they print the note. `refresh --write` is the one command that writes outside the Library: it appends version entries to the catalog file it was given (`--catalog`, or the shipped `bmc_toolkit/spec/catalog.toml`).

## The Source Catalog

`bmc_toolkit/spec/catalog.toml` lists every family, document, version and
URL; comments in the file record when a URL was last confirmed. Every
document has an access tier (`open`, `gated`: free registration or a
request to the publisher, `member`, `confidential`) and a fetch method
(`direct`, `wayback`, `manual`). A version may carry its own `access` when
the publisher keeps the newest revisions behind a registration (PMBus 1.4
and 1.5 are listed that way, with no URL): `fetch` refuses such a version,
prints the Drop-in instruction and names the newest open one (`newest open
version: 1.3.1; fetch it with --version 1.3.1`), and `fetch --all` takes
the newest open version with a `note:`. A `manual` document may list no
versions at all (member and NDA documents are registered so); `add`
accepts any version string for it and `check` lists it under
`unchecked (manual):` with its tier. A document's `limits` records its
Known Limits (tables drawn as images, no ruling lines, a defective text
layer); `catalog --table` prints the Support Level table from the catalog
(family, document, access, latest, fetch, Verified, known limit), and
`--golden docs/golden-questions.md` fills the Verified column from that
file's `Document` column with the question ids per version they were
checked on (`G13, G15 (1.3.1)`). The latest version is the one with the
newest publication date; same-day versions are told apart by the numbers
in their version strings (`2.0.0` over `1.3.0`). A document
may name companions in `searched_with` (errata, specification updates)
that `find` searches together with it, and a `listing`
(`dmtf:<DSP>`, implied for DMTF documents; `nvme:<slug>` of the
nvmexpress.org API; `ocp:<wiki page>|<description prefix>`) that `check`
and `refresh` consult. `refresh` prints the versions the publishers list
that the catalog lacks (`add`), catalog URLs that moved (`changed`, for
DMTF and NVMe) and versions a human has to handle (`confirm`: OCP rows,
whose download URL has to be found, and DMTF Work-in-Progress rows, which
the catalog lists only by hand with `wip = true`); `refresh --write`
appends the `add` entries as `[[documents.versions]]` blocks at the end of
the document's block, leaving every other line and comment as it was, and
refuses an edit the parser would not accept. If `check` reports a newer version, please open a
pull request with the `refresh --write` result (and the confirmed OCP
URL).

## Development

```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

## License

MIT. The specifications the tool downloads remain under their publishers'
licences and are never redistributed with this repository.
