# bmc-toolkit

Claude Code plugin for BMC firmware developers.

The first skill, `bmc-spec`, answers questions about BMC specifications
(IPMI, DCMI, DMTF MCTP / PLDM / SPDM / NC-SI / SMBIOS, Redfish, NVMe and
NVMe-MI, OCP DC-SCM and DC-MHS, I2C, SMBus, CMIS) and about OpenBMC source
code. It keeps a local library of the documents and repositories you have
asked about, defaults to the latest published version of each document,
serves any specific version on request, and cites document, version, section
and page in every answer.

**Status: pre-release.** The Source Catalog, document fetching and text
extraction work; the answering workflow is being added milestone by
milestone.

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
- `pypdfium2` (BSD-3-Clause or Apache-2.0): PDF text with character
  positions and bookmarks; the text layer.
- `pdfplumber` (MIT): table extraction (used from a later milestone on).

## Library location

Documents and code checkouts live under `~/.bmc-specs/` by default. Set
`BMC_SPEC_LIBRARY` to move it. The path is shared by every project on the
machine. Each document version sits at
`specs/<family>/<document>/<version>/original.<pdf|zip>` next to a
`meta.json` that records where it came from and its SHA-256. After
`extract` the same directory holds `extract.txt` (one `=== page N ===`
marker per physical page, layout preserved), `outline.json` (section
titles with pages, from PDF bookmarks or from the contents pages),
`linemap.json` (DMTF printed line numbers, per page) and `extract.json`
(extractor version, timing, what was found).

## Command line

The skill drives `skills/bmc-spec/scripts/bmcspec.py`; you can run it
yourself:

```
python skills/bmc-spec/scripts/bmcspec.py catalog              # every document, one per line
python skills/bmc-spec/scripts/bmcspec.py catalog DSP0236      # one document, all versions
python skills/bmc-spec/scripts/bmcspec.py fetch DSP0236        # latest published version
python skills/bmc-spec/scripts/bmcspec.py fetch IPMI --version "2.0 rev 1.1"
python skills/bmc-spec/scripts/bmcspec.py fetch --all          # several hundred MB
python skills/bmc-spec/scripts/bmcspec.py add vendor.pdf --document DSP0236 --version 1.1.0   # --force to replace
python skills/bmc-spec/scripts/bmcspec.py scan                 # register hand-placed files
python skills/bmc-spec/scripts/bmcspec.py status
python skills/bmc-spec/scripts/bmcspec.py extract DSP0236      # text, outline, line map
python skills/bmc-spec/scripts/bmcspec.py extract --all
```

Exit codes: 0 done, 1 error, 2 you need to act (the message says what).

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
  previous original and everything extracted from it.
- Never runs a subprocess and never re-uploads or redistributes anything.

## The Source Catalog

`bmc_toolkit/spec/catalog.toml` lists every family, document, version and
URL; comments in the file record when a URL was last confirmed. Publishers
add versions faster than any one maintainer notices: if `catalog DOC` shows
an older latest than the publisher's site, please open a pull request
adding the version entry.

## Development

```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

## License

MIT. The specifications the tool downloads remain under their publishers'
licences and are never redistributed with this repository.
