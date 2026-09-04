"""M10: second round of publishers, manual entries, the kernel Code Tree,
refresh --write insertion order and one version-number reading."""

import pytest

from bmc_toolkit.spec import code as C
from bmc_toolkit.spec import listing as L
from bmc_toolkit.spec import refresh as R
from bmc_toolkit.spec.catalog import load_catalog, version_numbers
from bmc_toolkit.spec.cli import main
from tests.conftest import MINI_CATALOG
from tests.test_code import make_repo

DIRECT_CURRENT_ONLY = [
    ("CALIPTRA", "ocp-security"),
    ("OCP-ATTEST", "ocp-security"),
    ("OCP-NIC", "ocp-nic"),
    ("SFF-8472", "sff"),
    ("SFF-8636", "sff"),
    ("SFF-8024", "sff"),
    ("SP800-193", "nist"),
    ("SBMR", "arm-server"),
    ("SBSA", "arm-server"),
    ("BBR", "arm-server"),
]
TCG_VIA_WAYBACK = [
    "TPM2-P0",
    "TPM2-P1",
    "TPM2-P2",
    "TPM2-P3",
    "TCG-PFP",
    "DICE-HW",
    "DICE-ATT",
]
UEFI_FORUM = {"UEFI": "2.11", "ACPI": "6.6", "PI": "1.10"}
MANUAL = {
    "JESD400-5": "gated",
    "JESD216": "gated",
    "JESD251": "gated",
    "JESD302": "gated",
    "MIPI-I3C-BASIC": "gated",
    "PCIE-BASE": "member",
    "IEEE-1149.1": "member",
    "SES": "member",
    "HPM.1": "member",
    "HPM.2": "member",
    "CXL": "member",
    "PECI": "confidential",
    "PFR": "confidential",
    "ASD": "confidential",
    "SPI-PG": "confidential",
    "APML": "confidential",
    "AST2500": "confidential",
    "AST2600": "confidential",
    "NPCM7XX": "confidential",
    "NPCM8XX": "confidential",
}
LINUX_SPARSE = (
    "Documentation",
    "drivers/hwmon",
    "drivers/i2c",
    "drivers/gpio",
    "drivers/peci",
    "drivers/char/ipmi",
    "net/ncsi",
    "net/mctp",
    "drivers/net/mctp",
    "drivers/mtd/spi-nor",
)


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def run(capsys, *argv, catalog_file=None):
    args = ["--catalog", str(catalog_file)] if catalog_file else []
    code = main([*args, *argv])
    return code, capsys.readouterr().out


# ------------------------------------------------------------------- AC-1


def test_ac1_new_publishers_carry_the_current_version_fetched_directly(shipped):
    for doc_id, family in DIRECT_CURRENT_ONLY:
        doc = shipped.get(doc_id)
        assert doc is not None, doc_id
        assert doc.family == family and shipped.families[family] is not None
        assert doc.fetch == "direct" and doc.access == "open"
        assert len(doc.versions) == 1, doc_id
        (ver,) = doc.versions
        assert ver.open and ver.url.startswith("https://") and ver.type == "pdf"
        assert doc.latest() is ver


def test_ac1_tpm_library_parts_are_searched_together(shipped):
    parts = {"TPM2-P0", "TPM2-P1", "TPM2-P2", "TPM2-P3"}
    for part in parts:
        others = set(shipped.get(part).searched_with)
        assert others == parts - {part}, part
    assert shipped.get("SFF-8472").searched_with == ("SFF-8024",)
    assert shipped.get("DICE-HW").searched_with == ("DICE-ATT",)


def test_ac1_tcg_documents_come_from_the_archive_current_version_only(shipped):
    # TCG answers scripted clients with 403, so the fetch chain goes to the
    # Internet Archive straight away; the catalog says so in the notes.
    for doc_id in TCG_VIA_WAYBACK:
        doc = shipped.get(doc_id)
        assert doc is not None and doc.family == "tcg", doc_id
        assert doc.fetch == "wayback" and doc.access == "open"
        assert len(doc.versions) == 1 and doc.versions[0].open
        assert "Internet Archive" in doc.notes


# ------------------------------------------------------------------- AC-2


