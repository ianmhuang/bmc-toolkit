"""Reviewer acceptance tests for M10: `refresh --write` inserts a newly
seen version at its place in the publication order of the document's
version blocks (AC-7), and the OCP listing key reads version numbers the
way the catalog orders them, through one function (AC-8).

Black-box through the ``bmcspec`` CLI with a scripted DMTF and OCP listing;
the direct calls go to the public functions of ``refresh`` and ``listing``.
Nothing touches the network.
"""

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec import listing as listing_mod
from bmc_toolkit.spec import refresh as refresh_mod
from bmc_toolkit.spec.catalog import load_catalog, version_numbers
from bmc_toolkit.spec.fetch import Response
from tests.conftest import MINI_CATALOG, ScriptedClient

DMTF_DSP0236 = "https://www.dmtf.org/dsp/DSP0236"
OCP_PAGE = "Server/MHS/DC-MHS-Specs-and-Designs"
OCP_WIKI = f"https://www.opencompute.org/w/index.php?title={OCP_PAGE}"
DRIVE_URL = "https://drive.google.com/file/d/review-m10/view"

# The catalog's DSP0236 block: 1.3.2 (2024-01-02), 1.3.3 (2024-03-25) and
# 1.4.0 (WIP, 2025-06-01), in that order.
URL = "https://example.test/DSP0236_{v}.pdf"
ROWS = (
    ("1.3.4", "3 Aug 2026", "Standard"),  # newer than all: last
    ("1.2.0", "1 Jan 2023", "Standard"),  # older than all: first
    ("1.3.2", "2 Jan 2024", "Standard"),  # known, same URL: nothing
    ("1.3.2.1", "1 Feb 2024", "Standard"),  # between 1.3.2 and 1.3.3
    ("1.3.2.5", "25 Mar 2024", "Standard"),  # same day as 1.3.3, lower: before
    ("1.3.3", "25 Mar 2024", "Standard"),  # known, same URL: nothing
    ("1.4.0", "1 Jun 2025", "Work in Progress"),  # known WIP: nothing
)
EXPECTED_ORDER = ["1.2.0", "1.3.2", "1.3.2.1", "1.3.2.5", "1.3.3", "1.4.0", "1.3.4"]
INNER_COMMENT = "# the first block is the oldest (review fixture)"


def dsp_page(rows=ROWS) -> str:
    body = "".join(
        f'<tr><td>{v}</td><td><a href="{URL.format(v=v)}">MCTP Base</a></td>'
        f"<td>{date}</td><td>{comment}</td></tr>"
        for v, date, comment in rows
    )
    return (
        "<html><body><table><thead><tr><th>Version</th><th>Title</th>"
        "<th>Publication Date</th><th>Comments</th></tr></thead>"
        f"<tbody>{body}</tbody></table></body></html>"
    )


def ocp_page(version: str) -> str:
    return (
        '<html><body><table class="wikitable"><tbody>'
        "<tr><th>Type</th><th>Description</th><th>Version</th><th>Submit Date</th>"
        "<th>Contributor</th><th>Link</th><th>Notes</th></tr>"
        f"<tr><td>Specification</td><td>M-CRPS Base Specification</td><td>{version}</td>"
        f'<td>4/24/26</td><td>Someone</td><td><a href="{DRIVE_URL}">Link</a></td>'
        "<td></td></tr></tbody></table></body></html>"
    )


OCP_BLOCK = """
[families.ocp]
title = "OCP"
publisher = "Open Compute Project"

[[documents]]
id = "M-CRPS"
family = "ocp"
title = "M-CRPS Base Specification"
access = "open"
fetch = "direct"
listing = "ocp:Server/MHS/DC-MHS-Specs-and-Designs|M-CRPS Base"

[[documents.versions]]
version = "R1 v1.00 RC4"
url = "https://example.test/m-crps-r1-v1p00-rc4-pdf"
type = "pdf"
published = "2023-01-01"
"""


def html(text: str) -> Response:
    return Response(200, {"content-type": "text/html"}, text.encode("utf-8"))


@pytest.fixture
def catalog_file(tmp_path):
    marker = 'fetch = "direct"\n\n[[documents.versions]]\nversion = "1.3.2"'
    assert MINI_CATALOG.count(marker) == 1
    text = MINI_CATALOG.replace(
        marker, f'fetch = "direct"\n{INNER_COMMENT}\n\n' + marker.split("\n\n", 1)[1]
    )
    assert INNER_COMMENT in text
    path = tmp_path / "catalog.toml"
    path.write_text(text + OCP_BLOCK, encoding="utf-8", newline="")
    load_catalog(path)
    return path


