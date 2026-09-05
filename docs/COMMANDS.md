# Commands

What each `bmcspec.py` command does beyond the one-line examples in the
README, the Library's `config.toml`, the Freshness Check, and everything
the tool touches on the network and on disk. The files it writes are
described in [LIBRARY.md](LIBRARY.md); the documents it knows, in
[CATALOG.md](CATALOG.md).

## Reading commands

Exit codes: 0 done, 1 error, 2 you need to act (the message says what),
3 busy (another Session holds the lock; see [Sessions sharing a
Library](#sessions-sharing-a-library)). `--wait SECONDS`, given before the
subcommand, says how long a command waits for that lock (default 60, `0`
returns at once).

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

`table` prints every table touching the page as a Logical Table: the
pages it spans are read and joined (a table continues when it is the last
thing on its page, the next page starts with a table with the same column
edges, and only running headers, footers and page numbers lie between;
a repeated header row is dropped), and the result is a `cite:` line with
`PDF pages A-B` and `table K`, a `table:` line with the caption and how
the table is drawn, and the rows as a text grid. Two drawings are read:
`ruled` tables, whose cells are bounded by ruling lines (thin filled
rectangles or stroked lines), and `cells` tables, which have no rules and
paint every cell as a filled box tiled edge to edge, the way DMTF's
current PDFs are made; a box's edges are its cell's edges, so a merged
cell stays one cell, and boxes inside a ruled table (a shaded header) are
not a second table. A table laid out with spaces alone is not detected.
A table longer than 300 rows (DSP2053's property guide is one table over
the whole document) prints a `note:` line and only the rows that start
on the page asked for; `--all-rows` prints every row. Tables are read on
demand and kept in `tables.json` next to the Extract, so a page is read
from the PDF once; `--force` reads it again.

`schema` reads a Redfish schema bundle (DSP8010): without a resource it
lists the resources and their newest schema version; with one it prints
the properties (type resolved through `anyOf` and `$ref`, read-only flag,
the version that added it, description); `--property` or `--definition`
prints one property or one named definition in full, including every
value of an enum with its description, following `$ref` into the file that
defines it. Each block starts with a `cite:` line naming the bundle
version, the schema file and the JSON pointer. The profile bundle
(DSP8013) holds only the profile schema and is read the same way; its
object is defined at the file's root, so the pointer is `#`.

`registry` reads the Redfish message registries bundle (DSP8011): without
a registry it lists the registries with their version and message count;
with one it lists the messages (key, severity, text); with a message key
(or a full MessageId such as `Base.1.23.PropertyValueTypeError`) it prints
the message in full: a `cite:` line with the file and `#/Messages/<Key>`,
the MessageId, severity and argument count, the message text verbatim,
description, resolution, one line per argument, and when the message was
added or deprecated. Only the newest file of each registry is unpacked;
an older registry version is read from an older bundle with `--version`.

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
moving name re-fetched with `--force`), every `.tmp-*` directory a failed
clone left behind, every `.part` file older than five minutes that a
failed write left behind, and every stale `.lock`, and removes nothing;
`prune --yes` removes them. A directory whose lock is live is skipped
whole. The current tree of each name, trees reached by a commit, user
checkouts and the documents under `specs/` are never touched.

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
[CATALOG.md](CATALOG.md)) or as a Drop-in. The outcome and the time go to
`freshness.json` at the Library root; `fetch` and `status` print a
`note:` when a document served has not been checked within
`freshness_days` (default 30), once per document until the next `check`,
and that note never touches the network.
OCP versions are mostly Google Drive links on the wiki, so `check`
reports them with `(URL to confirm by hand)`.

## Sessions sharing a Library

Several Sessions (Claude Code conversations) on one machine share the
Library, and a Windows Session and a WSL Session may share it through
`BMC_SPEC_LIBRARY`. Nothing else is shared: there is no daemon and no run
state. Sharing across machines or through a sync service is unsupported.

The commands that write several files hold a lock while they do: `fetch`
and `add` (the original and its `meta.json`), `extract` (the Extract and
its companions, or a bundle's `schemas/` / `registries/`), `table` (the
merge into `tables.json`; reading the PDF is not locked) and `clone`. The
lock is the file `.lock` in the version directory, or `code/<repo>/.lock`
for a clone; it holds the holder's pid, host, command and start time, and
its modification time is refreshed every 30 seconds while the holder is
alive. A lock untouched for 5 minutes is stale: the next command removes
it, prints `note: took over a stale lock from pid P on host H (...)` and
does the whole operation again from scratch: a take-over trusts only state
whose meta is complete (`meta.json`, `extract.json`, `.bmc-tree.json` are
written last), and a `fetch --force` or `add --force` killed midway leaves
an original without `meta.json`, which the next `fetch` redoes and `scan`
can still register. Pids are never trusted (they mean nothing across
Windows and WSL and are reused after a reboot); only the modification time
decides. When two Sessions meet the same stale lock, one takes it over and
the other waits for it like any live lock. A Session that cannot remove its
own lock at the end (Windows, when another process has the file open at
that moment) prints a `note:` naming the path; the lock expires as stale.

