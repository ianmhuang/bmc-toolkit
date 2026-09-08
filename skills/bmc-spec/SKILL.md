---
name: bmc-spec
description: Answer questions about BMC specifications (IPMI, DCMI, DMTF MCTP/PLDM/SPDM/NC-SI/SMBIOS, Redfish, NVMe/NVMe-MI, OCP DC-SCM/DC-MHS, I2C, SMBus, CMIS) and about OpenBMC source code (bmcweb, phosphor-host-ipmid, pldm, dbus-sensors and ninety more repositories, at master or at a named OpenBMC release), citing document, version, section and page, or repository, commit and line. Use whenever the user asks what a spec says, how a command or field is defined, or how OpenBMC implements something.
allowed-tools: Bash(python *)
---

# bmc-spec

Answer spec questions from the documents themselves: find the section or
the phrase (the reading commands bring the document into the Library and
extract it on their own), read only the pages involved, and cite what the
tool printed. A table is read whole with `table`, even
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
  the user asks for WIP. The local catalog changes only when the plugin
  updates; a publisher's newer version reaches you as a `note: newer` line.
- **Ready**: a document version that is in the Library and whose Extract
  (or unpacked bundle) is current, so a question about it is answered
  without downloading or extracting anything. The reading commands
  (`section`, `find`, `page`, `render`, `table`, `schema`, `registry`)
  bring the version they need to Ready by themselves: Latest, or the
  `--version` given, downloaded and extracted when the Library lacks it,
  with `fetched ...` and `extracted ...` lines before the answer. You never
  run `fetch` or `extract` before a reading command.
- **Drop-in**: a file the user placed into the Library by hand because the
  tool cannot download it (registration, membership, NDA, or a blocked
  download).
- **Access Tier**: `open` (downloadable), `gated` (free registration or a
  request to the publisher), `member`, `confidential` (NDA). A document has
  one; a version may have its own when the newest revisions are gated
  (PMBus 1.4 and 1.5). Only open versions are fetched; the rest are
  Drop-ins. A `manual` document may list no versions at all: the gated,
  member and NDA specifications (JEDEC, MIPI, PCI-SIG, PICMG, CXL, the
  BMC SoC datasheets, Intel's and AMD's NDA interfaces) are listed that
  way so you can tell the user why the tool has no copy.
- **Version coverage**: DMTF and NVM Express documents carry their full
  version history; every other publisher carries the current version
  plus older ones only where the catalog lists them by hand; UEFI Forum
  and TCG documents come from the Internet Archive (the newest release and
  the one before it for UEFI, ACPI and PI; the current one for TCG). Say
  so when a user asks for an older version the catalog does not list.
- **Extract**: `extract.txt` next to the original, every page introduced by
  `=== page N ===` (physical page, 1-based), layout preserved so tables read
  column by column. DMTF printed line numbers are removed from the text and
  kept in `linemap.json` (the Line Map), so a citation can say "lines
  680-700".
- **Outline**: `outline.json`, the section titles with their physical pages,
  from the PDF bookmarks or parsed from the contents pages (also when the
  bookmarks are only Word anchors such as `Ref_DSP0236`, or two or more of
  them all point at one page of a longer document). An entry whose page
  could not be confirmed is *approximate* and is printed with `~`; when
  its heading is found on the page before or after instead, the reading
  commands count it from there.
- **Figure region**: `figures.json` records, per page, where raster images
  and vector drawings sit and which Extract lines lie inside them. Text
  inside a figure is often fragmentary; `find` and `page` mark such lines
  `[figure]`. Box-only diagrams (rectangles and text, nothing diagonal or
  curved) are not detected and read like tables.
- **Schema bundle**: a ZIP document (DSP8010) holding the Redfish JSON
  Schema. `extract` keeps, under `schemas/` next to the original, every
  unversioned `<Name>.json` (the index and the common definitions such as
  `Resource.json`) and the newest `<Name>.vX_Y_Z.json` per resource;
  nothing else leaves the archive. The profile bundle (DSP8013) ships only
  the profile schema, `RedfishInteroperabilityProfile.vX_Y_Z.json`, and is
  unpacked the same way. `schema` reads them; the text commands (`find`,
  `page`, `table`, ...) refuse bundles and say so.
