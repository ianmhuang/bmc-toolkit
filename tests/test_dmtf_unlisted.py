"""DMTF documents the catalog has not decided on: `refresh` over the whole
catalog reads DMTF's published-documents page and prints `unlisted` for
each DSP id there that no document lists and `[listings.dmtf] not_taken`
does not cover. Never written; the catalog workflow counts them."""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import catalog as C
from bmc_toolkit.spec import cli
from bmc_toolkit.spec import listing as L
from tests.conftest import MINI_CATALOG, ScriptedClient, ok
from tests.test_catalog_workflow import TAIL, _run_refresh_block

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "catalog.yml"

DMTF_DSP0236 = "https://www.dmtf.org/dsp/DSP0236"
NVME_API = "https://nvmexpress.org/wp-json/vtm/v1/specifications"
FILES = "/sites/default/files/standards/documents"

NVME_DOC = """
[families.nvme]
title = "NVM Express"
publisher = "NVM Express, Inc."

[[documents]]
id = "NVME-MI"
family = "nvme"
title = "NVMe Management Interface"
access = "open"
fetch = "direct"
listing = "nvme:nvme-mi-specification"

[[documents.versions]]
version = "2.1"
url = "https://example.test/NVM-Express-Management-Interface-Specification-2.1.pdf"
type = "pdf"
published = "2025-08-01"
"""


def not_taken(*entries: str) -> str:
    items = ", ".join(f'"{e}"' for e in entries)
    return f"\n[listings.dmtf]\nnot_taken = [{items}]\n"


def row(dsp: str, version: str, title: str) -> str:
    return (
        f"<tr><td>{dsp}</td><td>{version}</td>"
        f'<td><a href="{FILES}/{dsp}_{version}.pdf">{title}</a></td>'
        f'<td>Standard</td><td><a href="/dsp/{dsp}">View</a></td></tr>'
    )


def page(*rows: str) -> bytes:
    head = (
        "<html><body><table><thead><tr><th>DSP #</th><th>Version</th>"
        "<th>Title</th><th>Comments</th><th>Versions</th></tr></thead><tbody>"
    )
    return (head + "".join(rows) + "</tbody></table></body></html>").encode()


# DSP0236 is listed by the mini catalog; the others are not.
PAGE = page(
    row("DSP0236", "1.3.3", "MCTP Base"),
    row("DSP0297", "1.0.0", "A New PMCI Document"),
    row("DSP0801", "1.0.0", "CLP Service Profile Mapping"),
    row("DSP0282", "1.1.0", "MMBI"),
    row("DSP-IS0501", "1.0.0", "SDDC White Paper"),
)

DSP_PAGE = b"""<html><body><table><thead><tr>
<th>Version</th><th>Title</th><th>Publication Date</th><th>Comments</th>
</tr></thead><tbody>
<tr><td>1.3.3</td><td><a href="https://example.test/DSP0236_1.3.3.pdf">MCTP Base</a>
</td><td>25 Mar 2024</td><td>Standard</td></tr>
<tr><td>1.3.2</td><td><a href="https://example.test/DSP0236_1.3.2.pdf">MCTP Base</a>
</td><td>2 Jan 2024</td><td>Standard</td></tr>
</tbody></table></body></html>"""


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "lib"))
    scripted = ScriptedClient(
        {
            L.DMTF_PUBLISHED: ok(PAGE, "text/html"),
            DMTF_DSP0236: ok(DSP_PAGE, "text/html"),
        }
    )
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: scripted)
    return scripted


def write_catalog(tmp_path, text: str) -> Path:
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def run(capsys, catalog_file, *argv):
    code = cli.main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def lines_of(out: str, kind: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith(kind + " ")]


def summary(out: str) -> str:
    (line,) = lines_of(out, "summary:")
    return line


def parse(text: str) -> C.Catalog:
    import tomllib

    return C.parse_catalog(tomllib.loads(text))


# ------------------------------------------------------------------ AC-1


def test_not_taken_entries_are_prefixes_matched_without_case():
    cat = parse(MINI_CATALOG + not_taken("dsp08", "DSP0004", " DSP-IS "))
    assert cat.dmtf_not_taken == ("DSP08", "DSP0004", "DSP-IS")
    assert cat.dmtf_not_taken_covers("DSP0801")
    assert cat.dmtf_not_taken_covers("dsp0899")
    assert cat.dmtf_not_taken_covers("DSP0004")
    assert cat.dmtf_not_taken_covers("DSP-IS0501")
    assert not cat.dmtf_not_taken_covers("DSP0900")
    assert not cat.dmtf_not_taken_covers("DSP0282")


