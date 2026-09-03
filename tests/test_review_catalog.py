"""Acceptance tests for the Source Catalog side of M1: AC-1, AC-2, AC-3, AC-4, AC-13.

Black-box through ``bmc_toolkit.spec.cli.main``. The only seam used is the
documented ``CLIENT_FACTORY`` hook so that no test can reach the network.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmc_toolkit.spec import cli  # noqa: E402
from bmc_toolkit.spec import fetch as fetch_mod  # noqa: E402

REVIEW_CATALOG = """
schema_version = 1

[families.mctp]
title = "MCTP"
publisher = "DMTF"

[families.ipmi]
title = "IPMI"
publisher = "Intel"

[families.vendor]
title = "Vendor"
publisher = "various"

[[documents]]
id = "DSP0236"
family = "mctp"
title = "MCTP Base Specification"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.3.2"
url = "https://example.invalid/DSP0236_1.3.2.pdf"
type = "pdf"
published = "2024-01-02"

[[documents.versions]]
version = "1.3.3"
url = "https://example.invalid/DSP0236_1.3.3.pdf"
type = "pdf"
published = "2024-03-25"

[[documents.versions]]
version = "1.4.0"
url = "https://example.invalid/DSP0236_1.4.0.pdf"
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
url = "https://example.invalid/ipmi-v2-rev1-1.pdf"
type = "pdf"
published = "2013-10-01"

[[documents]]
id = "ONLYWIP"
family = "mctp"
title = "Only a work in progress"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "0.1"
url = "https://example.invalid/onlywip_0.1.pdf"
type = "pdf"
published = "2025-01-01"
wip = true

[[documents]]
id = "SECRET"
family = "vendor"
title = "A confidential datasheet"
access = "confidential"
fetch = "manual"

