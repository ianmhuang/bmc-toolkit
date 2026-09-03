"""Acceptance tests for the fetch chain: AC-5, AC-6, AC-7, AC-8, AC-9, AC-14.

Black-box through ``bmc_toolkit.spec.cli.main`` with a scripted HTTP client
installed through the documented ``CLIENT_FACTORY`` seam. The client refuses
every URL it was not told about, so no test can reach the network.
"""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmc_toolkit.spec import cli  # noqa: E402
from bmc_toolkit.spec import fetch as fetch_mod  # noqa: E402
from tests.test_review_catalog import REVIEW_CATALOG  # noqa: E402

PDF = b"%PDF-1.7\n%review\n" + b"z" * 400
PDF_OLD = b"%PDF-1.4\n%older\n" + b"o" * 40
HTML = b"<!DOCTYPE html><html><body>Access denied</body></html>"
DSP_URL = "https://example.invalid/DSP0236_1.3.3.pdf"
IPMI_URL = "https://example.invalid/ipmi-v2-rev1-1.pdf"
TS = "20250101000000"


def pdf_ok(body=PDF, length=None):
    headers = {"content-type": "application/pdf"}
    if length is not None:
        headers["content-length"] = str(length)
    return fetch_mod.Response(200, headers, body)


def html_ok():
    return fetch_mod.Response(200, {"content-type": "text/html"}, HTML)


class Scripted:
    """Exact routes plus Wayback behaviour per original URL."""

    def __init__(self):
        self.routes = {}
        self.wayback = {}  # original url -> Response for the raw snapshot, or None
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url in self.routes:
            item = self.routes[url]
            if isinstance(item, Exception):
                raise item
            return item
        if "archive.org/wayback/available" in url:
            for original, snap in self.wayback.items():
                if original in url:
                    if snap is None:
                        return fetch_mod.Response(
                            200,
                            {"content-type": "application/json"},
                            b'{"archived_snapshots": {}}',
                        )
                    body = json.dumps(
                        {
                            "archived_snapshots": {
                                "closest": {
                                    "available": True,
                                    "status": "200",
                                    "url": f"http://web.archive.org/web/{TS}/{original}",
                                    "timestamp": TS,
                                }
                            }
                        }
                    ).encode()
                    return fetch_mod.Response(
                        200, {"content-type": "application/json"}, body
                    )
        if "web.archive.org/web/" in url:
            for original, snap in self.wayback.items():
                if snap is not None and url.endswith(original):
                    return snap
        raise OSError(f"no route to {url}")

    def wayback_calls(self):
        return [u for u in self.calls if "archive.org" in u]


@pytest.fixture
def catalog_path(tmp_path):
    p = tmp_path / "review_catalog.toml"
    p.write_text(REVIEW_CATALOG, encoding="utf-8", newline="")
    return p


@pytest.fixture
def lib_root(tmp_path, monkeypatch):
    root = tmp_path / "library"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


@pytest.fixture
def client(monkeypatch):
    c = Scripted()
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: c)
    return c


def run(capsys, catalog_path, *argv):
    code = cli.main(["--catalog", str(catalog_path), *argv])
    return code, capsys.readouterr().out


def meta_of(lib_root, family, doc, vdir):
    return json.loads(
        (lib_root / "specs" / family / doc / vdir / "meta.json").read_text("utf-8")
    )


# ----------------------------------------------------------------- AC-5


