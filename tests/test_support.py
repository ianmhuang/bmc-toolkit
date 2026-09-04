"""M8a: version-level access, manual entries without versions, Known Limits,
the gated-version paths of fetch, check's manual line, and the Support
Level table with its Golden Questions parser."""

import tomllib

import pytest

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import CatalogError, load_catalog, parse_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG, PDF_BYTES, ok

PMB_OPEN_URL = "https://example.test/pmb-1.0.pdf"

EXTRA = f"""
[[documents]]
id = "PMB"
family = "mctp"
title = "A bus specification whose newest revisions are gated"
access = "open"
fetch = "direct"
limits = "Tables are images: page and render, not table."

[[documents.versions]]
version = "1.0"
url = "{PMB_OPEN_URL}"
type = "pdf"
published = "2015-03-13"

[[documents.versions]]
version = "Rev 1.1"
url = ""
type = "pdf"
published = "2021-06-01"
access = "gated"
notes = "Sent on request."

[[documents]]
id = "JEDEC-X"
family = "vendor"
title = "A gated standard registered without versions"
access = "gated"
fetch = "manual"

[[documents]]
id = "CLOSED"
family = "vendor"
title = "A document with only gated versions"
access = "gated"
fetch = "direct"

[[documents.versions]]
version = "2.0"
url = ""
type = "pdf"
published = "2020-01-01"
"""


def _parse(text: str):
    return parse_catalog(tomllib.loads(text))


@pytest.fixture
def extended_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(MINI_CATALOG + EXTRA, encoding="utf-8", newline="")
    return path


@pytest.fixture
def extended(extended_file):
    return load_catalog(extended_file)


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ------------------------------------------------------------------ schema


def test_version_access_inherits_the_document_and_can_override(extended):
    pmb = extended.get("PMB")
    assert [(v.version, v.access, v.open) for v in pmb.versions] == [
        ("1.0", "open", True),
        ("Rev 1.1", "gated", False),
    ]
    assert extended.get("DSP0236").versions[0].access == "open"
    # the document keeps its own tier; latest is the gated one
    assert pmb.access == "open"
    assert pmb.latest().version == "Rev 1.1"
    assert pmb.newest_open().version == "1.0"
    assert extended.get("CLOSED").newest_open() is None
    assert extended.get("JEDEC-X").newest_open() is None


def test_unknown_version_access_is_named():
    bad = MINI_CATALOG.replace(
        'published = "2024-03-25"', 'published = "2024-03-25"\naccess = "paywall"'
    )
    with pytest.raises(CatalogError, match=r"documents\[0\]\.versions\[1\]\.access"):
        _parse(bad)


def test_open_version_of_a_direct_document_needs_a_url():
    bad = MINI_CATALOG.replace(
        'url = "https://example.test/DSP0236_1.3.3.pdf"', 'url = ""'
    )
    with pytest.raises(CatalogError, match=r"versions\[1\]\.url: required for an open"):
        _parse(bad)
    # the same version without a URL is fine once it is gated
    ok_text = MINI_CATALOG.replace(
        'url = "https://example.test/DSP0236_1.3.3.pdf"', 'url = ""\naccess = "gated"'
    )
    doc = _parse(ok_text).get("DSP0236")
    assert doc.find_version("1.3.3").access == "gated"
    assert doc.latest().version == "1.3.3"
    assert doc.newest_open().version == "1.3.2"


def test_manual_document_may_list_no_versions_but_direct_may_not(extended):
    doc = extended.get("JEDEC-X")
    assert doc.versions == ()
    assert doc.latest() is None
    manual_head = 'id = "JEDEC-X"\nfamily = "vendor"\n'
    manual_tail = '\naccess = "gated"\nfetch = "manual"'
    assert manual_head in EXTRA and manual_tail in EXTRA
    bad = MINI_CATALOG + EXTRA.replace(
        manual_tail, manual_tail.replace("manual", "direct"), 1
    )
    with pytest.raises(CatalogError, match=r"documents\[5\].*versions"):
        _parse(bad)
    bad_empty = bad.replace(
        'fetch = "direct"\n\n[[documents]]\nid = "CLOSED"',
        'fetch = "direct"\nversions = []\n\n[[documents]]\nid = "CLOSED"',
    )
    with pytest.raises(CatalogError, match=r"versions: must list at least one"):
        _parse(bad_empty)


def test_limits_is_optional_and_kept(extended):
    assert extended.get("PMB").limits.startswith("Tables are images")
    assert extended.get("DSP0236").limits == ""


# --------------------------------------------------------------------- CLI


