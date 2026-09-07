"""Freshness Check: the state file and its age, the check and refresh
commands against scripted listings, the notes fetch and status print,
and the OpenBMC release comparison."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from bmc_toolkit.spec import freshness as F
from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec import refresh as R
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.fetch import Response
from tests.conftest import MINI_CATALOG, PDF_BYTES, ok
from tests.test_listing import (
    DMTF_DSP_HTML,
    DMTF_PUBLISHED_HTML,
    NVME_JSON,
    OCP_WIKI_HTML,
)

LISTED_CATALOG = (
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
"""
)


def html(text):
    return Response(200, {"content-type": "text/html"}, text.encode())


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(LISTED_CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def pages(scripted):
    """Every listing the mini catalog can reach, on the CLI's client."""
    scripted.responses.update(
        {
            L.DMTF_PUBLISHED: html(DMTF_PUBLISHED_HTML),
            L.DMTF_DSP.format(key="DSP0236"): html(DMTF_DSP_HTML),
            L.NVME_API: ok(NVME_JSON.encode(), "application/json"),
            L.OCP_WIKI.format(page="Server/MHS/DC-MHS-Specs-and-Designs"): html(
                OCP_WIKI_HTML
            ),
        }
    )
    return scripted


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


# ------------------------------------------------------------- state


def test_state_file_round_trip_and_age(tmp_path):
    state = F.Freshness(tmp_path / "lib")
    assert state.age_days("DSP0236") is None
    assert state.stale("DSP0236", 30)
    check = F.Check("dsp0236", "1.3.3", "2026-08-01T00:00:00+00:00", [L.Seen("1.3.4")])
    state.record(check)
    state.save()
    again = F.Freshness(tmp_path / "lib")
    now = datetime(2026, 8, 31, 12, tzinfo=UTC)
    assert again.age_days("DSP0236", now) == 30
    assert again.stale("DSP0236", 31, now) is False
    assert again.stale("DSP0236", 30, now) is True
    saved = json.loads((tmp_path / "lib" / F.FRESHNESS_NAME).read_text("utf-8"))
    assert saved["documents"]["DSP0236"]["newer"][0]["version"] == "1.3.4"
    (tmp_path / "lib" / F.FRESHNESS_NAME).write_text("not json", encoding="utf-8")
    assert F.Freshness(tmp_path / "lib").age_days("DSP0236") is None


def test_max_age_days_from_config(tmp_path):
    assert F.max_age_days(tmp_path) == F.DEFAULT_MAX_AGE_DAYS
    (tmp_path / "config.toml").write_text(
        '[library]\nfreshness_days = 7\n[code]\nrelease = "1.0"\n', encoding="utf-8"
    )
    assert F.max_age_days(tmp_path) == 7
    (tmp_path / "config.toml").write_text(
        "[library]\nfreshness_days = 0\n", encoding="utf-8"
    )
    with pytest.raises(F.FreshnessError, match="positive integer"):
        F.max_age_days(tmp_path)
    (tmp_path / "config.toml").write_text("[library\n", encoding="utf-8")
    with pytest.raises(F.FreshnessError):
        F.max_age_days(tmp_path)


def test_compare_and_notes(catalog_file, tmp_path):
    catalog = load_catalog(catalog_file)
    doc = catalog.get("DSP0236")
    check = F.compare(doc, [L.Seen("1.3.3", "u")])
    assert check.status == "current" and check.catalog_latest == "1.3.3"
    check = F.compare(doc, [L.Seen("1.3.5", "u", "2026-09-01")])
    assert check.status == "newer" and check.newer[0].version == "1.3.5"
    crps = catalog.get("M-CRPS")
    assert F.compare(crps, [L.Seen("1.0 RC4")]).status == "current"
    assert F.compare(crps, [L.Seen("1.06")]).status == "newer"
    state = F.Freshness(tmp_path)
    note = state.note_for(doc, 30)
    assert note == (
        "note: DSP0236 has never been checked against DMTF; run: bmcspec check DSP0236"
    )
    assert state.note_for(catalog.get("IPMI"), 30) == ""  # no listing
    stale = state.stale_documents(catalog, ["dsp0236", "IPMI", "NVME-MI"], 30)
    assert [d.id for d in stale] == ["DSP0236", "NVME-MI"]
    state.mark_reminded(["dsp0236"])
    assert state.reminded("DSP0236") and not state.reminded("NVME-MI")
    due = state.due_documents(catalog, ["dsp0236", "IPMI", "NVME-MI"], 30)
    assert [d.id for d in due] == ["NVME-MI"]
    state.record(F.compare(doc, [L.Seen("1.3.3")]))  # a check spends it
    assert not state.reminded("DSP0236")


@pytest.mark.parametrize(
    "configured, newest, expected",
    [
        ("2.18.0", "3.0.0", True),
        ("3.0.0", "3.0.0", False),
        ("3.1.0", "3.0.0", False),
        ("2.9.0", "2.18.0", True),
        ("scarthgap", "3.0.0", None),
    ],
)
def test_release_is_newer(configured, newest, expected):
    assert F.release_is_newer(configured, newest) is expected


def test_newest_release_tag_parses_ls_remote(monkeypatch):
    class Proc:
        stdout = "\n".join(
            [
                "aaa\trefs/tags/2.18.0",
                "bbb\trefs/tags/2.18.0-dev",
                "ccc\trefs/tags/3.0.0",
                "ddd\trefs/tags/v2.4",
                "eee\trefs/tags/2.9.0",
                "fff\trefs/heads/master",
            ]
        )

    monkeypatch.setattr(F.code_mod, "run_git", lambda args, **kw: Proc())
    assert F.newest_release_tag("https://example.test/openbmc.git") == "3.0.0"
    Proc.stdout = "ddd\trefs/tags/v2.4\n"
    assert F.newest_release_tag("https://example.test/openbmc.git") is None


# --------------------------------------------------------------- check


def test_check_one_document_current_newer_and_records(
    catalog_file, library, pages, capsys
):
    code, out = run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines() == [
        "current DSP0236 1.3.3",
        "summary: current 1, newer 0, unreachable 0",
    ]
    assert not (library.root / "specs").exists()  # no download, no Library
    saved = json.loads((library.root / F.FRESHNESS_NAME).read_text("utf-8"))
    assert saved["documents"]["DSP0236"]["catalog_latest"] == "1.3.3"
    assert saved["documents"]["DSP0236"]["newer"] == []
    code, out = run(capsys, "check", "NVME-MI", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[0] == (
        "newer NVME-MI: catalog latest 2.1, NVM Express lists 2.2 (2026-07-31) "
        "https://nvmexpress.org/wp-content/uploads/NVM-Express-Management-"
        "Interface-Specification-Revision-2.2-Ratified-2026.07.31.pdf"
    )
    assert "nothing was downloaded" in out
    assert not list(library.root.glob("specs/**/*"))
    code, out = run(capsys, "check", "M-CRPS", catalog_file=catalog_file)
    assert out.splitlines()[0] == (
        "newer M-CRPS: catalog latest R1 v1.0 RC4, the OCP wiki lists 1.06 "
        "(2026-04-24) https://drive.google.com/file/d/abc/view "
        "(URL to confirm by hand) [M-CRPS Base Specification]"
    )


def test_check_made_stale_by_hand_reports_newer(catalog_file, library, pages, capsys):
    """AC-3: drop the catalog's latest and the publisher's version shows."""
    text = catalog_file.read_text("utf-8")
    start = text.index('[[documents.versions]]\nversion = "1.3.3"')
    end = text.index("[[documents.versions]]", start + 1)
    catalog_file.write_text(text[:start] + text[end:], encoding="utf-8", newline="")
    code, out = run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[0] == (
        "newer DSP0236: catalog latest 1.3.2, DMTF lists 1.3.3 "
        "https://www.dmtf.org/sites/default/files/standards/documents/DSP0236_1.3.3.pdf"
    )


def test_check_all_continues_past_failures_and_lists_unchecked(
    catalog_file, library, pages, capsys
):
    del pages.responses[L.NVME_API]
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "current DSP0236 1.3.3"
    assert lines[1].startswith("unreachable NVME-MI: ") and "no route to" in lines[1]
    assert lines[2].startswith("newer M-CRPS: ")
    assert lines[3] == "unchecked: IPMI, BUNDLE (no publisher listing)"
    assert lines[4] == (
        "unchecked (manual): SECRET (confidential) (never fetched by the tool)"
    )
    assert lines[5].startswith("nothing was downloaded")
    assert lines[6] == "summary: current 1, newer 1, unreachable 1, unchecked 3"
    assert lines[-1] == lines[6]  # the summary is the last line (AC-2)
    assert pages.calls.count(L.DMTF_PUBLISHED) == 1
    saved = json.loads((library.root / F.FRESHNESS_NAME).read_text("utf-8"))
    assert "no route to" in saved["documents"]["NVME-MI"]["problem"]


def test_check_rejects_unknown_and_unlisted_documents(catalog_file, library, capsys):
    code, out = run(capsys, "check", "nope", catalog_file=catalog_file)
    assert code == 2 and out.startswith("unknown document 'nope'")
    code, out = run(capsys, "check", "IPMI", catalog_file=catalog_file)
    assert code == 2 and out.startswith("IPMI has no publisher listing")


def test_check_release_against_openbmc_tags(
    catalog_file, library, pages, capsys, monkeypatch
):
    text = catalog_file.read_text("utf-8") + (
        '\n[[repos]]\nid = "openbmc"\nurl = "https://example.test/openbmc.git"\n'
        'topics = ["release"]\n'
    )
    catalog_file.write_text(text, encoding="utf-8", newline="")
    library.root.mkdir(parents=True)
    (library.root / "config.toml").write_text(
        '[code]\nrelease = "2.18.0"\n', encoding="utf-8"
    )
    monkeypatch.setattr(F, "newest_release_tag", lambda url: "3.0.0")
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert code == 0
    assert "release: 2.18.0 (config.toml); newest openbmc tag 3.0.0 -> newer" in out
    saved = json.loads((library.root / F.FRESHNESS_NAME).read_text("utf-8"))
    assert saved["release"]["newest"] == "3.0.0"
    monkeypatch.setattr(F, "newest_release_tag", lambda url: "2.18.0")
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert "newest openbmc tag 2.18.0 -> 2.18.0 is the newest" in out
    (library.root / "config.toml").write_text(
        '[code]\nrelease = "scarthgap"\n', encoding="utf-8"
    )
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert "newest openbmc tag 2.18.0 (scarthgap is a branch, not compared)" in out

    def boom(url):
        raise F.code_mod.CodeError("git ls-remote failed: no network")

    monkeypatch.setattr(F, "newest_release_tag", boom)
    code, out = run(capsys, "check", catalog_file=catalog_file)
    assert code == 0 and "unreachable release: git ls-remote failed" in out
    assert "summary:" in out


# --------------------------------------------------------------- notes


def test_fetch_and_status_print_the_freshness_note(
    catalog_file, library, pages, capsys, monkeypatch
):
    url = "https://example.test/DSP0236_1.3.3.pdf"
    pages.responses[url] = ok(PDF_BYTES, length=len(PDF_BYTES))
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[-1] == (
        "note: DSP0236 has never been checked against DMTF; run: bmcspec check DSP0236"
    )
    saved = json.loads((library.root / F.FRESHNESS_NAME).read_text("utf-8"))
    assert saved["documents"]["DSP0236"]["reminded_at"]
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert "note:" not in out  # reminded once; not again until the next check
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert "note:" not in out
    code, out = run(capsys, "fetch", "IPMI", catalog_file=catalog_file)
    assert "note:" not in out  # no listing: nothing to remind about
    assert L.DMTF_PUBLISHED not in pages.calls  # the notes never go online
    run(capsys, "check", "DSP0236", catalog_file=catalog_file)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    lines = out.splitlines()  # the fake PDF cannot be extracted; no note
    assert lines[0] == "skipped DSP0236 1.3.3: already in Library"
    assert lines[1].startswith("failed DSP0236 1.3.3: ") and len(lines) == 2
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert "note:" not in out
    # 31 days later, with the default age
    state = F.Freshness(library.root)
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    state.data["documents"]["DSP0236"]["checked_at"] = old
    state.save()
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert out.splitlines()[-1] == (
        "note: DSP0236 has not been checked against DMTF for 31 days; "
        "run: bmcspec check DSP0236"
    )
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert "note:" not in out  # once
    (library.root / "config.toml").write_text(
        "[library]\nfreshness_days = 60\n", encoding="utf-8"
    )
    code, out = run(capsys, "fetch", "--all", catalog_file=catalog_file)
    assert out.splitlines()[-2] == (  # the two never checked, not DSP0236
        "note: 2 of these documents have not been checked against their "
        "publishers in the last 60 days; run: bmcspec check"
    )
    assert out.splitlines()[-1].startswith("summary: ")
    code, out = run(capsys, "fetch", "--all", catalog_file=catalog_file)
    assert "note:" not in out  # once for those two as well
    code, out = run(capsys, "status", catalog_file=catalog_file)
    assert "note:" not in out


def test_catalog_shows_the_listing(catalog_file, capsys):
    code, out = run(capsys, "catalog", "DSP0236", catalog_file=catalog_file)
    assert "listing: dmtf:DSP0236\n" in out
    code, out = run(capsys, "catalog", "IPMI", catalog_file=catalog_file)
    assert "listing: - (hand-maintained)\n" in out


# ------------------------------------------------------------- refresh


def test_refresh_reports_and_writes_only_file_versions(
    catalog_file, library, pages, capsys
):
    code, out = run(capsys, "refresh", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == (
        "add DSP0236 1.3.4 (2026-08-03) "
        "https://www.dmtf.org/sites/default/files/standards/documents/DSP0236_1.3.4.pdf"
    )
    assert lines[1] == (
        "changed DSP0236 1.3.3 (2024-03-25) "
        "https://www.dmtf.org/sites/default/files/standards/documents/DSP0236_1.3.3_0.pdf"
    )
    assert lines[2].startswith("changed DSP0236 1.4.0 (2027-01-01) ")  # the WIP entry
    assert lines[3].startswith("add NVME-MI 2.2 (2026-07-31) https://nvmexpress.org/")
    assert lines[4].startswith("confirm M-CRPS 1.06 (2026-04-24) https://drive.google")
    assert lines[5] == (
        "summary: add 2, confirm 1, changed 2, unreachable 0 "
        "(dry run; --write adds them)"
    )
    before = catalog_file.read_text("utf-8")
    code, out = run(capsys, "refresh", "--write", catalog_file=catalog_file)
    assert code == 0, out
    assert "wrote 1 version(s) of DSP0236" in out
    assert "wrote 1 version(s) of NVME-MI" in out
    assert out.splitlines()[-1].endswith("unreachable 0, written 2")
    after = catalog_file.read_text("utf-8")
    catalog = load_catalog(catalog_file)
    doc = catalog.get("DSP0236")
    assert doc.latest().version == "1.3.4"
    assert doc.find_version("1.3.4").published == "2026-08-03"
    assert doc.find_version("1.4.0").wip  # untouched
    assert catalog.get("NVME-MI").latest().version == "2.2"
    assert catalog.get("M-CRPS").latest().version == "R1 v1.0 RC4"  # never written
    # a text edit: every original line is intact and in order; the file is LF
    assert "\r" not in after
    it = iter(after.split("\n"))
    assert all(any(ln == got for got in it) for ln in before.split("\n"))
    # the new block sits at the end of the document's block, before the next one
    dsp = after.index('id = "DSP0236"')
    nxt = after.index("[[documents]]", dsp)
    block = after[dsp:nxt]
    assert 'version = "1.3.4"' in block
    assert block.index('version = "1.4.0"') < block.index('version = "1.3.4"')
    assert block.rstrip("\n").endswith('published = "2026-08-03"')
    assert block.endswith('published = "2026-08-03"\n\n')  # one blank line, as before
    code, out = run(capsys, "refresh", "DSP0236", catalog_file=catalog_file)
    assert out.splitlines()[0].startswith("changed DSP0236 1.3.3")
    assert "add DSP0236" not in out


def test_refresh_restores_the_catalog_when_the_edit_would_not_parse(
    catalog_file, library, pages, capsys, monkeypatch
):
    monkeypatch.setattr(
        R, "version_block", lambda seen: "[[documents.versions]]\nversion = 1\n"
    )
    before = catalog_file.read_text("utf-8")
    code, out = run(capsys, "refresh", "DSP0236", "--write", catalog_file=catalog_file)
    assert code == 1 and "cannot write DSP0236" in out and "restored" in out
    assert catalog_file.read_text("utf-8") == before


def test_refresh_unreachable_and_unlisted(catalog_file, library, scripted, capsys):
    code, out = run(capsys, "refresh", "DSP0236", catalog_file=catalog_file)
    assert code == 0
    assert out.splitlines()[0].startswith("unreachable DSP0236: ")
    assert out.splitlines()[-1].startswith(
        "summary: add 0, confirm 0, changed 0, unreachable 1"
    )
    code, out = run(capsys, "refresh", "IPMI", catalog_file=catalog_file)
    assert code == 2


def test_document_span_and_block_text(tmp_path):
    text = (
        '# head\n\n[[documents]]\nid = "A"\n\n[[documents.versions]]\nversion = "1"\n\n'
        '# ---------------- next\n\n[[documents]]\nid = "B"\n'
    )
    lines = text.split("\n")
    assert R._document_span(lines, "a") == (2, 8)
    assert R._document_span(lines, "B") == (10, len(lines))
    with pytest.raises(R.RefreshError):
        R._document_span(lines, "C")
    assert R.version_block(L.Seen("2", "https://x/y.zip", "2026-01-02")) == (
        '[[documents.versions]]\nversion = "2"\nurl = "https://x/y.zip"\n'
        'type = "zip"\npublished = "2026-01-02"\n'
    )
    assert R.version_block(L.Seen("3", "https://x/z.pdf", "2027-01-01", "WIP")) == (
        '[[documents.versions]]\nversion = "3"\nurl = "https://x/z.pdf"\n'
        'type = "pdf"\npublished = "2027-01-01"\nnotes = "WIP"\n'
    )


# ------------------------------------------------------- round 1 fixes


def test_refresh_never_writes_a_work_in_progress_row(
    catalog_file, library, pages, capsys
):
    """F1: a WIP row the catalog lacks is reported as confirm, not added."""
    text = catalog_file.read_text("utf-8")
    start = text.index('[[documents.versions]]\nversion = "1.4.0"')
    end = text.index("[[documents]]", start)
    catalog_file.write_text(text[:start] + text[end:], encoding="utf-8", newline="")
    assert load_catalog(catalog_file).get("DSP0236").find_version("1.4.0") is None
    code, out = run(capsys, "refresh", "DSP0236", "--write", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    wip = [ln for ln in lines if ln.startswith("confirm DSP0236 1.4.0")]
    assert len(wip) == 1
    assert wip[0].endswith(
        "[Work in Progress] (work in progress, not written; add it by hand "
        "with wip = true)"
    )
    assert "wrote 1 version(s) of DSP0236" in out  # 1.3.4 only
    doc = load_catalog(catalog_file).get("DSP0236")
    assert doc.find_version("1.3.4") is not None
    assert doc.find_version("1.4.0") is None
    assert doc.latest().version == "1.3.4"


def test_version_block_escapes_quotes_and_backslashes():
    """F2: publisher strings with a quote still make a TOML the parser reads."""
    block = R.version_block(
        L.Seen('1.0 "final"', "https://x/a\\b.pdf", "2026-01-02", 'say "hi"')
    )
    assert block == (
        "[[documents.versions]]\n"
        'version = "1.0 \\"final\\""\n'
        'url = "https://x/a\\\\b.pdf"\n'
        'type = "pdf"\n'
        'published = "2026-01-02"\n'
        'notes = "say \\"hi\\""\n'
    )
    import tomllib

    parsed = tomllib.loads("[[documents]]\n" + block)
    assert parsed["documents"][0]["versions"][0]["version"] == '1.0 "final"'


def test_refresh_reports_a_moved_nvme_file(catalog_file, library, scripted, capsys):
    """F5: `changed` covers NVMe, not only DMTF."""
    moved = (
        NVME_JSON.replace(
            "Revision-2.1-2025.08.01-Ratified.pdf",
            "Revision-2.1-2025.08.02-Ratified.pdf",
        )
        .replace("Revision-2.2-", "Revision-2.1-")
        .replace("2026.07.31", "2025.08.02")
    )
    scripted.responses[L.NVME_API] = ok(moved.encode(), "application/json")
    code, out = run(capsys, "refresh", "NVME-MI", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0].startswith("changed NVME-MI 2.1 (2025-08-02) ")
    assert "add NVME-MI" not in out


def test_status_survives_a_malformed_catalog(library, tmp_path, capsys, monkeypatch):
    """F6: status prints the holdings and a note, exit 0, without a catalog."""
    from bmc_toolkit.spec.library import Library

    lib = Library(library.root)
    lib.store("mctp", "DSP0236", "1.3.3", PDF_BYTES, "pdf", url="u", method="direct")
    bad = tmp_path / "bad.toml"
    bad.write_text("schema_version = 1\n[families\n", encoding="utf-8")
    code, out = run(capsys, "status", catalog_file=bad)
    assert code == 0
    lines = out.splitlines()
    assert lines[1].startswith("mctp\tDSP0236\t1.3.3")
    assert lines[-1].startswith(
        "note: freshness not checked, the catalog does not load"
    )


def test_document_span_ignores_ids_in_repos_blocks():
    """F7: a repository sharing a document's id does not stand in for it."""
    lines = (
        '[[repos]]\nid = "X"\nurl = "https://x"\n\n'
        '[[documents]]\nid = "X"\nfamily = "f"\n\n[[documents.versions]]\nversion = "1"\n'
    ).split("\n")
    assert R._document_span(lines, "X") == (4, len(lines))
    only_repo = '[[repos]]\nid = "Y"\n'.split("\n")
    with pytest.raises(R.RefreshError):
        R._document_span(only_repo, "Y")


# ---------------------------------------------------------- M8 follow-ups


def test_refresh_write_orders_same_day_versions_by_their_numbers(catalog_file):
    # DMTF publishes the errata of several branches on one day and lists
    # the higher branch first; the catalog keeps same-day versions ascending
    # so that the file order matches what latest() picks.
    seen = [
        L.Seen("1.5.0", "https://example.test/DSP0236_1.5.0.pdf", "2026-08-03"),
        L.Seen("1.3.4", "https://example.test/DSP0236_1.3.4.pdf", "2026-08-03"),
        L.Seen("1.3.5", "https://example.test/DSP0236_1.3.5.pdf", "2026-09-01"),
    ]
    R.append_versions(catalog_file, "DSP0236", seen)
    text = catalog_file.read_text("utf-8")
    assert (
        text.index('version = "1.3.4"')
        < text.index('version = "1.5.0"')
        < text.index('version = "1.3.5"')
    )
    assert load_catalog(catalog_file).get("DSP0236").latest().version == "1.3.5"
