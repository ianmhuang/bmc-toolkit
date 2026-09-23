"""Acceptance tests for "Fetch reports an archive.org rate limit instead of
'no Wayback snapshot'": AC-1 to AC-5.

Black-box through ``bmc_toolkit.spec.cli.main`` with the scripted HTTP client
from conftest, so no test can reach the network. AC-3 and AC-4 name
``wayback_snapshot`` and ``check_body`` directly, so those two are also
exercised at the function level.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmc_toolkit.spec import fetch as fetch_mod  # noqa: E402
from bmc_toolkit.spec.cli import main  # noqa: E402
from tests.conftest import (  # noqa: E402
    HTML_BYTES,
    PDF_BYTES,
    ScriptedClient,
    ok,
    wayback_hit,
    wayback_miss,
)

URL = "https://example.test/DSP0236_1.3.3.pdf"
OLD_URL = "https://example.test/DSP0236_1.3.2.pdf"
IPMI_URL = "https://example.test/ipmi-v2-rev1-1.pdf"
WB_QUERY = fetch_mod.WAYBACK_AVAILABLE + URL
WB_RAW = "http://web.archive.org/web/20250101000000id_/" + URL

RATE_LIMITED = "rate limited by archive.org (HTTP 429), try again in "
NO_SNAPSHOT = "no Wayback snapshot"


def run(capsys, *argv, catalog_file):
    code = main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def status(code, headers=None, body=b""):
    return fetch_mod.Response(code, headers or {}, body)


def attempt_lines(out, document="DSP0236", version="1.3.3"):
    """The per-step attempt lines ``fetch`` prints for one version."""
    prefix = f"  {document} {version}: "
    return [ln[len(prefix) :] for ln in out.splitlines() if ln.startswith(prefix)]


# ----------------------------------------------------------------- AC-1


@pytest.mark.parametrize(
    "headers, wait",
    [
        ({}, "a few minutes"),
        ({"retry-after": "90"}, "90 s"),
        ({"retry-after": "Wed, 23 Sep 2026 07:28:00 GMT"}, "a few minutes"),
        ({"retry-after": ""}, "a few minutes"),
    ],
)
def test_fetch_names_a_throttled_availability_query(
    headers, wait, catalog_file, library, scripted, capsys
):
    scripted.responses[URL] = status(403, body=HTML_BYTES)
    scripted.responses[WB_QUERY] = status(429, headers)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 2, out
    assert attempt_lines(out) == [
        "direct: HTTP 403",
        f"wayback: {RATE_LIMITED}{wait}",
    ]
    assert NO_SNAPSHOT not in out
    assert "failed DSP0236 1.3.3" in out.splitlines()
    assert not (library.specs / "mctp" / "DSP0236" / "1.3.3").exists()


def test_a_wayback_only_document_reports_the_throttle_as_its_single_attempt(
    catalog_file, library, scripted, capsys
):
    # IPMI is fetch = "wayback": no direct step, so the throttle is the whole story.
    scripted.responses[fetch_mod.WAYBACK_AVAILABLE + IPMI_URL] = status(
        429, {"retry-after": "300"}
    )
    code, out = run(capsys, "fetch", "IPMI", catalog_file=catalog_file)
    assert code == 2, out
    assert attempt_lines(out, "IPMI", "2.0 rev 1.1") == [
        f"wayback: {RATE_LIMITED}300 s"
    ]
    assert NO_SNAPSHOT not in out
    assert scripted.calls == [fetch_mod.WAYBACK_AVAILABLE + IPMI_URL]


def test_a_throttled_query_does_not_try_to_download_a_snapshot(
    catalog_file, library, scripted, capsys
):
    scripted.responses[URL] = status(403, body=HTML_BYTES)
    scripted.responses[WB_QUERY] = status(429)
    scripted.responses[WB_RAW] = ok(PDF_BYTES)  # must never be asked for
    run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert scripted.calls == [URL, WB_QUERY]


# ----------------------------------------------------------------- AC-2


@pytest.mark.parametrize("code", [500, 503, 502, 404])
def test_fetch_names_the_status_of_a_failed_availability_query(
    code, catalog_file, library, scripted, capsys
):
    scripted.responses[URL] = status(403, body=HTML_BYTES)
    scripted.responses[WB_QUERY] = status(code)
    exit_code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert exit_code == 2, out
    assert attempt_lines(out) == [
        "direct: HTTP 403",
        f"wayback: availability query failed (HTTP {code})",
    ]
    assert NO_SNAPSHOT not in out
    assert scripted.calls == [URL, WB_QUERY]


def test_a_transport_failure_on_the_query_is_still_reported_as_such(
    catalog_file, library, scripted, capsys
):
    # Not a status at all: the OSError path stays what it was.
    scripted.responses[URL] = status(403, body=HTML_BYTES)
    scripted.responses[WB_QUERY] = OSError("connection reset")
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 2, out
    assert attempt_lines(out) == ["direct: HTTP 403", "wayback: connection reset"]
    assert NO_SNAPSHOT not in out


# ----------------------------------------------------------------- AC-3


@pytest.mark.parametrize(
    "response",
    [
        wayback_miss(),
        status(200, {}, b'{"archived_snapshots": {"closest": {"available": false}}}'),
        status(200, {}, b'{"archived_snapshots": {"closest": {"available": true}}}'),
        status(200, {"content-type": "text/html"}, b"<html>not json</html>"),
        status(200, {}, b""),
        status(200, {}, b"[]"),
    ],
    ids=["no-closest", "available-false", "fields-missing", "html", "empty", "list"],
)
def test_a_real_miss_is_still_no_snapshot(response):
    client = ScriptedClient({WB_QUERY: response})
    assert fetch_mod.wayback_snapshot(URL, client) is None


def test_fetch_still_says_no_wayback_snapshot_on_a_real_miss(
    catalog_file, library, scripted, capsys
):
    scripted.responses[URL] = status(403, body=HTML_BYTES)
    scripted.responses[WB_QUERY] = wayback_miss()
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 2, out
    assert attempt_lines(out) == ["direct: HTTP 403", f"wayback: {NO_SNAPSHOT}"]
    assert "rate limited" not in out
    assert "availability query failed" not in out


def test_a_hit_still_downloads_the_snapshot(catalog_file, library, scripted, capsys):
    scripted.responses[URL] = status(403, body=HTML_BYTES)
    scripted.responses[WB_QUERY] = wayback_hit(URL)
    scripted.responses[WB_RAW] = ok(PDF_BYTES)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 0, out
    assert "fetched DSP0236 1.3.3 via wayback" in out.splitlines()
    assert scripted.calls == [URL, WB_QUERY, WB_RAW]


# ----------------------------------------------------------------- AC-4


def test_check_body_words_a_429_as_a_rate_limit():
    with pytest.raises(fetch_mod.RejectedBody) as exc:
        fetch_mod.check_body(status(429, {"retry-after": "60"}, b""), "pdf")
    assert str(exc.value) == "HTTP 429 (rate limited; try again later)"
    with pytest.raises(fetch_mod.RejectedBody) as exc:
        fetch_mod.check_body(status(429, {}, PDF_BYTES), "zip")
    assert str(exc.value) == "HTTP 429 (rate limited; try again later)"


@pytest.mark.parametrize("code", [403, 404, 500, 502, 503, 301])
def test_check_body_keeps_the_bare_status_for_every_other_code(code):
    with pytest.raises(fetch_mod.RejectedBody) as exc:
        fetch_mod.check_body(status(code, {}, HTML_BYTES), "pdf")
    assert str(exc.value) == f"HTTP {code}"


def test_fetch_names_the_rate_limit_on_the_direct_download(
    catalog_file, library, scripted, capsys
):
    scripted.responses[URL] = status(429, {"retry-after": "10"})
    scripted.responses[WB_QUERY] = wayback_miss()
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 2, out
    assert attempt_lines(out) == [
        "direct: HTTP 429 (rate limited; try again later)",
        f"wayback: {NO_SNAPSHOT}",
    ]


def test_fetch_names_the_rate_limit_on_the_snapshot_download(
    catalog_file, library, scripted, capsys
):
    scripted.responses[URL] = status(403, body=HTML_BYTES)
    scripted.responses[WB_QUERY] = wayback_hit(URL)
    scripted.responses[WB_RAW] = status(429)
    code, out = run(capsys, "fetch", "DSP0236", catalog_file=catalog_file)
    assert code == 2, out
    assert attempt_lines(out) == [
        "direct: HTTP 403",
        "wayback: HTTP 429 (rate limited; try again later)",
    ]
    assert scripted.calls == [URL, WB_QUERY, WB_RAW]
    assert not (library.specs / "mctp" / "DSP0236" / "1.3.3").exists()


# ----------------------------------------------------------------- AC-5


def _held_older_version(catalog_file, scripted, tmp_path, capsys):
    from tests import pdfgen

    page = pdfgen.plain_page(["1 Intro", "old text"])
    pdf = pdfgen.write_pdf(tmp_path / "old.pdf", [page], bookmarks=[(0, "1 Intro", 0)])
    scripted.responses[OLD_URL] = ok(pdf.read_bytes())
    code, out = run(
        capsys, "fetch", "DSP0236", "--version", "1.3.2", catalog_file=catalog_file
    )
    assert code == 0, out
    scripted.calls.clear()


@pytest.mark.parametrize(
    "headers, wait",
    [({}, "a few minutes"), ({"retry-after": "45"}, "45 s")],
)
def test_the_fallback_note_carries_the_rate_limit_message(
    headers, wait, catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    _held_older_version(catalog_file, scripted, tmp_path, capsys)
    scripted.responses[URL] = status(403, body=HTML_BYTES)
    scripted.responses[WB_QUERY] = status(429, headers)
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == (
        "note: could not fetch DSP0236 1.3.3: direct: HTTP 403; "
        f"wayback: {RATE_LIMITED}{wait}; answering from held 1.3.2"
    )
    assert NO_SNAPSHOT not in out
    assert "old text" in out
    assert scripted.calls == [URL, WB_QUERY]


def test_the_fallback_note_carries_a_failed_query_status(
    catalog_file, library, scripted, tmp_path, capsys
):
    pytest.importorskip("pypdfium2")
    _held_older_version(catalog_file, scripted, tmp_path, capsys)
    scripted.responses[URL] = status(403, body=HTML_BYTES)
    scripted.responses[WB_QUERY] = status(503)
    code, out = run(capsys, "page", "DSP0236", "1", catalog_file=catalog_file)
    assert code == 0, out
    assert out.splitlines()[0] == (
        "note: could not fetch DSP0236 1.3.3: direct: HTTP 403; "
        "wayback: availability query failed (HTTP 503); answering from held 1.3.2"
    )
    assert NO_SNAPSHOT not in out
    assert "old text" in out