[[documents.versions]]
version = "0.9"
url = "https://example.invalid/secret.pdf"
type = "pdf"
published = "2020-01-01"
"""

PDF = b"%PDF-1.7\n%review\n" + b"y" * 300


class NoNetwork:
    """Client that refuses every URL and records the attempt."""

    def __init__(self):
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        raise OSError("network disabled in tests")


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
def offline(monkeypatch):
    client = NoNetwork()
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: client)
    return client


def run(capsys, catalog_path, *argv):
    code = cli.main(["--catalog", str(catalog_path), *argv])
    return code, capsys.readouterr().out


# ----------------------------------------------------------------- AC-1


def test_catalog_list_is_one_record_per_document(catalog_path, capsys):
    code, out = run(capsys, catalog_path, "catalog")
    assert code == 0
    lines = out.strip().splitlines()
    assert len(lines) == 4, out
    rows = {ln.split("\t")[1]: ln.split("\t") for ln in lines}
    assert set(rows) == {"DSP0236", "IPMI", "ONLYWIP", "SECRET"}
    fam, _id, access, fetch, latest, *_ = rows["DSP0236"]
    assert (fam, access, fetch, latest) == ("mctp", "open", "direct", "1.3.3")
    fam, _id, access, fetch, latest, *_ = rows["SECRET"]
    assert (fam, access, fetch, latest) == ("vendor", "confidential", "manual", "0.9")
    # a document with only WIP versions has no latest
    assert rows["ONLYWIP"][4] == "-"
    # every record has the same number of fields, so the skill can split on tabs
    assert len({len(r) for r in rows.values()}) == 1
    # AC-1: the list form names each document's known versions
    dsp_line = "\t".join(rows["DSP0236"])
    for v in ("1.3.2", "1.3.3", "1.4.0"):
        assert v in dsp_line, dsp_line
    assert "2.0 rev 1.1" in "\t".join(rows["IPMI"])


def test_catalog_single_document_lists_every_version(catalog_path, capsys):
    code, out = run(capsys, catalog_path, "catalog", "dsp0236")
    assert code == 0
    assert "latest: 1.3.3" in out
    assert "access: open" in out
    assert "fetch: direct" in out
    for v in ("1.3.2", "1.3.3", "1.4.0"):
        assert v in out
    version_lines = [ln for ln in out.splitlines() if "1.4.0" in ln]
    assert version_lines and "wip" in version_lines[0]


def test_catalog_unknown_document_exits_2(catalog_path, capsys):
    code, out = run(capsys, catalog_path, "catalog", "DSP9999")
    assert code == 2
    assert "DSP9999" in out


# ----------------------------------------------------------------- AC-2


def test_shipped_catalog_is_toml_under_spec_package():
    shipped = ROOT / "bmc_toolkit" / "spec" / "catalog.toml"
    assert shipped.is_file()
    import tomllib

    with open(shipped, "rb") as fh:
        data = tomllib.load(fh)
    assert data["schema_version"] == 1
    assert "families" in data and "documents" in data


@pytest.mark.parametrize(
    "text, key",
    [
        ('schema_version = 1\n[families.x]\ntitle = "x"\n', "publisher"),
        (
            'schema_version = 1\n[families.x]\ntitle = "x"\npublisher = "p"\n'
            '[[documents]]\nid = "D"\nfamily = "x"\ntitle = "t"\naccess = "secret"\n'
            'fetch = "direct"\n[[documents.versions]]\nversion = "1"\n'
            'url = "https://example.invalid/d.pdf"\ntype = "pdf"\npublished = "2020-01-01"\n',
            "access",
        ),
        (
            'schema_version = 1\n[families.x]\ntitle = "x"\npublisher = "p"\n'
            '[[documents]]\nid = "D"\nfamily = "x"\ntitle = "t"\naccess = "open"\n'
            'fetch = "direct"\n[[documents.versions]]\nversion = "1"\n'
            'url = "https://example.invalid/d.pdf"\ntype = "pdf"\npublished = "yesterday"\n',
            "published",
        ),
        (
            'schema_version = 1\n[families.x]\ntitle = "x"\npublisher = "p"\n'
            '[[documents]]\nid = "D"\nfamily = "nope"\ntitle = "t"\naccess = "open"\n'
            'fetch = "direct"\n[[documents.versions]]\nversion = "1"\n'
            'url = "https://example.invalid/d.pdf"\ntype = "pdf"\npublished = "2020-01-01"\n',
            "family",
        ),
    ],
)
def test_malformed_catalog_exits_1_naming_the_key(tmp_path, capsys, text, key):
    bad = tmp_path / "bad.toml"
    bad.write_text(text, encoding="utf-8", newline="")
    # main() must return, not raise: no traceback for the user
    code = cli.main(["--catalog", str(bad), "catalog"])
    out = capsys.readouterr().out
    assert code == 1
    assert key in out


def test_invalid_toml_syntax_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("schema_version = [\n", encoding="utf-8", newline="")
    code = cli.main(["--catalog", str(bad), "catalog"])
    assert code == 1
    assert "toml" in capsys.readouterr().out.lower()


# ----------------------------------------------------------------- AC-3

V1_IDS = [
    # Intel
    "IPMI",
    "IPMI-UPDATE",
    "IPMB",
    "IPMI-FRU",
    "DCMI",
    "ESPI",
    # DMTF MCTP core
    "DSP0236",
    "DSP0237",
    "DSP0238",
    "DSP0239",
    # DMTF PLDM core
    "DSP0240",
    "DSP0241",
    "DSP0245",
    "DSP0248",
    # DMTF SPDM core
    "DSP0274",
    "DSP0275",
    "DSP0276",
    "DSP0277",
    # NC-SI, SMBIOS
    "DSP0222",
    "DSP0134",
    # Redfish set named in the AC
    "DSP0266",
    "DSP8010",
    "DSP0268",
    "DSP2046",
    "DSP0270",
    "DSP0272",
    "DSP8011",
    # NVMe
    "NVME-BASE",
    "NVME-MI",
    # OCP
    "DC-SCM",
    "M-CRPS",
    "M-PIC",
    "M-XIO",
    "M-DNO",
    "M-FLW",
    # buses
    "UM10204",
    "SMBUS",
    "CMIS",
]


def test_shipped_catalog_covers_v1_scope_with_a_published_version(capsys):
    code = cli.main(["catalog"])
    out = capsys.readouterr().out
    assert code == 0
    rows = {ln.split("\t")[1].upper(): ln.split("\t") for ln in out.strip().splitlines()}
    missing = [d for d in V1_IDS if d not in rows]
    assert not missing, missing
    without_latest = [d for d in V1_IDS if rows[d][4] == "-"]
    assert not without_latest, without_latest


def test_shipped_catalog_urls_are_https_and_public_hosts(capsys):
    """No plain http, no private hosts, and DSP8010 is a zip (AC-3, out-of-scope note)."""
    code = cli.main(["catalog", "DSP8010"])
    out = capsys.readouterr().out
    assert code == 0
    version_lines = [ln for ln in out.splitlines() if ln.startswith("\t")]
    assert version_lines
    for ln in version_lines:
        fields = ln.strip().split("\t")
        assert fields[2] == "zip"
        assert fields[4].startswith("https://")


# ----------------------------------------------------------------- AC-4


def test_fetch_latest_is_newest_non_wip(catalog_path, lib_root, capsys, monkeypatch):
    calls = []

    def client(url):
        calls.append(url)
        return fetch_mod.Response(200, {"content-type": "application/pdf"}, PDF)

    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: client)
    code, out = run(capsys, catalog_path, "fetch", "DSP0236")
    assert code == 0
    assert calls == ["https://example.invalid/DSP0236_1.3.3.pdf"]
    assert (lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3" / "original.pdf").is_file()
    assert not (lib_root / "specs" / "mctp" / "DSP0236" / "1.4.0").exists()


def test_fetch_wip_lets_wip_be_latest(catalog_path, lib_root, capsys, monkeypatch):
    calls = []

    def client(url):
        calls.append(url)
        return fetch_mod.Response(200, {"content-type": "application/pdf"}, PDF)

    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: client)
    code, out = run(capsys, catalog_path, "fetch", "DSP0236", "--wip")
    assert code == 0
    assert calls == ["https://example.invalid/DSP0236_1.4.0.pdf"]
    assert (lib_root / "specs" / "mctp" / "DSP0236" / "1.4.0" / "original.pdf").is_file()


def test_fetch_explicit_version_string(catalog_path, lib_root, capsys, monkeypatch):
    calls = []

    def client(url):
        calls.append(url)
        return fetch_mod.Response(200, {"content-type": "application/pdf"}, PDF)

    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: client)
    code, out = run(capsys, catalog_path, "fetch", "DSP0236", "--version", "1.3.2")
    assert code == 0
    assert calls == ["https://example.invalid/DSP0236_1.3.2.pdf"]
    assert "1.3.2" in out


def test_fetch_only_wip_document_without_flag_exits_2(
    catalog_path, lib_root, offline, capsys
):
    code, out = run(capsys, catalog_path, "fetch", "ONLYWIP")
    assert code == 2
    assert "--wip" in out
    assert offline.calls == []


def test_fetch_unknown_version_names_known_versions_and_dropin_path(
    catalog_path, lib_root, offline, capsys
):
    code, out = run(capsys, catalog_path, "fetch", "DSP0236", "--version", "9.9")
    assert code == 2
    for known in ("1.3.2", "1.3.3", "1.4.0"):
        assert known in out
    assert "mctp/DSP0236/9.9" in out.replace("\\", "/")
    assert offline.calls == []
    # a failed request creates nothing, not even the Library root
    assert not lib_root.exists()
    assert "created" not in out.lower()


def test_fetch_unknown_document_exits_2(catalog_path, lib_root, offline, capsys):
    code, out = run(capsys, catalog_path, "fetch", "DSP9999")
    assert code == 2
    assert offline.calls == []
    assert not lib_root.exists()


# ----------------------------------------------------------------- AC-13


def test_non_fetch_commands_run_without_curl_cffi(
    catalog_path, lib_root, tmp_path, capsys, monkeypatch
):
    # A None entry in sys.modules makes ``import curl_cffi`` raise ImportError.
    monkeypatch.setitem(sys.modules, "curl_cffi", None)
    for name in [m for m in sys.modules if m.startswith("curl_cffi.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    with pytest.raises(ImportError):
        import curl_cffi  # noqa: F401

    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert run(capsys, catalog_path, "catalog")[0] == 0
    assert run(capsys, catalog_path, "status")[0] == 0
    assert run(capsys, catalog_path, "scan")[0] == 0
    src = tmp_path / "hand.pdf"
    src.write_bytes(PDF)
    code, out = run(
        capsys,
        catalog_path,
        "add",
        str(src),
        "--document",
        "SECRET",
        "--version",
        "0.9",
    )
    assert code == 0
    # the default client degrades to the standard library instead of crashing
    assert callable(fetch_mod.default_client())
