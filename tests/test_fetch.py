"""The fetch chain: direct, Wayback, manual; body checks; skip and force."""

import json

import pytest

from bmc_toolkit.spec import fetch as fetch_mod
from bmc_toolkit.spec.fetch import (
    RejectedBody,
    check_body,
    fetch_version,
    wayback_snapshot,
)
from tests.conftest import (
    HTML_BYTES,
    PDF_BYTES,
    ZIP_BYTES,
    ScriptedClient,
    ok,
    wayback_hit,
    wayback_miss,
)

URL = "https://example.test/DSP0236_1.3.3.pdf"
WB_QUERY = fetch_mod.WAYBACK_AVAILABLE + URL
WB_RAW = "http://web.archive.org/web/20250101000000id_/" + URL


def test_check_body_accepts_pdf_and_zip():
    assert check_body(ok(PDF_BYTES), "pdf") == PDF_BYTES
    assert check_body(ok(ZIP_BYTES, "application/zip"), "zip") == ZIP_BYTES


def test_check_body_tolerates_decompressed_bodies():
    # Content-Length counted compressed bytes; the client decompressed.
    longer = ok(PDF_BYTES, length=len(PDF_BYTES) - 50)
    assert check_body(longer, "pdf") == PDF_BYTES
    encoded = fetch_mod.Response(
        200,
        {
            "content-type": "application/pdf",
            "content-length": "10",
            "content-encoding": "gzip",
        },
        PDF_BYTES,
    )
    assert check_body(encoded, "pdf") == PDF_BYTES


@pytest.mark.parametrize(
    "resp, expected, needle",
    [
        (ok(HTML_BYTES, "text/html"), "pdf", "not a pdf"),
        (ok(PDF_BYTES), "zip", "not a zip"),
        (fetch_mod.Response(403, {}, HTML_BYTES), "pdf", "HTTP 403"),
        (ok(PDF_BYTES, length=len(PDF_BYTES) + 10), "pdf", "truncated"),
        (ok(b"", "application/pdf"), "pdf", "not a pdf"),
    ],
)
def test_check_body_rejects(resp, expected, needle):
    with pytest.raises(RejectedBody) as exc:
        check_body(resp, expected)
    assert needle in str(exc.value)


def test_wayback_snapshot_builds_raw_url():
    client = ScriptedClient({WB_QUERY: wayback_hit(URL)})
    assert wayback_snapshot(URL, client) == WB_RAW


def test_wayback_snapshot_none_when_missing_or_broken():
    assert wayback_snapshot(URL, ScriptedClient({WB_QUERY: wayback_miss()})) is None
    garbage = fetch_mod.Response(200, {}, b"<html>")
    assert wayback_snapshot(URL, ScriptedClient({WB_QUERY: garbage})) is None
    assert (
        wayback_snapshot(
            URL, ScriptedClient({WB_QUERY: fetch_mod.Response(500, {}, b"")})
        )
        is None
    )


def test_direct_success_records_method_and_url(catalog, library):
    doc = catalog.get("DSP0236")
    ver = doc.latest()
    client = ScriptedClient({URL: ok(PDF_BYTES, length=len(PDF_BYTES))})
    out = fetch_version(library, doc, ver, client=client)
    assert out.status == "fetched"
    assert out.method == "direct"
    assert client.calls == [URL]
    meta = json.loads(
        (library.version_dir("mctp", "DSP0236", "1.3.3") / "meta.json").read_text(
            "utf-8"
        )
    )
    assert meta["url"] == URL
    assert meta["fetch_method"] == "direct"


def test_html_block_page_falls_through_to_wayback(catalog, library):
    doc = catalog.get("DSP0236")
    ver = doc.latest()
    client = ScriptedClient(
        {
            URL: ok(HTML_BYTES, "text/html"),
            WB_QUERY: wayback_hit(URL),
            WB_RAW: ok(PDF_BYTES),
        }
    )
    out = fetch_version(library, doc, ver, client=client)
    assert out.status == "fetched"
    assert out.method == "wayback"
    assert out.attempts == ("direct: not a pdf (text/html, 39 bytes)",)
    meta = json.loads(
        (library.version_dir("mctp", "DSP0236", "1.3.3") / "meta.json").read_text(
            "utf-8"
        )
    )
    assert meta["url"] == WB_RAW
    assert not list(library.version_dir("mctp", "DSP0236", "1.3.3").glob("*.part"))


