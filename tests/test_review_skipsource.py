"""Reviewer acceptance tests for ``refresh --skip-source`` (AC-1, AC-2),
the 1.1.0 bump (AC-8) and the release-notes grouping file (AC-11).

Black-box through the CLI with a scripted client that answers every
listing, so a skipped publisher is proven both uncontacted (its URL is
absent from the call list) and unreported (its proposal lines are absent
while the others still appear). A second client answers nothing, so the
same holds on a network that is down. Nothing touches the network.
"""

import json
import re
import tomllib
from pathlib import Path

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec.fetch import Response
from tests.conftest import MINI_CATALOG, ScriptedClient, ok

ROOT = Path(__file__).resolve().parents[1]

DMTF_PUBLISHED = "https://www.dmtf.org/standards/published_documents"
DMTF_DSP0236 = "https://www.dmtf.org/dsp/DSP0236"
NVME_API = "https://nvmexpress.org/wp-json/vtm/v1/specifications"
OCP_PAGE = "Server/MHS/DC-MHS-Specs-and-Designs"
OCP_WIKI = f"https://www.opencompute.org/w/index.php?title={OCP_PAGE}"

URL_132 = "https://example.test/DSP0236_1.3.2.pdf"
URL_133 = "https://example.test/DSP0236_1.3.3.pdf"
URL_134 = "https://example.test/DSP0236_1.3.4.pdf"
URL_140 = "https://example.test/DSP0236_1.4.0.pdf"
NVME_MI_22_URL = (
    "https://nvmexpress.org/wp-content/uploads/NVM-Express-Management-Interface-"
    "Specification-Revision-2.2-Ratified-2026.07.31.pdf"
)
DRIVE_URL = "https://drive.google.com/file/d/review-skip/view"

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

NVME_JSON = json.dumps(
    {
        "posts": [
            {
                "slug": "nvme-mi-specification",
                "post_title": "NVM Express Management Interface Specification",
                "file": {"url": NVME_MI_22_URL},
            }
        ]
    }
)

OCP_HTML = f"""
<html><body><table class="wikitable"><tbody>
<tr><th>Type</th><th>Description</th><th>Version</th><th>Submit Date</th>
<th>Contributor</th><th>Link</th><th>Notes</th></tr>
<tr><td>Specification</td><td>M-CRPS Base Specification</td><td>1.06</td>
<td>4/24/26</td><td>Someone</td>
<td><a href="{DRIVE_URL}">Link (Base Spec)</a></td><td></td></tr>
</tbody></table></body></html>
"""

# DSP0236 (DMTF, implied listing) from the mini catalog, plus one NVMe and
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


def html(text: str) -> Response:
    return Response(200, {"content-type": "text/html"}, text.encode("utf-8"))


@pytest.fixture
def catalog_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(CATALOG, encoding="utf-8", newline="")
    return path


@pytest.fixture
def lib_root(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


@pytest.fixture
def client(monkeypatch, lib_root):
    """Every publisher answers, so each listed document yields a proposal."""
    scripted = ScriptedClient(
        {
            DMTF_PUBLISHED: html(PUBLISHED_HTML),
            DMTF_DSP0236: html(DSP_HTML),
            NVME_API: ok(NVME_JSON.encode("utf-8"), "application/json"),
            OCP_WIKI: html(OCP_HTML),
        }
    )
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: scripted)
    return scripted


@pytest.fixture
def dead_client(monkeypatch, lib_root):
    """No publisher answers: every contacted document is ``unreachable``."""
    scripted = ScriptedClient({})
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: scripted)
    return scripted


def run(capsys, *argv, catalog_file):
    code = cli.main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def summary_of(out: str) -> str:
    lines = [ln for ln in out.splitlines() if ln.startswith("summary: ")]
    assert len(lines) == 1, out
    return lines[0]


def counts_of(out: str) -> dict[str, int]:
    """``{"add": n, "confirm": n, "changed": n, "unreachable": n}``."""
    found = re.findall(r"(add|confirm|changed|unreachable) (\d+)", summary_of(out))
    return {kind: int(n) for kind, n in found}


def kinds_by_document(out: str) -> dict[str, set[str]]:
    """Which proposal kinds were printed for which document id."""
    seen: dict[str, set[str]] = {}
    for ln in out.splitlines():
        m = re.match(r"^(add|confirm|changed|unreachable) (\S+?):? ", ln)
        if m:
            seen.setdefault(m.group(2), set()).add(m.group(1))
    return seen


def hosts(calls) -> set[str]:
    return {re.match(r"https://([^/]+)/", url).group(1) for url in calls}


# ----------------------------------------------------------------- AC-1
# control: without the flag every publisher is asked and reported


def test_without_the_flag_every_publisher_is_asked_and_reported(
    catalog_file, client, capsys
):
    code, out = run(capsys, "refresh", catalog_file=catalog_file)
    assert code == 0, out
    assert hosts(client.calls) == {
        "www.dmtf.org",
        "nvmexpress.org",
        "www.opencompute.org",
    }
    by_doc = kinds_by_document(out)
    assert by_doc == {
        "DSP0236": {"add"},
        "NVME-MI": {"add"},
        "M-CRPS": {"confirm"},
    }, out
    assert counts_of(out) == {"add": 2, "confirm": 1, "changed": 0, "unreachable": 0}


