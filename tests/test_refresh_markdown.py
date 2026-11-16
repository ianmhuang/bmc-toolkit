"""refresh and pinned Markdown versions (T5.3): the newest commit touching
the file is compared with the pin, reported and never written."""

import json

import pytest

from bmc_toolkit.spec import fetch as fetch_mod
from bmc_toolkit.spec import refresh as refresh_mod
from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_catalog_workflow import _run_refresh_block

PINNED = "a" * 40
NEWER = "b" * 40
RAW = "https://raw.githubusercontent.com/chips/RoT/{sha}/doc/Ro T.md"
API = "https://api.github.com/repos/chips/RoT/commits?path=doc/Ro%20T.md&per_page=1"
OLD_RAW = "https://raw.githubusercontent.com/chips/RoT/" + "c" * 40 + "/doc/Old.md"

MD_CATALOG = (
    MINI_CATALOG
    + f"""
[families.security]
title = "Security"
publisher = "various"

[[documents]]
id = "ROT"
family = "security"
title = "A root of trust specification"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "2.0"
url = "{OLD_RAW}"
type = "md"
published = "2025-07-31"

[[documents.versions]]
version = "2.1"
url = "{RAW.format(sha=PINNED)}"
type = "md"
published = "2026-09-17"
wip = true

[[documents]]
id = "ELSEWHERE"
family = "security"
title = "Markdown on another host"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "https://example.test/{PINNED}/doc.md"
type = "md"
published = "2026-01-01"

[[documents]]
id = "SHORTPIN"
family = "security"
title = "Markdown pinned to a short id"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "https://raw.githubusercontent.com/chips/RoT/abc1234/doc/x.md"
type = "md"
published = "2026-01-01"

[[documents]]
id = "HANDPDF"
family = "security"
title = "A PDF maintained by hand"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "https://example.test/hand.pdf"
type = "pdf"
published = "2026-01-01"
"""
)

CHANGED = (
    "changed ROT 2.1: doc/Ro T.md has commit bbbbbbb (2026-11-20), the catalog "
    f"pins aaaaaaa; {RAW.format(sha=NEWER)} (not written; re-pin by hand)"
)


def commits(*items, status=200):
    body = json.dumps(list(items)).encode()
    return fetch_mod.Response(status, {"content-type": "application/json"}, body)


def commit(sha, date="2026-11-20T08:00:00Z"):
    return {"sha": sha, "commit": {"committer": {"date": date}}}


def raw_reply(body: bytes, status=200):
    return fetch_mod.Response(status, {}, body)