def test_transport_error_then_wayback(catalog, library):
    doc = catalog.get("DSP0236")
    ver = doc.latest()
    client = ScriptedClient(
        {
            URL: OSError("connection reset"),
            WB_QUERY: wayback_hit(URL),
            WB_RAW: ok(PDF_BYTES),
        }
    )
    out = fetch_version(library, doc, ver, client=client)
    assert out.status == "fetched"
    assert out.attempts[0].startswith("direct: connection reset")


def test_all_steps_fail_gives_manual_instruction(catalog, library):
    doc = catalog.get("DSP0236")
    ver = doc.latest()
    client = ScriptedClient(
        {URL: fetch_mod.Response(403, {}, HTML_BYTES), WB_QUERY: wayback_miss()}
    )
    out = fetch_version(library, doc, ver, client=client)
    assert out.status == "failed"
    assert out.method == "manual"
    lines = out.message.splitlines()
    assert lines[0] == f"Open in a browser: {URL}"
    assert lines[1].startswith("Save it as: ")
    assert lines[1].endswith(
        str(library.version_dir("mctp", "DSP0236", "1.3.3") / "original.pdf")
    )
    assert out.attempts == ("direct: HTTP 403", "wayback: no Wayback snapshot")
    assert not library.version_dir("mctp", "DSP0236", "1.3.3").exists()


def test_wayback_method_skips_direct(catalog, library):
    doc = catalog.get("IPMI")
    ver = doc.latest()
    url = ver.url
    raw = "http://web.archive.org/web/20250101000000id_/" + url
    client = ScriptedClient(
        {
            fetch_mod.WAYBACK_AVAILABLE + url: wayback_hit(url),
            raw: ok(PDF_BYTES),
        }
    )
    out = fetch_version(library, doc, ver, client=client)
    assert out.status == "fetched"
    assert out.method == "wayback"
    assert url not in client.calls


def test_manual_method_never_touches_network(catalog, library):
    doc = catalog.get("SECRET")
    ver = doc.latest()
    client = ScriptedClient()
    out = fetch_version(library, doc, ver, client=client)
    assert out.status == "failed"
    assert client.calls == []
    assert "example.test" not in out.message
    assert "Obtain 'A confidential datasheet' version 0.9" in out.message


def test_present_version_is_skipped_without_network(catalog, library):
    doc = catalog.get("DSP0236")
    ver = doc.latest()
    library.store(
        "mctp", "DSP0236", "1.3.3", PDF_BYTES, "pdf", url=URL, method="direct"
    )
    client = ScriptedClient()
    out = fetch_version(library, doc, ver, client=client)
    assert out.status == "skipped"
    assert client.calls == []


def test_force_redownloads(catalog, library):
    doc = catalog.get("DSP0236")
    ver = doc.latest()
    library.store(
        "mctp", "DSP0236", "1.3.3", b"%PDF old", "pdf", url=URL, method="direct"
    )
    client = ScriptedClient({URL: ok(PDF_BYTES)})
    out = fetch_version(library, doc, ver, force=True, client=client)
    assert out.status == "fetched"
    assert (
        library.version_dir("mctp", "DSP0236", "1.3.3") / "original.pdf"
    ).read_bytes() == PDF_BYTES


def test_zip_documents_are_checked_as_zip(catalog, library):
    doc = catalog.get("BUNDLE")
    ver = doc.latest()
    client = ScriptedClient(
        {
            ver.url: ok(PDF_BYTES, "application/zip"),
            fetch_mod.WAYBACK_AVAILABLE + ver.url: wayback_miss(),
        }
    )
    out = fetch_version(library, doc, ver, client=client)
    assert out.status == "failed"
    assert out.attempts[0].startswith("direct: not a zip")


def test_default_client_falls_back_to_urllib(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_curl(name, *args, **kwargs):
        if name.startswith("curl_cffi"):
            raise ImportError("no curl_cffi")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_curl)
    assert fetch_mod.default_client() is fetch_mod._urllib_client