def test_catalog_document_prints_access_per_version_and_limits(extended_file, capsys):
    code, out, _ = run(capsys, "catalog", "PMB", catalog_file=extended_file)
    assert code == 0
    assert "access: open" in out
    assert "limits: Tables are images: page and render, not table." in out
    rows = [ln.split("\t") for ln in out.splitlines() if ln.startswith("\t")]
    assert [(r[1], r[5], r[6]) for r in rows] == [
        ("Rev 1.1", "-", "gated"),
        ("1.0", PMB_OPEN_URL, "open"),
    ]


def test_catalog_manual_document_without_versions_says_how_to_add(
    extended_file, capsys
):
    code, out, _ = run(capsys, "catalog", "jedec-x", catalog_file=extended_file)
    assert code == 0
    assert "latest: -" in out
    assert (
        "versions: (none listed; add any version with: bmcspec add FILE "
        "--document JEDEC-X --version V)" in out
    )
    assert "limits:" not in out


def test_fetch_of_a_gated_latest_names_the_newest_open_version(
    extended_file, library, scripted, capsys
):
    code, out, _ = run(capsys, "fetch", "PMB", catalog_file=extended_file)
    assert code == 2
    assert scripted.calls == []
    assert out.splitlines()[0] == (
        "PMB Rev 1.1 is gated: the tool does not download it."
    )
    assert "Obtain 'A bus specification whose newest revisions are gated'" in out
    assert "Then run: bmcspec scan" in out
    assert "newest open version: 1.0; fetch it with --version 1.0" in out
    assert not library.root.exists()


def test_fetch_of_a_gated_requested_version_and_of_a_closed_document(
    extended_file, library, scripted, capsys
):
    code, out, _ = run(
        capsys, "fetch", "PMB", "--version", "Rev 1.1", catalog_file=extended_file
    )
    assert code == 2 and "newest open version: 1.0" in out
    code, out, _ = run(capsys, "fetch", "CLOSED", catalog_file=extended_file)
    assert code == 2
    assert "CLOSED 2.0 is gated" in out
    assert "no open version is listed" in out
    assert scripted.calls == []


def test_fetch_all_takes_the_newest_open_version_and_says_so_once(
    extended_file, library, scripted, capsys
):
    scripted.responses[PMB_OPEN_URL] = ok(PDF_BYTES)
    code, out, _ = run(capsys, "fetch", "--all", catalog_file=extended_file)
    lines = out.splitlines()
    notes = [ln for ln in lines if ln.startswith("note: PMB")]
    assert notes == ["note: PMB latest Rev 1.1 is gated; fetching 1.0 instead"]
    assert (
        "note: CLOSED latest 2.0 is gated; no open version is listed, nothing fetched"
        in lines
    )
    assert "fetched PMB 1.0 via direct" in lines
    assert PMB_OPEN_URL in scripted.calls
    assert not any(
        "JEDEC-X" in ln or "CLOSED 2.0" in ln
        for ln in lines
        if ln.startswith(("fetched", "failed", "skipped"))
    )
    assert library.find("PMB", "1.0") is not None
    assert code == 2  # the example.test URLs of the mini catalog are unreachable


def test_add_accepts_any_version_of_a_manual_document(
    extended_file, library, tmp_path, capsys
):
    src = tmp_path / "jesd.pdf"
    src.write_bytes(PDF_BYTES)
    code, out, _ = run(
        capsys,
        "add",
        str(src),
        "--document",
        "JEDEC-X",
        "--version",
        "1.2 (2024)",
        catalog_file=extended_file,
    )
    assert code == 0 and "added JEDEC-X 1.2 (2024) as Drop-in" in out
    code, out, _ = run(capsys, "status", catalog_file=extended_file)
    assert code == 0
    row = [ln for ln in out.splitlines() if "\tJEDEC-X\t" in ln]
    assert len(row) == 1 and row[0].split("\t")[2:4] == ["1.2 (2024)", "dropin"]


