"""Acceptance tests for the ``unlisted`` report of ``refresh``: a DSP id on
DMTF's published-documents page that no catalog document lists and
``[listings.dmtf] not_taken`` does not cover is printed and never written
(feature/dmtf-unlisted, AC-1 to AC-11). Black-box through ``cli.main`` with
a scripted HTTP client; the shipped catalog is loaded, not fetched."""

import tomllib
from pathlib import Path

import pytest

from bmc_toolkit.spec import catalog as catalog_mod
from bmc_toolkit.spec import cli
from bmc_toolkit.spec import fetch as fetch_mod
from bmc_toolkit.spec import listing as listing_mod
from tests.conftest import MINI_CATALOG, ScriptedClient, ok
from tests.test_catalog_workflow import TAIL, _run_refresh_block

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "bmc_toolkit" / "spec" / "catalog.toml"

PUBLISHED = listing_mod.DMTF_PUBLISHED
DSP0236_PAGE = listing_mod.DMTF_DSP.format(key="DSP0236")
FILES = "https://www.dmtf.org/sites/default/files/standards/documents"


# ------------------------------------------------------------- fixtures


def published_row(dsp: str, version: str, title: str) -> str:
    return (
        f"<tr><td>{dsp}</td><td>{version}</td>"
        f'<td><a href="{FILES}/{dsp}_{version}.pdf">{title}</a></td>'
        f'<td>Standard</td><td><a href="/dsp/{dsp}">Versions</a></td></tr>'
    )


def published_page(*rows: str) -> bytes:
    return (
        "<html><body><table><thead><tr><th>DSP #</th><th>Version</th>"
        "<th>Title</th><th>Comments</th><th>Versions</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table></body></html>"
    ).encode()


def dsp_row(version: str, date: str) -> str:
    # the same file URLs the mini catalog carries, so nothing is "changed"
    return (
        f'<tr><td>{version}</td><td><a href="https://example.test/DSP0236_{version}.pdf">'
        f"MCTP Base</a></td><td>{date}</td><td>Standard</td></tr>"
    )


def dsp_page(*rows: str) -> bytes:
    return (
        "<html><body><table><thead><tr><th>Version</th><th>Title</th>"
        "<th>Publication Date</th><th>Comments</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>"
    ).encode()


# The mini catalog lists DSP0236 (versions 1.3.2, 1.3.3 and a WIP 1.4.0).
PAGE = published_page(
    published_row("DSP0236", "1.3.3", "MCTP Base"),
    published_row("DSP0237", "1.2.0", "MCTP SMBus Binding"),
    published_row("DSP0297", "1.0.0", "A New PMCI Document"),
    published_row("DSP0801", "1.0.0", "A CLP Mapping"),
    published_row("DSP8010", "2026.1", "Redfish Schema Bundle"),
)

# The per-DSP page agrees with the catalog: nothing to add.
DSP0236_CURRENT = dsp_page(
    dsp_row("1.3.3", "25 Mar 2024"), dsp_row("1.3.2", "2 Jan 2024")
)

# The per-DSP page lists 1.3.4, which the catalog lacks: one ``add``.
DSP0236_NEWER = dsp_page(
    dsp_row("1.3.4", "1 Sep 2026"),
    dsp_row("1.3.3", "25 Mar 2024"),
    dsp_row("1.3.2", "2 Jan 2024"),
)


def not_taken(*entries: str) -> str:
    items = ", ".join(f'"{e}"' for e in entries)
    return f"\n[listings.dmtf]\nnot_taken = [{items}]\n"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "lib"))
    scripted = ScriptedClient(
        {
            PUBLISHED: ok(PAGE, "text/html"),
            DSP0236_PAGE: ok(DSP0236_CURRENT, "text/html"),
        }
    )
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: scripted)
    return scripted


def write_catalog(tmp_path, text: str) -> Path:
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def run(capsys, catalog_path, *argv):
    code = cli.main(["--catalog", str(catalog_path), *argv])
    return code, capsys.readouterr().out


def lines_starting(out: str, prefix: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith(prefix)]


def summary_line(out: str) -> str:
    (line,) = lines_starting(out, "summary:")
    return line


