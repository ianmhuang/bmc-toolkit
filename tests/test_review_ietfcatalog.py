"""Reviewer acceptance tests for T81.2 (feature/ietf-rfcs), the catalog
side: the ``ietf`` family and its seventeen RFCs (AC-1), the notes and
limits the criteria name (AC-2), what ``catalog`` prints and the totals
(AC-3), and the Golden Questions G118 to G134 with the Verified column and
the Support Level table they feed (AC-8), and where the IETF block sits in
the catalog file (AC-13, round 2).

Only the shipped catalog, docs/golden-questions.md and docs/SUPPORT.md are
read; nothing touches the network or the Library. Whether a cited line of
an RFC says what a row claims cannot be checked here (no RFC text is in the
repository).
"""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import plaintext
from bmc_toolkit.spec.catalog import DEFAULT_CATALOG, load_catalog
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "golden-questions.md"
SUPPORT = ROOT / "docs" / "SUPPORT.md"

# AC-1: the seventeen, in this order.
NUMBERS = (
    9846,
    5246,
    9110,
    9112,
    7617,
    4251,
    4252,
    4253,
    4254,
    3414,
    3416,
    5424,
    5905,
    2131,
    9915,
    6455,
    6143,
)
IDS = [f"RFC{n}" for n in NUMBERS]
FIRST_QUESTION = 118  # AC-8: G118 to G134, in catalog order

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
MONTH_VERSION = re.compile(rf"({'|'.join(MONTHS)}) (\d{{4}})")

# Title and printed month of the RFCs the reviewer knows from their first
# page. RFC 9846 and RFC 9915 are left to the form checks: the reviewer had
# no network to read their front matter.
KNOWN = {
    "RFC5246": (
        "The Transport Layer Security (TLS) Protocol Version 1.2",
        "August 2008",
    ),
    "RFC9110": ("HTTP Semantics", "June 2022"),
    "RFC9112": ("HTTP/1.1", "June 2022"),
    "RFC7617": ("The 'Basic' HTTP Authentication Scheme", "September 2015"),
    "RFC4251": ("The Secure Shell (SSH) Protocol Architecture", "January 2006"),
    "RFC4252": ("The Secure Shell (SSH) Authentication Protocol", "January 2006"),
    "RFC4253": ("The Secure Shell (SSH) Transport Layer Protocol", "January 2006"),
    "RFC4254": ("The Secure Shell (SSH) Connection Protocol", "January 2006"),
    "RFC3414": (
        "User-based Security Model (USM) for version 3 of the Simple "
        "Network Management Protocol (SNMPv3)",
        "December 2002",
    ),
    "RFC3416": (
        "Version 2 of the Protocol Operations for the Simple Network "
        "Management Protocol (SNMP)",
        "December 2002",
    ),
    "RFC5424": ("The Syslog Protocol", "March 2009"),
    "RFC5905": (
        "Network Time Protocol Version 4: Protocol and Algorithms Specification",
        "June 2010",
    ),
    "RFC2131": ("Dynamic Host Configuration Protocol", "March 1997"),
    "RFC6455": ("The WebSocket Protocol", "December 2011"),
    "RFC6143": ("The Remote Framebuffer Protocol", "March 2011"),
}


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out