def test_skip_source_ocp_neither_contacts_nor_reports_ocp(
    catalog_file, client, capsys
):
    code, out = run(
        capsys, "refresh", "--skip-source", "ocp", catalog_file=catalog_file
    )
    assert code == 0, out
    # not contacted
    assert OCP_WIKI not in client.calls
    assert "www.opencompute.org" not in hosts(client.calls)
    assert hosts(client.calls) == {"www.dmtf.org", "nvmexpress.org"}
    # not reported, while the others still are
    assert "M-CRPS" not in out
    assert DRIVE_URL not in out
    assert kinds_by_document(out) == {"DSP0236": {"add"}, "NVME-MI": {"add"}}, out
    # the summary counts only the rest
    assert counts_of(out) == {"add": 2, "confirm": 0, "changed": 0, "unreachable": 0}
    assert summary_of(out).endswith("(dry run; --write adds them)")


def test_skip_source_dmtf_leaves_dmtf_out_and_the_others_in(
    catalog_file, client, capsys
):
    code, out = run(
        capsys, "refresh", "--skip-source", "dmtf", catalog_file=catalog_file
    )
    assert code == 0, out
    assert "www.dmtf.org" not in hosts(client.calls)
    assert hosts(client.calls) == {"nvmexpress.org", "www.opencompute.org"}
    assert "DSP0236" not in out
    assert kinds_by_document(out) == {"NVME-MI": {"add"}, "M-CRPS": {"confirm"}}
    assert counts_of(out) == {"add": 1, "confirm": 1, "changed": 0, "unreachable": 0}


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
    assert client.calls == [OCP_WIKI]
    assert "DSP0236" not in out and "NVME-MI" not in out
    assert kinds_by_document(out) == {"M-CRPS": {"confirm"}}, out
    assert counts_of(out) == {"add": 0, "confirm": 1, "changed": 0, "unreachable": 0}