def test_ac2_uefi_forum_documents_hold_the_newest_and_the_previous_release(shipped):
    for doc_id, newest in UEFI_FORUM.items():
        doc = shipped.get(doc_id)
        assert doc is not None and doc.family == "uefi", doc_id
        assert doc.fetch == "wayback" and doc.access == "open"
        assert len(doc.versions) == 2, doc_id
        assert doc.latest().version == newest
        older, newer = doc.versions
        assert older.published < newer.published
        assert all(v.open for v in doc.versions)
        assert all(v.url.startswith("https://uefi.org/") for v in doc.versions)
        assert "Internet Archive" in doc.notes


# ------------------------------------------------------------------- AC-3


def test_ac3_manual_entries_name_the_tier_and_the_reason_and_carry_no_url(shipped):
    for doc_id, tier in MANUAL.items():
        doc = shipped.get(doc_id)
        assert doc is not None, doc_id
        assert doc.fetch == "manual" and doc.access == tier, doc_id
        assert doc.versions == (), doc_id
        assert doc.notes, doc_id
        assert doc.latest() is None and doc.newest_open() is None


def test_ac3_no_manual_document_in_the_shipped_catalog_carries_a_url(shipped):
    manual = [d for d in shipped.documents if d.fetch == "manual"]
    assert len(manual) >= len(MANUAL)
    assert all(v.url == "" for d in manual for v in d.versions)
    assert all(d.access != "open" for d in manual)


def test_ac3_fetch_all_skips_manual_entries_without_touching_the_network(
    tmp_path, library, scripted, capsys
):
    only_manual = (
        "schema_version = 1\n\n"
        '[families.jedec]\ntitle = "JEDEC"\npublisher = "JEDEC"\n\n'
        '[[documents]]\nid = "JESD216"\nfamily = "jedec"\ntitle = "SFDP"\n'
        'access = "gated"\nfetch = "manual"\nnotes = "registration"\n'
    )
    path = tmp_path / "manual.toml"
    path.write_text(only_manual, encoding="utf-8", newline="")
    code, out = run(capsys, "fetch", "--all", catalog_file=path)
    assert code == 0, out
    assert scripted.calls == []
    assert "JESD216" not in out or "skipped" in out


def test_ac3_catalog_prints_the_add_instruction_for_a_manual_document(library, capsys):
    code, out = run(capsys, "catalog", "JESD216")
    assert code == 0, out
    assert "add FILE --document JESD216" in out or "bmcspec add" in out
    assert "https://" not in out


def test_ac3_support_table_lists_manual_documents_with_their_tier(library, capsys):
    code, out = run(capsys, "catalog", "--table")
    assert code == 0
    rows = {}
    for line in out.splitlines():
        if line.startswith("| ") and "`" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows[cells[1].split("`")[1]] = cells
    for doc_id, tier in MANUAL.items():
        cells = rows[doc_id]
        assert cells[2] == tier, doc_id
        assert cells[4] == "manual (Drop-in)", doc_id
        assert cells[3] == "-", doc_id  # no version to name


# ------------------------------------------------------------------- AC-4


def test_ac4_linux_is_a_sparse_code_tree_with_the_kernel_topics(shipped):
    linux = shipped.get_repo("linux")
    assert linux is not None
    assert linux.url == "https://github.com/openbmc/linux.git"
    assert linux.sparse == LINUX_SPARSE
    for topic in ("hwmon", "ipmi", "mctp", "ncsi", "peci", "i2c", "gpio", "docs"):
        assert topic in linux.topics, topic


def test_ac4_repos_topic_lists_linux(library, capsys):
    for topic in ("hwmon", "ipmi", "mctp", "ncsi", "peci"):
        code, out = run(capsys, "repos", "--topic", topic)
        assert code == 0, (topic, out)
        assert any(line.startswith("linux\t") for line in out.splitlines()), topic


