---
name: bmc-spec
description: Answer questions about BMC specifications (IPMI, DCMI, DMTF MCTP/PLDM/SPDM/NC-SI/SMBIOS, Redfish, NVMe/NVMe-MI, OCP DC-SCM/DC-MHS, I2C, SMBus, CMIS) and about OpenBMC source code (bmcweb, phosphor-host-ipmid, pldm, dbus-sensors and ninety more repositories, at master or at a named OpenBMC release), citing document, version, section and page, or repository, commit and line. Use whenever the user asks what a spec says, how a command or field is defined, or how OpenBMC implements something.
allowed-tools: Bash(python *)
---

# bmc-spec

Answer spec questions from the documents themselves: bring the document into
the Library, find the section or the phrase, read only the pages involved,
and cite what the tool printed. A table is read whole with `table`, even
when the PDF splits it over pages. OpenBMC source questions are answered
from a Code Tree: the repository at the commit the user's Ref or Release
names (or the default branch), searched with `grep` and read with `code`.

## Vocabulary

- **Source Catalog**: the list of known documents, their versions and
  download URLs, shipped with the plugin.
- **Library**: the on-disk store of downloaded documents, shared by every
  project on the machine. `$BMC_SPEC_LIBRARY` overrides the default
  `~/.bmc-specs`. Tell the user the path the first time a command prints
  `Library created at ...`.
- **Latest**: the newest published version in the catalog; versions
  published on the same day are told apart by the numbers in their version
  strings (`2.0.0` over `1.3.0`). Work-in-Progress versions count only when
  the user asks for WIP.
- **Drop-in**: a file the user placed into the Library by hand because the
  tool cannot download it (registration, membership, NDA, or a blocked
  download).
- **Access Tier**: `open` (downloadable), `gated` (free registration or a
  request to the publisher), `member`, `confidential` (NDA). A document has
  one; a version may have its own when the newest revisions are gated
  (PMBus 1.4 and 1.5). Only open versions are fetched; the rest are
  Drop-ins. A `manual` document may list no versions at all.
- **Extract**: `extract.txt` next to the original, every page introduced by
  `=== page N ===` (physical page, 1-based), layout preserved so tables read
  column by column. DMTF printed line numbers are removed from the text and
  kept in `linemap.json` (the Line Map), so a citation can say "lines
  680-700".
- **Outline**: `outline.json`, the section titles with their physical pages,
  from the PDF bookmarks or parsed from the contents pages (also when the
  bookmarks are only Word anchors such as `Ref_DSP0236`, or two or more of
  them all point at one page of a longer document). An entry whose page
  could not be confirmed is *approximate* and is printed with `~`.
- **Figure region**: `figures.json` records, per page, where raster images
  and vector drawings sit and which Extract lines lie inside them. Text
  inside a figure is often fragmentary; `find` and `page` mark such lines
  `[figure]`. Box-only diagrams (rectangles and text, nothing diagonal or
  curved) are not detected and read like tables.
- **Schema bundle**: a ZIP document (DSP8010) holding the Redfish JSON
  Schema. `extract` keeps, under `schemas/` next to the original, every
  unversioned `<Name>.json` (the index and the common definitions such as
  `Resource.json`) and the newest `<Name>.vX_Y_Z.json` per resource;
  nothing else leaves the archive. `schema` reads them; the text commands
  (`find`, `page`, `table`, ...) refuse bundles and say so.
- **Logical Table**: one ruled table of the document as its author meant
  it, reassembled from every page it spans: the header once, then the
  rows. `table` prints it and stores it in `tables.json` next to the
  Extract. Only tables drawn with ruling lines are found; a table laid out
  with spaces alone stays readable in the Extract.
- **Code Tree**: a shallow checkout of one catalog repository at one
  commit, at `code/<repo>/<commit>/` in the Library. The commit is its
  identity; the Ref or Release it was reached by is its provenance.
  Several Code Trees of one repository coexist (master today, the one a
  product ships); a re-fetched moving name marks the older tree
  `superseded`, never deletes it.
- **Ref**: a name on the component repository itself: a branch, a tag or
  a full commit id. Without one, the repository's default branch at fetch
  time (`master` for most OpenBMC repositories, `main` for libpldm).
- **Release**: a tag (`2.18.0`) or a Yocto-named branch (`scarthgap`) of
  `openbmc/openbmc`, whose recipes fix which commit of every component
  ships together. `config.toml` at the Library root may set a default
  Release for every answer; the tool never changes it.