- **Registries bundle**: a ZIP document (DSP8011) holding the Redfish
  message registries. `extract` keeps, under `registries/`, the newest
  `<Prefix>.<M>.<m>.<p>.json` per registry (Base, ResourceEvent, Update,
  ...); the privilege registries, the HTML and the PDF stay in the
  archive. `registry` reads them and prints a message's text verbatim,
  since that text is what a client matches.
- **Logical Table**: one table of the document as its author meant it,
  reassembled from every page it spans: the header once, then the rows.
  `table` prints it and stores it in `tables.json` next to the Extract.
  Two drawings are read: `ruled` tables (ruling lines, most publishers)
  and `cells` tables (no rules; every cell is a filled box tiled edge to
  edge, DMTF's current PDFs); the `table:` line says which. A table laid
  out with spaces alone is not found and stays readable in the Extract.
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
  outcome and the time go to `freshness.json` at the Library root. A
  reading command runs the check itself, after its output, when the
  document has not been checked within `freshness_days` (`[library]` in
  `config.toml`, default 30), and prints the outcome as `note: newer DOC:
  ...` (nothing when current, `note: unreachable DOC: ...` when the
  publisher could not be read); the outcome is recorded, so the next
  question within that age does not check again. `fetch` and `status`
  print a `note:` reminder to run `check` instead, once per document.
  `[library] offline = true` in `config.toml` turns the reading commands'
  downloads and checks off (a held version is still extracted); `fetch`,
  `check` and `clone` ignore it.
- **Citation**: a `cite:` line printed by `page`, `render` or `table`. Its
  fields, separated by ` | `: family, document and version, the sections
  the page spans (joined by `; `; one section for `page --section` and
  `table`), `PDF page N` (or `PDF pages A-B` for a Logical Table), `lines A-B` (or
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
| `catalog --table [--golden FILE] [--by-family]` | the Support Level table (Markdown): family, document, access (`open (latest gated)` when the newest version differs), latest, fetch, Verified (the question ids from the Golden Questions file's `Document` column, grouped by the version they were checked on: `G13, G15 (1.3.1)`; `-` without `--golden`), known limit; `--by-family` prints the reader's form kept in `docs/SUPPORT.md` instead: one heading and table per family, no fetch column, Verified as `PASS` or `-`, documents with `unlisted = true` in the catalog left out. For README and support questions, not for answering a specification question |
| `fetch DOC [--version V] [--wip] [--force] [--no-extract]` | download one version into the Library and leave it Ready: latest by default; prints a `skipped` line and stays off the network if already present, then the `extracted` line (or `skipped ...: already extracted`); `--no-extract` stops after the download. A failed extraction after a good download prints `failed DOC V: ...` and exit stays 0 (the download landed). A gated, member or confidential version is not downloaded: exit 2 with the Drop-in instruction and `newest open version: X; fetch it with --version X` (or `no open version is listed`), unless the user already registered it with `add` or `scan`, which gives the usual `skipped` line and exit 0. Not needed before a reading command; for prefetching a document the user names |
| `fetch --all [--wip] [--force]` | latest open version of every downloadable document (a `note:` per document whose latest is gated); ends with a `summary:` line |
| `add FILE --document DOC --version V [--force]` | register a file the user obtained themselves (Drop-in); refuses to replace a version already present unless `--force`; the file must really be a PDF or ZIP |
| `scan` | register files placed by hand under `specs/<family>/<document>/<version>/original.pdf` |
| `status` | what the Library holds; columns: family, id, version, origin, size, `extracted` / `stale` (extracted by an older extractor: run `extract` again) / `-`, outline source; then one `lock:` line per lock another Session holds (path, pid, host, command, since when, `live` or `stale`); a final `note:` when held documents are due for a Freshness Check |
| `check [DOC]` | ask the publisher whether the catalog is behind: `current DOC V`, `newer DOC: catalog latest V, <publisher> lists W (date) URL` (OCP: `(URL to confirm by hand)`), or `unreachable DOC: reason`; without DOC every document with a listing, an `unchecked:` line for the hand-maintained ones, an `unchecked (manual):` line naming each manual document with its access tier, a `release:` line comparing `config.toml`'s release with the newest `openbmc/openbmc` tag (`-> newer` or `-> L is the newest`), and a `summary:`. Nothing is downloaded. Exit 2 for an unknown document or one without a listing |
| `refresh [DOC] [--write]` | maintainer command: what `check` found, per version (`add`, `changed`, `confirm` with the reason: an OCP URL to find, a DMTF Work-in-Progress row); `--write` inserts the `add` entries into the catalog file at their place in publication order (a document whose version blocks the text scan cannot read is reported and left alone). Not for answering questions |
| `extract DOC [--version V] [--force]` | write the Extract, Outline, Line Map and figure regions for a PDF version already in the Library (latest held version by default), or unpack a bundle: a schema bundle's JSON Schema into `schemas/` (DSP8010, and DSP8013's profile schema), a registries bundle's newest registry files into `registries/` (DSP8011); skips if current. A ZIP with neither is skipped with a message |
| `extract --all [--force]` | every PDF and bundle in the Library; ends with a `summary:` line |
| `section DOC QUERY [--version V]` | Outline entries matching a section number prefix (`20.1` also matches `20.1.2`) or every word of QUERY; one per line: `LEVEL \| title \| pages FIRST-LAST` (LEVEL 0 is a top-level heading), where LAST is where the next entry of the same or a higher level begins, or the page before it when that heading opens the page (`~` in front of an approximate page). `no matching section` when nothing matches. Like every reading command it first brings the version to Ready (Latest, or `--version V`): `fetched DOC V via ...` and `extracted DOC V: ...` lines come before the answer when the Library lacked it; a download that fails with an older version held prints `note: could not fetch DOC V: ...; answering from held W` and answers from W; with nothing held, exit 2 with the browser URL and the save path; a gated version, exit 2 with the Drop-in instruction; an unknown `--version`, exit 2 listing the known ones (exact match); another Session downloading or extracting the same version, exit 3 (`busy:`). After the answer, a due Freshness Check may add `note: newer DOC: ...` or `note: unreachable DOC: ...` |
| `find DOC PATTERN [--version V] [--regex] [--case] [--context N] [--max N] [--only]` | search the Extract (the version is brought to Ready first, as `section` says); one line per hit: `DOC p.N [line L] \| section \| [figure] text`. Case-insensitive literal unless `--regex` / `--case`; `--context N` adds the surrounding lines (`line L:` or `row I:`) and a `--` separator; at most 50 hits unless `--max N` (`--max 0` prints all), then a `... more hits` line. Documents the catalog lists in `searched_with` (IPMI-UPDATE for IPMI) are searched too, their hits first; they are brought to Ready the same way, with every line about that as a `note:` (`note: fetched IPMI-UPDATE ...`, or why it could not be), and one that cannot be read is left out; `--only` skips them. `no hits` when nothing matches |
| `page DOC N [--to M]` or `page DOC --section QUERY [--version V] [--max-pages K]` | print pages of the Extract (the version is brought to Ready first, as `section` says), each starting with a `cite:` line, every line behind its printed line number when there is one, `[figure]` appended to lines inside a figure. Refuses more than 10 pages per call unless `--max-pages` |
| `render DOC --page N [--version V] [--scale S] [--force]` | write `renders/page-N.png` (S times 72 dpi, default 2) under the version directory (the version is brought to Ready first, as `section` says); prints `rendered <path>` and a `cite:` line with `rendered page`. Reuses an existing file unless `--force` |
| `schema DOC [RESOURCE] [--property P \| --definition D] [--version V]` | read a schema bundle (downloaded and unpacked first when the Library lacks it, as `section` says). No RESOURCE: every resource, one per line, `Name\tvX.Y.Z` (`-` for an index-only name such as a collection). RESOURCE: a `cite:` line, a `schema:` line (name, version, property count, the file's definitions), then one property per line: `name \| type \| readonly or writable \| added vX.Y.Z or - \| description`; types read `string`, `enum Def`, `object Def`, `array of T`, `odata name`, or the raw `$ref` when its file is not in `schemas/`. `--property P`: its description, longDescription, deprecation and other notes, and when it is an enum, a second `cite:` for the file that defines it (for instance `Resource.json`) followed by `values:` with every value, its description and when it was added. `--definition D`: the same for a named definition of the file (an enum, or an action with its `parameters:`). Names are case-insensitive; an unknown resource lists the names containing the query (exit 2). A schema whose object is defined at the file's root (the profile schema) is read from the root, pointer `#` |
| `registry DOC [REGISTRY] [MESSAGE] [--version V]` | read a registries bundle (downloaded and unpacked first when the Library lacks it, as `section` says). No REGISTRY: every registry, one per line, `Prefix\tversion\tN messages`. REGISTRY: a `cite:` line (`#/Messages`), a `registry:` line (prefix, version, count, the MessageId form `Base.1.23.*`), then one message per line: `Key \| severity \| text`. MESSAGE (a key such as `PropertyMissing`, or a full MessageId): a `cite:` line with `#/Messages/<Key>`, a `message:` line (MessageId, severity, argument count), `text:` (the message verbatim, `%1` and so on for the arguments), `description:`, `longDescription:`, `resolution:`, `args:` (`%n \| type \| what it is`), `added vX.Y.Z` and `deprecated (since vX.Y.Z): ...` when the registry says so. Names are case-insensitive; an unknown registry or key lists the names containing the query (exit 2); a schema bundle is refused with the `schema` command to use |
| `repos [--topic T]` | the catalog's repositories, one per line, four tab-separated fields: id, held Code Trees (`commit7 provenance`, `superseded` when re-fetched) or `-`, `user checkout: path` or `-`, topics; a first line `release: L (config.toml) -> openbmc <commit7>` when a default Release is set |
| `repos --search PATTERN` | GitHub code search over the openbmc organisation through `gh` (must be installed and logged in), `repo path` per hit; searches default branches only. For when no topic matches |
| `clone REPO [--ref R \| --release L] [--force]` | bring the repository into the Library as a Code Tree (REPO not in the catalog: `https://github.com/openbmc/REPO.git` is tried, with a `note:` saying so, and `repos` lists it as `(not in catalog)` afterwards): at branch/tag/full commit R, at the Pin of OpenBMC release L (the `openbmc` repository is fetched at L first, recipes only), or at the default branch. Prints `cloned <repo> <commit7> (<provenance>) -> <path>` or `held ...` when already there (no network); `--force` resolves a moving name again and prints `superseded` for the older tree. Uses the `config.toml` default Release when no flag is given, and says `release: L (from config.toml)` |
| `grep REPO PATTERN [--ref R \| --release L] [--regex] [--glob G] [--context N] [--max N]` | `git grep` over the selected Code Tree (user checkout first, then the named Ref or Release, then the config Release, then the default-branch tree): one hit per line `REPO@commit7 path:line \| text`, context lines as `line N:` with `--` between groups, at most 50 hits unless `--max` (0 = all); `no hits`; exit 2 with the `clone` command when the tree is not held. Case-sensitive, a fixed string unless `--regex` |
| `code REPO PATH [--lines A-B] [--ref R \| --release L]` | a `cite:` line then the file's lines behind their numbers; a file over 200 lines needs `--lines`. Same tree selection as `grep`; a `note:` line says when a user checkout or the config Release was used |
| `prune [--yes]` | `would remove <path> (...)` for every superseded Code Tree, every `.tmp-*` / `.part` leftover nobody is working on and every stale `.lock` (untouched for 5 minutes), then a `prune:` summary; only with `--yes` are they removed (`removed <path>`). A live lock and a fresh temp file are never listed; a stale lock that another Session takes over while `prune` runs is kept (`kept <path> (...)`, counted as `, N kept` in the summary). Run `--yes` only when the user asked to free space |
| `table DOC --page N [--version V] [--index K] [--force] [--all-rows]` | print every Logical Table touching page N, whole (the version is brought to Ready first, as `section` says): a `cite:` line (`PDF pages A-B`, `table K`), a `table:` line (caption or `-`, `ruled` or `cells (no ruling lines)`, page range, columns, rows including the header), then the rows as a grid, columns separated by ` \| `, one physical line per cell line, a rule after the header and after every row with a multi-line cell. A table longer than 300 rows prints a `note:` line and only the rows that start on page N; `--all-rows` prints them all. `--index K` keeps only the K-th table on the page. Read from `tables.json` when the page was read before, unless `--force`. Exit 2 with `no table on page N` when the page has neither kind |

Exit codes: 0 done, 1 error (malformed catalog, unreadable file), 2 the
user must act (unknown document or version, download impossible, document
not in the Library or not extracted, too many pages asked for), 3 busy
(another Session is writing the same document version or repository; the
`busy:` line names its pid, host, command and start time). Every command
takes `--wait SECONDS` before the subcommand (default 60, `0` returns at
once): how long to wait for that Session before giving up with 3.

## Answering workflow

0. A Redfish data-model question (which properties a resource has, what a
   property means, which values an enum allows, what an action takes) is
   answered from the schema bundle: `schema DSP8010 <Resource> --property
   <P>` (the command downloads and unpacks the bundle itself when needed)
   and cite the two `cite:` lines it prints. Questions about the protocol
   itself (HTTP, sessions, eventing) stay with the PDF, DSP0266. A Redfish
   message question (what a MessageId means, its severity, arguments or
   resolution) is answered from the registries bundle: `registry DSP8011
   <Registry> <Key>`, quoting the `text:` line verbatim. Profile questions
   (what a profile may require of a property) use `schema DSP8013
   RedfishInteroperabilityProfile --definition <Name>`.
1. Identify the Family and the Document. Without a named family prefer the
   one the project context suggests (CLAUDE.md, the conversation), else
   answer for the most likely family and say that another family has a
   same-named item. `catalog --family F` lists the candidates.
2. Locate: `section DOC QUERY` when the user names a section or a topic
   that is a heading; `find DOC PATTERN` for a command name, a field, a
   code, a phrase. Read the section field of each hit to see where it lies.
   This is the first helper call of a question: the reading command brings
   the document to Ready itself, answering from Latest, or from the
   version the user named, passed verbatim with `--version`. Repeat its
   `fetched` and `extracted` lines to the user in one sentence (they say
   the document was downloaded or extracted just now); on exit 2 relay the
   message and stop; on exit 3 follow the `busy:` rule below. A `note:
   could not fetch DOC V: ...; answering from held W` line means the
   answer comes from W: say so.
   A `notes DOC V: N` line followed by `ID DATE | question | pages` lines
   means the Library remembers earlier answers that cite this document
   (Notes; only when the user turned them on). A Note printed whole right
   there, from `note: answer from a Note of DATE (ID); ask to re-read to
   verify` to `end of note ID`, is the answer: give it, with its
   Citations, and repeat that first line to the user in one sentence.
   When no Note is printed whole but a title line's question is the
   user's question in other words, run `recall ID` before reading pages;
   a title line marked `superseded` cites a version the Library no longer
   answers from: use its pages as a place to start reading, never its
   answer. When the user asks to re-read, or doubts a Note, read the
   pages as usual; the new answer replaces the Note.
3. Read only what you need: `page DOC N` for the hit pages, or
   `page DOC --section QUERY` for a short section. Never read a whole
   Extract into the conversation; a section longer than ten pages is read a
   few pages at a time.
4. A reading command may end with a Freshness Check note.
   `note: newer DOC: catalog latest V, <publisher> lists W (date) URL`:
   tell the user in one sentence that the publisher lists W and that the
   answer comes from V; never fetch or add W unless the user asks, and
   never edit the catalog during a question (`refresh` is for
   maintainers). `note: unreachable DOC: ...`: say nothing about it.
   `check` is run only when the user asks whether a newer version exists,
   never during a question.
5. When the answer sits in a table (a `Table` caption near the hit, or
   `page` shows columns), run `table DOC --page N` and read the row from
   the grid instead of from the page text: the grid has the header once and
   every row of the table, including those the PDF put on other pages.
   When the `table:` line says `cells` and a cell is empty or its text
   looks cut off (a row the page break split), compare that row with the
   `page` text before citing it. A `note:` line means the table is longer
   than 300 rows and only the rows starting on page N were printed; ask
   for the page the row is on, or `--all-rows`. `no table on page N` means
   the page has neither ruling lines nor cell boxes; read the page text or
   render the page instead.
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
   Kernel questions (hwmon sysfs attributes, I2C, GPIO, PECI, the IPMI
   and MCTP drivers, NC-SI) go to the `linux` Code Tree (topics `kernel`,
   `hwmon`, `ipmi`, `mctp`, ...), which holds `Documentation/` and the
   BMC-facing driver directories only; PECI in particular has no open
   specification, the driver and `Documentation/` are the reference.
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
- The `cite:` section field lists every section the page spans: the entry
  in force at the top, then each whose heading is on the page. Copy the
  field whole, or keep the one your claim sits in when the page text or
  the section printed by `find` for that hit shows which one it is. A
  field holding several titles is cited as the `cite:` line itself, not
  rewritten in prose (a title with a comma would end the prose form early).
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
- A registry answer cites the `cite:` line `registry` printed (bundle
  version, registry and its version, file, `#/Messages/<Key>`), gives the
  MessageId form (`Base.1.23.PropertyValueTypeError`) and quotes the
  `text:` line verbatim; the argument list explains the `%n` markers.
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
- When a download fails (a reading command or `fetch` prints `failed DOC
  V` with a browser URL and a save path), relay the URL and the exact save
  path, then ask the user to run `scan` after saving. Never invent an
  alternative URL.
- When a reading command or `fetch` exits 2 because the version is gated,
  member or confidential, relay the `newest open version:` line as it is
  and offer that version; read it (`--version X`) only when the user
  agrees, and never claim the gated version's content from the open one
  without saying which version the answer comes from.
- `fetch --all` downloads several hundred megabytes; only run it when the
  user asks for everything. `extract --all` on a full Library takes a couple
  of minutes.
- `check` goes to the publishers' sites (a few requests) and says whether
  the catalog is behind; run it only when the user asks whether a newer
  version exists (the reading commands run it themselves when it is due
  and report the outcome as a `note:`). It never downloads. `prune --yes`
  deletes directories: only on request.
- Exit 3 (`busy:`) means another Session (another Claude Code conversation
  on this machine, or one in WSL sharing the Library) is fetching,
  extracting or cloning the same thing. Run the same command once more
  with `--wait 300` before the subcommand; if it is 3 again, tell the user
  who holds the lock (copy the `busy:` line) and stop. Never read
  `extract.txt`, `tables.json` or a Code Tree directly to get around it:
  the files may be half-written.
- `clone` is one repository at a time (2 to 32 MB each); a Release needs the
  the `openbmc` repository too (the recipe files of every layer, about 20
  MB), so `--release` resolves any repository a layer's recipe pins; a
  repository no layer builds has no Pin and `clone` says so. For the
  `openbmc` repository itself a release is its tag or branch: `clone openbmc
  --release L` and `grep openbmc ... --release L` read the recipes at L.
  Repository ids are case-insensitive; a commit given to `--ref` must be
  the full 40 characters.