def test_a_catalog_without_the_table_loads_as_before():
    cat = parse(MINI_CATALOG)
    assert cat.dmtf_not_taken == ()
    assert not cat.dmtf_not_taken_covers("DSP0801")
    assert parse(MINI_CATALOG + "\n[listings.dmtf]\n").dmtf_not_taken == ()


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ('\n[listings.dmtf]\nnot_taken = "DSP08"\n', "listings.dmtf.not_taken"),
        ("\n[listings.dmtf]\nnot_taken = [8]\n", r"not_taken\[0\]"),
        (not_taken("DSP08", "MCTP"), r"not_taken\[1\].*not a DSP id"),
        (not_taken("DSP08", ""), r"not_taken\[1\].*not a DSP id"),
        (not_taken("DSP08", "dsp08"), r"not_taken\[1\].*duplicate"),
        (not_taken("DSP0236"), r"not_taken\[0\].*listing of DSP0236"),
        (not_taken("dsp0236"), r"not_taken\[0\].*listing of DSP0236"),
        ("\n[listings.nvme]\nnot_taken = []\n", "listings.nvme"),
        ("\n[listings.dmtf]\nskip = []\n", "listings.dmtf.skip"),
        ("\n[listings]\ndmtf = 1\n", "listings.dmtf"),
    ],
    ids=[
        "not-a-list",
        "not-a-string",
        "not-dsp",
        "empty",
        "duplicate",
        "taken",
        "taken-lower",
        "other-publisher",
        "other-key",
        "dmtf-not-table",
    ],
)
def test_bad_not_taken_is_refused_naming_the_place(extra, message):
    with pytest.raises(C.CatalogError, match=message):
        parse(MINI_CATALOG + extra)


def test_listings_that_is_not_a_table_is_refused():
    text = MINI_CATALOG.replace(
        "schema_version = 1", "schema_version = 1\nlistings = 1"
    )
    with pytest.raises(C.CatalogError, match="catalog.listings: expected dict"):
        parse(text)


def test_a_prefix_over_a_listed_document_is_accepted():
    cat = parse(MINI_CATALOG + not_taken("DSP02"))
    assert cat.dmtf_not_taken_covers("DSP0236")


# ----------------------------------------------------------- AC-3, AC-4


def test_whole_catalog_run_prints_unlisted_ids_in_id_order(tmp_path, client, capsys):
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP08"))
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert lines_of(out, "unlisted") == [
        f'unlisted DSP-IS0501 1.0.0 "SDDC White Paper" '
        f"https://www.dmtf.org{FILES}/DSP-IS0501_1.0.0.pdf",
        f'unlisted DSP0282 1.1.0 "MMBI" https://www.dmtf.org{FILES}/DSP0282_1.1.0.pdf',
        f'unlisted DSP0297 1.0.0 "A New PMCI Document" '
        f"https://www.dmtf.org{FILES}/DSP0297_1.0.0.pdf",
    ]
    lines = out.splitlines()
    first = lines.index(lines_of(out, "unlisted")[0])
    assert all(
        not ln.startswith(("add ", "confirm ", "changed ")) for ln in lines[first:]
    )
    assert summary(out) == (
        "summary: add 0, confirm 0, changed 0, unreachable 0, unlisted 3 "
        "(dry run; --write adds them)"
    )


def test_listed_ids_are_never_unlisted_even_under_a_prefix(tmp_path, client, capsys):
    path = write_catalog(
        tmp_path, MINI_CATALOG + not_taken("DSP08", "DSP2", "DSP-IS", "DSP0297")
    )
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert [ln.split()[1] for ln in lines_of(out, "unlisted")] == ["DSP0282"]
    assert "DSP0236" not in " ".join(lines_of(out, "unlisted"))


def test_nothing_left_says_unlisted_0(tmp_path, client, capsys):
    path = write_catalog(
        tmp_path, MINI_CATALOG + not_taken("DSP08", "DSP-IS", "DSP0282", "DSP0297")
    )
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert lines_of(out, "unlisted") == []
    assert ", unreachable 0, unlisted 0 (dry run" in summary(out)


def test_a_catalog_without_not_taken_reports_every_other_id(tmp_path, client, capsys):
    path = write_catalog(tmp_path, MINI_CATALOG)
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert len(lines_of(out, "unlisted")) == 4
    assert "unlisted 4" in summary(out)