def test_fetch_of_a_gated_version_the_user_added_is_skipped_not_refused(
    extended_file, library, scripted, tmp_path, capsys
):
    src = tmp_path / "pmb-1.1.pdf"
    src.write_bytes(PDF_BYTES)
    code, out, _ = run(
        capsys,
        "add",
        str(src),
        "--document",
        "PMB",
        "--version",
        "Rev 1.1",
        catalog_file=extended_file,
    )
    assert code == 0
    for argv in (["fetch", "PMB"], ["fetch", "PMB", "--version", "Rev 1.1"]):
        code, out, _ = run(capsys, *argv, catalog_file=extended_file)
        assert code == 0, out
        assert "skipped PMB Rev 1.1: already in Library" in out
        assert "newest open version" not in out
    scripted.responses[PMB_OPEN_URL] = ok(PDF_BYTES)
    code, out, _ = run(capsys, "fetch", "--all", catalog_file=extended_file)
    lines = out.splitlines()
    assert "skipped PMB Rev 1.1: already in Library" in lines
    assert not any(ln.startswith("note: PMB") for ln in lines)
    assert PMB_OPEN_URL not in scripted.calls
    # --force asks for a download, which a gated version cannot have
    calls_before = list(scripted.calls)
    code, out, _ = run(capsys, "fetch", "PMB", "--force", catalog_file=extended_file)
    assert code == 2 and "PMB Rev 1.1 is gated" in out
    assert scripted.calls == calls_before
    # --all --force re-downloads the open versions and leaves the Drop-in alone
    code, out, _ = run(capsys, "fetch", "--all", "--force", catalog_file=extended_file)
    lines = out.splitlines()
    assert "note: PMB latest Rev 1.1 is gated; fetching 1.0 instead" in lines
    assert "fetched PMB 1.0 via direct" in lines
    assert not any("PMB Rev 1.1" in ln for ln in lines)
    assert scripted.calls.count(PMB_OPEN_URL) == 1  # the earlier --all skipped it
    assert library.find("PMB", "Rev 1.1").dropin


def test_fetch_of_a_manual_document_without_versions_points_at_add(
    extended_file, library, scripted, capsys
):
    for argv in (["fetch", "JEDEC-X"], ["fetch", "JEDEC-X", "--version", "1.2"]):
        code, out, _ = run(capsys, *argv, catalog_file=extended_file)
        assert code == 2
        assert out.strip() == (
            "JEDEC-X is gated and lists no versions: the tool does not download "
            "it. Register the file you obtained with: bmcspec add FILE "
            "--document JEDEC-X --version V"
        )
    assert scripted.calls == []
    assert not library.root.exists()


def test_fetch_of_a_manual_document_with_a_version_names_its_tier(
    extended_file, library, scripted, capsys
):
    code, out, _ = run(capsys, "fetch", "SECRET", catalog_file=extended_file)
    assert code == 2
    lines = out.splitlines()
    assert lines[0] == "SECRET 0.9 is confidential: the tool does not download it."
    assert "example.test/secret.pdf" not in out  # confidential: no URL shown
    assert "Then run: bmcspec scan" in out
    assert lines[-1] == "no open version is listed"
    assert scripted.calls == []


def test_check_counts_a_manual_document_with_a_listing_once(
    extended_file, library, scripted, capsys
):
    text = extended_file.read_text(encoding="utf-8")
    text += (
        '\n[[documents]]\nid = "DSP9999"\nfamily = "mctp"\ntitle = "A manual DMTF '
        'document with a listing"\naccess = "member"\nfetch = "manual"\n'
    )
    extended_file.write_text(text, encoding="utf-8", newline="")
    code, out, _ = run(capsys, "check", catalog_file=extended_file)
    assert code == 0
    lines = out.splitlines()
    assert any(ln.startswith("unreachable DSP9999: ") for ln in lines)
    manual = [ln for ln in lines if ln.startswith("unchecked (manual): ")]
    assert len(manual) == 1 and "DSP9999" not in manual[0]
    # DSP0236 (listed, no scripted DMTF page) and DSP9999 are the unreachable two
    assert lines[-1].endswith("unreachable 2, unchecked 6")


def test_table_reports_a_golden_file_in_another_encoding(
    extended_file, tmp_path, capsys
):
    golden = tmp_path / "golden.md"
    rows = "| # | Question | Document |\n|---|---|---|\n| G1 | é | DSP0236 1.3.3 |\n"
    golden.write_bytes(rows.encode("cp1252"))
    code, out, _ = run(
        capsys,
        "catalog",
        "--table",
        "--golden",
        str(golden),
        catalog_file=extended_file,
    )
    assert code == 1 and out.startswith(f"cannot read {golden}")


def test_check_lists_manual_documents_with_their_tier(
    extended_file, library, scripted, capsys
):
    code, out, _ = run(capsys, "check", catalog_file=extended_file)
    assert code == 0
    lines = out.splitlines()
    assert "unchecked: IPMI, BUNDLE, PMB, CLOSED (no publisher listing)" in lines
    assert (
        "unchecked (manual): SECRET (confidential), JEDEC-X (gated) "
        "(never fetched by the tool)"
    ) in lines
    assert lines[-1].endswith("unchecked 6")