def cells(line):
    """The cells of a Markdown table row, stripped."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", body)]


def golden_rows(text):
    """Every question row of the file as its cells."""
    return [cells(ln) for ln in text.splitlines() if re.match(r"^\|\s*G\d+\s*\|", ln)]


def golden_text():
    return GOLDEN.read_text(encoding="utf-8")


def the_version(doc):
    assert len(doc.versions) == 1, doc.id
    return doc.versions[0]


# ------------------------------------------------------------------ AC-1


def test_ac1_the_family_is_ietf_with_its_title_and_publisher(shipped):
    assert "ietf" in shipped.families
    family = shipped.families["ietf"]
    assert family.title == "IETF Requests for Comments"
    assert family.publisher == "IETF"


def test_ac1_the_family_holds_the_seventeen_in_order(shipped):
    assert [d.id for d in shipped.by_family("ietf")] == IDS
    # nothing else is an RFC, and no RFC sits in another family
    assert [d.id for d in shipped.documents if d.id.startswith("RFC")] == IDS


@pytest.mark.parametrize("number", NUMBERS)
def test_ac1_each_rfc_is_open_direct_and_has_one_txt_version(shipped, number):
    doc = shipped.get(f"RFC{number}")
    assert doc is not None
    assert doc.family == "ietf"
    assert (doc.access, doc.fetch) == ("open", "direct")
    assert doc.title.strip() == doc.title and doc.title
    version = the_version(doc)
    assert version.type == "txt"
    assert version.url == f"https://www.rfc-editor.org/rfc/rfc{number}.txt"
    assert version.open and not version.wip
    # the version is the printed month, published the first day of it
    m = MONTH_VERSION.fullmatch(version.version)
    assert m, version.version
    month = MONTHS.index(m.group(1)) + 1
    assert version.published == f"{m.group(2)}-{month:02d}-01"
    assert doc.latest() == version


@pytest.mark.parametrize("doc_id", sorted(KNOWN))
def test_ac1_title_and_month_are_the_rfcs_own(shipped, doc_id):
    title, month = KNOWN[doc_id]
    doc = shipped.get(doc_id)
    assert doc is not None
    assert doc.title == title
    assert the_version(doc).version == month


# ------------------------------------------------------------------ AC-2


def test_ac2_rfc5246_says_what_obsoletes_it_and_why_it_stays(shipped):
    notes = shipped.get("RFC5246").notes
    assert "obsoleted" in notes.lower()
    assert "RFC 8446" in notes and "RFC 9846" in notes
    assert "TLS 1.2" in notes and "deployed" in notes


def test_ac2_rfc3414_records_the_twice_numbered_section(shipped):
    limits = shipped.get("RFC3414").limits
    assert "12.1" in limits
    assert "Normative" in limits and "Informative" in limits
    # the other sixteen record no limit
    assert [d.id for d in shipped.by_family("ietf") if d.limits] == ["RFC3414"]


# ------------------------------------------------------------------ AC-3


@pytest.mark.parametrize("name", ["ietf", "IETF"])
def test_ac3_catalog_family_lists_the_seventeen(capsys, name):
    code, out = run(capsys, "catalog", "--family", name)
    assert code == 0, out
    rows = [ln.split("\t") for ln in out.splitlines()]
    assert [r[1] for r in rows] == IDS
    assert {r[0] for r in rows} == {"ietf"}
    assert {(r[2], r[3]) for r in rows} == {("open", "direct")}


def test_ac3_catalog_document_shows_version_type_and_url(capsys):
    code, out = run(capsys, "catalog", "RFC9110")
    assert code == 0, out
    lines = out.splitlines()
    assert "document: RFC9110" in lines
    assert "family: ietf (IETF)" in lines
    assert "latest: June 2022" in lines
    rows = [ln.split("\t") for ln in lines if ln.startswith("\t")]
    assert len(rows) == 1, out
    assert rows[0][1:4] == ["June 2022", "2022-06-01", "txt"]
    assert rows[0][5] == "https://www.rfc-editor.org/rfc/rfc9110.txt"


def test_ac3_the_totals_are_145_documents_37_families_125_open(shipped):
    docs = shipped.documents
    assert len(docs) == 145
    assert len({d.family for d in docs}) == 37
    assert sum(d.access == "open" for d in docs) == 125
    # the seventeen are the whole difference: nothing else left or came
    assert len([d for d in docs if d.family != "ietf"]) == 128


# ------------------------------------------------------------------ AC-8


def ietf_rows():
    text = golden_text()
    assert text.count("\n## IETF RFCs\n") == 1
    section = text.split("\n## IETF RFCs\n", 1)[1].split("\n## ", 1)[0]
    return golden_rows(section)


def test_ac8_one_question_per_rfc_in_catalog_order(shipped):
    rows = ietf_rows()
    wanted = [f"G{FIRST_QUESTION + i}" for i in range(len(IDS))]
    assert [r[0] for r in rows] == wanted
    assert wanted[-1] == "G134"
    for doc_id, row in zip(IDS, rows, strict=True):
        version = the_version(shipped.get(doc_id)).version
        assert row[2] == f"{doc_id} {version}", row[0]
    # the ids are used once in the whole file and nothing follows G134
    numbers = [int(r[0][1:]) for r in golden_rows(golden_text())]
    assert len(numbers) == len(set(numbers))
    assert max(numbers) == 134


def test_ac8_each_answer_cites_a_section_and_lines_of_the_text(shipped):
    for doc_id, row in zip(IDS, ietf_rows(), strict=True):
        label = f"{doc_id} {the_version(shipped.get(doc_id)).version}"
        where = row[3]
        assert where.startswith(label + ","), row[0]
        assert re.search(r"\bsection \d[\d.]*", where), row[0]
        spans = re.findall(r"\blines (\d+)-(\d+)", where)
        assert spans, f"{row[0]}: no 'lines A-B'"
        assert all(0 < int(a) <= int(b) for a, b in spans), row[0]
        assert not re.search(r"\bpages? \d", where), f"{row[0]}: an RFC has no page"


def test_ac8_each_row_is_answered_with_section_or_page_lines():
    for doc_id, row in zip(IDS, ietf_rows(), strict=True):
        commands = re.findall(r"`([^`]+)`", row[4])
        assert commands, row[0]
        # every command reads this RFC
        assert all(c.split()[1] == doc_id for c in commands), row[0]
        by_section = [c for c in commands if c.startswith(f"section {doc_id} ")]
        by_lines = [c for c in commands if c.startswith(f"page {doc_id} --lines ")]
        assert by_section or by_lines, row[0]
        # a --lines range is one `page` prints in a single call
        for command in by_lines:
            m = re.fullmatch(rf"page {doc_id} --lines (\d+)-(\d+)", command)
            assert m, command
            first, last = int(m.group(1)), int(m.group(2))
            assert 0 < first <= last
            assert last - first + 1 <= plaintext.MAX_LINES, command


def _is_text_row(catalog, document_cell):
    pairs = []
    for entry in document_cell.split(";"):
        entry = entry.strip()
        if entry and entry != "-":
            doc_id, _, version = entry.partition(" ")
            pairs.append((doc_id, version.strip()))
    if not pairs:
        return False
    for doc_id, version in pairs:
        doc = catalog.get(doc_id)
        found = doc.find_version(version) if doc else None
        if found is None or found.type != "txt":
            return False
    return True


def test_ac8_lines_locate_a_text_row_and_every_other_row_keeps_its_page(shipped):
    text_rows = []
    for row in golden_rows(golden_text()):
        if int(row[0][1:]) <= 24:
            continue  # the rows from before the page rule
        where = row[3]
        if _is_text_row(shipped, row[2]):
            text_rows.append(row[0])
            assert re.search(r"\blines? \d+", where), row[0]
        else:
            paged = re.search(r"\bpages?\s+\d+", where, re.I) or "#/" in where
            assert paged, f"{row[0]}: no physical PDF page named"
    assert text_rows == [f"G{FIRST_QUESTION + i}" for i in range(len(IDS))]


def test_ac8_the_golden_file_marks_all_seventeen_verified(shipped, capsys):
    code = main(["catalog", "--table", "--golden", str(GOLDEN)])
    captured = capsys.readouterr()
    assert code == 0, captured.out
    assert captured.err == "", captured.err
    by_id = {}
    for line in captured.out.splitlines()[2:]:
        row = cells(line)
        by_id[row[1].split("`")[1]] = row
    for index, doc_id in enumerate(IDS):
        doc = shipped.get(doc_id)
        version = the_version(doc).version
        family, document, access, latest, fetch, verified, _limit = by_id[doc_id]
        assert family == "IETF Requests for Comments"
        assert document == f"`{doc_id}` {doc.title}"
        assert (access, latest, fetch) == ("open", version, "direct")
        assert verified == f"G{FIRST_QUESTION + index} ({version})"


def _family_block(lines, heading):
    start = lines.index(heading)
    block = [heading]
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        block.append(line)
    while block and not block[-1].strip():
        block.pop()
    return block


def test_ac8_support_md_holds_the_generated_ietf_section(capsys):
    code = main(["catalog", "--table", "--by-family", "--golden", str(GOLDEN)])
    captured = capsys.readouterr()
    assert code == 0, captured.out
    heading = "## IETF Requests for Comments"
    generated = _family_block(captured.out.splitlines(), heading)
    shipped_lines = SUPPORT.read_text(encoding="utf-8").splitlines()
    assert heading in shipped_lines
    assert _family_block(shipped_lines, heading) == generated
    rows = [cells(ln) for ln in generated if ln.startswith("| `RFC")]
    assert [r[0].split("`")[1] for r in rows] == IDS
    assert {r[3] for r in rows} == {"PASS"}
    limits = {r[0].split("`")[1]: r[4] for r in rows}
    assert "12.1" in limits["RFC3414"]
    assert {v for k, v in limits.items() if k != "RFC3414"} == {"-"}


# ----------------------------------------------------------------- AC-13


def _tables_of_the_catalog_file():
    """(table, id, line number) of every ``[[documents]]`` and ``[[repos]]``
    table of the shipped catalog file, in file order."""
    lines = DEFAULT_CATALOG.read_text(encoding="utf-8").splitlines()
    tables = []
    for index, line in enumerate(lines):
        if line.strip() not in ("[[documents]]", "[[repos]]"):
            continue
        found = None
        for follower in lines[index + 1 :]:
            if follower.startswith("["):
                break
            found = re.fullmatch(r'id\s*=\s*"([^"]+)"\s*', follower)
            if found:
                break
        assert found, f"line {index + 1}: a table without an id"
        tables.append((line.strip().strip("[]"), found.group(1), index + 1))
    return tables


def test_ac13_the_ietf_block_follows_odata_and_precedes_the_first_repository():
    tables = _tables_of_the_catalog_file()
    kinds = [kind for kind, _, _ in tables]
    assert "repos" in kinds
    first_repo = kinds.index("repos")
    # the seventeen are the last documents before the first repository,
    # in the order AC-1 gives, and the OData documents come right before
    before = [name for _, name, _ in tables[:first_repo]]
    assert before[-len(IDS) :] == IDS
    odata = ["ODATA-PROTOCOL", "ODATA-URL", "ODATA-CSDL", "ODATA-JSON"]
    assert before[-len(IDS) - len(odata) : -len(IDS)] == odata
    # no RFC (and no other document) is left among the repositories
    assert "documents" not in kinds[first_repo:]
    after = [name for _, name, _ in tables[first_repo:]]
    assert not [name for name in after if name.startswith("RFC")]