def test_repeating_the_same_source_is_harmless(catalog_file, client, capsys):
    code, out = run(
        capsys,
        "refresh",
        "--skip-source",
        "ocp",
        "--skip-source",
        "ocp",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    assert OCP_WIKI not in client.calls
    assert "M-CRPS" not in out
    assert counts_of(out) == {"add": 2, "confirm": 0, "changed": 0, "unreachable": 0}


def test_skipping_every_source_contacts_nobody_and_counts_nothing(
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
        catalog_file=catalog_file,
    )
    assert code == 0, out
    assert client.calls == []
    assert kinds_by_document(out) == {}, out
    assert counts_of(out) == {"add": 0, "confirm": 0, "changed": 0, "unreachable": 0}
    # nothing but the summary line is printed
    assert out.strip().splitlines() == [summary_of(out)]


def test_skip_source_with_write_writes_only_the_remaining_publishers(
    catalog_file, client, capsys
):
    before = catalog_file.read_text("utf-8")
    code, out = run(
        capsys,
        "refresh",
        "--skip-source",
        "nvme",
        "--skip-source",
        "ocp",
        "--write",
        catalog_file=catalog_file,
    )
    assert code == 0, out
    assert client.calls and hosts(client.calls) == {"www.dmtf.org"}
    assert "written 1" in summary_of(out)
    after = catalog_file.read_text("utf-8")
    assert after != before
    assert f'url = "{URL_134}"' in after  # the DMTF proposal landed
    assert NVME_MI_22_URL not in after  # the skipped NVMe proposal did not
    assert DRIVE_URL not in after
    assert "NVME-MI" not in out and "M-CRPS" not in out


def test_skipping_every_source_with_write_leaves_the_catalog_untouched(
    catalog_file, client, capsys
):
    before = catalog_file.read_bytes()
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
    assert client.calls == []
    assert summary_of(out) == (
        "summary: add 0, confirm 0, changed 0, unreachable 0, written 0"
    )
    assert catalog_file.read_bytes() == before


def test_skipped_publisher_is_not_counted_as_unreachable_when_the_network_is_down(
    catalog_file, dead_client, capsys
):
    """The workflow's case: without the flag OCP would be one more
    ``unreachable``; with it the count covers only the publishers asked."""
    code, out = run(capsys, "refresh", catalog_file=catalog_file)
    assert code == 0, out
    assert counts_of(out)["unreachable"] == 3
    assert OCP_WIKI in dead_client.calls

    dead_client.calls.clear()
    code, out = run(
        capsys, "refresh", "--skip-source", "ocp", catalog_file=catalog_file
    )
    assert code == 0, out
    assert kinds_by_document(out) == {
        "DSP0236": {"unreachable"},
        "NVME-MI": {"unreachable"},
    }, out
    assert counts_of(out) == {"add": 0, "confirm": 0, "changed": 0, "unreachable": 2}
    assert OCP_WIKI not in dead_client.calls
    assert "M-CRPS" not in out


@pytest.mark.parametrize("bad", ["uefi", "DMTF", "ocp,dmtf", "all", ""])
def test_unknown_source_is_an_argparse_error_that_contacts_nobody(
    catalog_file, client, capsys, bad
):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--catalog", str(catalog_file), "refresh", "--skip-source", bad])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--skip-source" in err
    assert "dmtf" in err and "nvme" in err and "ocp" in err
    assert client.calls == []


def test_skip_source_without_a_value_is_an_argparse_error(
    catalog_file, client, capsys
):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--catalog", str(catalog_file), "refresh", "--skip-source"])
    assert exc.value.code == 2
    assert client.calls == []


def test_refresh_help_names_the_flag_and_its_three_values(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["refresh", "--help"])
    assert exc.value.code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "--skip-source SOURCE" in text
    assert "dmtf" in text and "nvme" in text and "ocp" in text


def test_check_does_not_take_the_flag(catalog_file, client, capsys):
    """Out of scope by the description: a source filter on ``check``."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["--catalog", str(catalog_file), "check", "--skip-source", "ocp"])
    assert exc.value.code == 2
    assert client.calls == []


# ----------------------------------------------------------------- AC-2


def test_naming_a_document_of_a_skipped_source_exits_2_with_one_line(
    catalog_file, client, capsys
):
    before = catalog_file.read_bytes()
    code, out = run(
        capsys,
        "refresh",
        "M-CRPS",
        "--skip-source",
        "ocp",
        "--write",
        catalog_file=catalog_file,
    )
    assert code == 2, out
    lines = out.strip().splitlines()
    assert len(lines) == 1, out
    assert "M-CRPS" in lines[0]
    assert "ocp" in lines[0]
    assert "skip" in lines[0].lower()
    assert "summary:" not in out
    assert client.calls == []  # not contacted: the client was never used
    assert catalog_file.read_bytes() == before


def test_naming_a_document_of_a_skipped_implied_dmtf_listing_exits_2(
    catalog_file, client, capsys
):
    """DSP0236 has no explicit ``listing``; its source is implied from the
    publisher, and the flag applies to it all the same."""
    code, out = run(
        capsys, "refresh", "DSP0236", "--skip-source", "dmtf", catalog_file=catalog_file
    )
    assert code == 2, out
    assert "DSP0236" in out and "dmtf" in out
    assert "summary:" not in out
    assert client.calls == []


def test_naming_a_document_of_another_source_still_runs(
    catalog_file, client, capsys
):
    code, out = run(
        capsys, "refresh", "NVME-MI", "--skip-source", "ocp", catalog_file=catalog_file
    )
    assert code == 0, out
    assert client.calls == [NVME_API]
    assert kinds_by_document(out) == {"NVME-MI": {"add"}}, out
    assert counts_of(out) == {"add": 1, "confirm": 0, "changed": 0, "unreachable": 0}


def test_unknown_document_still_wins_over_the_skip(catalog_file, client, capsys):
    """The existing exit-2 paths of ``refresh DOC`` are unchanged: an unknown
    document, and one without a listing, are reported as before."""
    code, out = run(
        capsys, "refresh", "NOPE", "--skip-source", "ocp", catalog_file=catalog_file
    )
    assert code == 2
    assert "unknown document 'NOPE'" in out
    assert client.calls == []

    code, out = run(
        capsys, "refresh", "IPMI", "--skip-source", "ocp", catalog_file=catalog_file
    )
    assert code == 2
    assert "IPMI has no publisher listing" in out
    assert client.calls == []


# ----------------------------------------------------------------- AC-8

RELEASE = "1.1.0"


def test_version_1_1_0_in_the_four_records():
    import bmc_toolkit

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    readme = (ROOT / "README.md").read_text("utf-8")
    status = re.search(r"^\*\*Status: ([^*]+)\*\*", readme, re.M)
    assert status is not None
    assert (
        bmc_toolkit.__version__
        == pyproject["project"]["version"]
        == plugin["version"]
        == status.group(1).rstrip(".")
        == RELEASE
    )


def test_marketplace_manifest_carries_no_version():
    manifest = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text("utf-8")
    )
    assert "version" not in manifest
    for plugin in manifest.get("plugins", []):
        assert "version" not in plugin


def test_bmcspec_version_flag_reports_1_1_0(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert f"bmc-toolkit {RELEASE}" in capsys.readouterr().out


# ---------------------------------------------------------------- AC-11


def test_release_yml_groups_by_the_four_labels_and_excludes_skip_changelog():
    path = ROOT / ".github" / "release.yml"
    assert path.is_file()
    text = path.read_text("utf-8")
    assert re.search(r"^changelog:\s*$", text, re.M)
    labels = re.findall(r"^\s+- \"?([\w*-]+)\"?\s*$", text, re.M)
    for label in ("major", "minor", "patch", "docs", "skip-changelog"):
        assert label in labels, (label, labels)
    exclude = text.index("exclude:")
    categories = text.index("categories:")
    assert exclude < text.index("skip-changelog") < categories
    for label in ("major", "minor", "patch", "docs"):
        assert re.search(rf"^\s+- {label}\s*$", text[categories:], re.M), label