- **Pin**: the commit of a component repository that a Release fixes
  through its recipe (`SRCREV`). `clone REPO --release L` resolves the Pin
  and holds the Code Tree at that commit.
- **User checkout**: a local checkout the user names in `config.toml`
  (`[code.checkouts] bmcweb = "/path"`); it wins over every Library Code
  Tree of that repository, whatever it has checked out.
- **Freshness Check**: `check` asks the publisher (DMTF, nvmexpress.org,
  the OCP wiki) what versions it lists and reports one the catalog lacks
  (`newer DOC: ...`). It never downloads or switches versions; the catalog
  stays the authority for Latest until a maintainer updates it. The
  outcome and the time go to `freshness.json` at the Library root. `fetch`
  and `status` print a `note:` when a document has not been checked
  within `freshness_days` (`[library]` in `config.toml`, default 30),
  once per document until the next `check` (the reminder is stamped in
  the same file).
- **Citation**: a `cite:` line printed by `page`, `render` or `table`. Its
  fields, separated by ` | `: family, document and version, section,
  `PDF page N` (or `PDF pages A-B` for a Logical Table), `lines A-B` (or
  `lines -`, `rendered page`, or `table K` for the K-th table on the first
  page), origin (download URL or `user-provided`), Library path. A `schema`
  Citation has, in the section, page and lines positions: `<Resource>
  vX.Y.Z` (or the index name), `file <name>.json`, and the JSON pointer of
  what was printed. A `code` Citation reads `cite: code | <repo>
  <commit7> | <provenance> | <path> lines A-B | - | <repository URL> |
  <Code Tree path>`, where provenance is `master 2026-09-03` (a branch or
  tag and the day it was fetched), `release 2.18.0`, or `user checkout`.

## Helper CLI

Every operation goes through one launcher; run it with the Bash tool:

```
python "${CLAUDE_SKILL_DIR}/scripts/bmcspec.py" <command> ...
```

