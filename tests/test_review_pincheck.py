"""Reviewer acceptance tests for ``refresh`` and pinned Markdown versions:
the commit check (AC-1), never written (AC-2), URLs it cannot check (AC-3),
failed checks (AC-4), documents with and without a listing (AC-5),
``--skip-source github`` (AC-6), no GitHub request outside ``refresh``
(AC-7) and the catalog workflow's count (AC-8).

Black-box through ``bmc_toolkit.spec.cli.main`` with the scripted client of
conftest: every request the command makes is in ``scripted.calls``, and a
URL that is not served raises ``OSError``. Nothing touches the network.
"""

import json
import re

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec.fetch import Response
from tests.conftest import MINI_CATALOG, ok
from tests.test_catalog_workflow import _run_refresh_block

# The real after-output Freshness Check: conftest's autouse fixture replaces
# it with a no-op for every test, and the reading test here puts it back.
REAL_CHECK = cli._check_when_due

PINNED = "1f3a5c7e9b" * 4
NEWER = "0a2b4c6d8e" * 4
OLDER = "9e8d7c6b5a" * 4


def raw(repo: str, sha: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"


def api(repo: str, path: str) -> str:
    return f"https://api.github.com/repos/{repo}/commits?path={path}&per_page=1"


API_SPEC = api("acme/rot-spec", "docs/spec.md")
API_OLD = api("acme/rot-spec", "docs/old.md")
API_SECOND = api("acme/second", "README.md")
API_DSP = api("acme/dsp", "spec/DSP0999.md")

FOREIGN_URL = f"https://git.example.test/acme/rot-spec/{PINNED}/docs/spec.md"
SHORT_URL = raw("acme/rot-spec", "1f3a5c7", "docs/spec.md")
BRANCH_URL = raw("acme/rot-spec", "main", "docs/spec.md")

DMTF_PUBLISHED = "https://www.dmtf.org/standards/published_documents"
DMTF_DSP0236 = "https://www.dmtf.org/dsp/DSP0236"
DMTF_DSP0999 = "https://www.dmtf.org/dsp/DSP0999"
URL_132 = "https://example.test/DSP0236_1.3.2.pdf"
URL_133 = "https://example.test/DSP0236_1.3.3.pdf"
URL_134 = "https://example.test/DSP0236_1.3.4.pdf"
URL_140 = "https://example.test/DSP0236_1.4.0.pdf"

# MDSPEC and MDSECOND have no listing, only Markdown versions; MDSPEC's
# newest one (1.1) pins PINNED, its older one another file at OLDER.
CATALOG = (
    MINI_CATALOG
    + f"""
[families.security]
title = "Security"
publisher = "various"

[[documents]]
id = "MDSPEC"
family = "security"
title = "A Markdown specification kept in a repository"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "{raw("acme/rot-spec", OLDER, "docs/old.md")}"
type = "md"
published = "2025-03-01"

[[documents.versions]]
version = "1.1"
url = "{raw("acme/rot-spec", PINNED, "docs/spec.md")}"
type = "md"
published = "2026-06-01"

[[documents]]
id = "MDSECOND"
family = "security"
title = "A second Markdown specification"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "0.9"
url = "{raw("acme/second", PINNED, "README.md")}"
type = "md"
published = "2026-02-01"

[[documents]]
id = "FOREIGN"
family = "security"
title = "Markdown on another host"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "{FOREIGN_URL}"
type = "md"
published = "2026-01-01"

[[documents]]
id = "SHORT"
family = "security"
title = "Markdown pinned to an abbreviated commit id"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "{SHORT_URL}"
type = "md"
published = "2026-01-01"

[[documents]]
id = "BRANCH"
family = "security"
title = "Markdown that follows a branch"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "{BRANCH_URL}"
type = "md"
published = "2026-01-01"
"""
)

# DSP0999: a DMTF document (implied dmtf listing) whose latest version is
# Markdown, so it has both a listing and a pin.
BOTH = (
    CATALOG
    + f"""
[[documents]]
id = "DSP0999"
family = "mctp"
title = "A DMTF document whose newest version is Markdown"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0.0"
url = "https://example.test/DSP0999_1.0.0.pdf"
type = "pdf"
published = "2024-05-01"

[[documents.versions]]
version = "1.1.0"
url = "{raw("acme/dsp", PINNED, "spec/DSP0999.md")}"
type = "md"
published = "2026-05-01"
"""
)

PUBLISHED_HTML = f"""
<html><body><table><thead><tr>
<th>DSP</th><th>Version</th><th>Title</th><th>Comments</th><th>DSP</th>
</tr></thead><tbody>
<tr><td>DSP0236</td><td>1.3.4</td><td><a href="{URL_134}">MCTP Base</a></td>
<td>Standard</td><td><a href="/dsp/DSP0236">View</a></td></tr>
</tbody></table></body></html>
"""

DSP_HTML = f"""
<html><body><h1>All Published Versions of DSP0236</h1>
<table><thead><tr>
<th>Version</th><th>Title</th><th>Publication Date</th><th>Comments</th>
</tr></thead><tbody>
<tr><td>1.3.4</td><td><a href="{URL_134}">MCTP Base</a></td>
<td>3 Aug 2026</td><td>Standard</td></tr>
<tr><td>1.3.3</td><td><a href="{URL_133}">MCTP Base</a></td>
<td>25 Mar 2024</td><td>Standard</td></tr>
<tr><td>1.3.2</td><td><a href="{URL_132}">MCTP Base</a></td>
<td>2 Jan 2024</td><td>Standard</td></tr>
<tr><td>1.4.0</td><td><a href="{URL_140}">MCTP Base</a></td>
<td>1 Jun 2025</td><td>Work in Progress</td></tr>
</tbody></table></body></html>
"""

MD_BODY = b"# Overview\nThe device boots from ROM.\n\n## Scope\nScope of it.\n"

DRY = " (dry run; --write adds them)"
MOVED = (
    "changed MDSPEC 1.1: docs/spec.md has commit 0a2b4c6 (2026-11-20), the "
    f"catalog pins 1f3a5c7; {raw('acme/rot-spec', NEWER, 'docs/spec.md')} "
    "(not written; re-pin by hand)"
)


def commit(sha, committed="2026-11-20T08:15:00Z", authored="2026-10-02T10:00:00Z"):
    """One item of a commits API reply, with the fields GitHub sends that
    matter here; the author date differs from the committer date."""
    return {
        "sha": sha,
        "commit": {
            "author": {"name": "A", "date": authored},
            "committer": {"name": "C", "date": committed},
            "message": "edit",
        },
        "html_url": f"https://github.com/acme/rot-spec/commit/{sha}",
    }


def reply(*commits, status=200):
    body = json.dumps(list(commits)).encode("utf-8")
    return Response(status, {"content-type": "application/json; charset=utf-8"}, body)


def body_reply(body: bytes, status=200):
    return Response(status, {"content-type": "application/json"}, body)


def html(text: str) -> Response:
    return Response(200, {"content-type": "text/html"}, text.encode("utf-8"))


def summary(add=0, confirm=0, changed=0, unreachable=0, tail=DRY):
    return (
        f"summary: add {add}, confirm {confirm}, changed {changed}, "
        f"unreachable {unreachable}{tail}"
    )


def github_calls(calls):
    return [c for c in calls if "api.github.com" in c]


@pytest.fixture
def catalog_file(tmp_path, library):
    path = tmp_path / "catalog.toml"
    path.write_text(CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def both_file(tmp_path, library):
    path = tmp_path / "both.toml"
    path.write_text(BOTH, encoding="utf-8", newline="")
    return path


def run(capsys, catalog, *argv):
    code = cli.main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


# ------------------------------------------------------------------- AC-1


def test_pinned_commit_is_the_newest_prints_nothing_and_asks_once(
    catalog_file, scripted, capsys
):
    scripted.responses[API_SPEC] = reply(commit(PINNED), commit(OLDER))
    scripted.responses[API_OLD] = reply(commit(NEWER))
    code, out = run(capsys, catalog_file, "refresh", "MDSPEC")
    assert code == 0, out
    assert out.splitlines() == [summary()]
    # one request, in the AC's form, for the newest Markdown version only:
    # 1.0's file would report a newer commit if it were asked about
    assert scripted.calls == [API_SPEC]


def test_newer_commit_is_reported_in_the_ac_line_and_counted_as_changed(
    catalog_file, scripted, capsys
):
    scripted.responses[API_SPEC] = reply(commit(NEWER), commit(PINNED))
    code, out = run(capsys, catalog_file, "refresh", "MDSPEC")
    assert code == 0, out
    assert out.splitlines() == [MOVED, summary(changed=1)]
    assert scripted.calls == [API_SPEC]


def test_the_date_printed_is_the_committer_date(catalog_file, scripted, capsys):
    scripted.responses[API_SPEC] = reply(
        commit(NEWER, committed="2026-07-04T23:59:59Z", authored="2026-01-31T00:00:00Z")
    )
    code, out = run(capsys, catalog_file, "refresh", "MDSPEC")
    assert code == 0, out
    (line,) = [ln for ln in out.splitlines() if ln.startswith("changed ")]
    assert "has commit 0a2b4c6 (2026-07-04), the catalog pins 1f3a5c7" in line
    assert "2026-01-31" not in line


def test_refresh_without_a_document_checks_every_markdown_document(
    catalog_file, scripted, capsys
):
    scripted.responses[API_SPEC] = reply(commit(NEWER))
    scripted.responses[API_SECOND] = reply(commit(NEWER))
    code, out = run(capsys, catalog_file, "refresh", "--skip-source", "dmtf")
    assert code == 0, out
    lines = out.splitlines()
    assert MOVED in lines
    assert (
        "changed MDSECOND 0.9: README.md has commit 0a2b4c6 (2026-11-20), the "
        f"catalog pins 1f3a5c7; {raw('acme/second', NEWER, 'README.md')} "
        "(not written; re-pin by hand)"
    ) in lines
    # one request per pinned document; the three that cannot be checked
    # (AC-3) make none and are the three confirms
    assert sorted(scripted.calls) == sorted([API_SPEC, API_SECOND])
    assert lines[-1] == summary(confirm=3, changed=2)


# ------------------------------------------------------------------- AC-2


def test_write_never_edits_a_markdown_version(catalog_file, scripted, capsys):
    before = catalog_file.read_bytes()
    scripted.responses[API_SPEC] = reply(commit(NEWER))
    code, out = run(capsys, catalog_file, "refresh", "MDSPEC", "--write")
    assert code == 0, out
    assert out.splitlines() == [MOVED, summary(changed=1, tail=", written 0")]
    assert catalog_file.read_bytes() == before


def test_write_adds_the_listing_version_and_leaves_the_pin_alone(
    catalog_file, scripted, capsys
):
    """A whole-catalog ``--write``: DMTF's new DSP0236 version is written
    and counted, the moved pin is reported and neither written nor counted
    in ``written``."""
    scripted.responses[DMTF_PUBLISHED] = html(PUBLISHED_HTML)
    scripted.responses[DMTF_DSP0236] = html(DSP_HTML)
    scripted.responses[API_SPEC] = reply(commit(NEWER))
    scripted.responses[API_SECOND] = reply(commit(PINNED))
    before = catalog_file.read_text("utf-8")
    code, out = run(capsys, catalog_file, "refresh", "--write")
    assert code == 0, out
    lines = out.splitlines()
    assert MOVED in lines
    assert any(ln.startswith("add DSP0236 1.3.4") for ln in lines), out
    last = lines[-1]
    assert last.startswith("summary: add 1, confirm 3, changed 1, unreachable 0"), out
    assert last.endswith("written 1"), out
    after = catalog_file.read_text("utf-8")
    assert f'url = "{URL_134}"' in after  # the DMTF proposal landed
    assert NEWER not in after
    # everything from the Markdown documents on is as it was
    mark = "[families.security]"
    assert after[after.index(mark) :] == before[before.index(mark) :]


# ------------------------------------------------------------------- AC-3


@pytest.mark.parametrize(
    "doc_id, url",
    [("FOREIGN", FOREIGN_URL), ("SHORT", SHORT_URL), ("BRANCH", BRANCH_URL)],
    ids=["another-host", "seven-hex", "branch-name"],
)
def test_a_url_that_is_not_a_full_pin_is_a_confirm_and_is_not_requested(
    catalog_file, scripted, capsys, doc_id, url
):
    code, out = run(capsys, catalog_file, "refresh", doc_id)
    assert code == 0, out
    assert out.splitlines() == [
        f"confirm {doc_id} 1.0: {url} "
        "(cannot check: not a pinned raw.githubusercontent.com URL)",
        summary(confirm=1),
    ]
    assert scripted.calls == []


# ------------------------------------------------------------------- AC-4


@pytest.mark.parametrize(
    "served",
    [
        OSError("connection reset by peer"),
        body_reply(b'{"message": "Not Found"}', status=404),
        body_reply(b"", status=500),
        body_reply(b"", status=304),
        body_reply(b"<html><body>Unicorn!</body></html>"),
        body_reply(b""),
        body_reply(b'{"message": "Moved", "url": "https://api.github.com/x"}'),
        body_reply(json.dumps([{"sha": NEWER}]).encode()),
        body_reply(
            json.dumps([{"commit": {"committer": {"date": "2026-11-20T08:15:00Z"}}}])
            .encode()
        ),
        body_reply(json.dumps([{"sha": NEWER, "commit": {"committer": {}}}]).encode()),
        reply(),
    ],
    ids=[
        "network-error",
        "http-404",
        "http-500",
        "http-304",
        "html-body",
        "empty-body",
        "json-object",
        "no-committer-date",
        "no-sha",
        "committer-without-date",
        "empty-list",
    ],
)
def test_a_failed_check_is_one_unreachable_line_and_exit_0(
    catalog_file, scripted, capsys, served
):
    scripted.responses[API_SPEC] = served
    code, out = run(capsys, catalog_file, "refresh", "MDSPEC")
    assert code == 0, out
    lines = out.splitlines()
    assert len(lines) == 2, out
    assert re.match(r"unreachable MDSPEC 1\.1: \S", lines[0]), out
    assert lines[1] == summary(unreachable=1)
    assert scripted.calls == [API_SPEC]  # asked once, not retried


def test_http_403_names_the_github_rate_limit(catalog_file, scripted, capsys):
    scripted.responses[API_SPEC] = body_reply(
        b'{"message": "API rate limit exceeded"}', status=403
    )
    code, out = run(capsys, catalog_file, "refresh", "MDSPEC")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0].startswith("unreachable MDSPEC 1.1: "), out
    assert "403" in lines[0] and "rate limit" in lines[0].lower(), out
    assert lines[1] == summary(unreachable=1)


def test_a_failed_check_with_write_leaves_the_catalog_alone(
    catalog_file, scripted, capsys
):
    before = catalog_file.read_bytes()
    code, out = run(capsys, catalog_file, "refresh", "MDSPEC", "--write")
    assert code == 0, out  # the API is not served: a network error
    assert out.splitlines()[-1] == summary(unreachable=1, tail=", written 0")
    assert catalog_file.read_bytes() == before


# ------------------------------------------------------------------- AC-5


def test_a_document_without_listing_or_markdown_keeps_its_message(
    catalog_file, scripted, capsys
):
    # with a Markdown version and no listing: the check runs
    scripted.responses[API_SPEC] = reply(commit(PINNED))
    code, out = run(capsys, catalog_file, "refresh", "MDSPEC")
    assert (code, out.splitlines()) == (0, [summary()])
    scripted.calls.clear()
    # with neither: as before
    code, out = run(capsys, catalog_file, "refresh", "IPMI")
    assert code == 2
    assert "IPMI has no publisher listing" in out
    assert "summary:" not in out
    assert scripted.calls == []
    # and an unknown document is still unknown
    code, out = run(capsys, catalog_file, "refresh", "NOPE")
    assert code == 2
    assert "unknown document 'NOPE'" in out
    assert scripted.calls == []


def test_a_document_with_a_listing_and_markdown_gets_both(both_file, scripted, capsys):
    scripted.responses[API_DSP] = reply(commit(NEWER))
    code, out = run(capsys, both_file, "refresh", "DSP0999")
    assert code == 0, out
    lines = out.splitlines()
    # the pin check
    assert (
        "changed DSP0999 1.1.0: spec/DSP0999.md has commit 0a2b4c6 (2026-11-20), "
        f"the catalog pins 1f3a5c7; {raw('acme/dsp', NEWER, 'spec/DSP0999.md')} "
        "(not written; re-pin by hand)"
    ) in lines
    # the listing: DMTF's page is not served here, which the listing says
    assert any(ln.startswith("unreachable DSP0999: ") for ln in lines), out
    assert lines[-1] == summary(changed=1, unreachable=1)
    assert API_DSP in scripted.calls and DMTF_DSP0999 in scripted.calls


# ------------------------------------------------------------------- AC-6


def test_skip_source_github_leaves_every_pin_check_out(catalog_file, scripted, capsys):
    scripted.responses[API_SPEC] = reply(commit(NEWER))
    scripted.responses[API_SECOND] = reply(commit(NEWER))
    code, out = run(
        capsys,
        catalog_file,
        "refresh",
        "--skip-source",
        "github",
        "--skip-source",
        "dmtf",
    )
    assert code == 0, out
    # neither requested nor reported: no changed, and no confirm for the
    # URLs that cannot be checked
    assert scripted.calls == []
    assert out.splitlines() == [summary()]


def test_skip_source_github_keeps_the_listings(both_file, scripted, capsys):
    scripted.responses[API_DSP] = reply(commit(NEWER))
    code, out = run(capsys, both_file, "refresh", "--skip-source", "github")
    assert code == 0, out
    assert github_calls(scripted.calls) == []
    assert DMTF_DSP0236 in scripted.calls and DMTF_DSP0999 in scripted.calls
    assert "MDSPEC" not in out and "changed" not in out.replace("changed 0", "")


@pytest.mark.parametrize("doc_id", ["MDSPEC", "FOREIGN"])
def test_naming_a_markdown_only_document_with_github_skipped_exits_2(
    catalog_file, scripted, capsys, doc_id
):
    scripted.responses[API_SPEC] = reply(commit(NEWER))
    before = catalog_file.read_bytes()
    code, out = run(
        capsys, catalog_file, "refresh", doc_id, "--skip-source", "github", "--write"
    )
    assert code == 2, out
    lines = out.strip().splitlines()
    assert len(lines) == 1, out
    assert doc_id in lines[0] and "github" in lines[0]
    assert "--skip-source" in lines[0]
    assert "summary:" not in out
    assert scripted.calls == []
    assert catalog_file.read_bytes() == before


def test_a_document_with_both_runs_whichever_check_is_not_skipped(
    both_file, scripted, capsys
):
    scripted.responses[API_DSP] = reply(commit(NEWER))
    # the listing skipped: the pin check alone
    code, out = run(capsys, both_file, "refresh", "DSP0999", "--skip-source", "dmtf")
    assert code == 0, out
    assert scripted.calls == [API_DSP]
    assert out.splitlines()[-1] == summary(changed=1)
    # the pin check skipped: the listing alone
    scripted.calls.clear()
    code, out = run(capsys, both_file, "refresh", "DSP0999", "--skip-source", "github")
    assert code == 0, out
    assert github_calls(scripted.calls) == []
    assert DMTF_DSP0999 in scripted.calls
    assert out.splitlines()[-1] == summary(unreachable=1)
    # both skipped: nothing is left to run
    scripted.calls.clear()
    code, out = run(
        capsys,
        both_file,
        "refresh",
        "DSP0999",
        "--skip-source",
        "github",
        "--skip-source",
        "dmtf",
    )
    assert code == 2, out
    assert "DSP0999" in out and "--skip-source" in out
    assert "summary:" not in out
    assert scripted.calls == []


def test_github_is_listed_among_the_accepted_sources(catalog_file, scripted, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--catalog", str(catalog_file), "refresh", "--skip-source", "gitlab"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--skip-source" in err and "github" in err
    assert scripted.calls == []
    with pytest.raises(SystemExit) as exc:
        cli.main(["refresh", "--help"])
    assert exc.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "--skip-source SOURCE" in text and "github" in text
    for source in ("dmtf", "nvme", "ocp"):  # the listing sources are still there
        assert source in text


# ------------------------------------------------------------------- AC-7


def test_check_makes_no_github_request(both_file, scripted, capsys):
    scripted.responses[API_SPEC] = reply(commit(NEWER))
    scripted.responses[API_DSP] = reply(commit(NEWER))
    # refresh asks GitHub about the same catalog ...
    code, out = run(capsys, both_file, "refresh", "MDSPEC")
    assert (code, scripted.calls) == (0, [API_SPEC]), out
    # ... and check never does: not over the whole catalog,
    scripted.calls.clear()
    code, out = run(capsys, both_file, "check")
    assert code == 0, out
    assert scripted.calls, "check read no listing at all"
    assert github_calls(scripted.calls) == []
    assert "changed" not in out
    (unchecked,) = [ln for ln in out.splitlines() if ln.startswith("unchecked:")]
    assert "MDSPEC" in unchecked  # still a document nobody can check
    # not for a document with a listing and a pin,
    scripted.calls.clear()
    code, out = run(capsys, both_file, "check", "DSP0999")
    assert code == 0, out
    assert scripted.calls and github_calls(scripted.calls) == []
    # and a Markdown-only document is still not checkable
    scripted.calls.clear()
    code, out = run(capsys, both_file, "check", "MDSPEC")
    assert code == 2
    assert "MDSPEC has no publisher listing" in out
    assert scripted.calls == []


def test_a_reading_commands_freshness_check_makes_no_github_request(
    both_file, scripted, capsys, monkeypatch
):
    scripted.responses[API_DSP] = reply(commit(NEWER))
    # refresh asks GitHub about this document ...
    code, out = run(capsys, both_file, "refresh", "DSP0999", "--skip-source", "dmtf")
    assert (code, scripted.calls) == (0, [API_DSP]), out
    # ... and reading it, with its Freshness Check due, does not
    scripted.calls.clear()
    scripted.responses[raw("acme/dsp", PINNED, "spec/DSP0999.md")] = ok(
        MD_BODY, "text/plain; charset=utf-8"
    )
    monkeypatch.setattr(cli, "_check_when_due", REAL_CHECK)
    code, out = run(capsys, both_file, "section", "DSP0999", "overview")
    assert code == 0, out
    assert "Overview" in out
    assert any("dmtf.org" in c for c in scripted.calls), (
        "the Freshness Check did not run",
        scripted.calls,
        out,
    )
    assert github_calls(scripted.calls) == []
    assert "changed" not in out and "0a2b4c6" not in out


# ------------------------------------------------------------------- AC-8


def test_the_workflow_counts_a_moved_pin_as_one_proposal(
    catalog_file, scripted, capsys, tmp_path
):
    scripted.responses[API_SPEC] = reply(commit(NEWER))
    _, moved = run(capsys, catalog_file, "refresh", "MDSPEC")
    assert MOVED in moved.splitlines()
    scripted.responses[API_SPEC] = reply(commit(PINNED))
    _, same = run(capsys, catalog_file, "refresh", "MDSPEC")

    work = tmp_path / "moved"
    work.mkdir()
    proc, step_summary, proposals = _run_refresh_block(work, moved)
    assert proc.returncode == 0, proc.stderr
    assert proposals == "1"
    assert MOVED in step_summary

    work = tmp_path / "same"
    work.mkdir()
    proc, _step_summary, proposals = _run_refresh_block(work, same)
    assert proc.returncode == 0, proc.stderr
    assert proposals == "0"
