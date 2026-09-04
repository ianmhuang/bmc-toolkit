"""Reviewer acceptance tests for M8a, part 2: the Support Level table and
its Golden Questions parser (AC-9, AC-10), the six new document groups in
the shipped catalog (AC-11 to AC-16) and the seven Known Limits (AC-4).

The shipped catalog is exercised with a scripted HTTP client only; no test
touches the network. Dates and URLs are checked for shape and internal
consistency (the PMBus file names carry their dates); whether a URL still
serves the file is not testable here.
"""

import re
import urllib.parse
from pathlib import Path

import pytest

from bmc_toolkit.spec import fetch as fetch_mod
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG, PDF_BYTES, ok, wayback_hit

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SHIPPED = ROOT / "docs" / "golden-questions.md"

BUS_131_URL = "https://example.test/bus-1.3.1.pdf"

EXTRA = f"""
[[documents]]
id = "BUS"
family = "mctp"
title = "A bus specification whose newest revisions are gated"
access = "open"
fetch = "direct"
limits = "Tables are images."

[[documents.versions]]
version = "1.3.1"
url = "{BUS_131_URL}"
type = "pdf"
published = "2015-03-13"

[[documents.versions]]
version = "1.5"
url = ""
type = "pdf"
published = "2025-01-01"
access = "gated"

[[documents]]
id = "NDA-ONLY"
family = "vendor"
title = "A member document registered without versions"
access = "member"
fetch = "manual"

[[documents]]
id = "ALLGATED"
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

GOLDEN = """# Golden Questions

Some prose with a | pipe that is not a table.

| # | Question | Document | Where the answer is | Commands |
|---|---|---|---|---|
| G1 | first | BUS 1.3.1 | somewhere | `page BUS 1` |
| G2 | two documents | DSP0236 1.3.3; BUS 1.3.1 | elsewhere | `find DSP0236 x` |
| G3 | code only | - | bmcweb | `grep bmcweb y` |
| G4 | unknown id | NOSUCH 9.9 | nowhere | `find NOSUCH z` |
| G5 | lower-case id | dsp0236 1.3.3 | again | `page DSP0236 2` |

## Named table checks

| Table | Command | Expected |
|---|---|---|
| IPMI 2.0 Table 5-1 | `table IPMI --page 68` | one Logical Table |

