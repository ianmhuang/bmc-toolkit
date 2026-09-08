# The Source Catalog

`bmc_toolkit/spec/catalog.toml` lists every family, document, version and
URL; comments in the file record when a URL was last confirmed. How far
back the versions go depends on the publisher. DMTF and NVM Express
documents carry their full version history, kept current by `refresh`.
Intel, OCP, SNIA SFF, TCG, NIST, Arm and the other publishers carry the
current version, plus older ones only where the catalog records them by
hand. UEFI Forum documents (UEFI, ACPI, PI) and TCG documents come from
the Internet Archive's copy of the publisher's file, since both sites
refuse scripted downloads, so the versions listed are the ones the
Archive holds: the newest release and the one before it for the UEFI
Forum, the current one for TCG. Gated, member and NDA documents (JEDEC,
MIPI, PCI-SIG, PICMG, CXL, the BMC SoC datasheets, Intel's and AMD's NDA
interfaces) are listed with their tier and the reason, never downloaded,
and registered with `add` when the user has a copy. Every
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
checked on (`G13, G15 (1.3.1)`); `--by-family` prints the reader's form
kept in `docs/SUPPORT.md`: a heading and a table per family, without the
Fetch column, Verified reduced to `PASS` or `-`, and documents marked
`unlisted = true` in the catalog left out (the BMC SoC datasheets are).
The latest version is the one with the newest publication date; same-day
versions are told apart by the numbers in their version strings (`2.0.0`
over `1.3.0`). A document
may name companions in `searched_with` (errata, specification updates)
that `find` searches together with it, and a `listing`
(`dmtf:<DSP>`, implied for DMTF documents; `nvme:<slug>` of the
nvmexpress.org API; `ocp:<wiki page>|<description prefix>`) that `check`
and `refresh` consult. `refresh` prints the versions the publishers list
that the catalog lacks (`add`), catalog URLs that moved (`changed`, for
DMTF and NVMe) and versions a human has to handle (`confirm`: OCP rows,
whose download URL has to be found, and DMTF Work-in-Progress rows, which
the catalog lists only by hand with `wip = true`); `refresh --write`
inserts the `add` entries as `[[documents.versions]]` blocks at their
place in the document's block (publication order, same-day versions by
their numbers), leaving every other line and comment as it was, and
refuses an edit the parser would not accept.

Once a month, and on demand from the Actions tab (`catalog`, Run
workflow), `.github/workflows/catalog.yml` runs `refresh --skip-source
ocp` without `--write` on a GitHub runner and puts the output in the
run's summary, whether or not `refresh` succeeded. When it reports
anything to add, confirm or change, it opens an issue labelled `catalog`
with that output, or comments on the open one; a run that finds nothing,
or only unreachable listings, opens nothing. OCP is left out because
opencompute.org answers HTTP 403 to GitHub's runners (the same client
gets the wiki from a developer machine), so OCP versions come from
`refresh` run locally. The catalog itself changes only through a pull
request: run `refresh --write` locally, confirm any OCP URL by hand,
verify each new version against `docs/golden-questions.md`, and bump
`plugin.json` as CONVENTIONS.md says. If `check` reports a newer version
before the workflow does, please open that pull request yourself.