A command that meets a live lock waits up to `--wait` seconds (default
60), then prints one line, `busy: <path> is held by pid P on host H
(COMMAND, since T); retry with --wait`, writes nothing and exits 3. The
reading commands (`find`, `section`, `page`, `render`, `table`, `schema`,
`registry`) take no lock; they consult one only when the version is not
extracted, wait the same way for the Session that is extracting it, and
then answer from the finished Extract, or exit 3 if it is still busy. In
`--all` runs a busy document is counted (`busy N` in the summary) and the
run exits 3 unless something failed, which exits 2 as before.

Single files (`meta.json`, `extract.json`, `tables.json`, `.bmc-tree.json`,
`freshness.json`, originals and rendered pages) are written to a temporary
name beside the target, `<name>.<pid>-<token>.part`, and renamed into
place, so a reader never sees a half-written file and two Sessions writing
the same file do not collide. `status` lists every lock with its holder and
whether it is live or stale; `prune` removes stale locks and abandoned
temporary files (see above).

## What the tool does on the network and on disk

- Downloads only URLs listed in `bmc_toolkit/spec/catalog.toml`, in this
  order: the publisher's URL (with a browser TLS fingerprint through
  `curl_cffi`, which Intel's and OCP's CDNs require), then the Internet
  Archive's Wayback Machine snapshot of that URL, then it stops and prints
  the URL and the path to save the file to. Documents whose publisher
  refuses every scripted client (uefi.org, trustedcomputinggroup.org) are
  marked `fetch = "wayback"` and go to the Archive straight away. Manual
  documents are never requested at all.
- A response that is not the expected PDF or ZIP (an HTML block page, a
  cut-off download) is discarded and never written to the Library. The same
  leading-bytes check applies to files given to `add` or found by `scan`.
- Writes only under the Library. Files placed there by hand are registered
  as Drop-ins and their origin is recorded as user-provided, never as a URL;
  `scan` also records whether the document id is in the catalog
  (`catalog_known`). Nothing already in the Library is replaced without
  `--force`. `fetch`, `add`, `extract` and `table` hold `.lock` in the
  version directory while they write (see above), and every single-file
  write goes through a `<name>.<pid>-<token>.part` temporary beside the
  target; nothing else is created.
- Replacing an original (`add --force`, `fetch --force`) removes the
  previous original and everything extracted from it, `tables.json`,
  `schemas/` and rendered pages included; so does `extract --force`.
- From a schema bundle only the JSON Schema files an answer needs leave the
  archive: every unversioned `<Name>.json` and the newest
  `<Name>.vX_Y_Z.json` per resource (452 files, 7.4 MB on disk, out of
  DSP8010 2026.1's 6890 JSON Schema files and 234 MB); CSDL, OpenAPI,
  dictionaries and the PDFs stay in the ZIP. Member paths that would
  escape `schemas/` are refused, and a base name that appears twice is
  written once. From the profile bundle (DSP8013, no `json-schema/`
  folder) the newest `RedfishInteroperabilityProfile.vX_Y_Z.json` is
  kept. From the registries bundle (DSP8011) only the newest file of each
  message registry leaves the archive (22 files, about 0.8 MB, out of
  DSP8011 2026.1's 264 members); the privilege registries, the HTML and
  the PDF stay in the ZIP.
- `check` and `refresh` read listing pages only: `https://www.dmtf.org/standards/published_documents` and `https://www.dmtf.org/dsp/<DSP>`, `https://nvmexpress.org/wp-json/vtm/v1/specifications`, and `https://www.opencompute.org/w/index.php?title=<page>` for the pages named in the catalog's `listing` keys. They download no document.
- Runs `git` as a subprocess for `clone` (shallow, one commit; `--filter=blob:none --sparse` for the `openbmc` repository and for `linux`, which is held only for `Documentation/` and the BMC-facing driver directories), `grep` and `code` (reading `HEAD` of a user checkout), and `git ls-remote --tags` on the `openbmc` repository for `check`; `gh search code` for `repos --search`. Nothing else is executed, and nothing is re-uploaded or redistributed.
- `clone` writes only under the Library's `code/` directory: `code/<repo>/<commit>/` plus a temporary `.tmp-<pid>-<token>` directory that is removed on failure, and `code/<repo>/.lock` while it runs. A user checkout named in `config.toml` is only read. `prune --yes` removes superseded trees, `.tmp-*` and `.part` leftovers and stale `.lock` files under `code/` and `specs/`, nothing else.
- `check` writes `freshness.json` at the Library root; `fetch` and `status` stamp the reminder there (`reminded_at`) when they print the note. `refresh --write` is the one command that writes outside the Library: it inserts version entries into the catalog file it was given (`--catalog`, or the shipped `bmc_toolkit/spec/catalog.toml`).
