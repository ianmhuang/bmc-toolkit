"""Shared fixtures: a tiny catalog, an isolated Library, a scripted HTTP client."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bmc_toolkit.spec import fetch as fetch_mod  # noqa: E402
from bmc_toolkit.spec.catalog import load_catalog  # noqa: E402
from bmc_toolkit.spec.library import Library  # noqa: E402

MINI_CATALOG = """
schema_version = 1

[families.mctp]
title = "MCTP"
publisher = "DMTF"

[families.ipmi]
title = "IPMI"
publisher = "Intel"

[families.vendor]
title = "Vendor documents"
publisher = "various"

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

[[documents.versions]]
version = "1.4.0"
url = "https://example.test/DSP0236_1.4.0.pdf"
type = "pdf"
published = "2025-06-01"
wip = true

[[documents]]
id = "IPMI"
family = "ipmi"
title = "IPMI Specification v2.0"
access = "open"
fetch = "wayback"

[[documents.versions]]
version = "2.0 rev 1.1"
url = "https://example.test/ipmi-v2-rev1-1.pdf"
type = "pdf"
published = "2013-10-01"

[[documents]]
id = "BUNDLE"
family = "mctp"
title = "A zip bundle"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "2026.1"
url = "https://example.test/bundle_2026.1.zip"
type = "zip"
published = "2026-01-15"

[[documents]]
id = "SECRET"
family = "vendor"
title = "A confidential datasheet"
access = "confidential"
fetch = "manual"

[[documents.versions]]
version = "0.9"
url = "https://example.test/secret.pdf"
type = "pdf"
published = "2020-01-01"
"""

PDF_BYTES = b"%PDF-1.7\n%fake\n" + b"x" * 200
ZIP_BYTES = b"PK\x03\x04" + b"\x00" * 100
HTML_BYTES = b"<html><body>Access Denied</body></html>"


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(MINI_CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def catalog(catalog_file):
    return load_catalog(catalog_file)


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return Library(root)


class ScriptedClient:
    """Returns canned responses per URL and records every call."""

    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls: list[str] = []

    def __call__(self, url):
        self.calls.append(url)
        if url not in self.responses:
            raise OSError(f"no route to {url}")
        item = self.responses[url]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item()
        return item


def ok(body, ctype="application/pdf", length=None):
    headers = {"content-type": ctype}
    if length is not None:
        headers["content-length"] = str(length)
    return fetch_mod.Response(200, headers, body)


def wayback_hit(url, timestamp="20250101000000"):
    body = (
        '{"archived_snapshots": {"closest": {"available": true, "status": "200", '
        f'"url": "http://web.archive.org/web/{timestamp}/{url}", '
        f'"timestamp": "{timestamp}"}}}}}}'
    ).encode()
    return fetch_mod.Response(200, {"content-type": "application/json"}, body)


def wayback_miss():
    return fetch_mod.Response(
        200, {"content-type": "application/json"}, b'{"archived_snapshots": {}}'
    )


@pytest.fixture
def scripted(monkeypatch):
    """A ScriptedClient that the CLI will use instead of the network."""
    from bmc_toolkit.spec import cli

    client = ScriptedClient()
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: client)
    return client
