# Commands

The one-line examples first, then what each `bmcspec.py` command does
beyond them, the Library's `config.toml`, the Freshness Check, and everything
the tool touches on the network and on disk. The files it writes are
described in [LIBRARY.md](LIBRARY.md); the documents it knows, in
[CATALOG.md](CATALOG.md).

## Examples

Every command once, through a shell alias for the launcher:

```
alias bmcspec='python skills/bmc-spec/scripts/bmcspec.py'

bmcspec library              # the Library path
bmcspec catalog              # every document, one per line
bmcspec catalog DSP0236      # one document, all versions
bmcspec catalog --family pldm   # one family's documents (any case; a miss lists the family ids)
bmcspec catalog --table --golden docs/golden-questions.md   # Support Level table, one flat table
bmcspec catalog --table --by-family --golden docs/golden-questions.md   # the same per family (docs/SUPPORT.md)
bmcspec fetch DSP0236        # latest published version
bmcspec fetch DSP0236 --version 1.2.0
bmcspec fetch PMBUS-II --version 1.3.1   # the latest is gated: fetch names this one
bmcspec fetch IPMI --version "2.0 rev 1.1"
bmcspec fetch --all          # several hundred MB
bmcspec add vendor.pdf --document DSP0236 --version 1.1.0   # --force to replace
bmcspec scan                 # register hand-placed files
bmcspec status
bmcspec check DSP0236        # is the catalog behind DMTF? (no download)
bmcspec check                # every document with a listing, plus the OpenBMC release
bmcspec refresh --write      # maintainer: add the versions the publishers list
bmcspec refresh --skip-source ocp   # as the catalog workflow runs it: OCP refreshed locally
bmcspec extract DSP0236      # text, outline, line map, figures
bmcspec extract --all
bmcspec section DSP0236 8.1  # level | title | pages, per matching entry
bmcspec find DSP0236 "Msg tag" --context 1   # hits with page, line, section
bmcspec page DSP0236 24 --to 25              # the pages, with a cite: line each
bmcspec page DSP0236 --section 8.2
bmcspec render DSP0236 --page 24             # renders/page-24.png
bmcspec table DSP0236 --page 122             # the table(s) on the page, whole
bmcspec table DSP0239 --page 13              # a table drawn as cell boxes, no rules
bmcspec schema DSP8010 Chassis --property PowerState   # the JSON Schema bundle, fetched and unpacked as needed
bmcspec registry DSP8011 Base PropertyValueTypeError
bmcspec schema DSP8013 RedfishInteroperabilityProfile --definition ReadRequirement
bmcspec repos --topic redfish                # repositories and held Code Trees
bmcspec clone bmcweb                         # default branch, shallow
bmcspec clone pldm --release 2.18.0          # the commit OpenBMC 2.18.0 ships
bmcspec grep bmcweb CurrentPowerState --context 2
bmcspec code bmcweb redfish-core/lib/chassis.hpp --lines 160-175
bmcspec prune                # list superseded Code Trees; --yes removes them
bmcspec invocation ipmi 'NetFn:1=0x06' 'Cmd:1=0x01'   # Get Device ID as ipmitool raw
bmcspec recall 1a2b3c4d      # one Note whole (Notes on)
bmcspec notes list DSP0236   # the Notes citing a document
```

## Reading commands

