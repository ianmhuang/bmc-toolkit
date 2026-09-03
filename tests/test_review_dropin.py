"""Acceptance tests for Drop-ins: AC-10 (add), AC-11 (scan), AC-12 (status).

Black-box through ``bmc_toolkit.spec.cli.main``; no command here may touch
the network, so the client factory is replaced by one that refuses.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmc_toolkit.spec import cli  # noqa: E402
from tests.test_review_catalog import REVIEW_CATALOG  # noqa: E402

PDF = b"%PDF-1.5\n%dropin\n" + b"d" * 128


@pytest.fixture
def catalog_path(tmp_path):
    p = tmp_path / "review_catalog.toml"
    p.write_text(REVIEW_CATALOG, encoding="utf-8", newline="")
    return p


@pytest.fixture
def lib_root(tmp_path, monkeypatch):
    root = tmp_path / "library"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))

    def refuse(url):
        raise AssertionError(f"network call in a Drop-in test: {url}")

    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: refuse)
    return root


def run(capsys, catalog_path, *argv):
    code = cli.main(["--catalog", str(catalog_path), *argv])
    return code, capsys.readouterr().out


def read_meta(vdir):
    return json.loads((vdir / "meta.json").read_text("utf-8"))


# ----------------------------------------------------------------- AC-10


def test_add_copies_file_and_writes_dropin_meta(catalog_path, lib_root, tmp_path, capsys):
    src = tmp_path / "from-vendor.pdf"
    src.write_bytes(PDF)
    code, out = run(
        capsys, catalog_path, "add", str(src), "--document", "dsp0236", "--version", "1.9.9"
    )
    assert code == 0
    vdir = lib_root / "specs" / "mctp" / "DSP0236" / "1.9.9"
    assert (vdir / "original.pdf").read_bytes() == PDF
    assert src.is_file(), "add copies, it does not move"
    meta = read_meta(vdir)
    assert meta["dropin"] is True
    assert meta.get("url") in (None, "")
    assert meta["document"] == "DSP0236"
    assert meta["version"] == "1.9.9"  # a version the catalog does not know is allowed
    assert meta["sha256"] == hashlib.sha256(PDF).hexdigest()


def test_add_confidential_document_records_no_url(catalog_path, lib_root, tmp_path, capsys):
    src = tmp_path / "secret.pdf"
    src.write_bytes(PDF)
    code, out = run(
        capsys, catalog_path, "add", str(src), "--document", "SECRET", "--version", "0.9"
    )
    assert code == 0
    meta = read_meta(lib_root / "specs" / "vendor" / "SECRET" / "0.9")
    assert meta.get("url") in (None, "")
    assert "example.invalid" not in json.dumps(meta)


def test_add_rejects_unknown_document_and_missing_file(
    catalog_path, lib_root, tmp_path, capsys
):
    src = tmp_path / "x.pdf"
    src.write_bytes(PDF)
    code, out = run(
        capsys, catalog_path, "add", str(src), "--document", "NOPE", "--version", "1"
    )
    assert code == 2
    assert not (lib_root / "specs").exists() or not any(
        (lib_root / "specs").rglob("meta.json")
    )
    code, out = run(
        capsys,
        catalog_path,
        "add",
        str(tmp_path / "absent.pdf"),
        "--document",
        "DSP0236",
        "--version",
        "1",
    )
    assert code == 2


def test_add_refuses_to_replace_a_present_version_without_force(
    catalog_path, lib_root, tmp_path, capsys
):
    """AC-10 with the round-1 fix: a version already in the Library (here one
    that looks fetched) is not overwritten unless --force is given."""
    vdir = lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3"
    vdir.mkdir(parents=True)
    fetched = b"%PDF-1.7\n%publisher copy\n" + b"p" * 64
    (vdir / "original.pdf").write_bytes(fetched)
    fetched_meta = {
        "family": "mctp",
        "document": "DSP0236",
        "version": "1.3.3",
        "file": "original.pdf",
        "url": "https://example.invalid/DSP0236_1.3.3.pdf",
        "fetch_method": "direct",
        "sha256": hashlib.sha256(fetched).hexdigest(),
        "size": len(fetched),
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "dropin": False,
    }
    (vdir / "meta.json").write_text(json.dumps(fetched_meta), encoding="utf-8")

    mine = tmp_path / "mine.pdf"
    mine.write_bytes(PDF)
    args = ["add", str(mine), "--document", "DSP0236", "--version", "1.3.3"]
    code, out = run(capsys, catalog_path, *args)
    assert code == 2
    assert "force" in out.lower()
    assert (vdir / "original.pdf").read_bytes() == fetched
    assert read_meta(vdir) == fetched_meta

    code, out = run(capsys, catalog_path, *args, "--force")
    assert code == 0
    assert (vdir / "original.pdf").read_bytes() == PDF
    meta = read_meta(vdir)
    assert meta["dropin"] is True
    assert meta.get("url") in (None, "")
    assert meta["sha256"] == hashlib.sha256(PDF).hexdigest()


def test_add_rejects_a_block_page_saved_as_pdf(catalog_path, lib_root, tmp_path, capsys):
    """A file whose bytes are not a PDF must not become a Drop-in."""
    fake = tmp_path / "blocked.pdf"
    fake.write_bytes(b"<!DOCTYPE html><html><body>Access denied</body></html>")
    code, out = run(
        capsys, catalog_path, "add", str(fake), "--document", "DSP0236", "--version", "1.3.2"
    )
    assert code == 2
    assert not (lib_root / "specs" / "mctp" / "DSP0236" / "1.3.2").exists()


# ----------------------------------------------------------------- AC-11


def test_scan_registers_hand_placed_files_and_reports_the_rest(
    catalog_path, lib_root, capsys
):
    placed = lib_root / "specs" / "mctp" / "DSP0236" / "1.3.2"
    placed.mkdir(parents=True)
    (placed / "original.pdf").write_bytes(PDF)
    already = lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3"
    already.mkdir(parents=True)
    (already / "original.pdf").write_bytes(PDF)
    (already / "meta.json").write_text(
        json.dumps({"document": "DSP0236", "version": "1.3.3", "dropin": False}),
        encoding="utf-8",
    )
    odd = lib_root / "specs" / "ipmi" / "IPMI" / "2.0_rev_1.1"
    odd.mkdir(parents=True)
    (odd / "original.docx").write_bytes(b"not a spec type")

    code, out = run(capsys, catalog_path, "scan")
    assert code == 0
    meta = read_meta(placed)
    assert meta["dropin"] is True
    assert meta["document"] == "DSP0236"
    assert meta["version"] == "1.3.2"
    assert meta.get("url") in (None, "")
    assert meta["sha256"] == hashlib.sha256(PDF).hexdigest()
    # the registered directory is named in the report
    assert "1.3.2" in out
    # the one already registered is left alone
    assert read_meta(already)["dropin"] is False
    # the uninterpretable one is reported and not registered
    assert not (odd / "meta.json").exists()
    assert "original.docx" in out or "2.0_rev_1.1" in out

    # scanning again registers nothing new
    code, out = run(capsys, catalog_path, "scan")
    assert code == 0
    assert read_meta(placed)["sha256"] == hashlib.sha256(PDF).hexdigest()


def test_scan_on_empty_library_is_a_clean_no_op(catalog_path, lib_root, capsys):
    code, out = run(capsys, catalog_path, "scan")
    assert code == 0


def test_scan_does_not_register_a_block_page_saved_as_pdf(
    catalog_path, lib_root, capsys
):
    bad = lib_root / "specs" / "mctp" / "DSP0236" / "1.3.2"
    bad.mkdir(parents=True)
    (bad / "original.pdf").write_bytes(b"<html><body>Access denied</body></html>")
    good = lib_root / "specs" / "mctp" / "DSP0236" / "1.3.3"
    good.mkdir(parents=True)
    (good / "original.pdf").write_bytes(PDF)
    code, out = run(capsys, catalog_path, "scan")
    assert code == 0
    assert not (bad / "meta.json").exists()
    assert read_meta(good)["dropin"] is True
    assert "1.3.2" in out  # the rejected directory is reported


# ----------------------------------------------------------------- AC-12


def test_status_lists_holdings_and_flags_dropins(catalog_path, lib_root, tmp_path, capsys):
    code, out = run(capsys, catalog_path, "status")
    assert code == 0
    assert str(lib_root) in out

    src = tmp_path / "hand.pdf"
    src.write_bytes(PDF)
    assert (
        run(
            capsys,
            catalog_path,
            "add",
            str(src),
            "--document",
            "IPMI",
            "--version",
            "2.0 rev 1.1",
        )[0]
        == 0
    )
    code, out = run(capsys, catalog_path, "status")
    assert code == 0
    assert str(lib_root) in out
    rows = [ln for ln in out.splitlines() if "IPMI" in ln and "2.0 rev 1.1" in ln]
    assert len(rows) == 1, out
    assert "dropin" in rows[0].lower()