| Command | What it does |
|---|---|
| `library` | print the Library path |
| `catalog [DOC] [--family F]` | list documents (one per line, tab-separated: family, id, access, fetch, latest, title, known versions joined by `;`) or show one document with every version, newest first (version, date, type, published/wip, URL or `-`, access), its `notes:` and `limits:` (Known Limits of the document itself); a manual document without versions prints the `add` command to use |
| `catalog --table [--golden FILE]` | the Support Level table (Markdown): family, document, access (`open (latest gated)` when the newest version differs), latest, fetch, Verified (the question ids from the Golden Questions file's `Document` column, grouped by the version they were checked on: `G13, G15 (1.3.1)`; `-` without `--golden`), known limit. For README and support questions, not for answering a specification question |
| `fetch DOC [--version V] [--wip] [--force]` | download one version into the Library; latest by default; prints a `skipped` line and stays off the network if already present. A gated, member or confidential version is not downloaded: exit 2 with the Drop-in instruction and `newest open version: X; fetch it with --version X` (or `no open version is listed`), unless the user already registered it with `add` or `scan`, which gives the usual `skipped` line and exit 0 |
| `fetch --all [--wip] [--force]` | latest open version of every downloadable document (a `note:` per document whose latest is gated); ends with a `summary:` line |
| `add FILE --document DOC --version V [--force]` | register a file the user obtained themselves (Drop-in); refuses to replace a version already present unless `--force`; the file must really be a PDF or ZIP |
| `scan` | register files placed by hand under `specs/<family>/<document>/<version>/original.pdf` |
| `status` | what the Library holds; columns: family, id, version, origin, size, `extracted` / `stale` (extracted by an older extractor: run `extract` again) / `-`, outline source; a final `note:` when held documents are due for a Freshness Check |
| `check [DOC]` | ask the publisher whether the catalog is behind: `current DOC V`, `newer DOC: catalog latest V, <publisher> lists W (date) URL` (OCP: `(URL to confirm by hand)`), or `unreachable DOC: reason`; without DOC every document with a listing, an `unchecked:` line for the hand-maintained ones, an `unchecked (manual):` line naming each manual document with its access tier, a `release:` line comparing `config.toml`'s release with the newest `openbmc/openbmc` tag (`-> newer` or `-> L is the newest`), and a `summary:`. Nothing is downloaded. Exit 2 for an unknown document or one without a listing |
| `refresh [DOC] [--write]` | maintainer command: what `check` found, per version (`add`, `changed`, `confirm` with the reason: an OCP URL to find, a DMTF Work-in-Progress row); `--write` appends the `add` entries to the catalog file. Not for answering questions |
| `extract DOC [--version V] [--force]` | write the Extract, Outline, Line Map and figure regions for a PDF version already in the Library (latest held version by default), or unpack a schema bundle's JSON Schema into `schemas/`; skips if current. A ZIP without a `json-schema/` folder (registries, profiles) is skipped with a message |
| `extract --all [--force]` | every PDF and bundle in the Library; ends with a `summary:` line |
| `section DOC QUERY [--version V]` | Outline entries matching a section number prefix (`20.1` also matches `20.1.2`) or every word of QUERY; one per line: `LEVEL \| title \| pages FIRST-LAST` (LEVEL 0 is a top-level heading), where LAST is where the next entry of the same or a higher level begins (`~` in front of an approximate page). `no matching section` when nothing matches |
| `find DOC PATTERN [--version V] [--regex] [--case] [--context N] [--max N] [--only]` | search the Extract; one line per hit: `DOC p.N [line L] \| section \| [figure] text`. Case-insensitive literal unless `--regex` / `--case`; `--context N` adds the surrounding lines (`line L:` or `row I:`) and a `--` separator; at most 50 hits unless `--max N` (`--max 0` prints all), then a `... more hits` line. Documents the catalog lists in `searched_with` (IPMI-UPDATE for IPMI) are searched too, their hits first; a missing one gets a `note:` line with the command to run; `--only` skips them. `no hits` when nothing matches |
| `page DOC N [--to M]` or `page DOC --section QUERY [--version V] [--max-pages K]` | print pages of the Extract, each starting with a `cite:` line, every line behind its printed line number when there is one, `[figure]` appended to lines inside a figure. Refuses more than 10 pages per call unless `--max-pages` |
| `render DOC --page N [--version V] [--scale S] [--force]` | write `renders/page-N.png` (S times 72 dpi, default 2) under the version directory; prints `rendered <path>` and a `cite:` line with `rendered page`. Reuses an existing file unless `--force` |
| `schema DOC [RESOURCE] [--property P \| --definition D] [--version V]` | read a schema bundle. No RESOURCE: every resource, one per line, `Name\tvX.Y.Z` (`-` for an index-only name such as a collection). RESOURCE: a `cite:` line, a `schema:` line (name, version, property count, the file's definitions), then one property per line: `name \| type \| readonly or writable \| added vX.Y.Z or - \| description`; types read `string`, `enum Def`, `object Def`, `array of T`, `odata name`, or the raw `$ref` when its file is not in `schemas/`. `--property P`: its description, longDescription, deprecation and other notes, and when it is an enum, a second `cite:` for the file that defines it (for instance `Resource.json`) followed by `values:` with every value, its description and when it was added. `--definition D`: the same for a named definition of the file (an enum, or an action with its `parameters:`). Names are case-insensitive; an unknown resource lists the names containing the query (exit 2) |
| `repos [--topic T]` | the catalog's repositories, one per line, four tab-separated fields: id, held Code Trees (`commit7 provenance`, `superseded` when re-fetched) or `-`, `user checkout: path` or `-`, topics; a first line `release: L (config.toml) -> openbmc <commit7>` when a default Release is set |
| `repos --search PATTERN` | GitHub code search over the openbmc organisation through `gh` (must be installed and logged in), `repo path` per hit; searches default branches only. For when no topic matches |
| `clone REPO [--ref R \| --release L] [--force]` | bring the repository into the Library as a Code Tree (REPO not in the catalog: `https://github.com/openbmc/REPO.git` is tried, with a `note:` saying so, and `repos` lists it as `(not in catalog)` afterwards): at branch/tag/full commit R, at the Pin of OpenBMC release L (the `openbmc` repository is fetched at L first, recipes only), or at the default branch. Prints `cloned <repo> <commit7> (<provenance>) -> <path>` or `held ...` when already there (no network); `--force` resolves a moving name again and prints `superseded` for the older tree. Uses the `config.toml` default Release when no flag is given, and says `release: L (from config.toml)` |
| `grep REPO PATTERN [--ref R \| --release L] [--regex] [--glob G] [--context N] [--max N]` | `git grep` over the selected Code Tree (user checkout first, then the named Ref or Release, then the config Release, then the default-branch tree): one hit per line `REPO@commit7 path:line \| text`, context lines as `line N:` with `--` between groups, at most 50 hits unless `--max` (0 = all); `no hits`; exit 2 with the `clone` command when the tree is not held. Case-sensitive, a fixed string unless `--regex` |
| `code REPO PATH [--lines A-B] [--ref R \| --release L]` | a `cite:` line then the file's lines behind their numbers; a file over 200 lines needs `--lines`. Same tree selection as `grep`; a `note:` line says when a user checkout or the config Release was used |
| `prune [--yes]` | `would remove <path> (...)` for every superseded Code Tree and `.tmp-*` leftover, then a `prune:` summary; only with `--yes` are they removed (`removed <path>`). Run `--yes` only when the user asked to free space |
| `table DOC --page N [--version V] [--index K] [--force]` | print every Logical Table touching page N, whole: a `cite:` line (`PDF pages A-B`, `table K`), a `table:` line (caption or `-`, page range, columns, rows including the header), then the rows as a grid, columns separated by ` \| `, one physical line per cell line, a rule after the header and after every row with a multi-line cell. `--index K` keeps only the K-th table on the page. Read from `tables.json` when the page was read before, unless `--force`. Exit 2 with `no ruled table on page N` when the page has none |

Exit codes: 0 done, 1 error (malformed catalog, unreadable file), 2 the
user must act (unknown document or version, download impossible, document
not in the Library or not extracted, too many pages asked for).

## Answering workflow

0. A Redfish data-model question (which properties a resource has, what a
   property means, which values an enum allows, what an action takes) is
   answered from the schema bundle: `fetch DSP8010`, `extract DSP8010`,
   then `schema DSP8010 <Resource> --property <P>` and cite the two
   `cite:` lines it prints. Questions about the protocol itself (HTTP,
   sessions, eventing) stay with the PDF, DSP0266.
1. Identify the Family and the Document. Without a named family prefer the
   one the project context suggests (CLAUDE.md, the conversation), else
   answer for the most likely family and say that another family has a
   same-named item. `catalog --family F` lists the candidates.
2. Make sure the version is there: `fetch DOC` (`skipped` if already held),
   then `extract DOC` (`skipped` if current). Pass the user's version
   verbatim with `--version`; on exit 2 relay the message and stop.
   When `fetch` ends with `note: DOC has not been checked against ...`,
   run `check DOC` once, then go on answering from the held version. If
   it printed `newer`, tell the user in one sentence which version the
   publisher lists and that the answer comes from the catalog's latest;
   never fetch or add the newer version unless the user asks, and never
   edit the catalog during a question (`refresh` is for maintainers).
3. Locate: `section DOC QUERY` when the user names a section or a topic
   that is a heading; `find DOC PATTERN` for a command name, a field, a
   code, a phrase. Read the section field of each hit to see where it lies.
4. Read only what you need: `page DOC N` for the hit pages, or
   `page DOC --section QUERY` for a short section. Never read a whole
   Extract into the conversation; a section longer than ten pages is read a
   few pages at a time.
5. When the answer sits in a table (a `Table` caption near the hit, or
   `page` shows columns), run `table DOC --page N` and read the row from
   the grid instead of from the page text: the grid has the header once and
   every row of the table, including those the PDF put on other pages.
   `no ruled table` means the table has no ruling lines; read the page
   text or render the page instead.
6. When a hit is marked `[figure]`, or the text of a page looks fragmentary
   (single words on their own lines, columns that do not line up), run
   `render DOC --page N` and open the PNG with the Read tool to look at the
   page.
7. Answer, quoting at paragraph granularity and in the document's own
   language, with a Citation for every claim.

## Code workflow (OpenBMC questions)

1. Pick the repository: `repos --topic T` (ipmi, redfish, pldm, sensors,
   power, state, firmware-update, oem, openpower, ...). When no topic fits,
   `repos --search PATTERN` asks GitHub; when `gh` is not there, say which
   repository you guessed and why. Any repository of the openbmc
   organisation can be cloned by name even when the catalog does not list
   it; the `note:` line tells you it was a guess, and so should your answer.
2. Pick the commit. The user names a release ("we ship 2.18.0", "our base
   is scarthgap"): `clone REPO --release L`. A branch, tag or commit of the
   repository itself: `clone REPO --ref R`. Nothing named: `clone REPO`
   (default branch), unless `config.toml` sets a default Release, which
   `clone` and the reading commands then use and announce. Never edit
   `config.toml` yourself; a newer release is the user's move. `check`
   (no document) says when `openbmc/openbmc` has a tag newer than the
   configured release; mention it, do not act on it.
3. `grep REPO PATTERN` for the identifier, D-Bus interface, command name
   or Redfish property; `--context 2` to see the surrounding lines;
   `--glob 'src/*.cpp'` to narrow.
4. `code REPO PATH --lines A-B` for the lines you will cite; keep ranges
   small (a function, not a file).
5. Answer with a Citation per claim. A `note:` line saying a user checkout
   was used means the answer is about the user's own working tree: say so.

## Two-part answers (spec and code)

When a question touches both a specification and OpenBMC, answer in two
parts, each with its own Citations: **what the spec says** (from `page`,
`table` or `schema`) and **what the code does** (from `grep` and `code`).
Then call out differences: values the schema allows that the code never
produces, a command the spec defines that the handler does not register, a
field the code sets that the spec marks optional. A difference is a
finding, not an error; say which side you would trust for the user's
purpose and why. Say which commit the code part describes; master today
and the user's release may differ, and `grep` at both is cheap.

## Citation rules

- Every Citation is copied from a `cite:` line the tool printed in this
  session. Do not compose one from memory, and do not cite a page you did
  not read.
- Line numbers appear only when the `page` output printed them for those
  lines; give the range you actually used, not the page's whole range.
- The `cite:` section is the entry in force at the top of the page; for a
  claim further down use the section printed by `find` for that hit, or
  the heading you saw in the page text.
- A `~` page comes from a contents page whose offset could not be
  confirmed: open the page and check the heading before citing it.
- An answer read from a rendered PNG says "read from a rendered page" in
  its Citation.
- A schema answer cites the `cite:` line(s) `schema` printed: the resource
  file and pointer, and for an enum the file that defines it. Say the
  bundle version and the schema version (`Chassis v1.28.0`); the enum's
  `added vX.Y.Z` notes say when a value appeared.
- A code claim cites the `cite:` line `code` printed (repository, commit,
  provenance, path and lines). Name the commit's provenance in the answer
  ("bmcweb ae6cec2, master as of 2026-09-03", "pldm 93ad795, the 2.18.0
  pin"), and never present a default-branch answer as what a release does.
- A value read from a Logical Table is cited with the `cite:` line `table`
  printed (all the pages the table spans, `table K`), naming the caption
  and the row; it carries no line numbers.
- Drop-in sources say "user-provided" in the origin field; keep it.
  Confidential documents are cited by path, never by a URL.
- A statement without a Citation is labelled inference.
- IPMI questions: `find IPMI ...` searches the base document together with
  IPMI-UPDATE (errata and clarifications) and prints the Update's hits
  first. When both hit, cite the Update first, then the base document.

## Rules

- Document ids are case-insensitive (`dsp0236`, `IPMI`, `NVME-MI`).
- When the user names a version, pass it verbatim with `--version`; the
  catalog keeps the publisher's own strings (`2.0 rev 1.1`,
  `Rev 2.1 Ver 1.1`). On exit 2 the message lists the known versions.
- When a download fails, relay the printed browser URL and the exact save
  path, then ask the user to run `scan` after saving. Never invent an
  alternative URL.
- When `fetch` exits 2 because the version is gated, member or
  confidential, relay the `newest open version:` line as it is and offer
  that version; fetch it only when the user agrees, and never claim the
  gated version's content from the open one without saying which version
  the answer comes from.
- `fetch --all` downloads several hundred megabytes; only run it when the
  user asks for everything. `extract --all` on a full Library takes a couple
  of minutes.
- `check` goes to the publishers' sites (a few requests) and is the only
  command that says whether the catalog is behind; run it when a `note:`
  asks for it or when the user asks whether a newer version exists. It
  never downloads. `prune --yes` deletes directories: only on request.
- `clone` is one repository at a time (2 to 32 MB each); a Release needs the
  the `openbmc` repository too (the recipe files of every layer, about 20
  MB), so `--release` resolves any repository a layer's recipe pins; a
  repository no layer builds has no Pin and `clone` says so. For the
  `openbmc` repository itself a release is its tag or branch: `clone openbmc
  --release L` and `grep openbmc ... --release L` read the recipes at L.
  Repository ids are case-insensitive; a commit given to `--ref` must be
  the full 40 characters.