@pytest.fixture
def md_catalog(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(MD_CATALOG, encoding="utf-8", newline="")
    return path


def run(capsys, catalog, *argv):
    code = main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


def lines(out):
    return out.strip().splitlines()


# ------------------------------------------------------------------ AC-1


def test_the_pinned_commit_being_the_newest_prints_nothing(
    md_catalog, scripted, capsys
):
    scripted.responses[API] = commits(commit(PINNED))
    code, out = run(capsys, md_catalog, "refresh", "ROT")
    assert code == 0
    assert lines(out) == [
        "summary: add 0, confirm 0, changed 0, unreachable 0 "
        "(dry run; --write adds them)"
    ]
    # the newest Markdown version only: 2.0's older pin is not asked about
    assert scripted.calls == [API]


def test_a_newer_commit_is_reported_with_the_url_to_re_pin_to(
    md_catalog, scripted, capsys
):
    scripted.responses[API] = commits(commit(NEWER), commit(PINNED))
    code, out = run(capsys, md_catalog, "refresh", "ROT")
    assert code == 0
    assert lines(out) == [
        CHANGED,
        "summary: add 0, confirm 0, changed 1, unreachable 0 "
        "(dry run; --write adds them)",
    ]


def test_the_newest_markdown_version_is_the_last_listed():
    doc = load_catalog().get("CALIPTRA")
    assert refresh_mod.markdown_version(doc).version == "2.1"
    assert refresh_mod.markdown_version(load_catalog().get("OCP-ATTEST")) is None


# ------------------------------------------------------------------ AC-2


def test_write_leaves_the_catalog_byte_identical(md_catalog, scripted, capsys):
    before = md_catalog.read_bytes()
    scripted.responses[API] = commits(commit(NEWER))
    code, out = run(capsys, md_catalog, "refresh", "ROT", "--write")
    assert code == 0
    assert lines(out) == [
        CHANGED,
        "summary: add 0, confirm 0, changed 1, unreachable 0, written 0",
    ]
    assert md_catalog.read_bytes() == before


# ------------------------------------------------------------------ AC-3


@pytest.mark.parametrize(
    "doc_id, url",
    [
        ("ELSEWHERE", f"https://example.test/{PINNED}/doc.md"),
        ("SHORTPIN", "https://raw.githubusercontent.com/chips/RoT/abc1234/doc/x.md"),
    ],
    ids=["other-host", "short-id"],
)
def test_an_unpinned_or_foreign_url_is_a_confirm_without_a_request(
    md_catalog, scripted, capsys, doc_id, url
):
    code, out = run(capsys, md_catalog, "refresh", doc_id)
    assert code == 0
    assert lines(out)[0] == (
        f"confirm {doc_id} 1.0: {url} "
        "(cannot check: not a pinned raw.githubusercontent.com URL)"
    )
    assert "confirm 1," in lines(out)[1]
    assert scripted.calls == []


# ------------------------------------------------------------------ AC-4


@pytest.mark.parametrize(
    "reply, reason",
    [
        (OSError("connection reset"), f"{API}: connection reset"),
        (
            commits(status=403),
            f"{API}: HTTP 403 (the GitHub API rate limit: 60 requests an hour "
            "without a token; try again later)",
        ),
        (
            commits(status=429),
            f"{API}: HTTP 429 (the GitHub API rate limit: 60 requests an hour "
            "without a token; try again later)",
        ),
        (commits(status=404), f"{API}: HTTP 404"),
        (raw_reply(b"<html>busy</html>"), f"{API}: the reply is not JSON"),
        (raw_reply(b"\xff\xfe"), f"{API}: the reply is not JSON"),
        (
            raw_reply(b'{"message": "Not Found"}'),
            f"{API}: the reply is not a list of commits",
        ),
        (
            commits({"sha": NEWER}),
            f"{API}: the first commit has no sha or committer date",
        ),
        (commits("text"), f"{API}: the first commit has no sha or committer date"),
        (
            commits(commit("not-a-sha")),
            f"{API}: the first commit's sha is not a commit id",
        ),
        (
            commits(commit(NEWER, date="yesterday")),
            f"{API}: the first commit's date is not a date",
        ),
        (commits(), "doc/Ro T.md has no commit on the default branch of chips/RoT"),
    ],
    ids=[
        "network",
        "403",
        "429",
        "404",
        "html",
        "not-utf8",
        "object",
        "no-date",
        "not-a-dict",
        "bad-sha",
        "bad-date",
        "empty",
    ],
)
def test_a_failed_check_is_unreachable_and_exit_0(
    md_catalog, scripted, capsys, reply, reason
):
    scripted.responses[API] = reply
    code, out = run(capsys, md_catalog, "refresh", "ROT")
    assert code == 0
    assert lines(out) == [
        f"unreachable ROT 2.1: {reason}",
        "summary: add 0, confirm 0, changed 0, unreachable 1 "
        "(dry run; --write adds them)",
    ]


# ------------------------------------------------------------------ AC-5


def test_a_document_with_neither_keeps_its_message(md_catalog, scripted, capsys):
    code, out = run(capsys, md_catalog, "refresh", "HANDPDF")
    assert code == 2
    assert out.strip() == (
        "HANDPDF has no publisher listing; its versions are maintained by hand "
        "in the catalog"
    )
    assert scripted.calls == []


def test_a_document_with_a_listing_and_markdown_gets_both(
    md_catalog, scripted, capsys, monkeypatch
):
    text = md_catalog.read_text("utf-8").replace(
        'title = "A root of trust specification"\n',
        'title = "A root of trust specification"\nlisting = "dmtf:DSP9999"\n',
    )
    md_catalog.write_text(text, encoding="utf-8", newline="")
    seen = []

    def listing_proposals(doc, listings):
        seen.append(doc.id)
        return [refresh_mod.Proposal("unreachable", doc.id, problem="listing down")]

    monkeypatch.setattr(refresh_mod, "proposals", listing_proposals)
    scripted.responses[API] = commits(commit(NEWER))
    code, out = run(capsys, md_catalog, "refresh", "ROT")
    assert code == 0
    assert seen == ["ROT"]
    assert lines(out) == [
        CHANGED,
        "unreachable ROT: listing down",
        "summary: add 0, confirm 0, changed 1, unreachable 1 "
        "(dry run; --write adds them)",
    ]


def test_refresh_of_every_document_includes_markdown_ones(
    md_catalog, scripted, capsys, monkeypatch
):
    monkeypatch.setattr(refresh_mod, "proposals", lambda doc, listings: [])
    monkeypatch.setattr(refresh_mod, "unlisted", lambda catalog, listings: [])
    scripted.responses[API] = commits(commit(NEWER))
    code, out = run(capsys, md_catalog, "refresh")
    assert code == 0
    assert CHANGED in lines(out)
    assert scripted.calls == [API]  # ELSEWHERE and SHORTPIN make no request
    assert lines(out)[-1].startswith("summary: add 0, confirm 2, changed 1,")


# ------------------------------------------------------------------ AC-6


def test_skip_source_github_leaves_the_check_out(
    md_catalog, scripted, capsys, monkeypatch
):
    monkeypatch.setattr(refresh_mod, "proposals", lambda doc, listings: [])
    monkeypatch.setattr(refresh_mod, "unlisted", lambda catalog, listings: [])
    code, out = run(capsys, md_catalog, "refresh", "--skip-source", "github")
    assert code == 0
    assert "ROT" not in out and "confirm 0" in out
    assert not [c for c in scripted.calls if "api.github.com" in c]


def test_skip_source_github_on_a_markdown_only_document(md_catalog, scripted, capsys):
    code, out = run(capsys, md_catalog, "refresh", "ROT", "--skip-source", "github")
    assert code == 2
    assert out.strip() == "ROT is checked on github, which --skip-source leaves out"
    assert scripted.calls == []


def test_github_is_an_accepted_skip_source_and_others_are_not(md_catalog, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--catalog", str(md_catalog), "refresh", "--skip-source", "gitlab"])
    assert exc.value.code == 2
    assert "github" in capsys.readouterr().err


# ------------------------------------------------------------------ AC-7


def test_check_makes_no_github_request(md_catalog, scripted, capsys, library):
    scripted.responses[API] = commits(commit(NEWER))
    run(capsys, md_catalog, "check")
    assert not [c for c in scripted.calls if "api.github.com" in c]
    code, out = run(capsys, md_catalog, "check", "ROT")
    assert code == 2 and "has no publisher listing" in out
    assert not [c for c in scripted.calls if "api.github.com" in c]


# ------------------------------------------------------------------ AC-8


def test_the_workflow_counts_a_changed_pin(md_catalog, scripted, capsys, tmp_path):
    scripted.responses[API] = commits(commit(NEWER))
    _, out = run(capsys, md_catalog, "refresh", "ROT")
    proc, summary, proposals = _run_refresh_block(tmp_path, out)
    assert proc.returncode == 0, proc.stderr
    assert proposals == "1"
    assert CHANGED in summary
