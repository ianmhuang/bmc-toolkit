---
name: bmc-spec
description: Answer questions about BMC specifications (IPMI, DCMI, DMTF MCTP/PLDM/SPDM/NC-SI/SMBIOS, Redfish, NVMe/NVMe-MI, OCP DC-SCM/DC-MHS, I2C, SMBus, CMIS) and about OpenBMC source code, citing document, version, section and page. Use whenever the user asks what a spec says, how a command or field is defined, or how OpenBMC implements something.
allowed-tools: Bash(python *)
---

# bmc-spec

Status: the Library, the Source Catalog and text extraction work; the
answering workflow (search, section lookup, citations) arrives in the next
milestone. Until then this skill can tell the user which documents and
versions exist, bring the files onto the machine, and turn them into text.

## Vocabulary

- **Source Catalog**: the list of known documents, their versions and
  download URLs, shipped with the plugin.
- **Library**: the on-disk store of downloaded documents, shared by every
  project on the machine. `$BMC_SPEC_LIBRARY` overrides the default
  `~/.bmc-specs`. Tell the user the path the first time a command prints
  `Library created at ...`.
- **Latest**: the newest published version in the catalog. Work-in-Progress
  versions count only when the user asks for WIP.
- **Drop-in**: a file the user placed into the Library by hand because the
  tool cannot download it (registration, membership, NDA, or a blocked
  download).
- **Extract**: `extract.txt` next to the original, every page introduced by
  `=== page N ===` (physical page, 1-based), layout preserved so tables read
  column by column. DMTF printed line numbers are removed from the text and
  kept in `linemap.json` (per page: first, last, and the number of each
  line), so a citation can say "p.20, lines 680-700".
- **Outline**: `outline.json`, a flat list of `{level, title, page}` from the
  PDF bookmarks, or parsed from the contents pages when there are none
  (`extract.json` says which: `bookmarks`, `contents`, `none`).

## Helper CLI

Every operation goes through one launcher; run it with the Bash tool:

```
python "${CLAUDE_SKILL_DIR}/scripts/bmcspec.py" <command> ...
```

| Command | What it does |
|---|---|
| `library` | print the Library path |
| `catalog [DOC] [--family F]` | list documents (one per line, tab-separated: family, id, access, fetch, latest, title, known versions joined by `;`) or show one document with every version, newest first |
| `fetch DOC [--version V] [--wip] [--force]` | download one version into the Library; latest by default; prints a `skipped` line and stays off the network if already present |
| `fetch --all [--wip] [--force]` | latest of every downloadable document; ends with a `summary:` line |
| `add FILE --document DOC --version V [--force]` | register a file the user obtained themselves (Drop-in); refuses to replace a version already present unless `--force`; the file must really be a PDF or ZIP |
| `scan` | register files placed by hand under `specs/<family>/<document>/<version>/original.pdf` |
| `status` | what the Library holds; columns: family, id, version, origin, size, `extracted` or `-`, outline source |
| `extract DOC [--version V] [--force]` | write the Extract, Outline and Line Map for a version already in the Library (latest held version by default); skips if current |
| `extract --all [--force]` | every PDF in the Library; ends with a `summary:` line; ZIP bundles are skipped for now |

Exit codes: 0 done, 1 error (malformed catalog, unreadable file), 2 the
user must act (unknown document or version, download impossible).

## Rules

- Document ids are case-insensitive (`dsp0236`, `IPMI`, `NVME-MI`).
- When the user names a version, pass it verbatim with `--version`; the
  catalog keeps the publisher's own strings (`2.0 rev 1.1`,
  `Rev 2.1 Ver 1.1`). On exit 2 the message lists the known versions.
- When a download fails, relay the printed browser URL and the exact save
  path, then ask the user to run `scan` after saving. Never invent an
  alternative URL.
- IPMI questions need both `IPMI` (the base document) and `IPMI-UPDATE`
  (errata and clarifications); fetch both.
- `fetch --all` downloads several hundred megabytes; only run it when the
  user asks for everything. `extract --all` on a full Library takes a couple
  of minutes.
- Read a page from the Extract by locating its `=== page N ===` marker; the
  Outline gives the physical page of a section. Do not read whole Extracts
  into the conversation.