def test_ac4_sparse_directory_list_checks_out_only_those_paths(tmp_path):
    library = C.CodeLibrary(tmp_path / "lib")
    files = {
        "Documentation/hwmon/index.rst": "a\n",
        "drivers/hwmon/lm75.c": "b\n",
        "drivers/net/mctp/mctp-i2c.c": "c\n",
        "drivers/net/ethernet/x.c": "d\n",
        "drivers/gpu/big.c": "e\n",
        "net/mctp/route.c": "f\n",
        "net/ipv4/y.c": "g\n",
        "README": "h\n",
    }
    _, _, url = make_repo(tmp_path, "linux", files)
    tree, _ = library.clone(
        "linux",
        url,
        C.Provenance("ref", "main"),
        ref="main",
        sparse=("Documentation", "drivers/hwmon", "drivers/net/mctp", "net/mctp"),
    )
    for present in (
        "Documentation/hwmon/index.rst",
        "drivers/hwmon/lm75.c",
        "drivers/net/mctp/mctp-i2c.c",
        "net/mctp/route.c",
    ):
        assert (tree.path / present).is_file(), present
    for absent in ("drivers/net/ethernet/x.c", "drivers/gpu/big.c", "net/ipv4/y.c"):
        assert not (tree.path / absent).exists(), absent
    # cone-mode sparse checkout always keeps the files of the top directory
    # (the kernel's Makefile, MAINTAINERS and so on); only trees are cut.
    assert (tree.path / "README").is_file()


# ------------------------------------------------------------------- AC-7


@pytest.fixture
def mini_file(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(MINI_CATALOG, encoding="utf-8", newline="")
    return path


def _positions(text, versions):
    return [text.index(f'version = "{v}"') for v in versions]


def test_ac7_refresh_write_inserts_an_older_version_at_its_place(mini_file):
    # DSP0236 holds 1.3.2 (2024-01-02), 1.3.3 (2024-03-25), 1.4.0 (WIP,
    # 2025-06-01). A version published between the first two goes between
    # them; one older than all goes first; a newer one still goes last.
    seen = [
        L.Seen("1.3.2.1", "https://example.test/DSP0236_1.3.2.1.pdf", "2024-02-01"),
        L.Seen("1.2.0", "https://example.test/DSP0236_1.2.0.pdf", "2023-01-01"),
        L.Seen("1.5.0", "https://example.test/DSP0236_1.5.0.pdf", "2026-01-01"),
    ]
    R.append_versions(mini_file, "DSP0236", seen)
    text = mini_file.read_text("utf-8")
    order = ["1.2.0", "1.3.2", "1.3.2.1", "1.3.3", "1.4.0", "1.5.0"]
    assert _positions(text, order) == sorted(_positions(text, order))
    assert "\n\n\n" not in text  # one blank line between blocks, as before
    doc = load_catalog(mini_file).get("DSP0236")
    assert [v.version for v in doc.versions] == order
    keys = [(v.published, version_numbers(v.version)) for v in doc.versions]
    assert keys == sorted(keys)
    # the block that follows DSP0236 is intact and still one blank line away
    assert '\n\n[[documents]]\nid = "IPMI"' in text


def test_ac7_same_day_older_number_goes_before_the_existing_entry(mini_file):
    seen = [L.Seen("1.3.2a", "https://example.test/DSP0236_1.3.2a.pdf", "2024-03-25")]
    R.append_versions(mini_file, "DSP0236", seen)
    doc = load_catalog(mini_file).get("DSP0236")
    # same day as 1.3.3, lower numbers: before it
    assert [v.version for v in doc.versions] == ["1.3.2", "1.3.2a", "1.3.3", "1.4.0"]
    assert doc.latest().version == "1.3.3"


# ------------------------------------------------------------------- AC-8


@pytest.mark.parametrize(
    "a, b, same",
    [
        ("R1 v1.0 RC4", "1.00 rc4", True),  # the catalog's reading: numbers
        ("v1.10", "v1.1", False),
        ("Rev 2.1 Ver 1.1", "2.01", True),
        ("R1 v1.2 RC3", "1.2", False),
    ],
)
def test_ac8_ocp_version_key_reads_numbers_like_the_catalog(a, b, same):
    assert (L.version_key("ocp", a) == L.version_key("ocp", b)) is same


def test_ac8_dmtf_and_nvme_keys_stay_verbatim():
    assert L.version_key("dmtf", " 1.3.3 ") == "1.3.3"
    assert L.version_key("nvme", "2.1") != L.version_key("nvme", "2.10")