Exit codes: 0 done, 1 error, 2 you need to act (the message says what),
3 busy (another Session holds the lock; see [Sessions sharing a
Library](#sessions-sharing-a-library)). `--wait SECONDS`, given before the
subcommand, says how long a command waits for that lock (default 60, `0`
returns at once).

Every reading command (`section`, `find`, `page`, `render`, `table`,
`schema`, `registry`) first brings the version it needs to Ready: in the
Library, with its Extract (or unpacked bundle) current. The version is the
catalog's latest, or the one `--version` names (exact match; an unknown
one is exit 2 listing the known versions). When the Library lacks it the
command downloads it exactly as `fetch` would (same client, same lock,
`fetched DOC V via ...` first, after `Library created at ...` on first
use and one line per failed attempt), extracts it
(`extracted ...` next) and then answers; a held version whose Extract is
stale is extracted again first; a Ready version answers at once, with no
extra lines. A text command on a document the catalog lists as a bundle,
or `schema` / `registry` on a PDF, is refused before any download with
the command that reads it. Without `--version`, a download that fails
while an older version of the document is held prints `note: could not
fetch DOC V: <reason>; answering from held W` and answers from W (exit 0,
the Citation names W; a held WIP version is used only when no released one
is held); with `--version`, or with nothing held, it is exit 2 with the
browser URL and the save path, as `fetch` prints. A
gated, member or confidential version is exit 2 with the Drop-in
instruction, a manual document without versions exit 2 with the `add`
instruction, and another Session downloading or extracting the same
version exit 3 (`--wait` applies). `[library] offline = true` in
`config.toml` keeps the reading commands off the network: a missing
version is then exit 2 with the `fetch` command to run (or, without
`--version` and with an older version held, a note and the answer from
that one); extraction still
happens, it is local work. After its output a reading command runs the
Freshness Check when it is due, see below.

`fetch DOC` downloads one version (latest, or `--version`) and leaves it
Ready: after the `fetched` or `skipped` line it extracts the PDF or unpacks
the bundle and prints the `extracted` line (`skipped ...: already
extracted` when current); `--no-extract` stops after the download. A
failed extraction, or a missing dependency, is printed as `failed DOC V:
...` followed by `run: bmcspec extract DOC`, and the exit code stays 0
because the download landed. Without `--version`, `--wip` counts WIP
versions when picking the newest by publication date, so a WIP version
newer than every released one is the one fetched; a document with WIP
versions only needs it. `fetch --all` downloads only, as before. Nothing in the answering workflow needs
`fetch`; it is for prefetching a document you name, and for `--all`.

`find` searches the catalog's latest version (or `--version`),
case-insensitively unless `--case`, as a literal unless `--regex`; `--max`
(default 50) caps the hits. A document whose catalog entry lists
`searched_with` (IPMI lists its Specification Update) is searched together
with those, their hits first; they are brought to Ready the same way, with
every line about that as a `note:`, and one that cannot be read is left
out; `--only` skips them. When the entry also names `searched_with_from`,
a version the catalog lists before that one is searched alone, with
`note: <companion> not searched: it goes with <document> from <version>`
(DSP0248 1.3.1 and DSP0251). `page` prints at most 10 pages per call
(`--max-pages`). Each printed page and each rendered page comes with a
`cite:` line: family, document and version, the sections the page spans
(the one in force at its top, then every one whose heading is on the
page, joined by `; `; `page --section X` prints the same line for each
page it reads as `page N` would), PDF page, the printed line range as
`lines A-B` (or `lines -` without line numbers, `lines rendered page`),
origin URL or `user-provided`, and the
Library path. The Skill copies Citations from those lines and never
composes them. `render --page N` writes `renders/page-N.png` at `--scale
S` times 72 dpi (default 2.0); a page rendered already is reused unless
`--force`.

A Markdown version (catalog type `md`, held as `original.md`) has no
pages and is read by the line numbers of the file as stored, which are
the numbers the publisher's repository shows at the commit its URL pins.
`extract` writes its Outline from the ATX headings (`#` to `######` and
a space, outside fenced code blocks; level is the count of `#` minus one)
and prints `extracted DOC V: N lines, outline headings (K entries)`.
`section` prints `LEVEL | title | lines A-B`, the section ending before
the next heading of the same or a higher level. A title that two or more
headings share is shown and cited as its heading path, `Fuses > Goals`.
Words match a title as they do for a PDF; a repeated title also matches
when every word is in its path and one is in the title itself, so
`section DOC "fuses goals"` picks one of them and `fuses` alone lists
only `Fuses`. `find` prints
`DOC l.N | section | text`, N the file's line, and `--context` lines as
`line n: text`. `page DOC --lines A-B` prints lines A to B behind their
numbers (B past the end is cut to it; more than 200 lines, A outside the
file or a malformed range is exit 2), `page DOC --section X` the first
matching section the same way (one over 200 lines is exit 2: read it in
parts with `--lines`). The `cite:` line has `Markdown` where a PDF's has
`PDF page N` and the file's lines as `lines A-B`; its sections are, for
`--lines`, the one owning line A, then every heading on the lines after
it, and for `--section X` the matched section. `page DOC
N`, `render` and `table` on a Markdown version, and `--lines` on a PDF,
are exit 2 with the command that reads it, before any download. Pipe
tables are printed as text; images are not fetched (their `![alt](path)`
line stays). Notes do not record a Citation of a Markdown version.

A text version (catalog type `txt`, held as `original.txt`: an IETF RFC
in its plain-text form) is read the same way, by the line numbers of the
file as stored, with `Text` in the `cite:` line where Markdown has
`Markdown`; an RFC is cited by section and line even where its text is
printed in pages. Page furniture keeps its line numbers but is never a
heading, a `find` hit, a `--context` line or a printed line: the footer
ending in `[Page N]`, the form-feed line (which may carry the header),
the running header starting `RFC <number> ` and the blank lines padding
them; in a file with a page break, a footer that ends the file is
furniture too. The Outline holds lines starting in column 0: numbered
headings (`4.1.2.  Title`, `1.1 Title`, `Appendix A.  Title`,
`A.1. Title`; level is the count of number parts minus one; the older
`APPENDIX A - Title`, `Appendix A - Title` and `Appendix A: Title` are
read as `Appendix A.  Title`), a title wrapped onto an indented next
line joined to it; and, after the file's first block (the authors),
unnumbered headings (`Abstract`, `Authors' Addresses`), a line with
blank lines around it and indented text next that neither starts with a
lowercase letter nor ends with a colon (so a MIB line at a page's foot
or a legend such as `Key:` is not one), at level 0. Titles are shown as
`4.1.2 Client Hello` and `Appendix A State Machine`; `section DOC A`
finds that appendix as `section DOC 4` finds section 4. A text file
without that layout has an empty Outline: `section` finds nothing,
`find` and `page --lines` read it. `page DOC N`, `render` and `table`
refuse it as they refuse Markdown, and Notes do not record its
Citations.

`invocation PROTOCOL 'NAME:SIZE=VALUE' ...` arranges the bytes of a
request from its fields and prints them in the syntax of the sending
tools. It reads no Document and no network, takes no lock and writes
nothing; only `--subcommand` (below) reads the Source Catalog,
`config.toml` and the pldm Code Tree. PROTOCOL
is `ipmi` (prints `ipmitool raw 0x.. ...`; the first two fields are NetFn
and Cmd, one byte each), `mctp-control` or `spdm` (`mctp-client eid <eid>
type control data .. ..`, `type spdm`), or `pldm` (the `mctp-client` line
with `type pldm` and `pldmtool raw -m <eid> -d 0x.. ...`), or `nc-si` or
`nvme-mi` (below). A field is
`NAME:SIZE=VALUE`, SIZE in bytes. SIZE and every number take ASCII digits
only (`0`-`9`, and `a`-`f` or `A`-`F` after `0x`); digits of another
script are refused. In a VALUE, `0X` is read as `0x` wherever this page
says `0x`. A number (decimal, or hex with `0x`) is laid out least
significant byte first, `NAME:SIZE:be=VALUE` most significant byte first
(`:le` spells out the default). A comma-separated list of bytes
(`0xc0,0xa8,0x01,0x0a`, every byte but a zero written with `0x`) is laid
out as written and must hold SIZE bytes. `<text>` is a placeholder for two
hex digits per byte; a field of N bytes gets `<text 0>` to `<text N-1>`,
one per byte. In the lines whose bytes all carry `0x` (`ipmitool raw`,
`pldmtool raw` and the `ipmi` rows) each is printed `0x<text>`: both tools
read a bare `30` as decimal and refuse `08` as octal, so two hex digits
put in its place give the intended byte. In the `mctp-client` line and the
other rows it is printed `<text>`. The output is `bytes: N` (all fields
together), the line(s) to send, then `offset | size | field | bytes` and
one row per field. Refused with exit 2, a line naming the field and the
reason (a field or value longer than 80 characters is shown cut there,
followed by its length), and no line to send: a number that does not fit
SIZE or is negative; a number that is neither decimal nor `0x` hex, or has
a leading zero (`e1`, `08`: which base is meant is never guessed); a SIZE
that is missing, not a positive integer or above 65535; a list of another
length or with a byte above `0xff`; a number or a list written with spaces
instead of commas (`0xc0 0xa8`); a placeholder that is empty, not opened
or not closed (`<>`, `x>`, `<x`); more than one placeholder in a field, or
a bracket inside one (`<lsb>,<msb>`, `<a>b>`, `<>>`: each placeholder gets
a field of its own); a field without NAME or without VALUE; no field; an
unknown PROTOCOL; `ipmi` with fewer than two fields or a NetFn or Cmd of
more than one byte. The command knows no Document: the fields are the
caller's, and a wrong field gives a wrong line.

`invocation nc-si --type T --package P --channel C [--iid I] 'FIELD' ...`
builds the NC-SI header around the fields given. The fields are the
NC-SI payload alone (none for a Command without one), NAME:SIZE:be for
NC-SI's big-endian numbers. T is the Control Packet Type, P the package
(0..7), C the channel (`0x00`..`0x1f`, or `package` for `0x1f`, the whole
package), I the Instance ID (`0x01`..`0xff`); each is a number as a VALUE
is, P, C and I may be a `<placeholder>`, and without `--iid` the IID is
`<iid>`. A P or C placeholder is printed in the `ncsi-cmd` lines with ` in
hex` added (`<chan>` as `<chan in hex>`): a channel said as 10 is `0a` there. The output is `payload bytes: N`, `packet bytes: M` (16 + N +
padding + 4), then `ncsi-cmd -i <ifindex in hex> -p PP -c CC raw TT B...`
(netlink: the kernel adds header and checksum) and `ncsi-cmd -m <eid in
decimal> -p PP -c CC raw TT B...` (MCTP), both in the syntax of
phosphor-networkd 1c55a45, every number two hex digits without `0x`. Then
`mctp-client eid <eid> type nc-si data ..`, the whole packet from MC ID as
DSP0222 Table 10 lays it out: MC ID `00`, Header Revision `01`, Reserved,
IID, Control Packet Type, Channel ID (package in bits 7..5, channel in
4..0), Flags and the 12-bit Payload Length big-endian, 8 reserved bytes,
the payload, `00` padding to four bytes and the checksum (the two's
complement of the 32-bit sum of 16-bit big-endian words, DSP0222 8.2.2.3).
When the IID, package, channel or a payload byte is a placeholder the
Channel ID is `<channel id>` where unknown and the checksum is printed
`00 00 00 00`, which DSP0222 reads as no checksum. `note:` lines say that
ncsi-cmd reads `-i`, `-p`, `-c`, TYPE and the payload as hex (an ifindex
written in decimal reaches another interface) and `-m` in decimal, that
the IID must change between sends or the controller takes a retry
(DSP0222 6.2.2.2), how the Channel ID is laid out when the package or
channel is a placeholder, and why the checksum is zero when it is. The table has
one row per header field, payload field, padding and checksum, offsets
from MC ID. Refused with exit 2 and one line, besides the field refusals
above: `--type` missing, not a number or above `0x7f` (bit 7 marks a
response); `--package` missing or above 7; `--channel` missing or above
`0x1f`; `--iid` 0 or above `0xff`; a payload above `0xfff` (4095) bytes;
`--type`, `--package`, `--channel` or `--iid` with another protocol
(`--type is for nc-si, not ipmi`).

`invocation nvme-mi --nmimt mi|admin [--csi S] 'FIELD' ...` builds an
NVMe-MI message over MCTP. The fields are the request from the opcode on,
little-endian as NVMe-MI writes its numbers: for `mi` (an NVMe-MI
command) the opcode, three reserved bytes, NMD0, NMD1 and any request
data, at least 12 bytes; for `admin` (an NVMe Admin Command) the opcode,
CFLGS, CTLID, SQE Dwords 1 to 5, DOFST, DLEN, 8 reserved bytes, SQE
Dwords 10 to 15 and any request data, at least 64 bytes. S is the Command
Slot, 0 or 1 (0 when not given). The output is `request bytes: N`,
`message bytes: M` (4 + N + 4); for `admin`, `nvme admin-passthru
mctp:<net>,<eid>:C --opcode=0xOO ...` in the syntax of nvme-cli 2.16, C
the CTLID in decimal and then `--namespace-id`, `--cdw2`, `--cdw3`,
`--cdw10` to `--cdw15` and `--data-len` for each of those dwords that is
not zero, read from their offsets in the fields, in hex with `0x` (a dword
holding a placeholder is `--cdw10=<cdw10>`, `--namespace-id=<nsid>`,
`--data-len=<dlen>`; a placeholder CTLID is `<ctrl id>`). Then
`message:`, the whole message as NVMe-MI 2.2 Figure 20 lays it out: `84`
(IC 1, message type 4), ROR 0 with NMIMT (1 or 2) and CSI, `00 00`, the
fields, and the MIC: CRC-32C (Castagnoli, reflected, initial value and
final XOR `0xffffffff`) over every byte from the first, least
significant byte first. When a byte is a placeholder the MIC is four
`<mic>` bytes. No `mctp-client` line: it sends the message type with the
IC bit clear and no MIC, which an endpoint discards. `note:` lines say,
for `mi`, that no command on an OpenBMC BMC sends an NVMe-MI command-set
message, so the message is for a capture or a libnvme program; for
`admin`, the nvme-cli and libnvme versions and libnvme's probe before the
first command, that `mctp:` takes NET, EID and the controller in decimal,
that the opcode's bits 1..0 give the data direction and request data goes
on stdin or `-i <file>`, and, when the fields hold a DOFST or SQE Dword 4
or 5 that is not zero, that nvme-cli sends them as 0; why the MIC is
`<mic>` when it is; and that MCTP carries a message above 64 bytes in
several packets. The table has one row per header byte, field and the
MIC, offsets from byte 0. Refused with exit 2 and one line, besides the
field refusals above: `--nmimt` missing or not `mi` or `admin` (PCIe
Commands and Control Primitives get no bytes); `--csi` not 0 or 1; fewer
request bytes than 12 (`mi`) or 64 (`admin`); a message above 4224 bytes;
for `admin`, a DLEN above 4096 or an opcode whose bits 1..0 are 11
(bidirectional, which nvme-cli over MCTP refuses); `--nmimt` or `--csi`
with another protocol (`--nmimt is for nvme-mi, not ipmi`), and the nc-si
options with `nvme-mi`.

`invocation pldm --subcommand NAME 'FIELD' ...` prints all of the above,
then what pldmtool's own subcommand for the Command looks like, read from
the openbmc/pldm Code Tree that `grep pldm` would read (a user checkout,
the config Release, else the held default branch): the `add_subcommand`
registration line (`pldm <commit7> pldmtool/pldm_base_cmd.cpp:597 | ...`),
a `cite: code` line and the numbered constructor lines of the subcommand's
class (at most 60; a longer one ends with `(N more lines of the
constructor, to line L)`), the lines of a name map an option is checked against
(`-t,--type` and its `pldmTypes`) under their own cite, and
`subcommand: pldmtool <type> <Name> -m <eid> -i <sensor_id> -r <rearm>`:
one item per `add_option` / `add_flag` in source order, the option as the
source spells it (short form first), the placeholder the long name
without dashes, an option without `->required()` in brackets
(`[-s <state_set_id>]`), a flag as `[-a]`. Every value is a placeholder;
the caller fills them as it fills the fields. Last comes
`note: spellings of pldm <commit7> (<branch and date, or release N, or
user checkout>); the target's pldmtool may differ: check with pldmtool
<type> <Name> --help`: the subcommand names and option spellings are
those of the tree read, and the BMC's pldmtool may be another version;
the raw line above it runs on any. NAME is matched
case-insensitively. Four other outcomes, all exit 0 with the byte lines
printed first: `subcommand: none in pldmtool/` when no `add_subcommand`
carries the name (a name in the table GetPLDMCommands labels its output
with is not one; a type such as `base` or `oem-ibm`, and `raw`, are not
subcommands of a type); `subcommand: pldm Code Tree not held; clone pldm`
when the Library holds no pldm tree (nothing is cloned); and, when the
subcommand is registered but no option call could be read (the options are
added outside the constructor, or the class or constructor was not found),
a template of `-m <eid>` only and `subcommand: options not read; see the
lines above` (`no constructor found` when there were no lines to print);
and `subcommand: <message>` when reading the tree fails any other way.
`--subcommand` with another PROTOCOL is refused with
exit 2. The parse of the C++ is best effort: the source lines are always
printed and are what to trust. With a user checkout of pldm in
`config.toml`, the option reads the checkout's `HEAD` with `git`, as
`grep` and `code` do; a config Release that is not held is reported with
the clone to run (`subcommand: pldm Code Tree not held; clone pldm
--release X`).

## Notes

Off by default. The plugin's Stop hook runs `notes record` at the end of
every turn whether the feature is on or off; off, the command reads
`config.toml` and exits at once. With `[library] notes = true`: when
the turn ran a `bmcspec.py` command and the answer carries a Citation
(a `cite:` line, or `DOC V, section, PDF page N` in prose), the question,
the prompt before it, the answer (the first paragraph only and `partial`
when longer than 4096 characters), the Citations and the document
versions they name go to `notes.jsonl` at the Library root as one Note,
with an id of eight hex characters; the same question about the same versions
replaces the earlier Note.

`find` and `section` then print, after their `note:` / `fetched` /
`extracted` lines and before the hits, `notes DOC V: N` and up to ten
title lines, latest first: `ID DATE | question | DSP0248 1.3.0
pp.107-108; DSP0240 1.2.0 p.9`. A Note is current while every version
it cites is still the one answered from (a document not loaded by the
call only has to be held); otherwise the title line says `superseded`
after the date. `recall`, `notes list` and `notes prune` judge the same
way against the version `find` answers from without `--version` (the
catalog's Latest when held, else the newest held released version), so
a Note citing an older version held beside a newer one is superseded in
all of them. When every identifier in the pattern or query (ASCII
words of three or more characters) occurs in a current Note's question
or cited section titles, the latest such Note is printed whole after the
title lines, from `note: answer from a Note of DATE (ID); ask to re-read
to verify` to `end of note ID`; one Note per call at most, never a
`partial` one. `recall ID` prints one Note whole (a superseded one with
`note: this Note cites DOC V, the Library answers from W; read the pages
again` first, `which the Library no longer holds` when it holds no
version of DOC). `notes list [DOC]` prints the title lines, `notes
forget ID` removes one, `notes prune` removes the superseded ones
(`--days N` also those older than N days, `--all` every one); `status`
adds `notes: N (size)` after the holdings. The hook passes `notes record`
the transcript on stdin; `notes record --transcript FILE` records the last
turn of a transcript file by hand. `notes record` writes the
Note under the Library root's `.lock` (two Sessions ending a turn
together: the one replacing a Note rewrites the file), waiting up to
five seconds; held longer, it prints `note: notes: busy: ...; not
noted` and exits 0, and `status` lists that lock like any other.
When the file grows past `notes_limit` (default `"5MB"`: an integer with
`KB` or `MB`, or `"0"` or the bare integer `0` which never reminds; any
other form is refused),
`find`, `section` and `status` start with `note: notes.jsonl holds N
Notes (size), over notes_limit; run notes prune`; nothing is removed on
its own. Without a Note that cites the document the output is unchanged.
A `notes` value that is not `true` or `false`, or a `notes_limit` that
is not a size, is refused the way `library.offline` is: `find` and
`section` add one `note: notes: ...` line, `recall` and `notes` print
the message and exit 2.

What you accept by turning it on: an answer served from a Note is as
right as it was the first time, and it is not read again from the
document. The tool keys it to the versions so a new version supersedes
it, marks it every time it is served, and lets you forget it; it cannot
tell a wrong first answer from a right one. When in doubt ask to re-read,
and the new answer replaces the Note.

`table` prints every table touching the page as a Logical Table: the
pages it spans are read and joined (a table continues when it is the last
thing on its page, the next page starts with a table with the same column
edges, and only running headers, footers and page numbers lie between,
or a caption that repeats one on the page before or the two before that
(NVMe repeats a figure's caption at the top of each page; a different
caption starts a new table); a table drawn inside another table's cell
does not count as the last or first table on a page; the column edges
may also be a subset one of the other with the same left and right
edges, and under a repeated caption only the left and right edges must
match, since an NVMe figure's inner columns change with what its cells
hold; the joined rows sit on all the parts' column edges together, a
cell under the edge nearest where it starts (in order, one cell to an
edge) and empty cells where it spans more than one; a repeated header
row is dropped), and the
result is a `cite:` line with the section in force where the table starts
(the last heading above it on its first page, else the section at the top
of that page; a table without a caption is placed the same way), `PDF
pages A-B` and `lines table K`, a `table:` line with the caption and how
the table is drawn, and the rows as a text grid. The caption is the
nearest line within 40 points above the table that reads like one (`Table
...` or `Figure ...`), past lines that do not (IPMI draws its column
names between caption and table) but not past another table. A running
header is a line repeated at the same height on a page close by; a line
that reads like a caption with a table under it is never one. Two
drawings are read: `ruled` tables, whose cells are bounded by ruling
lines (thin filled rectangles or stroked lines), and `cells` tables,
which have no rules and paint every cell as a filled box tiled edge to
edge, the way DMTF's current PDFs are made; a box's edges are its cell's
edges, so a merged cell stays one cell, and boxes inside a ruled table (a
shaded header) are not a second table. Rules stroked as path curves
(DMTF's Redfish guides draw the rows a page break cut off that way) are
read as rules of a `ruled` table where neither kind of table was found; a
table read from them that overlaps one found already is dropped, so they
never change the tables found without them. A table laid out with spaces
alone is not detected. A box diagram inside a figure (a packet or
register layout, a ladder diagram, a timing grid) is read as a table too;
when no caption lies within 40 points above it, the `table:` line names
the figure's caption, the first `Figure N ...` line within 200 points
below it, else the nearest within 200 points above it (stopping at a line
that mentions `Table N`, and leaving a caption that has another table
between or right under it, unless that table takes a numbered caption of
its own lying between them: PMBus prints Figure 8's caption, then Table
3's, then Table 3). A table still without a caption takes the
nearest `Table N ...` line that ends within 40 points above it, though it
starts further up (PMBus puts two lines of notes under Table 31's
caption), when no other table stands between; a line such as `Table 3
lists ...` or `Table 12, Table 13 and ...` is prose and is not taken, nor
is a `Figure ...` line. A table that starts its page with no body text
above it and has no caption by these rules takes the last body line of
the page before when that line is `Table` (in any letter case) followed
by an id (`Table 21-4`, `Table A.1`, `Table II` or `table ii`,
`Table A -`; not
`Table: ...`, which has none) below every table there
(IPMI and DSP2058 leave the caption at the foot of a page); running
headers and page numbers are not body text on either page, so a header
above the table does not stop this, and a page number under the caption
is not the line taken. A `Figure ...` line there is not taken, since
SMBus puts a figure's caption under its drawing. Check a value read from such a grid with
`render`. A table longer than 300 rows (DSP2053's property guide is one
table over the whole document) prints a `note:` line and only the rows
that start on the page asked for; `--all-rows` prints every row.
`--index K` prints only the K-th table on the page (1-based). Tables
are read on demand and kept in `tables.json` next to the Extract, so a
page is read from the PDF once; `--force` reads it again.

`schema` reads a Redfish schema bundle (DSP8010): without a resource it
lists the resources and their newest schema version; with one it prints
the properties (type resolved through `anyOf` and `$ref`, read-only flag,
the version that added it, description); `--property` or `--definition`
prints one property or one named definition in full, including every
value of an enum with its description, following `$ref` into the file that
defines it. Each block starts with a `cite:` line naming the bundle
version, the schema file and the JSON pointer. `--definition D` looks in
the resource's newest versioned file, then in its unversioned file
(`ComputerSystem.json` holds `BootSource`), then in the files the
versioned file refers to with a `$ref` ending `/definitions/D`
(`ComputerSystem --definition ResetType` reads `Resource.json`); when that
last step finds D in more than one file it lists them, with the command
for each, and exits 2. An action prints, after its `parameters:` list, a
`parameter <Name>:` line, a `cite:` line and the `values:` of each
parameter whose type is an enum. The profile bundle
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
default branch, a `--ref` branch/tag/commit, or a `--release`), the paths
checked out (`sparse`, `[]` for the whole repository) and when. The
catalog also lists libraries OpenBMC recipes fetch from other projects
(`libspdm`, `ipmitool`, ...); `--release` pins them like the rest.
`--release L` resolves an OpenBMC release: `openbmc/openbmc` is fetched at
tag or branch L (only the `.bb` and `.inc` recipe files of every layer:
the top-level `meta-*` ones and the Yocto layers under `upstream-layers/`
or, up to 2.18.0, `poky/`; about 25 MB at 2.18.0 and 28 MB at `master` in
2026-11) and the component's `SRCREV` there is the commit checked out. A
recipe is read with the `.inc` files it `require`s; an entry with
`name=X` takes `SRCREV_X`. A catalog entry with a hosted URL
(`https://github.com/openbmc/bmcweb.git`) is pinned only by a recipe that
fetches that host and path, not by another project of the same name. A
repository no layer's recipe pins has no release commit, and `clone`
says so; layers that pin it at different commits are listed. An entry's
`moved_from` lists the repository's earlier URLs: a recipe that still
fetches one (`ipmitool` from GitHub up to 2.14.0) pins it too, and the
commit is fetched from the entry's `url`. A component OpenBMC builds
from a release tarball has no `SRCREV`; its entry's `release_tag`
(`v{version}`) turns the version of the recipe named like the entry
(`i2c-tools_4.4.bb`, or the recipe's `PV`) into a tag (`v4.4`), and that
tag is checked out as `--ref v4.4` would, then named after the release:
`pin: <commit7> tag v4.4 (version 4.4) from <recipe> of openbmc
<commit7>`. The tree is the tag's source, not the tarball: files the
tarball generates and the recipe's patches are not in it. A recipe that
pins the entry by `SRCREV` still wins. Recipes of that name at
different versions are listed; a recipe named like the entry with no
usable version (`<id>_git.bb`, a `PV` holding `${...}`) exits 2 with
`no version for <repo> in this release: <recipe> gives no version
(...)`; a version whose tag the remote does not have exits 2 with
`the release builds <repo> <version>, but <url> has no tag <tag>`; when
the remote cannot be asked, the fetch's error is printed instead. The
tag is fetched as `refs/tags/<tag>`, never a branch of that name. A
tree held with other paths than the catalog's (one fetched by an older
version, or before trees recorded them) is brought to the catalog's
paths in place by the next `clone` that reaches it, commit unchanged,
with `note: <repo> <commit> now holds the catalog's paths (...) instead
of (...)`; when git cannot (the new paths are fetched from the tree's
origin), `clone` exits 1, the old paths are put back (the message says
so when that fails too) and the next `clone` tries again. For the
`openbmc` repository itself `--release L` is the same as `--ref L`. A
vendor tree (a catalog entry with an `owner`, see
[CATALOG.md](CATALOG.md#code-trees)) is never guessed: an unlisted id
starting with a vendor owner (`aspeed-`, `nuvoton-`) exits 2. It has no
Release: `--release` on `clone`, `grep` or `code` prints `<repo> has no
Release; use --ref with an SDK branch or tag` and exits 2, and the
`config.toml` default Release is not used for it (`note: <repo> has no
Release; config.toml release L not used`). A catalog entry's `ref` stands
in for the remote's default branch when no flag is given (`nuvoton-linux`);
a tree held from `--ref` at that branch and a default-branch tree of it are
one branch: either answers the other without the network. Several
commits of one repository coexist; `--force` on a moving name fetches again
and marks the older tree of that branch superseded (whether it was held
under `--ref` or as the default branch) rather than deleting it. A plain
`clone` leaves one current default-branch tree: every other default-branch
tree (fetched under an earlier catalog `ref`, or under the remote's old
default branch name) is marked superseded too, and `clone` prints a
`superseded` line for each tree it marks; a held one also marks an older
current tree of its own branch. Trees held under `--release` or under
`--ref` of another branch stay. When a fetch lands on a commit held in a
superseded tree of the same name (the branch moved back), that tree is
current again. When a plain `clone` lands on a commit held already, that
tree becomes the default-branch tree under the branch name the remote uses
now: a default-branch tree takes that name, a superseded tree of another
branch becomes a default-branch tree, and a current `--ref` or `--release`
tree keeps its provenance and records `"default_branch": "<name>"` in its
`.bmc-tree.json`, so the next plain `clone` answers from it without the
network (a later plain `clone` that resolves elsewhere removes the field).
A `--ref` tree that supersedes the default-branch tree of its branch takes
the field the same way. When `--force` re-fetches the `--ref` or
`--release` name of a tree that carries the field and lands on another
commit, the marked tree is not superseded: it becomes the default-branch
tree under the name the field held, with no `superseded` line, and the new
commit holds the `--ref` or `--release`. Only a `--ref` of the branch the
field names moves the mark: the new tree supersedes the old one and takes
the field. A `--release` never counts as that branch, even one named like
it (`--release master` on a repository whose default branch is `master`).
When a `--ref` or `--release` clone lands on a commit held under another
name (a Release pin that is also the default branch's head, a tag on a
commit held as a Release), that tree keeps its provenance and records the
name in an `"also"` list in its `.bmc-tree.json` (a version before 1.3.0
ignores the list and drops it when it rewrites the file, so going back to
one loses the recorded names); `clone` prints `held`
with the tree's own provenance, and the next clone of that name answers
without the network. A tree with `also` names is not superseded when its
own name moves on: the first `also` name becomes its provenance instead.
When an `also` name moves on, only that entry leaves the tree. A tree is
superseded only when no name is left on it. `repos` lists the names after
the provenance (`<commit7> dev <date> (also release 2.18.0, v1.2)`). A
full or abbreviated commit id given as `--ref` is not recorded: a commit is
found by its id already. `clone` prints `cloned` when it downloaded the
commit and `held` when the commit was already in the Library: nothing was
downloaded, though `--force` still asks the remote where a name points.
`grep` (`git grep`) and `code` read a
tree: a user checkout named in `config.toml` first, then the `--ref` or
`--release` asked for (a tree's own provenance or an `also` name), then the
`config.toml` default Release, then a
held tree of the branch the catalog `ref` names (a superseded one still
counts until `prune` removes it), then the default-branch tree. Like
`find`, `grep` matches a fixed string unless `--regex`; unlike `find`, it
is case-sensitive unless `-i` (`--ignore-case`); `--glob G` limits it to
the paths matching the git pathspec G (`'*.hpp'`). Every `code` output starts with a `cite:` line naming
repository, commit, provenance, path and lines; a tree found by an `also`
name is cited under that name (`release L`, `<ref> <date>`).

`prune` lists every Code Tree marked superseded (an older commit of a
moving name re-fetched with `--force`), every `.tmp-*` directory a failed
clone left behind, every `.part` file or `.lock.takeover` gate older than
five minutes that a failed write or take-over left behind, and every stale
`.lock`, and removes nothing; `prune --yes` removes them, taking each stale
lock through the same `.lock.takeover` gate a writer uses and keeping one
that is no longer stale: `kept <path> (taken over meanwhile)` when a
Session now holds it, `(take-over in progress)` when a Session is inside the
gate; the summary then says `, N kept`. A stale lock its holder released
before `prune` reached it is printed as `gone <path> (released meanwhile)`
and counted as `, N gone`. A directory whose lock is live is skipped
whole. The current tree of each name, trees reached by a commit, user
checkouts and the documents under `specs/` are never touched.

`config.toml` at the Library root (optional):

```toml
[library]
freshness_days = 30           # how old a Freshness Check may be before a note
offline = false               # true: the reading commands download nothing
                               # and skip the check (fetch, check and clone
                               # still go online when you run them)
notes = false                 # true: remember answers in notes.jsonl and
                               # serve them again (see Notes above)
notes_limit = "5MB"           # remind to prune above this size; "0" never

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
OCP project pages' specification tables, the RFC Editor's metadata for an
RFC; publishers with no parseable index, such as Intel, NXP, SMBus, OIF,
NIST and OASIS, are printed as `unchecked`), then, when `config.toml` pins
a release, compares it with the newest `X.Y.Z` tag of
`openbmc/openbmc` (`release: 2.18.0 (config.toml); newest openbmc tag
3.0.0 -> newer`). Nothing is downloaded and no version is switched: a
newer version enters the Library only after the catalog lists it (see
[CATALOG.md](CATALOG.md)) or as a Drop-in. The outcome and the time go to
`freshness.json` at the Library root. A reading command runs the check
itself, after its output, when the document it answered from has not
been checked within `freshness_days` (default 30) and prints the outcome
as a note: `note: newer DOC: catalog latest V, <publisher> lists W (date)
URL`, nothing when current, `note: unreachable DOC: <reason>` when the
publisher could not be read; the outcome is recorded like `check`'s, so
the next question within that age does not check again, and the note
never changes the exit code. `fetch` and `status` print a `note:` reminder
to run `check` instead, once per document until the next check, and that
reminder never touches the network. `[library] offline = true` turns the
reading commands' check off.
OCP versions are mostly Google Drive links on the OCP pages, so `check`
reports them with `(URL to confirm by hand)`. `refresh --skip-source
SOURCE` (repeatable; `dmtf`, `nvme`, `ocp` or `rfc`) leaves that
publisher's documents out, neither read nor reported (`github` leaves
out the commit check below); the catalog workflow runs
`refresh --skip-source ocp` because opencompute.org refuses GitHub's
runners ([CATALOG.md](CATALOG.md)). Naming a document whose publisher is
skipped exits 2.
`refresh` without DOC and without `--skip-source dmtf` also reads the
DMTF published-documents page once and prints, after the per-document
lines and in id order, `unlisted DSP0297 1.0.0 "Title" URL` for each DSP
id there that no catalog document lists and the catalog's `[listings.dmtf]
not_taken` does not cover; the summary then ends its counts with
`unlisted N`. A page that cannot be read prints `unreachable unlisted:
<reason>` and counts as one `unreachable`. `unlisted` ids are never
written, `--write` or not. `check` does not read the page for this.

A Markdown version pins a commit in its raw.githubusercontent.com URL.
`refresh` takes each document's newest Markdown version (a document with
one and no listing included, so `refresh CALIPTRA` works) and asks the
GitHub API for the newest commit touching that file on the repository's
default branch. The pinned commit prints nothing; another one prints
`changed DOC V: <path> has commit <sha7> (<date>), the catalog pins
<sha7>; <raw URL at the new commit> (not written; re-pin by hand)`. It is
never written, `--write` or not: a newer commit may be a new revision of
the document, whose version string the maintainer decides. A Markdown URL
on another host or without a full 40-hex commit id prints `confirm DOC V:
<url> (cannot check: not a pinned raw.githubusercontent.com URL)` and is
not requested. A request that fails prints `unreachable DOC V: <reason>`
(HTTP 403 or 429 is GitHub's limit of 60 requests an hour without a
token). The summary counts these with the listing lines, so the catalog
workflow reports a moved pin like any other proposal.

An RFC (an `RFCnnnn` document of a family whose publisher is IETF; its
listing is `rfc:nnnn`) is checked against the RFC Editor's metadata,
`https://www.rfc-editor.org/rfc/rfcnnnn.json`. For an RFC, newer means
an RFC that obsoletes it, which is a different document: `check`,
`refresh` and the reading commands' note print `obsoleted RFCnnnn: the
RFC Editor lists it as obsoleted by RFCxxxx (<URL of its text>)`,
several joined by `; `, for each obsoleting RFC that the document's
`obsoleted_by` in the catalog does not already record. `check` prints
`current RFCnnnn V` when there is none and `refresh` prints nothing.
`check` counts an obsoleted RFC among `newer` and adds a line saying the
obsoleted RFC stays readable and citable. Whenever it checked an RFC,
`refresh`'s summary adds `obsoleted N` (the RFCs reported) after
`unreachable`, before `unlisted`, so the catalog workflow reports it
like any other proposal; `--write` writes nothing for it: the maintainer
adds the newer RFC as a document and extends `obsoleted_by` by hand.
`--skip-source rfc` leaves the RFCs out. RFCs that only update an RFC,
and errata, are not followed.

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
it (through a `.lock.takeover` gate created with `O_EXCL`, so that only one
Session removes it and never a fresh lock), prints
`note: took over a stale lock from pid P on host H (...)` and does the
whole operation again from scratch: a take-over trusts only state
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
`registry`) take no lock on a Ready version. One that is not Ready they
fetch or extract themselves under the version's lock, as `fetch` and
`extract` do: a Session already doing it is waited for the same way, and
the command then answers from the finished Extract, or exits 3 if it is
still busy. `table` also takes the lock to merge what it read into
`tables.json`. In
`--all` runs a busy document is counted (`busy N` in the summary) and the
run exits 3 unless something failed, which exits 2 as before.

Single files (`meta.json`, `extract.json`, `tables.json`, `.bmc-tree.json`,
`freshness.json`, originals and rendered pages) are written to a temporary
name beside the target, `<name>.<pid>-<token>.part`, and renamed into
place, so a reader never sees a half-written file and two Sessions writing
the same file do not collide. Two kinds of file are not: the schema and
registry files unpacked from a bundle are written in place under the
version's lock (`extract.json`, written last through a `.part`, is what
marks them complete), and a new Note is appended to `notes.jsonl` in one
write; replacing, forgetting and pruning Notes rewrite the file through a
`.part`. `status` lists every lock with its holder and
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
  documents are never requested at all. `fetch` downloads on request; the
  reading commands download the one version they need (the catalog's
  latest, or `--version`) when the Library lacks it, through the same
  chain, and `[library] offline = true` in `config.toml` stops them.
  The Archive throttles bursts of queries for a while; the tool then says
  "rate limited by archive.org (HTTP 429)" rather than "no Wayback
  snapshot", and does not retry on its own. Run the command again later.
- A response that is not the expected PDF or ZIP (an HTML block page, a
  cut-off download) is discarded and never written to the Library. A
  Markdown or text version, which has no leading bytes to check, must be UTF-8
  text that does not start as an HTML page. The same check applies to
  files given to `add` or found by `scan`.
- Writes only under the Library, besides the plugin's own data directory
  (the `SessionStart` hook, below). Files placed there by hand are registered
  as Drop-ins and their origin is recorded as user-provided, never as a URL;
  `scan` also records whether the document id is in the catalog
  (`catalog_known`). Nothing already in the Library is replaced without
  `--force`. `fetch`, `add`, `extract`, `table` and a reading command
  downloading or extracting hold `.lock` in the version directory while
  they write (see above), `notes record` holds `.lock` at the Library
  root while it writes `notes.jsonl`, and every single-file
  write goes through a `<name>.<pid>-<token>.part` temporary beside the
  target, except a bundle's unpacked files and a new Note appended to
  `notes.jsonl` (see above); nothing else is created.
- Replacing an original (`add --force`, `fetch --force`) removes the
  previous original and everything extracted from it, `tables.json`,
  `schemas/` and rendered pages included. `extract --force` replaces the
  Extract files and removes `tables.json`; rendered pages stay, since the
  original they come from is unchanged.
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
- `check` and `refresh` read listing pages only: `https://www.dmtf.org/standards/published_documents` and `https://www.dmtf.org/dsp/<DSP>`, `https://nvmexpress.org/wp-json/vtm/v1/specifications`, and `https://www.opencompute.org/projects/<page>/` for the pages named in the catalog's `listing` keys. They download no document. For each RFC they read `https://www.rfc-editor.org/rfc/rfc<N>.json`, the RFC Editor's record of it, not the RFC itself. The one exception is `refresh`, which also makes one unauthenticated request to `https://api.github.com/repos/<owner>/<repo>/commits?path=<path>&per_page=1` per document whose newest Markdown version is pinned in a raw.githubusercontent.com URL; `check` and the reading commands never do. A reading command reads the one listing page of the document it answered from when that document's Freshness Check is due (at most once per document per `freshness_days`), never with `[library] offline = true`.
- Runs `git` as a subprocess for `clone` (shallow, one commit; `--filter=blob:none --sparse` for the `openbmc` repository and for `linux`, which is held only for `Documentation/` and the BMC-facing driver directories), `grep` (`git grep`), `git rev-parse HEAD` in a user checkout for `grep`, `code` and `invocation --subcommand` (the commit their cite names; on a Library tree `code` reads the files only), and `git ls-remote --tags` on the `openbmc` repository for `check`; `gh search code` for `repos --search`. The plugin's `SessionStart` hook runs `pip install` of `requirements.txt` from PyPI into the plugin's data directory, once, and again only when the content of `requirements.txt` changes. Nothing else is executed, and nothing is re-uploaded or redistributed. `repos --search` searches the openbmc organisation only, not the external libraries the catalog lists (`libspdm`, `ipmitool`, ...). `clone` fetches from the URL of the catalog entry: GitHub, but Codeberg for `ipmitool` and git.kernel.org for `i2c-tools` and `ethtool`. For an entry with `release_tag`, `clone --release` also runs `git ls-remote --tags` on that URL when fetching the tag fails, to say whether the tag is missing. The vendor kernels `aspeed-linux` and `nuvoton-linux` are cloned sparse like `linux` (its directories plus the vendor's arch, dts and soc ones), and the vendor SDK layers `aspeed-openbmc` and `nuvoton-openbmc` hold only `meta-<vendor>*` and `meta-evb`. `nuvoton-igps` holds only its text files (scripts, XML layouts, notes), not the prebuilt images beside them. `libspdm` holds `include/`, `library/`, `os_stub/` and `doc/`, not `unit_test/` (about 7.5 MB instead of 60 MB at `main` in 2026-11).
- `clone` writes only under the Library's `code/` directory: `code/<repo>/<commit>/` plus a temporary `.tmp-<pid>-<token>` directory that is removed on failure, and `code/<repo>/.lock` while it runs. A user checkout named in `config.toml` is only read. `prune --yes` removes superseded trees, `.tmp-*` and `.part` leftovers, `.lock.takeover` files older than five minutes (a take-over creates one) and stale `.lock` files under `code/` and `specs/` and at the Library root, nothing else.
- `check` writes `freshness.json` at the Library root, and so does a reading command that ran the due check; `fetch` and `status` stamp the reminder there (`reminded_at`) when they print the note. `refresh --write` is the one command that writes outside the Library: it inserts version entries into the catalog file it was given (`--catalog`, or the shipped `bmc_toolkit/spec/catalog.toml`).