# ------------------------------------------------------------ AC-5, AC-6


def test_the_page_is_requested_once(tmp_path, client, capsys):
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP08"))
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert client.calls.count(L.DMTF_PUBLISHED) == 1
    assert client.calls.count(DMTF_DSP0236) == 1


def test_one_document_neither_reads_the_page_nor_reports(tmp_path, client, capsys):
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP08"))
    code, out = run(capsys, path, "refresh", "DSP0236")
    assert code == 0, out
    assert lines_of(out, "unlisted") == []
    assert "unlisted" not in summary(out)
    assert L.DMTF_PUBLISHED not in client.calls


def test_skip_source_dmtf_neither_reads_the_page_nor_reports(tmp_path, client, capsys):
    path = write_catalog(tmp_path, MINI_CATALOG + NVME_DOC + not_taken("DSP08"))
    code, out = run(capsys, path, "refresh", "--skip-source", "dmtf")
    assert code == 0, out
    assert "unlisted" not in out
    assert L.DMTF_PUBLISHED not in client.calls
    assert NVME_API in client.calls


def test_a_catalog_with_no_dmtf_document_does_not_read_the_page(
    tmp_path, client, capsys
):
    text = MINI_CATALOG.replace('publisher = "DMTF"', 'publisher = "other"')
    path = write_catalog(tmp_path, text)
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert "unlisted" not in out
    assert L.DMTF_PUBLISHED not in client.calls


# ------------------------------------------------------------------ AC-7


@pytest.mark.parametrize(
    "answer",
    [OSError("connection reset"), ok(b"", "text/html")],
    ids=["no-route", "no-rows"],
)
def test_an_unreadable_page_is_one_unreachable(tmp_path, client, capsys, answer):
    client.responses[L.DMTF_PUBLISHED] = answer
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP08"))
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    (line,) = lines_of(out, "unreachable")
    assert line.startswith("unreachable unlisted: ")
    assert L.DMTF_PUBLISHED in line
    assert lines_of(out, "unlisted") == []
    assert summary(out).startswith(
        "summary: add 0, confirm 0, changed 0, unreachable 1, unlisted 0 "
    )


def test_an_http_error_page_is_one_unreachable(tmp_path, client, capsys):
    from bmc_toolkit.spec import fetch as fetch_mod

    client.responses[L.DMTF_PUBLISHED] = fetch_mod.Response(503, {}, b"")
    path = write_catalog(tmp_path, MINI_CATALOG)
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert lines_of(out, "unreachable") == [
        f"unreachable unlisted: {L.DMTF_PUBLISHED}: HTTP 503"
    ]


# ------------------------------------------------------------------ AC-8


def test_write_leaves_unlisted_ids_out_of_the_catalog(tmp_path, client, capsys):
    text = MINI_CATALOG + not_taken("DSP08")
    path = write_catalog(tmp_path, text)
    code, out = run(capsys, path, "refresh", "--write")
    assert code == 0, out
    assert len(lines_of(out, "unlisted")) == 3
    assert summary(out).endswith(", unlisted 3, written 0")
    assert path.read_text(encoding="utf-8") == text


# ------------------------------------------------------------------ AC-9


def test_check_prints_no_unlisted_line(tmp_path, client, capsys):
    path = write_catalog(tmp_path, MINI_CATALOG)
    code, out = run(capsys, path, "check")
    assert code == 0, out
    assert "unlisted" not in out
    assert re.search(r"^summary: current \d+, newer \d+, unreachable \d+", out, re.M)


# ----------------------------------------------------------------- AC-10


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ("add 0, confirm 0, changed 0, unreachable 0, unlisted 0", "0"),
        ("add 0, confirm 0, changed 0, unreachable 3, unlisted 0", "0"),
        ("add 0, confirm 0, changed 0, unreachable 0, unlisted 2", "2"),
        ("add 1, confirm 0, changed 2, unreachable 4, unlisted 3", "6"),
        ("add 1, confirm 0, changed 0, unreachable 0", "1"),  # refresh DOC
    ],
)
def test_the_workflow_counts_unlisted_with_the_proposals(tmp_path, counts, expected):
    output = (
        "unreachable unlisted: https://www.dmtf.org/x: HTTP 503\n"
        'unlisted DSP0297 1.0.0 "New" https://www.dmtf.org/y\n'
        f"summary: {counts}{TAIL}\n"
    )
    proc, _summary, proposals = _run_refresh_block(tmp_path, output)
    assert proc.returncode == 0, proc.stderr
    assert proposals == expected