# ------------------------------------------------------------------- table

GOLDEN = """# Golden Questions

| # | Question | Document | Where | Commands |
|---|---|---|---|---|
| G1 | header layout | DSP0236 1.3.3 | section 8 | `page DSP0236 24` |
| G2 | two documents | IPMI 2.0 rev 1.1; PMB 1.0 | pages 1-2 | `find IPMI x` |
| G3 | again the base | DSP0236 1.3.3 | section 9 | `find DSP0236 y` |
| G4 | code only | - | bmcweb | `grep bmcweb z` |
| G5 | a typo | NOPE 1.0 | nowhere | `find NOPE q` |

A table without the column is ignored:

| Table | Command | Expected |
|---|---|---|
| G9 | `table IPMI --page 68` | one Logical Table |
"""


def test_read_golden_collects_question_ids_per_document(extended, tmp_path):
    path = tmp_path / "golden.md"
    path.write_text(GOLDEN, encoding="utf-8", newline="")
    verified, problems = support.read_golden(path, extended)
    assert verified == {
        "dsp0236": ["G1", "G3"],
        "ipmi": ["G2"],
        "pmb": ["G2"],
    }
    assert problems == ["G5: unknown document 'NOPE'"]


def test_table_columns_access_label_fetch_label_and_verified(
    extended_file, tmp_path, capsys
):
    golden = tmp_path / "golden.md"
    golden.write_text(GOLDEN, encoding="utf-8", newline="")
    code, out, err = run(
        capsys,
        "catalog",
        "--table",
        "--golden",
        str(golden),
        catalog_file=extended_file,
    )
    assert code == 0
    assert "G5: unknown document 'NOPE'" in err
    lines = out.splitlines()
    assert (
        lines[0]
        == "| Family | Document | Access | Latest | Fetch | Verified | Known limit |"
    )
    assert lines[1] == "|---|---|---|---|---|---|---|"
    rows = {ln.split(" | ")[1].split("`")[1]: ln.split(" | ") for ln in lines[2:]}
    assert list(rows) == [
        "DSP0236",
        "IPMI",
        "BUNDLE",
        "SECRET",
        "PMB",
        "JEDEC-X",
        "CLOSED",
    ]
    assert rows["DSP0236"][2:] == ["open", "1.3.3", "direct", "G1, G3", "- |"]
    assert rows["PMB"][2:] == [
        "open (latest gated)",
        "Rev 1.1",
        "direct",
        "G2",
        "Tables are images: page and render, not table. |",
    ]
    assert rows["SECRET"][2:] == ["confidential", "0.9", "manual (Drop-in)", "-", "- |"]
    assert rows["JEDEC-X"][2:] == ["gated", "-", "manual (Drop-in)", "-", "- |"]
    assert rows["IPMI"][0] == "| IPMI"  # the family title


def test_table_without_golden_marks_nothing_verified(extended_file, capsys):
    code, out, err = run(capsys, "catalog", "--table", catalog_file=extended_file)
    assert code == 0 and err == ""
    for ln in out.splitlines()[2:]:
        assert ln.split(" | ")[5] == "-"


def test_table_flags_are_checked(extended_file, tmp_path, capsys):
    code, out, _ = run(capsys, "catalog", "--table", "PMB", catalog_file=extended_file)
    assert code == 2 and "drop the document id or --family" in out
    code, out, _ = run(
        capsys, "catalog", "--table", "--family", "mctp", catalog_file=extended_file
    )
    assert code == 2
    code, out, _ = run(
        capsys,
        "catalog",
        "--golden",
        str(tmp_path / "g.md"),
        catalog_file=extended_file,
    )
    assert code == 2 and "--golden goes with --table" in out
    code, out, _ = run(
        capsys,
        "catalog",
        "--table",
        "--golden",
        str(tmp_path / "missing.md"),
        catalog_file=extended_file,
    )
    assert code == 1 and "cannot read" in out


def test_shipped_golden_questions_verify_sixteen_documents():
    from pathlib import Path

    from bmc_toolkit.spec.catalog import load_catalog as load_shipped

    root = Path(__file__).resolve().parents[1]
    catalog = load_shipped()
    verified, problems = support.read_golden(
        root / "docs" / "golden-questions.md", catalog
    )
    assert problems == []
    assert len(verified) == 16
    assert verified["ipmi"] == ["G1", "G2", "G3", "G4", "G5"]
    assert verified["dsp0248"] == ["G13", "G15"]