def parse(text: str) -> catalog_mod.Catalog:
    return catalog_mod.parse_catalog(tomllib.loads(text))


# ------------------------------------------------------------------ AC-1


def test_ac1_not_taken_entries_are_case_insensitive_prefixes():
    cat = parse(MINI_CATALOG + not_taken("dsp08", "DSP0004", "DSP-IS"))
    # a prefix covers every id starting with it, a full id that id only
    assert cat.dmtf_not_taken_covers("DSP0800")
    assert cat.dmtf_not_taken_covers("DSP0899")
    assert cat.dmtf_not_taken_covers("dsp0850")
    assert cat.dmtf_not_taken_covers("DSP0004")
    assert cat.dmtf_not_taken_covers("DSP-IS0501")
    assert not cat.dmtf_not_taken_covers("DSP0005")
    assert not cat.dmtf_not_taken_covers("DSP0900")
    assert not cat.dmtf_not_taken_covers("DSP1004")


def test_ac1_the_table_and_the_key_are_optional():
    plain = parse(MINI_CATALOG)
    assert not plain.dmtf_not_taken_covers("DSP0801")
    assert plain.get("DSP0236") is not None and len(plain.documents) == 4
    empty_table = parse(MINI_CATALOG + "\n[listings.dmtf]\n")
    assert not empty_table.dmtf_not_taken_covers("DSP0801")
    empty_list = parse(MINI_CATALOG + not_taken())
    assert not empty_list.dmtf_not_taken_covers("DSP0801")


def test_ac1_a_prefix_that_also_covers_a_listed_document_is_accepted():
    # DSP02 covers DSP0236, which the catalog lists: a prefix is not an id
    cat = parse(MINI_CATALOG + not_taken("DSP02"))
    assert cat.dmtf_not_taken_covers("DSP0297")


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize(
    ("extra", "where"),
    [
        ('\n[listings.dmtf]\nnot_taken = "DSP08"\n', "listings.dmtf.not_taken"),
        ("\n[listings.dmtf]\nnot_taken = [1, 2]\n", r"listings\.dmtf\.not_taken\[0\]"),
        (not_taken("DSP08", "MCTP"), r"listings\.dmtf\.not_taken\[1\]"),
        (not_taken("DSP08", "0236"), r"listings\.dmtf\.not_taken\[1\]"),
        (not_taken("DSP08", "DSP08"), r"listings\.dmtf\.not_taken\[1\]"),
        (not_taken("DSP08", "dsp08"), r"listings\.dmtf\.not_taken\[1\]"),
        (not_taken("DSP0236"), r"listings\.dmtf\.not_taken\[0\]"),
        (not_taken("DSP08", "dsp0236"), r"listings\.dmtf\.not_taken\[1\]"),
        ("\n[listings.nvme]\nnot_taken = []\n", "listings.nvme"),
        ("\n[listings.dmtf]\ntaken = []\n", "listings.dmtf.taken"),
        ("\n[listings]\ndmtf = []\n", "listings.dmtf"),
    ],
    ids=[
        "not-a-list",
        "not-strings",
        "no-dsp-prefix",
        "digits-only",
        "duplicate",
        "duplicate-case",
        "taken",
        "taken-lower",
        "other-publisher",
        "other-key",
        "dmtf-not-a-table",
    ],
)
def test_ac2_a_bad_not_taken_is_refused_naming_the_place(extra, where):
    with pytest.raises(catalog_mod.CatalogError, match=where):
        parse(MINI_CATALOG + extra)


def test_ac2_a_taken_entry_names_the_document_that_takes_it():
    with pytest.raises(catalog_mod.CatalogError, match="DSP0236"):
        parse(MINI_CATALOG + not_taken("dsp0236"))


def test_ac2_load_catalog_reports_the_refusal_as_a_catalog_error(tmp_path):
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP0236"))
    with pytest.raises(catalog_mod.CatalogError, match=r"not_taken\[0\]"):
        catalog_mod.load_catalog(path)


# ------------------------------------------------------------- AC-3, AC-4