def test_the_issue_text_says_what_to_do_with_an_unlisted_id():
    text = " ".join(WORKFLOW.read_text("utf-8").split())
    assert "An `unlisted` DMTF document goes into the catalog," in text
    assert "or its id into `[listings.dmtf] not_taken` when it is left out." in text


# ----------------------------------------------------------------- AC-11


def test_the_shipped_catalog_carries_the_reviewed_list():
    # properties, not a count: taking a candidate or adding a new id
    # changes the list without changing behaviour
    cat = C.load_catalog()
    assert cat.dmtf_not_taken
    assert all(entry.startswith("DSP") for entry in cat.dmtf_not_taken)
    listed = cat.dmtf_listed()
    assert "DSP0251" in listed and "DSP0236" in listed
    assert not set(cat.dmtf_not_taken) & set(listed)
    # the ranges with nothing BMC-related, and candidates not taken yet
    for dsp in ("DSP0801", "DSP1001", "DSP4015", "DSP5001", "DSP-IS0501"):
        assert cat.dmtf_not_taken_covers(dsp), dsp
    for dsp in ("DSP0285", "DSP0294", "DSP2015", "DSP2090"):
        assert cat.dmtf_not_taken_covers(dsp), dsp
    # taken since (T61): listed, so no longer in the list
    for dsp in ("DSP0282", "DSP0288", "DSP0293", "DSP2058"):
        assert dsp in listed and not cat.dmtf_not_taken_covers(dsp), dsp


# a document whose page lists a version the catalog lacks, followed by the
# table: the block refresh --write adds must stay above the table
TABLE_LAST = """schema_version = 1

[families.mctp]
title = "MCTP"
publisher = "DMTF"

[[documents]]
id = "DSP0236"
family = "mctp"
title = "MCTP Base Specification"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.3.2"
url = "https://example.test/DSP0236_1.3.2.pdf"
type = "pdf"
published = "2024-01-02"

# reviewed, not taken
[listings.dmtf]
not_taken = ["DSP08", "DSP-IS", "DSP0282", "DSP0297"]
"""


def test_write_keeps_a_new_version_above_a_table_after_the_document(
    tmp_path, client, capsys
):
    path = write_catalog(tmp_path, TABLE_LAST)
    code, out = run(capsys, path, "refresh", "--write")
    assert code == 0, out
    assert "wrote 1 version(s) of DSP0236" in out
    text = path.read_text(encoding="utf-8")
    added = text.index('version = "1.3.3"')
    assert added < text.index("# reviewed, not taken")
    assert text.endswith(
        '# reviewed, not taken\n[listings.dmtf]\nnot_taken = ["DSP08", "DSP-IS", '
        '"DSP0282", "DSP0297"]\n'
    )
    cat = C.load_catalog(path)
    assert cat.get("DSP0236").find_version("1.3.3") is not None
    assert cat.dmtf_not_taken == ("DSP08", "DSP-IS", "DSP0282", "DSP0297")


# ----------------------------------------------------------------- AC-12


def flat(path: Path) -> str:
    return " ".join(path.read_text("utf-8").split())


def test_the_docs_describe_not_taken_and_the_unlisted_line():
    schema = " ".join(C.__doc__.split())
    assert '[listings.dmtf] optional not_taken = ["DSP08"] DMTF documents' in schema
    # the document key of the same name is another thing (review F2)
    assert "unrelated to a document's `unlisted = true`" in schema
    assert "unrelated to a document's `unlisted = true`" in flat(
        ROOT / "docs" / "CATALOG.md"
    )
    catalog_md = flat(ROOT / "docs" / "CATALOG.md")
    assert '`unlisted DSP0297 1.0.0 "Title" URL`' in catalog_md
    assert "`[listings.dmtf] not_taken`" in catalog_md
    assert "or an `unlisted` DMTF document, it opens an issue" in catalog_md
    commands = flat(ROOT / "docs" / "COMMANDS.md")
    assert '`unlisted DSP0297 1.0.0 "Title" URL`' in commands
    assert "`unreachable unlisted: <reason>`" in commands
    row = next(
        ln
        for ln in (ROOT / "skills" / "bmc-spec" / "SKILL.md")
        .read_text("utf-8")
        .splitlines()
        if ln.startswith("| `refresh ")
    )
    assert '`unlisted DSP.. V "Title" URL`' in row
    assert "`[listings.dmtf] not_taken`" in row