| # | Question | Where the answer is |
|---|---|---|
| G6 | no Document column here | IPMI 2.0 rev 1.1 |
"""

HEADER = "| Family | Document | Access | Latest | Fetch | Verified | Known limit |"


@pytest.fixture
def cat_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(MINI_CATALOG + EXTRA, encoding="utf-8", newline="")
    return path


@pytest.fixture
def golden_file(tmp_path):
    path = tmp_path / "golden.md"
    path.write_text(GOLDEN, encoding="utf-8", newline="")
    return path


@pytest.fixture
def shipped():
    return load_catalog()


def run(capsys, *argv, catalog_file=None):
    head = ["--catalog", str(catalog_file)] if catalog_file is not None else []
    code = main([*head, *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _rows(out: str) -> dict[str, list[str]]:
    """Table rows keyed by catalog id; cells stripped, without the outer pipes."""
    rows = {}
    for ln in out.splitlines()[2:]:
        assert ln.startswith("| ") and ln.endswith(" |"), ln
        cells = [c.strip() for c in ln[2:-2].split(" | ")]
        assert len(cells) == 7, cells
        doc_id = cells[1].split("`")[1]
        rows[doc_id] = cells
    return rows


# ---------------------------------------------------------------- AC-9


def test_ac9_table_columns_rows_and_labels(cat_file, capsys):
    code, out, err = run(capsys, "catalog", "--table", catalog_file=cat_file)
    assert code == 0 and err == ""
    lines = out.splitlines()
    assert lines[0] == HEADER
    assert set(lines[1]) <= {"|", "-", ":", " "}
    rows = _rows(out)
    assert list(rows) == [
        "DSP0236",
        "IPMI",
        "BUNDLE",
        "SECRET",
        "BUS",
        "NDA-ONLY",
        "ALLGATED",
    ]
    # Family is the family's title, Document names id and title
    assert rows["DSP0236"][0] == "MCTP" and rows["SECRET"][0] == "Vendor documents"
    assert "MCTP Base Specification" in rows["DSP0236"][1]
    # Access, Latest, Fetch, Verified (no --golden), Known limit
    assert rows["DSP0236"][2:] == ["open", "1.3.3", "direct", "-", "-"]
    assert rows["BUS"][2:] == ["open (latest gated)", "1.5", "direct", "-", "Tables are images."]
    assert rows["ALLGATED"][2:] == ["gated", "2.0", "direct", "-", "-"]
    assert rows["SECRET"][2:] == ["confidential", "0.9", "manual (Drop-in)", "-", "-"]
    assert rows["NDA-ONLY"][2:] == ["member", "-", "manual (Drop-in)", "-", "-"]
    assert rows["IPMI"][4] == "wayback"


def test_ac9_table_is_rejected_with_a_document_id_or_family(cat_file, capsys):
    code, out, _ = run(capsys, "catalog", "--table", "BUS", catalog_file=cat_file)
    assert code == 2
    assert not out.startswith("| Family")
    code, out, _ = run(
        capsys, "catalog", "--table", "--family", "mctp", catalog_file=cat_file
    )
    assert code == 2
    assert not out.startswith("| Family")


# ---------------------------------------------------------------- AC-10


def test_ac10_golden_document_column_marks_verified_rows(cat_file, golden_file, capsys):
    code, out, err = run(
        capsys, "catalog", "--table", "--golden", str(golden_file), catalog_file=cat_file
    )
    assert code == 0
    rows = _rows(out)
    assert rows["BUS"][5] == "G1, G2"
    assert rows["DSP0236"][5] == "G2, G5"
    for doc_id in ("IPMI", "BUNDLE", "SECRET", "NDA-ONLY", "ALLGATED"):
        assert rows[doc_id][5] == "-", doc_id
    # the unknown id is reported on stderr and otherwise ignored
    assert "NOSUCH" in err
    assert "NOSUCH" not in out


def test_ac10_without_golden_nothing_is_verified(cat_file, capsys):
    code, out, err = run(capsys, "catalog", "--table", catalog_file=cat_file)
    assert code == 0 and err == ""
    assert all(cells[5] == "-" for cells in _rows(out).values())


def test_ac10_golden_file_in_another_encoding_is_reported_not_a_traceback(
    cat_file, tmp_path, capsys
):
    # Round 2 (F6): a file that is not UTF-8 ends in "cannot read", exit 1
    golden = tmp_path / "golden.md"
    rows = "| # | Question | Document |\n|---|---|---|\n| G1 | café | DSP0236 1.3.3 |\n"
    golden.write_bytes(rows.encode("cp1252"))
    code, out, _ = run(
        capsys, "catalog", "--table", "--golden", str(golden), catalog_file=cat_file
    )
    assert code == 1
    assert out.startswith(f"cannot read {golden}")
    assert "| Family" not in out


def test_ac10_missing_golden_file_is_an_error_not_a_traceback(cat_file, tmp_path, capsys):
    code, out, _ = run(
        capsys,
        "catalog",
        "--table",
        "--golden",
        str(tmp_path / "absent.md"),
        catalog_file=cat_file,
    )
    assert code != 0
    assert not out.startswith("| Family")


def test_ac10_shipped_golden_file_verifies_the_m8a_documents_and_more(capsys):
    assert GOLDEN_SHIPPED.is_file()
    code, out, err = run(capsys, "catalog", "--table", "--golden", str(GOLDEN_SHIPPED))
    assert code == 0, out
    assert err == ""
    rows = _rows(out)
    verified = {doc_id for doc_id, cells in rows.items() if cells[5] != "-"}
    # M8 (feature/golden-m8) adds questions for the remaining open documents;
    # the sixteen verified at M8a stay verified, so the check is a subset.
    assert verified >= {
        "IPMI",
        "IPMI-UPDATE",
        "DCMI",
        "DSP0236",
        "DSP0237",
        "DSP0239",
        "DSP0240",
        "DSP0245",
        "DSP0248",
        "DSP0267",
        "DSP0274",
        "DSP8010",
        "DSP0266",
        "NVME-MI",
        "DC-SCM",
        "UM10204",
    }
    assert rows["IPMI"][5] == "G1, G2, G3, G4, G5"
    assert rows["DC-SCM"][5] == "G20"
    # every question row of the shipped file names a document or "-"
    text = GOLDEN_SHIPPED.read_text(encoding="utf-8")
    question_rows = [ln for ln in text.splitlines() if re.match(r"^\|\s*G\d+\s*\|", ln)]
    # M8: G1-G24 plus one row per document added since; ids are unique and gap-free
    ids = [int(re.match(r"^\|\s*G(\d+)", ln).group(1)) for ln in question_rows]
    assert len(ids) >= 24
    assert sorted(ids) == list(range(1, len(ids) + 1))
    assert all(len(ln.split("|")) >= 6 for ln in question_rows)


# ------------------------------------------------- shipped catalog content


def test_ac4_seven_known_limits_live_in_limits_not_notes(shipped):
    expected = {"IPMI", "DC-SCM", "CMIS", "DSP0274", "DSP0239", "DSP8011", "DSP8013"}
    with_limits = {d.id for d in shipped.documents if d.limits}
    # M8 (feature/golden-m8) records further document defects found while
    # answering Golden Questions; the seven from M8a must still be there.
    assert with_limits >= expected
    for doc_id in with_limits:
        doc = shipped.get(doc_id)
        assert doc.limits.strip() and doc.limits not in doc.notes


def test_ac16_new_ids_are_present_in_their_families(shipped):
    expected = {
        "LPC": "lpc",
        "PWM-FAN": "fan",
        "LTPI": "ocp-dcscm",
        "SFF-8485": "sff",
        "PMBUS-I": "pmbus",
        "PMBUS-II": "pmbus",
    }
    for doc_id, family in expected.items():
        doc = shipped.get(doc_id)
        assert doc is not None, doc_id
        assert doc.family == family, doc_id
        assert family in shipped.families
        assert doc.latest() is not None, doc_id


def test_ac11_lpc(shipped):
    doc = shipped.get("LPC")
    assert doc.access == "open" and doc.fetch == "direct"
    assert shipped.families["lpc"].publisher == "Intel"
    v = doc.find_version("1.1")
    assert v is not None and v.open
    assert v.url.startswith("https://www.intel.com/")
    assert doc.latest() is v


def test_ac12_ltpi_and_dcscm_2_2(shipped):
    ltpi = shipped.get("LTPI")
    assert ltpi.family == "ocp-dcscm" and ltpi.fetch == "direct" and ltpi.access == "open"
    assert {v.version for v in ltpi.versions} == {"Rev 1.0 Ver 1.0", "Rev 1.2 Ver 1.0"}
    for v in ltpi.versions:
        assert v.url.startswith("https://www.opencompute.org/documents/"), v.version
        assert v.open and v.type == "pdf"
    assert ltpi.latest().version == "Rev 1.2 Ver 1.0"

    dcscm = shipped.get("DC-SCM")
    v22 = dcscm.find_version("Rev 2.2 Ver 1.0")
    assert v22 is not None and v22.open
    assert v22.url.startswith("https://www.opencompute.org/documents/")
    assert dcscm.latest() is v22
    assert dcscm.listing  # check still has something to compare against
    assert "DC-SCI" in dcscm.notes
    assert "not listed" not in dcscm.notes


def test_ac13_sff_8485(shipped):
    doc = shipped.get("SFF-8485")
    assert doc.access == "open" and doc.fetch == "direct"
    assert "SNIA" in shipped.families["sff"].publisher
    v = doc.find_version("Rev 0.7")
    assert v is not None and v.open
    assert v.url.startswith("https://members.snia.org/")
    assert doc.listing == ""
    assert "listing" in doc.notes.lower()


@pytest.mark.parametrize("doc_id", ["PMBUS-I", "PMBUS-II"])
def test_ac14_pmbus_open_and_gated_versions(shipped, doc_id):
    doc = shipped.get(doc_id)
    assert doc.access == "open" and doc.fetch == "direct"
    assert shipped.families["pmbus"].publisher == "System Management Interface Forum"
    tiers = {v.version: (v.access, v.url) for v in doc.versions}
    assert set(tiers) == {"1.2", "1.3", "1.3.1", "1.4", "1.5"}
    for ver in ("1.2", "1.3", "1.3.1"):
        access, url = tiers[ver]
        assert access == "open" and url.startswith("https://"), ver
    for ver in ("1.4", "1.5"):
        assert tiers[ver] == ("gated", ""), ver
    assert doc.latest().version == "1.5"
    assert doc.newest_open().version == "1.3.1"
    # the published date of each open revision matches the file name's stamp
    for v in doc.versions:
        if v.open:
            stamp = re.search(r"-(\d{8})\.pdf$", v.url)
            assert stamp, v.url
            assert v.published.replace("-", "") == stamp.group(1), v.version


def test_ac14_pmbus_ii_notes_point_at_the_command_language(shipped):
    assert "command" in shipped.get("PMBUS-II").notes.lower()
    assert "Part II" in shipped.get("PMBUS-I").notes


def test_ac14_fetch_pmbus_ii_names_1_3_1_then_fetches_it(library, scripted, capsys):
    code, out, _ = run(capsys, "fetch", "PMBUS-II")
    assert code == 2
    assert scripted.calls == []
    assert "gated" in out.splitlines()[0]
    assert "newest open version: 1.3.1; fetch it with --version 1.3.1" in out
    url = load_catalog().get("PMBUS-II").find_version("1.3.1").url
    scripted.responses[url] = ok(PDF_BYTES)
    code, out, _ = run(capsys, "fetch", "PMBUS-II", "--version", "1.3.1")
    assert code == 0, out
    assert "fetched PMBUS-II 1.3.1 via direct" in out
    assert scripted.calls == [url]
    assert library.find("PMBUS-II", "1.3.1") is not None


def test_ac15_pwm_fan_is_a_wayback_document_and_fetches_through_it(
    shipped, library, scripted, capsys
):
    doc = shipped.get("PWM-FAN")
    assert doc.fetch == "wayback" and doc.access == "open"
    assert shipped.families["fan"].publisher == "Intel"
    assert {v.version for v in doc.versions} == {"Rev 1.2", "Rev 1.3"}
    assert doc.latest().version == "Rev 1.3"
    for v in doc.versions:
        assert v.url.startswith(("http://", "https://")), v.version
    url = doc.latest().url
    availability = fetch_mod.WAYBACK_AVAILABLE + urllib.parse.quote(url, safe=":/?=&")
    scripted.responses[availability] = wayback_hit(url)
    scripted.responses[f"http://web.archive.org/web/20250101000000id_/{url}"] = ok(
        PDF_BYTES
    )
    code, out, _ = run(capsys, "fetch", "PWM-FAN")
    assert code == 0, out
    assert "fetched PWM-FAN Rev 1.3 via wayback" in out
    assert scripted.calls[0] == availability  # never the dead site itself
    assert library.find("PWM-FAN", "Rev 1.3") is not None


def test_ac16_new_versions_have_real_looking_dates_or_say_approximate(shipped):
    new_ids = ("LPC", "PWM-FAN", "LTPI", "SFF-8485", "PMBUS-I", "PMBUS-II")
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for doc_id in new_ids:
        for v in shipped.get(doc_id).versions:
            assert date_re.match(v.published), (doc_id, v.version)
            assert "2000-01-01" <= v.published <= "2026-09-04", (doc_id, v.version)
    # the cover of these gives only month and year: the notes must say so
    for doc_id, version in (("LPC", "1.1"), ("PWM-FAN", "Rev 1.2"), ("PWM-FAN", "Rev 1.3")):
        v = shipped.get(doc_id).find_version(version)
        assert v is not None and "approximate" in v.notes.lower(), (doc_id, version)
    v22 = shipped.get("DC-SCM").find_version("Rev 2.2 Ver 1.0")
    assert v22.published == "2025-10-16"
    for ver in ("1.4", "1.5"):
        for doc_id in ("PMBUS-I", "PMBUS-II"):
            v = shipped.get(doc_id).find_version(ver)
            assert "approximate" in v.notes.lower(), (doc_id, ver)


def test_ac16_fetch_all_never_targets_a_version_without_a_url(shipped):
    """The offline half of 'fetch --all ends with failed 0': whatever
    --all picks per document has a URL to try."""
    for doc in shipped.documents:
        if doc.fetch == "manual":
            continue
        ver = doc.latest()
        if ver is not None and not ver.open:
            ver = doc.newest_open()
        if ver is None:
            continue
        assert ver.url, (doc.id, ver.version)
        assert ver.open, (doc.id, ver.version)
