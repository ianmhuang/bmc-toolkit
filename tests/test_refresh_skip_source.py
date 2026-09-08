"""``refresh --skip-source`` (AC-1, AC-2): documents listed by a skipped
publisher are neither contacted nor reported. The client answers nothing,
so every document that is asked about shows up as ``unreachable`` and the
call list says who was asked."""

import pytest

from bmc_toolkit.spec import cli
from tests.conftest import MINI_CATALOG, ScriptedClient

DMTF_DSP0236 = "https://www.dmtf.org/dsp/DSP0236"
NVME_API = "https://nvmexpress.org/wp-json/vtm/v1/specifications"
OCP_WIKI = (
    "https://www.opencompute.org/w/index.php?title=Server/MHS/DC-MHS-Specs-and-Designs"
)

# DSP0236 (DMTF, implied listing) from the mini catalog plus one NVMe and
# one OCP document with explicit listings.
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
url = "https://example.test/NVM-Express-Management-Interface-Specification-2.1.pdf"
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
version = "1.05"
url = "https://example.test/m-crps-1.05.pdf"
type = "pdf"
published = "2025-01-01"
"""
)


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "lib"))
    scripted = ScriptedClient({})
    scripted.built = 0  # how often refresh asked for a client

    def factory():
        scripted.built += 1
        return scripted

    monkeypatch.setattr(cli, "CLIENT_FACTORY", factory)
    return scripted


def run(capsys, *argv, catalog_file):
    code = cli.main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def _summary(out: str) -> str:
    lines = [ln for ln in out.splitlines() if ln.startswith("summary: ")]
    assert len(lines) == 1, out
    return lines[0]


def _unreachable(out: str) -> set[str]:
    return {
        ln.split()[1].rstrip(":")
        for ln in out.splitlines()
        if ln.startswith("unreachable ")
    }


# ---------------------------------------------------------------- AC-1


def test_without_the_flag_every_listed_document_is_asked_about(
    catalog_file, client, capsys
):
    code, out = run(capsys, "refresh", catalog_file=catalog_file)
    assert code == 0, out
    assert _unreachable(out) == {"DSP0236", "NVME-MI", "M-CRPS"}
    assert "unreachable 3" in _summary(out)
    assert OCP_WIKI in client.calls


def test_skip_source_ocp_leaves_ocp_unasked_and_unreported(
    catalog_file, client, capsys
):
    code, out = run(
        capsys, "refresh", "--skip-source", "ocp", catalog_file=catalog_file
    )
    assert code == 0, out
    assert _unreachable(out) == {"DSP0236", "NVME-MI"}
    assert "M-CRPS" not in out
    assert _summary(out).startswith(
        "summary: add 0, confirm 0, changed 0, unreachable 2"
    )
    assert OCP_WIKI not in client.calls
    assert DMTF_DSP0236 in client.calls or any("dmtf.org" in c for c in client.calls)
    assert NVME_API in client.calls


def test_skip_source_is_repeatable(catalog_file, client, capsys):
    code, out = run(
        capsys,
        "refresh",
        "--skip-source",
        "dmtf",
        "--skip-source",
        "nvme",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    assert _unreachable(out) == {"M-CRPS"}
    assert "unreachable 1" in _summary(out)
    assert client.calls == [OCP_WIKI]


def test_skipping_every_source_asks_nobody_and_counts_nothing(
    catalog_file, client, capsys
):
    code, out = run(
        capsys,
        "refresh",
        "--skip-source",
        "dmtf",
        "--skip-source",
        "nvme",
        "--skip-source",
        "ocp",
        "--write",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    assert _unreachable(out) == set()
    assert (
        _summary(out)
        == "summary: add 0, confirm 0, changed 0, unreachable 0, written 0"
    )
    assert client.calls == []
    assert client.built == 0  # not even a client is made


def test_unknown_source_is_an_argparse_error(catalog_file, client, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--catalog", str(catalog_file), "refresh", "--skip-source", "uefi"])
    assert exc.value.code == 2
    assert "dmtf" in capsys.readouterr().err
    assert client.calls == []


def test_help_names_the_flag_and_the_sources(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["refresh", "--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert "--skip-source SOURCE" in text
    assert "dmtf, nvme, ocp" in text


# ---------------------------------------------------------------- AC-2


def test_naming_a_document_of_a_skipped_source_exits_2_without_contact(
    catalog_file, client, capsys
):
    code, out = run(
        capsys, "refresh", "M-CRPS", "--skip-source", "ocp", catalog_file=catalog_file
    )
    assert code == 2
    assert "M-CRPS" in out and "ocp" in out and "--skip-source" in out
    assert "summary:" not in out
    assert client.calls == []


def test_naming_a_document_of_another_source_still_runs(catalog_file, client, capsys):
    code, out = run(
        capsys, "refresh", "NVME-MI", "--skip-source", "ocp", catalog_file=catalog_file
    )
    assert code == 0, out
    assert _unreachable(out) == {"NVME-MI"}
    assert client.calls == [NVME_API]
