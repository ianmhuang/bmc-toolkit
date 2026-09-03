"""Review acceptance tests for the Freshness Check (AC-1 to AC-5, AC-10).

Black-box through the CLI with a scripted HTTP client shaped like the
three publishers' listings; nothing touches the network. The listing
fixtures here are written from the acceptance criteria, not copied from
the author's tests.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec import code as code_mod
from bmc_toolkit.spec.catalog import CatalogError, load_catalog
from bmc_toolkit.spec.fetch import Response
from tests.conftest import MINI_CATALOG, PDF_BYTES, ScriptedClient, ok

ROOT = Path(__file__).resolve().parents[1]

DMTF_PUBLISHED = "https://www.dmtf.org/standards/published_documents"
DMTF_DSP0236 = "https://www.dmtf.org/dsp/DSP0236"
NVME_API = "https://nvmexpress.org/wp-json/vtm/v1/specifications"
OCP_PAGE = "Server/MHS/DC-MHS-Specs-and-Designs"
OCP_WIKI = f"https://www.opencompute.org/w/index.php?title={OCP_PAGE}"

DSP0236_133_URL = (
    "https://www.dmtf.org/sites/default/files/standards/documents/DSP0236_1.3.3.pdf"
)
NVME_MI_22_URL = (
    "https://nvmexpress.org/wp-content/uploads/NVM-Express-Management-Interface-"
    "Specification-Revision-2.2-Ratified-2026.07.31.pdf"
)
DRIVE_URL = "https://drive.google.com/file/d/review-crps/view"

PUBLISHED_HTML = f"""
<html><body>
<table><thead><tr>
<th>DSP</th><th>Version</th><th>Title</th><th>Comments</th><th>DSP</th>
</tr></thead><tbody>
<tr><td>DSP0236</td><td>1.3.3</td>
<td><a href="{DSP0236_133_URL}">MCTP Base Specification</a></td>
<td>Standard</td><td><a href="/dsp/DSP0236">View</a></td></tr>
<tr><td>DSP0240</td><td>1.1.1</td>
<td><a href="/sites/default/files/standards/documents/DSP0240_1.1.1.pdf">PLDM Base</a></td>
<td>Standard</td><td><a href="/dsp/DSP0240">View</a></td></tr>
</tbody></table>
</body></html>
"""

NVME_JSON = json.dumps(
    {
        "posts": [
            {
                "slug": "nvme-mi-specification",
                "post_title": "NVM Express Management Interface Specification",
                "file": {"url": NVME_MI_22_URL},
            }
        ]
    }
)

OCP_HTML = f"""
<html><body>
<table class="wikitable"><tbody>
<tr><th>Type</th><th>Description</th><th>Version</th><th>Submit Date</th>
<th>Contributor</th><th>Link</th><th>Notes</th></tr>
<tr><td>Specification</td><td>M-CRPS Base Specification</td><td>1.06</td>
<td>4/24/26</td><td>Someone</td>
<td><a href="{DRIVE_URL}">Link (Base Spec)</a></td><td></td></tr>
<tr><td>Specification</td><td>M-XIO Base Specification</td><td>1.2 RC3</td>
<td>3/21/2024</td><td>Someone</td>
<td><a href="https://drive.google.com/file/d/xio/view">Link</a></td><td></td></tr>
</tbody></table>
</body></html>
"""

CATALOG = (
    MINI_CATALOG
    + """
[families.nvme]
title = "NVM Express"
publisher = "NVM Express, Inc."

[families.ocp]
title = "OCP"
publisher = "Open Compute Project"

[[documents]]
id = "NVME-MI"
family = "nvme"
title = "NVMe Management Interface"
access = "open"
fetch = "direct"
listing = "nvme:nvme-mi-specification"

[[documents.versions]]
version = "2.1"
url = "https://example.test/NVM-Express-Management-Interface-Specification-Revision-2.1-2025.08.01-Ratified.pdf"
type = "pdf"
published = "2025-08-01"

[[documents]]
id = "M-CRPS"
family = "ocp"
title = "M-CRPS Base Specification"
access = "open"
fetch = "direct"
listing = "ocp:Server/MHS/DC-MHS-Specs-and-Designs|M-CRPS Base"

[[documents.versions]]
version = "R1 v1.0 RC4"
url = "https://example.test/m-crps-r1-v1p0-rc4-pdf"
type = "pdf"
published = "2023-01-01"

[[documents]]
id = "M-XIO"
family = "ocp"
title = "M-XIO Base Specification"
access = "open"
fetch = "direct"
listing = "ocp:Server/MHS/DC-MHS-Specs-and-Designs|M-XIO Base"