def test_ac3_whole_catalog_refresh_prints_the_undecided_ids_in_id_order(
    tmp_path, client, capsys
):
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP08"))
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    # DSP0236 is listed, DSP0801 is covered; the other three remain, sorted
    assert lines_starting(out, "unlisted ") == [
        f'unlisted DSP0237 1.2.0 "MCTP SMBus Binding" {FILES}/DSP0237_1.2.0.pdf',
        f'unlisted DSP0297 1.0.0 "A New PMCI Document" {FILES}/DSP0297_1.0.0.pdf',
        f'unlisted DSP8010 2026.1 "Redfish Schema Bundle" {FILES}/DSP8010_2026.1.pdf',
    ]
    assert summary_line(out) == (
        "summary: add 0, confirm 0, changed 0, unreachable 0, unlisted 3 "
        "(dry run; --write adds them)"
    )


def test_ac3_unlisted_lines_come_after_the_per_document_lines(
    tmp_path, client, capsys
):
    client.responses[DSP0236_PAGE] = ok(DSP0236_NEWER, "text/html")
    path = write_catalog(tmp_path, MINI_CATALOG)
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    lines = out.splitlines()
    adds = [i for i, ln in enumerate(lines) if ln.startswith("add DSP0236 1.3.4 ")]
    unlisted = [i for i, ln in enumerate(lines) if ln.startswith("unlisted ")]
    assert len(adds) == 1 and len(unlisted) == 4, out
    assert max(adds) < min(unlisted)
    assert lines[-1].startswith("summary:")
    assert ", unreachable 0, unlisted 4 (dry run" in lines[-1]


def test_ac3_a_listed_id_is_never_reported_even_under_a_covering_prefix(
    tmp_path, client, capsys
):
    # DSP023 covers both DSP0236 (listed) and DSP0237 (not listed)
    path = write_catalog(
        tmp_path, MINI_CATALOG + not_taken("DSP023", "DSP0297", "DSP08", "DSP8010")
    )
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert lines_starting(out, "unlisted ") == []
    assert "DSP0236" not in " ".join(lines_starting(out, "unlisted "))
    assert ", unlisted 0 (dry run" in summary_line(out)


def test_ac3_a_full_id_entry_covers_that_id_only(tmp_path, client, capsys):
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP0297", "DSP0801"))
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    reported = [ln.split()[1] for ln in lines_starting(out, "unlisted ")]
    assert reported == ["DSP0237", "DSP8010"]
    assert ", unlisted 2 (dry run" in summary_line(out)


def test_ac4_a_run_reporting_none_says_unlisted_0(tmp_path, client, capsys):
    path = write_catalog(
        tmp_path, MINI_CATALOG + not_taken("DSP0237", "DSP0297", "DSP0801", "DSP8")
    )
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert "unlisted" not in "\n".join(
        ln for ln in out.splitlines() if not ln.startswith("summary:")
    )
    assert summary_line(out) == (
        "summary: add 0, confirm 0, changed 0, unreachable 0, unlisted 0 "
        "(dry run; --write adds them)"
    )


def test_ac4_unlisted_sits_before_the_written_tail(tmp_path, client, capsys):
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP08"))
    code, out = run(capsys, path, "refresh", "--write")
    assert code == 0, out
    assert summary_line(out) == (
        "summary: add 0, confirm 0, changed 0, unreachable 0, unlisted 3, written 0"
    )


# ------------------------------------------------------------- AC-5, AC-6


def test_ac5_ac6_the_page_is_read_once_for_the_whole_catalog_and_not_for_one_document(
    tmp_path, client, capsys
):
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP08"))
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert len(lines_starting(out, "unlisted ")) == 3
    assert client.calls.count(PUBLISHED) == 1
    assert client.calls.count(DSP0236_PAGE) == 1

    client.calls.clear()
    code, out = run(capsys, path, "refresh", "DSP0236")
    assert code == 0, out
    assert "unlisted" not in out
    assert PUBLISHED not in client.calls
    assert summary_line(out) == (
        "summary: add 0, confirm 0, changed 0, unreachable 0 "
        "(dry run; --write adds them)"
    )


