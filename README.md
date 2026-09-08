# bmc-toolkit

Claude Code plugin for BMC firmware developers.

The first skill, `bmc-spec`, answers questions about BMC specifications
(IPMI, DMTF MCTP / PLDM / SPDM / NC-SI / SMBIOS, Redfish, NVMe, OCP DC-SCM
and DC-MHS, I2C, SMBus, PMBus, eSPI, LPC, SFF, CMIS, TCG, UEFI, ACPI,
Arm server standards, NIST firmware resiliency and more) and about OpenBMC
source code. It keeps a local library of the documents and repositories you
have asked about, defaults to the latest published version of each document,
serves any specific version on request, and cites document, version, section
and page in every answer.

**Status: 1.0.0.** The Source Catalog lists 113 documents in
35 families. The 93 open ones are downloaded by the tool and every one of
them has been checked against the acceptance questions in
`docs/golden-questions.md`; the 20 gated, member and NDA documents are
listed with their tier and registered from your own copy. Which documents,
their limits and whether each is verified: [docs/SUPPORT.md](docs/SUPPORT.md);
how the catalog is kept: [docs/CATALOG.md](docs/CATALOG.md).

What the plugin is made of and where the data flows (a double arrow: read and write):

```mermaid
flowchart LR
    S["«component»<br/><b>Claude Code session</b><br/>bmc-spec Skill · Stop hook"]
    T["«component»<br/><b>bmcspec.py</b><br/>catalog · fetch · extract · search · tables"]
    N["«add-on, default off»<br/><b>Notes</b><br/>remembers cited answers"]
    W["«external»<br/><b>Publishers · Internet Archive · GitHub</b>"]
    subgraph L["Library  ~/.bmc-specs"]
        direction TB
        D[("specs/ · code/<br/>originals · Extracts · Code Trees")]
        J[("notes.jsonl")]
    end
    S <-->|"Bash: command in,<br/>answer with cite: out"| T
    W -->|"download,<br/>once per version"| T
    T <-->|"read;<br/>write under .lock"| D
    N -->|"Notes into the output<br/>of find / section"| T
    N <-->|"record · recall"| J
    classDef read fill:#E1EBF2,stroke:#2F5D7C,color:#1C242B
    classDef mem fill:#F6E6DD,stroke:#B4552C,color:#1C242B
    classDef disk fill:#ECEFF2,stroke:#8A96A0,color:#1C242B
    class S,T read
    class N,J mem
    class D,W disk
```

## Install

```
/plugin marketplace add ianmhuang/bmc-toolkit
/plugin install bmc-toolkit@bmc-toolkit
```

The same two steps from a terminal: `claude plugin marketplace add
ianmhuang/bmc-toolkit`, then `claude plugin install bmc-toolkit@bmc-toolkit`.

Requirements: Python 3.11 or newer on `PATH` as `python` or `python3`, and
`git`. A `SessionStart` hook installs the packages in `requirements.txt`
once; in a development checkout run `pip install -r requirements.txt` yourself.

- `curl_cffi` (MIT): HTTP client with a browser TLS fingerprint; without it
  Intel documents come from the Internet Archive instead of the publisher,
  OCP documents still download directly (both verified).
- `pypdfium2` 5.x (BSD-3-Clause or Apache-2.0): PDF text with character
  positions and bookmarks; older than 5.0 is refused.
- `pdfplumber` (MIT): cell geometry and cell text of tables (ruled, and
  drawn as cell boxes), for `table`; loaded only by that command.

### Updating

Claude Code offers an update when the version in `plugin.json` rises but
does not update third-party marketplaces on its own: enable auto-update for
`bmc-toolkit` in `/plugin` (Marketplaces tab), or run `claude plugin update
bmc-toolkit@bmc-toolkit`. The Library and the installed packages stay; after
an update that changes the extractor, `status` marks documents `stale` and
`extract --all` re-extracts them, downloading nothing.

## How a question is answered

```mermaid
sequenceDiagram
    actor User
    participant Claude as Claude<br/>(bmc-spec skill)
    participant CLI as bmcspec.py
    participant Lib as Library<br/>~/.bmc-specs
    participant Pub as Publisher /<br/>Internet Archive
    User->>Claude: What does DSP0236 say about message tags?
    Claude->>CLI: locate: section or find DSP0236 "Msg tag" (latest, or --version 1.2.0)
    CLI->>Lib: that version Ready?
    alt not held
        CLI->>Pub: fetch DSP0236 1.3.1: GET the version's PDF
        Pub-->>CLI: PDF
        CLI->>Lib: original.pdf, meta.json (URL, SHA-256)
    end
    CLI->>Lib: extract DSP0236 when not extracted: extract.txt, outline.json, linemap.json, figures.json
    CLI->>Lib: find DSP0236 "Msg tag" in extract.txt
    CLI-->>Claude: fetched / extracted lines, then hits: page, line, section
    opt Notes on
        CLI-->>Claude: notes DSP0236 1.3.1: N title lines, or one earlier Note whole (unverified, marked)
    end
    Claude->>CLI: page DSP0236 24 (or table, render)
    CLI->>Lib: read the pages
    CLI-->>Claude: text + cite: line
    CLI->>Pub: listing page, when the document's Freshness Check is due (once per 30 days)
    CLI-->>Claude: note: newer DSP0236 ... (or nothing)
    Claude-->>User: answer, Citation copied from cite:
    Claude->>CLI: Stop hook, every turn: notes record (writes notes.jsonl only when Notes is on)
    Note over Claude,Lib: OpenBMC questions have the same shape:<br/>repos, clone (GitHub), grep, code, cite:
```