[[documents.versions]]
version = "R1 v1.2 RC3"
url = "https://example.test/m-xio-r1-v1p2-rc3-pdf"
type = "pdf"
published = "2024-03-21"
"""
)


def html(text: str) -> Response:
    return Response(200, {"content-type": "text/html"}, text.encode("utf-8"))


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def lib_root(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


@pytest.fixture
def client(monkeypatch):
    scripted = ScriptedClient(
        {
            DMTF_PUBLISHED: html(PUBLISHED_HTML),
            NVME_API: ok(NVME_JSON.encode("utf-8"), "application/json"),
            OCP_WIKI: html(OCP_HTML),
        }
    )
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: scripted)
    return scripted


def run(capsys, *argv, catalog_file):
    code = cli.main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def freshness(lib_root) -> dict:
    return json.loads((lib_root / "freshness.json").read_text("utf-8"))


def library_entries(lib_root) -> list[str]:
    return sorted(p.name for p in lib_root.iterdir()) if lib_root.exists() else []


# ----------------------------------------------------------------- AC-1


def test_check_one_current_document_downloads_nothing(
    catalog_file, lib_root, client, capsys
):
    code, out = run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "current DSP0236 1.3.3"
    assert lines[-1].startswith("summary: current 1, newer 0, unreachable 0")
    # the Library root gains freshness.json and nothing else
    assert library_entries(lib_root) == ["freshness.json"]
    # only the listing page was requested; no document URL
    assert client.calls == [DMTF_PUBLISHED]
    assert freshness(lib_root)["documents"]["DSP0236"]["catalog_latest"] == "1.3.3"


def test_check_one_newer_document_prints_version_date_and_url(
    catalog_file, lib_root, client, capsys
):
    code, out = run(capsys, "check", "NVME-MI", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0] == (
        f"newer NVME-MI: catalog latest 2.1, NVM Express lists 2.2 (2026-07-31) "
        f"{NVME_MI_22_URL}"
    )
    assert client.calls == [NVME_API]  # the listed PDF was not fetched
    assert library_entries(lib_root) == ["freshness.json"]
    rec = freshness(lib_root)["documents"]["NVME-MI"]
    assert rec["newer"][0]["version"] == "2.2"
    assert rec["newer"][0]["url"] == NVME_MI_22_URL


def test_check_ocp_version_strings_match_across_naming(
    catalog_file, lib_root, client, capsys
):
    """The wiki's '1.2 RC3' is the catalog's 'R1 v1.2 RC3': current, not newer."""
    code, out = run(capsys, "check", "M-XIO", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0] == "current M-XIO R1 v1.2 RC3"


# ----------------------------------------------------------------- AC-3


def test_check_reports_newer_when_the_catalog_latest_is_removed_by_hand(
    catalog_file, lib_root, client, capsys
):
    text = catalog_file.read_text("utf-8")
    start = text.index('[[documents.versions]]\nversion = "1.3.3"')
    end = text.index("[[documents.versions]]", start + 1)
    catalog_file.write_text(text[:start] + text[end:], encoding="utf-8", newline="")
    assert load_catalog(catalog_file).get("DSP0236").latest().version == "1.3.2"
    code, out = run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    line = out.splitlines()[0]
    assert line.startswith("newer DSP0236: catalog latest 1.3.2, DMTF lists 1.3.3")
    assert DSP0236_133_URL in line
    assert client.calls == [DMTF_PUBLISHED]


def test_check_ocp_google_drive_link_is_to_confirm_by_hand(
    catalog_file, lib_root, client, capsys
):
    code, out = run(capsys, "check", "M-CRPS", catalog_file=catalog_file)
    assert code == 0, out
    line = out.splitlines()[0]
    assert line.startswith("newer M-CRPS: catalog latest R1 v1.0 RC4")
    assert "1.06" in line and "(2026-04-24)" in line
    assert DRIVE_URL in line and "(URL to confirm by hand)" in line


# ----------------------------------------------------------------- AC-2


def test_check_all_lists_unchecked_continues_past_failures_and_summarises(
    catalog_file, lib_root, client, capsys
):
    del client.responses[NVME_API]  # network failure for one listing
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert "current DSP0236 1.3.3" in lines
    unreachable = [ln for ln in lines if ln.startswith("unreachable NVME-MI: ")]
    assert len(unreachable) == 1 and "no route to" in unreachable[0]
    assert any(ln.startswith("newer M-CRPS: ") for ln in lines)
    assert "current M-XIO R1 v1.2 RC3" in lines
    unchecked = [ln for ln in lines if ln.startswith("unchecked: ")]
    assert len(unchecked) == 1
    for doc_id in ("IPMI", "BUNDLE", "SECRET"):
        assert doc_id in unchecked[0]
    assert "DSP0236" not in unchecked[0]
    summary = [ln for ln in lines if ln.startswith("summary: ")]
    assert len(summary) == 1
    assert summary[0].startswith("summary: current 2, newer 1, unreachable 1")
    assert "unchecked 3" in summary[0]
    # the failing listing is recorded as such, with the time of the check
    rec = freshness(lib_root)["documents"]["NVME-MI"]
    assert "no route to" in rec["problem"]
    datetime.fromisoformat(rec["checked_at"])
    assert library_entries(lib_root) == ["freshness.json"]


def test_check_reports_a_listing_that_does_not_parse_as_unreachable(
    catalog_file, lib_root, client, capsys
):
    client.responses[NVME_API] = html("<html><body>maintenance</body></html>")
    client.responses[DMTF_PUBLISHED] = Response(503, {}, b"")
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert any(ln.startswith("unreachable NVME-MI: ") for ln in lines)
    dmtf = [ln for ln in lines if ln.startswith("unreachable DSP0236: ")]
    assert len(dmtf) == 1 and "503" in dmtf[0]
    assert any(ln.startswith("summary: ") for ln in lines)


def test_check_unknown_or_unlisted_document_is_exit_2(
    catalog_file, lib_root, client, capsys
):
    code, out = run(capsys, "check", "NOPE", catalog_file=catalog_file)
    assert code == 2 and "NOPE" in out
    code, out = run(capsys, "check", "IPMI", catalog_file=catalog_file)
    assert code == 2 and "IPMI" in out
    assert client.calls == []


# ----------------------------------------------------------------- AC-4


def test_fetch_note_when_never_checked_once_until_the_next_check(
    catalog_file, lib_root, client, capsys
):
    url = "https://example.test/DSP0236_1.3.3.pdf"
    client.responses[url] = ok(PDF_BYTES, length=len(PDF_BYTES))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    notes = [ln for ln in out.splitlines() if ln.startswith("note: ")]
    assert len(notes) == 1
    assert notes[0].startswith("note: DSP0236 has never been checked against DMTF")
    assert "check DSP0236" in notes[0]
    assert DMTF_PUBLISHED not in client.calls  # the note never goes online
    assert freshness(lib_root)["documents"]["DSP0236"]["reminded_at"]
    # reminded once
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and "note:" not in out
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0 and "note:" not in out
    # a check spends the reminder and makes the document fresh
    run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert "note:" not in out
    # a document without a listing never gets a note
    code, out = run(capsys, "fetch", "IPMI", catalog_file=catalog_file)
    assert "note:" not in out


def test_fetch_note_after_freshness_days_and_the_config_key(
    catalog_file, lib_root, client, capsys
):
    url = "https://example.test/DSP0236_1.3.3.pdf"
    client.responses[url] = ok(PDF_BYTES, length=len(PDF_BYTES))
    run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    state = freshness(lib_root)
    old = (datetime.now(UTC) - timedelta(days=31)).replace(microsecond=0)
    state["documents"]["DSP0236"]["checked_at"] = old.isoformat()
    (lib_root / "freshness.json").write_text(json.dumps(state), encoding="utf-8")
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    notes = [ln for ln in out.splitlines() if ln.startswith("note: ")]
    assert len(notes) == 1
    assert notes[0].startswith(
        "note: DSP0236 has not been checked against DMTF for 31 days"
    )
    assert "check DSP0236" in notes[0]
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert "note:" not in out  # once
    # a larger freshness_days makes a 31-day-old check fresh again
    state = freshness(lib_root)
    state["documents"]["DSP0236"].pop("reminded_at", None)
    (lib_root / "freshness.json").write_text(json.dumps(state), encoding="utf-8")
    (lib_root / "config.toml").write_text(
        "[library]\nfreshness_days = 90\n", encoding="utf-8"
    )
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and "note:" not in out
    assert DMTF_PUBLISHED not in client.calls


def test_fetch_all_and_status_print_one_note_for_the_documents_together(
    catalog_file, lib_root, client, capsys
):
    url = "https://example.test/DSP0236_1.3.3.pdf"
    client.responses[url] = ok(PDF_BYTES, length=len(PDF_BYTES))
    code, out = run(capsys, "fetch", "--all", catalog_file=catalog_file)
    lines = out.splitlines()
    notes = [ln for ln in lines if ln.startswith("note: ")]
    assert len(notes) == 1, out
    assert "check" in notes[0]
    assert lines[-1].startswith("summary: ")  # the note comes before the summary
    assert lines.index(notes[0]) < len(lines) - 1
    for doc_id in ("DSP0236", "NVME-MI", "M-CRPS", "M-XIO"):
        assert freshness(lib_root)["documents"][doc_id]["reminded_at"]
    code, out = run(capsys, "fetch", "--all", catalog_file=catalog_file)
    assert "note:" not in out
    # status on held documents: reminded already, so silent; after a check
    # that ages out, one note
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert code == 0 and "note:" not in out
    run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    state = freshness(lib_root)
    old = (datetime.now(UTC) - timedelta(days=45)).replace(microsecond=0)
    state["documents"]["DSP0236"]["checked_at"] = old.isoformat()
    (lib_root / "freshness.json").write_text(json.dumps(state), encoding="utf-8")
    code, out = run(capsys, "status", catalog_file=catalog_file)
    notes = [ln for ln in out.splitlines() if ln.startswith("note: ")]
    assert len(notes) == 1 and "DSP0236" in notes[0]
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert "note:" not in out
    # the notes never went online: one listing request, from the explicit check
    assert client.calls.count(DMTF_PUBLISHED) == 1
    assert NVME_API not in client.calls and OCP_WIKI not in client.calls


def test_bad_freshness_days_is_reported_not_raised(
    catalog_file, lib_root, client, capsys
):
    url = "https://example.test/DSP0236_1.3.3.pdf"
    client.responses[url] = ok(PDF_BYTES, length=len(PDF_BYTES))
    lib_root.mkdir(parents=True)
    (lib_root / "config.toml").write_text(
        "[library]\nfreshness_days = -3\n", encoding="utf-8"
    )
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    assert "freshness_days" in out


# ----------------------------------------------------------------- AC-5


class _Proc:
    def __init__(self, stdout):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


@pytest.fixture
def release_setup(catalog_file, lib_root):
    text = catalog_file.read_text("utf-8") + (
        '\n[[repos]]\nid = "openbmc"\nurl = "https://example.test/openbmc.git"\n'
        'topics = ["release"]\n'
    )
    catalog_file.write_text(text, encoding="utf-8", newline="")
    lib_root.mkdir(parents=True)
    (lib_root / "config.toml").write_text(
        '[code]\nrelease = "2.18.0"\n', encoding="utf-8"
    )


def _fake_ls_remote(monkeypatch, tags, calls):
    def run_git(args, **kwargs):
        calls.append(list(args))
        assert args[0] == "ls-remote"
        lines = [f"{'a' * 40}\trefs/tags/{t}" for t in tags]
        lines.append(f"{'b' * 40}\trefs/heads/master")
        return _Proc("\n".join(lines) + "\n")

    monkeypatch.setattr(code_mod, "run_git", run_git)


def test_check_release_newer_than_config(
    catalog_file, lib_root, client, capsys, monkeypatch, release_setup
):
    calls = []
    _fake_ls_remote(monkeypatch, ["2.18.0", "2.18.0-dev", "3.0.0", "v9.9", "2.9.0"], calls)
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert code == 0, out
    release = [ln for ln in out.splitlines() if ln.startswith("release: ")]
    assert len(release) == 1
    assert release[0].startswith("release: 2.18.0 (config.toml); newest openbmc tag 3.0.0")
    assert "newer" in release[0]
    assert len(calls) == 1 and "https://example.test/openbmc.git" in calls[0]
    assert freshness(lib_root)["release"]["newest"] == "3.0.0"


def test_check_release_is_the_newest_and_numeric_order(
    catalog_file, lib_root, client, capsys, monkeypatch, release_setup
):
    # 2.18.0 is numerically above 2.9.0: string order would get this wrong
    _fake_ls_remote(monkeypatch, ["2.9.0", "2.18.0", "1.0.0"], [])
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert code == 0, out
    release = [ln for ln in out.splitlines() if ln.startswith("release: ")][0]
    assert "newest openbmc tag 2.18.0" in release
    assert "is the newest" in release and "-> newer" not in release


def test_check_release_branch_is_reported_with_the_newest_tag_only(
    catalog_file, lib_root, client, capsys, monkeypatch, release_setup
):
    (lib_root / "config.toml").write_text(
        '[code]\nrelease = "scarthgap"\n', encoding="utf-8"
    )
    _fake_ls_remote(monkeypatch, ["2.18.0", "3.0.0"], [])
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert code == 0, out
    release = [ln for ln in out.splitlines() if ln.startswith("release: ")][0]
    assert "scarthgap" in release and "3.0.0" in release
    assert "-> newer" not in release and "is the newest" not in release


def test_check_release_failure_does_not_stop_the_document_checks(
    catalog_file, lib_root, client, capsys, monkeypatch, release_setup
):
    def boom(args, **kwargs):
        raise code_mod.CodeError("git ls-remote failed: could not resolve host")

    monkeypatch.setattr(code_mod, "run_git", boom)
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert any(ln.startswith("unreachable release") for ln in lines)
    assert "current DSP0236 1.3.3" in lines
    assert any(ln.startswith("summary: ") for ln in lines)


def test_check_without_release_or_for_one_document_never_runs_ls_remote(
    catalog_file, lib_root, client, capsys, monkeypatch, release_setup
):
    calls = []
    _fake_ls_remote(monkeypatch, ["3.0.0"], calls)
    code, out = run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    assert code == 0 and "release:" not in out and calls == []
    (lib_root / "config.toml").write_text("[code]\n", encoding="utf-8")
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert code == 0 and "release:" not in out and calls == []


# ---------------------------------------------------------------- AC-10


def test_listing_key_is_validated_and_defaults_for_dmtf(tmp_path):
    good = tmp_path / "c.toml"
    good.write_text(CATALOG, encoding="utf-8", newline="")
    catalog = load_catalog(good)
    assert catalog.get("DSP0236").listing == "dmtf:DSP0236"
    assert catalog.get("IPMI").listing == ""
    assert catalog.get("NVME-MI").listing == "nvme:nvme-mi-specification"
    assert catalog.get("M-CRPS").listing_source == "ocp"
    assert catalog.get("M-CRPS").listing_key == (
        "Server/MHS/DC-MHS-Specs-and-Designs|M-CRPS Base"
    )
    for bad in ('listing = "intel:IPMI"', 'listing = "nvme:"', 'listing = "nvme"'):
        text = CATALOG.replace('fetch = "wayback"', f'fetch = "wayback"\n{bad}', 1)
        path = tmp_path / "bad.toml"
        path.write_text(text, encoding="utf-8", newline="")
        with pytest.raises(CatalogError, match="listing"):
            load_catalog(path)


def test_catalog_command_prints_the_listing_line(catalog_file, capsys):
    code, out = run(capsys, "catalog", "DSP0236", catalog_file=catalog_file)
    assert code == 0
    assert any(ln == "listing: dmtf:DSP0236" for ln in out.splitlines())
    code, out = run(capsys, "catalog", "NVME-MI", catalog_file=catalog_file)
    assert any(
        ln == "listing: nvme:nvme-mi-specification" for ln in out.splitlines()
    )
    code, out = run(capsys, "catalog", "IPMI", catalog_file=catalog_file)
    assert any(ln.startswith("listing: ") for ln in out.splitlines())


def test_shipped_catalog_carries_listings_for_nvme_and_ocp():
    catalog = load_catalog()
    for doc_id in ("NVME-BASE", "NVME-MI", "NVME-PCIE"):
        assert catalog.get(doc_id).listing_source == "nvme", doc_id
    ocp = [d for d in catalog.documents if d.listing_source == "ocp"]
    assert len(ocp) >= 8
    for doc in ocp:
        page, sep, prefix = doc.listing_key.partition("|")
        assert sep and page and prefix, doc.id
    assert catalog.get("DSP0236").listing == "dmtf:DSP0236"
    for doc_id in ("IPMI", "UM10204", "SMBUS", "CMIS"):
        doc = catalog.get(doc_id)
        if doc is not None:
            assert doc.listing == "", doc_id


def test_release_metadata_and_documentation():
    import tomllib

    import bmc_toolkit

    assert bmc_toolkit.__version__ == "1.0.0"
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    assert pyproject["project"]["version"] == "1.0.0"
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    assert plugin["version"] == "1.0.0"
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "pre-release" not in readme.lower()
    skill = (ROOT / "skills" / "bmc-spec" / "SKILL.md").read_text("utf-8")
    for text in (readme, skill):
        for word in ("check", "refresh", "prune", "freshness_days", "listing"):
            assert word in text, word
    assert "freshness.json" in readme  # SKILL.md names only the note (see findings)
    assert (ROOT / "docs" / "golden-questions.md").is_file()