def test_ac5_ac6_skip_source_dmtf_neither_reads_the_page_nor_reports(
    tmp_path, client, capsys
):
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP08"))
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert "unlisted 3" in summary_line(out)

    client.calls.clear()
    code, out = run(capsys, path, "refresh", "--skip-source", "dmtf")
    assert code == 0, out
    assert "unlisted" not in out
    assert PUBLISHED not in client.calls
    assert DSP0236_PAGE not in client.calls
    assert summary_line(out) == (
        "summary: add 0, confirm 0, changed 0, unreachable 0 "
        "(dry run; --write adds them)"
    )


def test_ac6_skipping_another_publisher_still_reads_the_page_once(
    tmp_path, client, capsys
):
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP08"))
    code, out = run(
        capsys, path, "refresh", "--skip-source", "ocp", "--skip-source", "nvme"
    )
    assert code == 0, out
    assert client.calls.count(PUBLISHED) == 1
    assert "unlisted 3" in summary_line(out)


# ------------------------------------------------------------------ AC-7


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (OSError("connection reset by peer"), "connection reset by peer"),
        (fetch_mod.Response(503, {}, b""), "HTTP 503"),
        (ok(b"<html><body><p>moved</p></body></html>", "text/html"), "no DSP rows"),
    ],
    ids=["os-error", "http-error", "no-rows"],
)
def test_ac7_an_unreadable_page_is_one_unreachable_and_unlisted_0(
    tmp_path, client, capsys, answer, reason
):
    client.responses[PUBLISHED] = answer
    path = write_catalog(tmp_path, MINI_CATALOG + not_taken("DSP08"))
    code, out = run(capsys, path, "refresh")
    assert code == 0, out  # the exit code is as before
    unreachable = lines_starting(out, "unreachable ")
    assert len(unreachable) == 1, out
    assert unreachable[0].startswith("unreachable unlisted: ")
    assert reason in unreachable[0]
    assert lines_starting(out, "unlisted ") == []
    assert summary_line(out) == (
        "summary: add 0, confirm 0, changed 0, unreachable 1, unlisted 0 "
        "(dry run; --write adds them)"
    )


def test_ac7_the_page_failure_is_counted_with_the_document_failures(
    tmp_path, client, capsys
):
    client.responses[PUBLISHED] = OSError("no route")
    client.responses[DSP0236_PAGE] = OSError("no route")
    path = write_catalog(tmp_path, MINI_CATALOG)
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    kinds = sorted(
        ln.split()[1].rstrip(":") for ln in lines_starting(out, "unreachable ")
    )
    assert kinds == ["DSP0236", "unlisted"]
    assert ", unreachable 2, unlisted 0 (dry run" in summary_line(out)


# ------------------------------------------------------------------ AC-8


def test_ac8_write_adds_the_listed_version_and_never_an_unlisted_id(
    tmp_path, client, capsys
):
    client.responses[DSP0236_PAGE] = ok(DSP0236_NEWER, "text/html")
    text = MINI_CATALOG + not_taken("DSP08")
    path = write_catalog(tmp_path, text)
    code, out = run(capsys, path, "refresh", "--write")
    assert code == 0, out
    assert "wrote 1 version(s) of DSP0236" in out
    assert len(lines_starting(out, "unlisted ")) == 3
    assert summary_line(out) == (
        "summary: add 1, confirm 0, changed 0, unreachable 0, unlisted 3, written 1"
    )
    after = path.read_text(encoding="utf-8")
    assert 'version = "1.3.4"' in after
    for dsp in ("DSP0237", "DSP0297", "DSP8010"):
        assert dsp not in after, dsp
    cat = catalog_mod.load_catalog(path)
    assert [d.id for d in cat.documents] == ["DSP0236", "IPMI", "BUNDLE", "SECRET"]
    assert cat.get("DSP0236").find_version("1.3.4") is not None
    assert cat.dmtf_not_taken_covers("DSP0801")


def test_ac8_write_with_nothing_to_add_leaves_the_file_byte_for_byte(
    tmp_path, client, capsys
):
    text = MINI_CATALOG + not_taken("DSP08")
    path = write_catalog(tmp_path, text)
    code, out = run(capsys, path, "refresh", "--write")
    assert code == 0, out
    assert summary_line(out).endswith(", unlisted 3, written 0")
    assert path.read_bytes() == text.encode("utf-8")