def test_fetched_file_layout_and_meta(catalog_path, lib_root, client, capsys):
    client.routes[DSP_URL] = pdf_ok()
    assert not lib_root.exists()
    code, out = run(capsys, catalog_path, "fetch", "DSP0236")
    assert code == 0
    # first creation announces the Library path
    assert str(lib_root) in out
    vdir = lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3"
    assert (vdir / "original.pdf").read_bytes() == PDF
    meta = meta_of(lib_root, "mctp", "DSP0236", "1.3.3")
    assert meta["document"] == "DSP0236"
    assert meta["version"] == "1.3.3"
    assert meta["url"] == DSP_URL
    assert meta["fetch_method"] == "direct"
    assert meta["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert meta["size"] == len(PDF)
    assert datetime.fromisoformat(meta["fetched_at"])
    # the version directory is path safe for a version string with spaces
    client.wayback[IPMI_URL] = pdf_ok()
    code, out = run(capsys, catalog_path, "fetch", "IPMI")
    assert code == 0
    assert str(lib_root) not in out.splitlines()[0] or "created" not in out.lower()
    ipmi_dirs = list((lib_root / "specs" / "ipmi" / "IPMI").iterdir())
    assert len(ipmi_dirs) == 1
    assert (ipmi_dirs[0] / "original.pdf").is_file()
    assert json.loads((ipmi_dirs[0] / "meta.json").read_text("utf-8"))["version"] == (
        "2.0 rev 1.1"
    )


# ----------------------------------------------------------------- AC-6


def test_present_version_skips_network_and_force_redownloads(
    catalog_path, lib_root, client, capsys
):
    client.routes[DSP_URL] = pdf_ok(PDF_OLD)
    assert run(capsys, catalog_path, "fetch", "DSP0236")[0] == 0
    assert client.calls == [DSP_URL]

    code, out = run(capsys, catalog_path, "fetch", "DSP0236")
    assert code == 0
    assert client.calls == [DSP_URL], "second fetch must not touch the network"
    assert "already" in out.lower() or "skipped" in out.lower()

    client.routes[DSP_URL] = pdf_ok(PDF)
    code, out = run(capsys, catalog_path, "fetch", "DSP0236", "--force")
    assert code == 0
    assert client.calls == [DSP_URL, DSP_URL]
    vdir = lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3"
    assert (vdir / "original.pdf").read_bytes() == PDF
    assert meta_of(lib_root, "mctp", "DSP0236", "1.3.3")["sha256"] == (
        hashlib.sha256(PDF).hexdigest()
    )


# ----------------------------------------------------------------- AC-7 / AC-8


def test_direct_block_page_falls_back_to_wayback_and_records_method(
    catalog_path, lib_root, client, capsys
):
    client.routes[DSP_URL] = html_ok()
    client.wayback[DSP_URL] = pdf_ok()
    code, out = run(capsys, catalog_path, "fetch", "DSP0236")
    assert code == 0
    assert client.calls[0] == DSP_URL
    assert client.wayback_calls(), "Wayback must be consulted after the block page"
    meta = meta_of(lib_root, "mctp", "DSP0236", "1.3.3")
    assert meta["fetch_method"] == "wayback"
    assert "web.archive.org" in meta["url"]
    assert (lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3" / "original.pdf").read_bytes() == PDF


def test_transport_error_on_direct_falls_back_to_wayback(
    catalog_path, lib_root, client, capsys
):
    client.routes[DSP_URL] = OSError("connection reset by peer")
    client.wayback[DSP_URL] = pdf_ok()
    code, out = run(capsys, catalog_path, "fetch", "DSP0236")
    assert code == 0
    assert meta_of(lib_root, "mctp", "DSP0236", "1.3.3")["fetch_method"] == "wayback"


class _FakeCurlResponse:
    """The subset of a curl_cffi response the tool may rely on."""

    def __init__(self, status_code, headers, content):
        self.status_code = status_code
        self.headers = headers
        self.content = content


class _NotAnOSError(Exception):
    """curl_cffi's own error type in releases where it does not subclass OSError."""


def test_curl_cffi_transport_error_falls_through_to_wayback(
    catalog_path, lib_root, capsys, monkeypatch
):
    """AC-7: with the default client (curl_cffi present) a direct-step failure
    that is not an OSError still leads to the Wayback step, no traceback."""
    import types

    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if url == DSP_URL:
            raise _NotAnOSError("Failed to connect to example.invalid")
        if "archive.org/wayback/available" in url:
            body = json.dumps(
                {
                    "archived_snapshots": {
                        "closest": {
                            "available": True,
                            "status": "200",
                            "url": f"http://web.archive.org/web/{TS}/{DSP_URL}",
                            "timestamp": TS,
                        }
                    }
                }
            ).encode()
            return _FakeCurlResponse(200, {"Content-Type": "application/json"}, body)
        if "web.archive.org/web/" in url and url.endswith(DSP_URL):
            return _FakeCurlResponse(200, {"Content-Type": "application/pdf"}, PDF)
        raise _NotAnOSError(f"no route to {url}")

    fake_requests = types.SimpleNamespace(get=get)
    fake = types.ModuleType("curl_cffi")
    fake.requests = fake_requests
    monkeypatch.setitem(sys.modules, "curl_cffi", fake)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_requests)
    # the real default client, not a scripted stand-in
    monkeypatch.setattr(cli, "CLIENT_FACTORY", fetch_mod.default_client)

    code, out = run(capsys, catalog_path, "fetch", "DSP0236")
    assert code == 0, out
    assert calls[0] == DSP_URL
    assert any("archive.org" in u for u in calls)
    meta = meta_of(lib_root, "mctp", "DSP0236", "1.3.3")
    assert meta["fetch_method"] == "wayback"
    assert (lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3" / "original.pdf").read_bytes() == PDF
    assert "Failed to connect" in out


def test_curl_cffi_transport_error_does_not_abort_fetch_all(
    catalog_path, lib_root, capsys, monkeypatch
):
    """AC-14: a curl_cffi error on one document must not stop --all."""
    import types

    def get(url, **kwargs):
        raise _NotAnOSError("TLS handshake failed")

    fake_requests = types.SimpleNamespace(get=get)
    fake = types.ModuleType("curl_cffi")
    fake.requests = fake_requests
    monkeypatch.setitem(sys.modules, "curl_cffi", fake)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_requests)
    monkeypatch.setattr(cli, "CLIENT_FACTORY", fetch_mod.default_client)

    code, out = run(capsys, catalog_path, "fetch", "--all")
    assert code == 2
    summary = [ln for ln in out.splitlines() if ln.lower().startswith("summary")]
    assert summary, out
    # DSP0236 and IPMI both attempted and both failed; SECRET and ONLYWIP skipped
    assert "failed 2" in summary[-1]
    assert "fetched 0" in summary[-1]


def test_wayback_method_never_tries_direct(catalog_path, lib_root, client, capsys):
    client.routes[IPMI_URL] = pdf_ok()  # would succeed, but must not be used
    client.wayback[IPMI_URL] = pdf_ok()
    code, out = run(capsys, catalog_path, "fetch", "IPMI")
    assert code == 0
    assert IPMI_URL not in client.calls
    ipmi_dirs = list((lib_root / "specs" / "ipmi" / "IPMI").iterdir())
    meta = json.loads((ipmi_dirs[0] / "meta.json").read_text("utf-8"))
    assert meta["fetch_method"] == "wayback"


def test_manual_method_prints_instruction_without_network(
    catalog_path, lib_root, client, capsys
):
    code, out = run(capsys, catalog_path, "fetch", "SECRET")
    assert code == 2
    assert client.calls == []
    assert "original.pdf" in out
    assert "scan" in out
    # confidential: the catalog URL is never shown or stored
    assert "example.invalid/secret.pdf" not in out
    assert not (lib_root / "specs" / "vendor" / "SECRET" / "0.9" / "meta.json").exists()


def test_truncated_body_is_rejected_and_chain_continues(
    catalog_path, lib_root, client, capsys
):
    client.routes[DSP_URL] = pdf_ok(PDF, length=len(PDF) + 100)
    client.wayback[DSP_URL] = pdf_ok(PDF, length=len(PDF))
    code, out = run(capsys, catalog_path, "fetch", "DSP0236")
    assert code == 0
    assert meta_of(lib_root, "mctp", "DSP0236", "1.3.3")["fetch_method"] == "wayback"


def test_rejected_bodies_write_nothing(catalog_path, lib_root, client, capsys):
    client.routes[DSP_URL] = html_ok()
    client.wayback[DSP_URL] = html_ok()  # the archived copy is a block page too
    code, out = run(capsys, catalog_path, "fetch", "DSP0236")
    assert code == 2
    doc_dir = lib_root / "specs" / "mctp" / "DSP0236"
    assert not doc_dir.exists() or not any(doc_dir.rglob("*"))


def test_http_error_status_is_rejected(catalog_path, lib_root, client, capsys):
    client.routes[DSP_URL] = fetch_mod.Response(403, {"content-type": "text/html"}, HTML)
    client.wayback[DSP_URL] = None
    code, out = run(capsys, catalog_path, "fetch", "DSP0236")
    assert code == 2
    assert "403" in out


# ----------------------------------------------------------------- AC-9


def test_total_failure_prints_url_and_save_path_on_separate_lines(
    catalog_path, lib_root, client, capsys
):
    client.routes[DSP_URL] = html_ok()
    client.wayback[DSP_URL] = None
    code, out = run(capsys, catalog_path, "fetch", "DSP0236")
    assert code == 2
    lines = out.splitlines()
    url_lines = [ln for ln in lines if DSP_URL in ln and "archive.org" not in ln]
    target = lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3" / "original.pdf"
    path_lines = [ln for ln in lines if str(target) in ln]
    assert url_lines, out
    assert path_lines, out
    assert url_lines[-1] != path_lines[-1]


# ----------------------------------------------------------------- AC-14


def test_fetch_all_continues_past_failures_and_summarises(
    catalog_path, lib_root, client, capsys
):
    client.routes[DSP_URL] = pdf_ok()
    client.wayback[IPMI_URL] = None  # IPMI: wayback only, no snapshot -> fails
    code, out = run(capsys, catalog_path, "fetch", "--all")
    assert code != 0
    assert (lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3" / "original.pdf").is_file()
    assert "example.invalid/secret.pdf" not in " ".join(client.calls)
    assert "https://example.invalid/onlywip_0.1.pdf" not in client.calls
    summary = [ln for ln in out.splitlines() if ln.lower().startswith("summary")]
    assert summary, out
    assert "1" in summary[-1]  # one fetched, one failed


def test_fetch_all_exits_0_when_nothing_fails(catalog_path, lib_root, client, capsys):
    client.routes[DSP_URL] = pdf_ok()
    client.wayback[IPMI_URL] = pdf_ok()
    code, out = run(capsys, catalog_path, "fetch", "--all")
    assert code == 0
    assert (lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3" / "original.pdf").is_file()
    assert any((lib_root / "specs" / "ipmi" / "IPMI").iterdir())
    calls_before = len(client.calls)
    code, out = run(capsys, catalog_path, "fetch", "--all")
    assert code == 0
    assert len(client.calls) == calls_before, "a second --all must be offline"