@pytest.fixture
def lib_root(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(root))
    return root


@pytest.fixture
def client(monkeypatch):
    scripted = ScriptedClient(
        {DMTF_DSP0236: html(dsp_page()), OCP_WIKI: html(ocp_page("1.0 RC4"))}
    )
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: scripted)
    return scripted


def run(capsys, *argv, catalog_file):
    code = cli.main(["--catalog", str(catalog_file), *argv])
    return code, capsys.readouterr().out


def _block(text: str, doc_id: str) -> str:
    start = text.index(f'id = "{doc_id}"')
    end = text.index("[[documents]]", start)
    return text[start:end]


def _order(block: str) -> list[str]:
    positions = []
    for line in block.split("\n"):
        if line.startswith("version = "):
            positions.append(line.split('"')[1])
    return positions


# ------------------------------------------------------------------ AC-7


def test_ac7_refresh_write_inserts_each_version_at_its_place(
    catalog_file, lib_root, client, capsys
):
    before = catalog_file.read_text("utf-8")
    code, out = run(capsys, "refresh", "DSP0236", "--write", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert sum(ln.startswith("add DSP0236 ") for ln in lines) == 4, out
    assert "written 4" in lines[-1], lines[-1]
    after = catalog_file.read_text("utf-8")
    assert "\r" not in catalog_file.read_bytes().decode("utf-8")
    block = _block(after, "DSP0236")
    assert _order(block) == EXPECTED_ORDER
    assert block.count("[[documents.versions]]") == 7
    # one blank line between blocks, none doubled, the comment where it was
    assert "\n\n\n" not in after
    assert f'fetch = "direct"\n{INNER_COMMENT}\n\n[[documents.versions]]' in after
    # every original line survives, in order
    it = iter(after.split("\n"))
    for original in before.split("\n"):
        assert any(got == original for got in it), original
    # the document that follows is still exactly one blank line away
    assert '\n\n[[documents]]\nid = "IPMI"' in after
    # each inserted block is complete
    for v, date in (("1.2.0", "2023-01-01"), ("1.3.2.5", "2024-03-25")):
        i = block.index(f'version = "{v}"')
        chunk = block[i : block.index("[[documents", i)]
        assert f'url = "{URL.format(v=v)}"' in chunk
        assert 'type = "pdf"' in chunk
        assert f'published = "{date}"' in chunk
    # the file parses and the catalog reads the versions in file order
    doc = load_catalog(catalog_file).get("DSP0236")
    assert [v.version for v in doc.versions] == EXPECTED_ORDER
    keys = [(v.published, version_numbers(v.version)) for v in doc.versions]
    assert keys == sorted(keys), keys
    assert doc.latest().version == "1.3.4"
    assert doc.find_version("1.4.0").wip
    # a second run has nothing to add and changes nothing
    code, out = run(capsys, "refresh", "DSP0236", "--write", catalog_file=catalog_file)
    assert code == 0, out
    assert not any(ln.startswith("add ") for ln in out.splitlines())
    assert catalog_file.read_text("utf-8") == after


def test_ac7_an_older_version_alone_goes_before_the_first_block(
    catalog_file, lib_root, client, capsys
):
    client.responses[DMTF_DSP0236] = html(
        dsp_page((("1.2.0", "1 Jan 2023", "Standard"),))
    )
    code, out = run(capsys, "refresh", "DSP0236", "--write", catalog_file=catalog_file)
    assert code == 0, out
    after = catalog_file.read_text("utf-8")
    block = _block(after, "DSP0236")
    assert _order(block) == ["1.2.0", "1.3.2", "1.3.3", "1.4.0"]
    assert "\n\n\n" not in after
    # the header of the document is untouched and one blank line away
    assert (
        f'fetch = "direct"\n{INNER_COMMENT}\n\n[[documents.versions]]\nversion = "1.2.0"'
        in after
    )
    assert load_catalog(catalog_file).get("DSP0236").latest().version == "1.3.3"


def test_ac7_append_versions_orders_by_date_then_numbers(catalog_file):
    seen = [
        listing_mod.Seen("1.3.2.9", URL.format(v="1.3.2.9"), "2024-03-25"),
        listing_mod.Seen("1.3.1", URL.format(v="1.3.1"), "2023-12-01", "Errata"),
        listing_mod.Seen("1.3.3.1", URL.format(v="1.3.3.1"), "2024-03-25"),
    ]
    refresh_mod.append_versions(catalog_file, "DSP0236", seen)
    text = catalog_file.read_text("utf-8")
    block = _block(text, "DSP0236")
    # 1.3.3.1 shares the day with 1.3.3 and sorts after it by number, so it
    # sits between 1.3.3 and the WIP 1.4.0 of 2025; 1.3.2.9 sits before 1.3.3
    assert _order(block) == ["1.3.1", "1.3.2", "1.3.2.9", "1.3.3", "1.3.3.1", "1.4.0"]
    assert "\n\n\n" not in text
    assert 'notes = "Errata"' in block
    doc = load_catalog(catalog_file).get("DSP0236")
    assert [v.version for v in doc.versions] == _order(block)
    assert doc.latest().version == "1.3.3.1"


def test_ac7_a_newer_version_still_goes_last_and_a_bad_edit_is_restored(
    catalog_file, lib_root, client, capsys, monkeypatch
):
    client.responses[DMTF_DSP0236] = html(
        dsp_page((("1.3.4", "3 Aug 2026", "Standard"),))
    )
    before = catalog_file.read_bytes()
    with monkeypatch.context() as bad:
        bad.setattr(
            refresh_mod,
            "version_block",
            lambda seen: "[[documents.versions]]\nversion = 1\n",
        )
        code, out = run(capsys, "refresh", "DSP0236", "--write", catalog_file=catalog_file)
    assert code == 1, out
    assert catalog_file.read_bytes() == before
    code, out = run(capsys, "refresh", "DSP0236", "--write", catalog_file=catalog_file)
    assert code == 0, out
    block = _block(catalog_file.read_text("utf-8"), "DSP0236")
    assert _order(block) == ["1.3.2", "1.3.3", "1.4.0", "1.3.4"]


# ------------------------------------------------------------------ AC-8


@pytest.mark.parametrize(
    "a, b",
    [
        ("R1 v1.00 RC4", "1.0 RC4"),
        ("R1 v1.0 RC4", "1.00 rc4"),
        ("Rev 2.1 Ver 1.1", "2.01"),
        ("v1.10", "1.10"),
        ("R1 v2.00", "2.0"),
    ],
)
def test_ac8_ocp_keys_agree_when_the_catalog_reads_the_same_numbers(a, b):
    assert listing_mod.version_key("ocp", a) == listing_mod.version_key("ocp", b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("v1.10", "v1.1"),
        ("R1 v1.2 RC3", "1.2"),
        ("1.2 RC3", "1.2 RC4"),
        ("2.0", "2.1"),
    ],
)
def test_ac8_ocp_keys_differ_when_the_numbers_or_the_rc_differ(a, b):
    assert listing_mod.version_key("ocp", a) != listing_mod.version_key("ocp", b)