# ------------------------------------------------------------------ AC-9


def test_ac9_check_reads_the_page_for_versions_but_prints_no_unlisted_line(
    tmp_path, client, capsys
):
    path = write_catalog(tmp_path, MINI_CATALOG)
    code, out = run(capsys, path, "check")
    assert code == 0, out
    assert "unlisted" not in out
    assert lines_starting(out, "current DSP0236") or lines_starting(
        out, "newer DSP0236"
    )
    assert summary_line(out).startswith("summary: current 1, newer 0, unreachable 0")

    # and refresh, the same catalog, the same page, does report
    code, out = run(capsys, path, "refresh")
    assert code == 0, out
    assert len(lines_starting(out, "unlisted ")) == 4


# ----------------------------------------------------------------- AC-10


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ("add 0, confirm 0, changed 0, unreachable 0, unlisted 0", "0"),
        ("add 0, confirm 0, changed 0, unreachable 2, unlisted 0", "0"),
        ("add 0, confirm 0, changed 0, unreachable 0, unlisted 5", "5"),
        ("add 2, confirm 1, changed 1, unreachable 9, unlisted 3", "7"),
    ],
)
def test_ac10_the_workflow_counts_unlisted_as_a_proposal(tmp_path, counts, expected):
    output = (
        "unreachable unlisted: https://www.dmtf.org/x: HTTP 503\n"
        'unlisted DSP0297 1.0.0 "A New PMCI Document" https://www.dmtf.org/y\n'
        f"summary: {counts}{TAIL}\n"
    )
    proc, step_summary, proposals = _run_refresh_block(tmp_path, output)
    assert proc.returncode == 0, proc.stderr
    assert proposals == expected
    assert 'unlisted DSP0297 1.0.0 "A New PMCI Document"' in step_summary


def test_ac10_a_summary_without_the_field_still_counts_as_before(tmp_path):
    output = f"summary: add 1, confirm 0, changed 2, unreachable 1{TAIL}\n"
    proc, _summary, proposals = _run_refresh_block(tmp_path, output)
    assert proc.returncode == 0, proc.stderr
    assert proposals == "3"


# ----------------------------------------------------------------- AC-11


def test_ac11_the_shipped_catalog_carries_a_checked_not_taken_list():
    cat = catalog_mod.load_catalog()
    assert cat.dmtf_not_taken, "the shipped catalog names no not_taken entry"
    listed = cat.dmtf_listed()
    assert listed, "the shipped catalog lists no DMTF document"
    for entry in cat.dmtf_not_taken:
        assert entry.startswith("DSP"), entry
        assert entry not in listed, entry
    # the candidates the change names as reviewed and not taken yet
    for dsp in ("DSP0282", "DSP0285", "DSP0288", "DSP0293", "DSP2058"):
        assert cat.dmtf_not_taken_covers(dsp), dsp
        assert dsp not in listed, dsp
    # what the catalog takes is not covered as a full id
    for dsp in listed:
        assert dsp not in cat.dmtf_not_taken, dsp


def test_ac11_the_shipped_list_sits_in_no_document_block():
    """Wherever the shipped file puts the table, its entries belong to the
    table and no document carries a key named not_taken."""
    text = SHIPPED.read_text(encoding="utf-8")
    assert "[listings.dmtf]" in text
    data = tomllib.loads(text)
    assert "not_taken" in data["listings"]["dmtf"]
    for doc in data["documents"]:
        assert "not_taken" not in doc, doc["id"]