Solid arrows are commands and Library access, dashed arrows what comes back.
A reading command brings the version it needs to Ready (held and extracted)
by itself: the catalog's latest, or the one `--version` names. The publisher
is contacted only when the Library lacks the version, and once per document
per 30 days to ask whether it lists a newer one (reported, never downloaded).
The skill copies its Citation from the `cite:` line of every printed page.
What each command does: [docs/COMMANDS.md](docs/COMMANDS.md).

## Library location

Documents and code checkouts live under `~/.bmc-specs/` by default; set
`BMC_SPEC_LIBRARY` to move it. Every project on the machine shares the path.
Documents sit at `specs/<family>/<document>/<version>/`, Code Trees at
`code/<repo>/<commit>/`; what each holds: [docs/LIBRARY.md](docs/LIBRARY.md).

## Command line

The skill drives `skills/bmc-spec/scripts/bmcspec.py`; you can run it
yourself. The examples use a shell alias for it:

```
alias bmcspec='python skills/bmc-spec/scripts/bmcspec.py'

bmcspec catalog              # every document, one per line
bmcspec catalog --table --by-family --golden docs/golden-questions.md   # Support Level table per family (docs/SUPPORT.md)
bmcspec fetch DSP0236 --version 1.2.0   # without --version: the latest published version
bmcspec add vendor.pdf --document DSP0236 --version 1.1.0   # a gated or NDA document, from your copy
bmcspec check DSP0236        # is the catalog behind DMTF? (no download)
bmcspec find DSP0236 "Msg tag" --context 1   # hits with page, line, section
bmcspec page DSP0236 24 --to 25              # the pages, with a cite: line each
bmcspec table DSP0236 --page 122             # the table(s) on the page, whole
bmcspec schema DSP8010 Chassis --property PowerState   # the Redfish JSON Schema bundle (DSP8013 profiles alike)
bmcspec registry DSP8011 Base PropertyValueTypeError   # the message registries bundle
bmcspec repos --topic redfish                # repositories and held Code Trees
bmcspec clone pldm --release 2.18.0          # the commit OpenBMC 2.18.0 ships
bmcspec grep bmcweb CurrentPowerState --context 2
bmcspec code bmcweb redfish-core/lib/chassis.hpp --lines 160-175
```

Exit codes, `--wait` (several conversations can share one Library), flags,
output formats, `config.toml` and every command with an example:
[docs/COMMANDS.md](docs/COMMANDS.md).

## What the tool does on the network and on disk

- Downloads only URLs listed in the Source Catalog, the publisher's first
  and then the Internet Archive's snapshot of it; a manual document is
  never requested, and a response that is not the expected PDF or ZIP is
  discarded. A reading command downloads the version it answers from when
  the Library lacks it (`offline = true` in `config.toml` stops that).
- Writes only under the Library and replaces nothing there without
  `--force`. From a Redfish ZIP bundle only the schema or registry files an
  answer needs are unpacked.
- `check`, `refresh` and a reading command due for its Freshness Check read
  publisher listing pages and download nothing. `refresh --write` is the one
  command that writes outside the Library: version entries into the catalog
  file it was given.
- Runs `notes record` from a Stop hook at the end of every turn; it exits
  unless `config.toml` says `notes = true`, then keeps the answer in
  `notes.jsonl` and serves it again, unverified and marked as such
  ([docs/COMMANDS.md](docs/COMMANDS.md#notes)).
- Runs `git` as a subprocess for `clone`, `grep` and `code`, and
  `gh search code` for `repos --search`; `clone` writes only under the
  Library's `code/` directory. Nothing else is executed, and nothing is
  re-uploaded or redistributed. Full list: [docs/COMMANDS.md](docs/COMMANDS.md).

## Further reading

- [docs/COMMANDS.md](docs/COMMANDS.md): every command, `config.toml`, Notes, the Freshness Check.
- [docs/LIBRARY.md](docs/LIBRARY.md): the files under the Library.
- [docs/CATALOG.md](docs/CATALOG.md): how the Source Catalog is kept and extended.
- [docs/SUPPORT.md](docs/SUPPORT.md): the Support Level table per family.

## Development

```
pip install -r requirements.txt -r requirements-dev.txt
ruff check .
ruff format --check .
python -m pytest -q
```

The same commands run on GitHub Actions for every pull request (Linux and
Windows) and every push to main (Linux, Windows and macOS).

## License

MIT. The specifications the tool downloads remain under their publishers'
licences and are never redistributed with this repository.