@pytest.mark.parametrize(
    "a, b",
    [("1.0", "1.00"), ("2.0.1", "2.00.01"), ("1.10", "1.9"), ("1.2", "1.3")],
)
def test_ac8_one_reading_serves_ordering_and_the_ocp_key(a, b):
    """Two bare OCP numbers are one version exactly when the catalog's
    ordering numbers are equal."""
    same_numbers = version_numbers(a) == version_numbers(b)
    same_key = listing_mod.version_key("ocp", a) == listing_mod.version_key("ocp", b)
    assert same_key is same_numbers, (a, b)


def test_ac8_dmtf_and_nvme_keys_stay_verbatim():
    assert listing_mod.version_key("dmtf", " 1.3.3 ") == "1.3.3"
    assert listing_mod.version_key("dmtf", "1.0") != listing_mod.version_key("dmtf", "1.00")
    assert listing_mod.version_key("nvme", "2.1") != listing_mod.version_key("nvme", "2.10")


def test_ac8_refresh_does_not_ask_to_confirm_an_ocp_version_the_catalog_holds(
    catalog_file, lib_root, client, capsys
):
    """The wiki says ``1.0 RC4`` and the catalog ``R1 v1.00 RC4``: one
    version, so nothing to confirm and nothing to write."""
    before = catalog_file.read_bytes()
    code, out = run(capsys, "refresh", "M-CRPS", "--write", catalog_file=catalog_file)
    assert code == 0, out
    lines = out.splitlines()
    assert not any(ln.startswith(("confirm ", "add ")) for ln in lines), out
    assert "confirm 0" in lines[-1] and "written 0" in lines[-1]
    assert catalog_file.read_bytes() == before
    # a version the catalog lacks is still reported for confirmation
    client.responses[OCP_WIKI] = html(ocp_page("1.06"))
    code, out = run(capsys, "refresh", "M-CRPS", catalog_file=catalog_file)
    assert code == 0, out
    assert any(ln.startswith("confirm M-CRPS 1.06 ") for ln in out.splitlines()), out