def test_ac11_the_shipped_catalog_reports_nothing_for_its_own_listed_ids(
    monkeypatch, tmp_path, capsys
):
    """A page made of the ids the shipped catalog lists and the ids it names
    as not taken reports ``unlisted 0``; one id of neither kind is reported.
    The live page is not committed, so this is the offline half of AC-11."""
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "lib"))
    cat = catalog_mod.load_catalog()
    listed = sorted(cat.dmtf_listed())
    rows = [published_row(dsp, "1.0.0", f"Title of {dsp}") for dsp in listed]
    rows.append(published_row("DSP0282", "1.1.0", "MMBI"))
    rows.append(published_row("DSP0801", "1.0.0", "A CLP Mapping"))
    rows.append(published_row("DSP9999", "1.0.0", "Not Decided"))
    scripted = ScriptedClient({PUBLISHED: ok(published_page(*rows), "text/html")})
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: scripted)
    code = cli.main(["refresh", "--skip-source", "nvme", "--skip-source", "ocp"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert [ln.split()[1] for ln in lines_starting(out, "unlisted ")] == ["DSP9999"]
    assert ", unlisted 1 (dry run" in summary_line(out)
    assert scripted.calls.count(PUBLISHED) == 1


# ------------------------------------------- AC-8 with the table after a document
# (round 1 F1: the text editor of --write must not put a new version block
# under a [listings.dmtf] header that follows the document)

HEAD = """schema_version = 1

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

[[documents.versions]]
version = "1.3.3"
url = "https://example.test/DSP0236_1.3.3.pdf"
type = "pdf"
published = "2024-03-25"
"""

TABLE = """
# reviewed and left out
# (two comment lines introduce the table)
[listings.dmtf]
not_taken = [
    "DSP08", "DSP0237", "DSP0297", "DSP8010",
]
"""

SECOND_DOCUMENT = """
[[documents]]
id = "OTHER"
family = "mctp"
title = "Another document, no listing"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "https://example.test/other.pdf"
type = "pdf"
published = "2020-01-01"
"""


def _written_block_index(text: str) -> int:
    return text.index('version = "1.3.4"')


def test_ac8_write_keeps_the_new_version_above_a_table_that_ends_the_file(
    tmp_path, client, capsys
):
    client.responses[DSP0236_PAGE] = ok(DSP0236_NEWER, "text/html")
    path = write_catalog(tmp_path, HEAD + TABLE)
    code, out = run(capsys, path, "refresh", "--write")
    assert code == 0, out
    assert "wrote 1 version(s) of DSP0236" in out
    assert summary_line(out).endswith(", unlisted 0, written 1")
    after = path.read_text(encoding="utf-8")
    # the new block comes after 1.3.3 and before the comments and the table
    assert after.index('version = "1.3.3"') < _written_block_index(after)
    assert _written_block_index(after) < after.index("# reviewed and left out")
    assert after.endswith(TABLE)
    cat = catalog_mod.load_catalog(path)
    versions = [v.version for v in cat.get("DSP0236").versions]
    assert versions == ["1.3.2", "1.3.3", "1.3.4"]
    assert cat.dmtf_not_taken_covers("DSP0801")
    assert not cat.dmtf_not_taken_covers("DSP9999")


def test_ac8_write_keeps_the_new_version_above_a_table_between_documents(
    tmp_path, client, capsys
):
    client.responses[DSP0236_PAGE] = ok(DSP0236_NEWER, "text/html")
    path = write_catalog(tmp_path, HEAD + TABLE + SECOND_DOCUMENT)
    code, out = run(capsys, path, "refresh", "--write")
    assert code == 0, out
    assert "wrote 1 version(s) of DSP0236" in out
    after = path.read_text(encoding="utf-8")
    assert after.index('version = "1.3.3"') < _written_block_index(after)
    assert _written_block_index(after) < after.index("# reviewed and left out")
    assert after.endswith(TABLE + SECOND_DOCUMENT)
    cat = catalog_mod.load_catalog(path)
    assert [d.id for d in cat.documents] == ["DSP0236", "OTHER"]
    assert cat.get("DSP0236").find_version("1.3.4") is not None
    assert [v.version for v in cat.get("OTHER").versions] == ["1.0"]


def test_ac8_write_with_nothing_to_add_leaves_a_trailing_table_untouched(
    tmp_path, client, capsys
):
    text = HEAD + TABLE
    path = write_catalog(tmp_path, text)
    code, out = run(capsys, path, "refresh", "--write")
    assert code == 0, out
    assert summary_line(out).endswith(", unlisted 0, written 0")
    assert path.read_bytes() == text.encode("utf-8")
