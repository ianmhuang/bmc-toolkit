"""Review tests for the 2026-10-21 catalog batch: DSP0282, DSP0293,
DSP0288, DSP2058 and NVME-NVM join the shipped catalog (AC-1), the DMTF
ids leave not_taken (AC-2), the caption limits are recorded (AC-3), each
document has a Golden Question of its own (AC-5) and docs/SUPPORT.md and
the counts follow (AC-6, AC-7). Shipped files only, no network."""

import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import CatalogError, load_catalog
from bmc_toolkit.spec.cli import main

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "bmc_toolkit" / "spec" / "catalog.toml"
GOLDEN = ROOT / "docs" / "golden-questions.md"
SUPPORT = ROOT / "docs" / "SUPPORT.md"
README = ROOT / "README.md"
MARKER = (
    "<!-- generated below: catalog --table --by-family "
    "--golden docs/golden-questions.md -->"
)
DMTF_FILES = "https://www.dmtf.org/sites/default/files/standards/documents/"

# id -> (family, versions in publication order)
BATCH = {
    "DSP0282": ("mctp", ["1.0.0", "1.0.1", "1.0.2", "1.1.0"]),
    "DSP0293": ("pldm", ["1.0.0"]),
    "DSP0288": ("redfish", ["1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0"]),
    "DSP2058": ("spdm", ["1.0.0", "1.1.0", "1.2.0", "1.3.0"]),
    "NVME-NVM": ("nvme", ["1.3"]),
}
DMTF_IDS = ("DSP0282", "DSP0293", "DSP0288", "DSP2058")
QUESTIONS = {
    "DSP0282": "G104",
    "DSP0293": "G105",
    "DSP0288": "G106",
    "DSP2058": "G107",
    "NVME-NVM": "G108",
}
HEADING = "## Catalog additions of 2026-10-21"
PREVIOUS_HEADING = "## PLDM Platform Descriptor Records"
VERBS = ("find", "page", "table", "section", "extract", "fetch", "registry")


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def _run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _rows(text: str) -> list[list[str]]:
    """(question id, cells) of every Golden row, in file order."""
    rows = []
    for line in text.splitlines():
        if not line.startswith("| G"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        rows.append(cells)
    return rows


# ------------------------------------------------------------------ AC-1


def test_ac1_the_five_are_the_last_documents_in_order(shipped):
    ids = [d.id for d in shipped.documents]
    assert ids[ids.index("DSP0251") + 1 :] == list(BATCH)
    assert ids[-5:] == list(BATCH)
    assert len(ids) == len({i.lower() for i in ids})


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac1_entry_is_open_direct_pdf_with_every_version_in_order(shipped, doc_id):
    family, versions = BATCH[doc_id]
    doc = shipped.get(doc_id)
    assert doc is not None, f"{doc_id} is not in the catalog"
    assert doc.id == doc_id
    assert doc.family == family
    assert doc.title.strip()
    assert doc.access == "open"
    assert doc.fetch == "direct"
    assert doc.unlisted is False
    assert [v.version for v in doc.versions] == versions
    for v in doc.versions:
        assert v.type == "pdf", (doc_id, v.version)
        assert v.url.startswith("https://") and v.url.endswith(".pdf"), v.url
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.published), (doc_id, v.version)
        assert v.wip is False and v.access == "open" and v.open
    # publication order: dates never go backwards along the list
    dates = [v.published for v in doc.versions]
    assert dates == sorted(dates), doc_id
    assert len(set(v.url for v in doc.versions)) == len(versions)
    newest = doc.latest()
    assert newest is not None and newest.version == versions[-1]


@pytest.mark.parametrize("doc_id", DMTF_IDS)
def test_ac1_dmtf_entries_follow_the_dmtf_file_naming_and_listing(shipped, doc_id):
    doc = shipped.get(doc_id)
    assert shipped.families[doc.family].publisher == "DMTF"
    assert doc.listing == f"dmtf:{doc_id}"
    for v in doc.versions:
        assert v.url.startswith(f"{DMTF_FILES}{doc_id}_{v.version}"), v.url


def test_ac1_nvme_nvm_carries_the_nvme_listing(shipped):
    doc = shipped.get("NVME-NVM")
    assert doc.listing == "nvme:nvm-command-set-specification"
    assert doc.listing_source == "nvme"
    assert doc.listing_key == "nvm-command-set-specification"
    assert "nvmexpress.org" in doc.versions[0].url


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac1_catalog_command_names_the_newest_as_latest(capsys, doc_id):
    code, out, err = _run(capsys, "catalog", doc_id)
    assert code == 0, out
    assert err == ""
    lines = out.splitlines()
    assert f"document: {doc_id}" in lines
    assert f"latest: {BATCH[doc_id][1][-1]}" in lines
    assert f"family: {BATCH[doc_id][0]} (" in out
    assert "access: open" in lines and "fetch: direct" in lines
    assert "versions:" in lines
    body = out.split("versions:", 1)[1]
    for version in BATCH[doc_id][1]:
        assert version in body, version


# ------------------------------------------------------------------ AC-2


def test_ac2_the_dmtf_ids_are_listed_and_left_not_taken(shipped):
    listed = shipped.dmtf_listed()
    for dsp in DMTF_IDS:
        assert listed.get(dsp) == dsp, dsp
        assert dsp not in shipped.dmtf_not_taken, dsp
        assert not shipped.dmtf_not_taken_covers(dsp), dsp
    # four entries left; what the review named next is still there
    assert len(shipped.dmtf_not_taken) == 135
    for dsp in ("DSP0285", "DSP0294"):
        assert shipped.dmtf_not_taken_covers(dsp), dsp
        assert dsp not in listed, dsp


def test_ac2_the_catalog_refuses_a_not_taken_entry_that_names_a_taken_one(tmp_path):
    text = CATALOG.read_text(encoding="utf-8")
    assert text.count("not_taken = [\n") == 1
    for dsp in DMTF_IDS:
        bad = text.replace("not_taken = [\n", f'not_taken = [\n    "{dsp}",\n', 1)
        path = tmp_path / f"{dsp}.toml"
        path.write_text(bad, encoding="utf-8", newline="")
        with pytest.raises(CatalogError, match=dsp):
            load_catalog(path)


# ------------------------------------------------------------------ AC-3


@pytest.mark.parametrize(
    "doc_id, words",
    [
        ("DSP0282", ("Table 2", "caption", "Table 1", "byte number", "page")),
        ("DSP2058", ("Table 1", "caption", "page 14", "page 15")),
        ("NVME-NVM", ("Figure 123", "caption", "page")),
    ],
)
def test_ac3_limits_record_the_caption_cases_with_the_command_to_use(
    shipped, doc_id, words
):
    limits = shipped.get(doc_id).limits
    assert limits, doc_id
    for word in words:
        assert word in limits, (doc_id, word)
    assert "`-`" in limits, doc_id


def test_ac3_the_other_two_have_no_limit(shipped):
    assert shipped.get("DSP0293").limits == ""
    assert shipped.get("DSP0288").limits == ""


# ------------------------------------------------------------------ AC-5


def test_ac5_each_document_has_one_golden_question_on_its_newest_version(shipped):
    verified, problems = support.read_golden(GOLDEN, shipped)
    assert problems == []
    for doc_id, qid in QUESTIONS.items():
        pairs = verified.get(doc_id.lower())
        assert pairs == [(qid, BATCH[doc_id][1][-1])], doc_id


def test_ac5_the_group_follows_the_pdr_group_and_ids_stay_gap_free():
    text = GOLDEN.read_text(encoding="utf-8")
    headings = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert text.count(HEADING) == 1
    assert headings.index(PREVIOUS_HEADING) + 1 == headings.index(HEADING), headings
    section = text.split(HEADING, 1)[1].split("\n## ", 1)[0]
    ids = [cells[0] for cells in _rows(section)]
    assert ids == list(QUESTIONS.values())
    numbers = [int(cells[0][1:]) for cells in _rows(text)]
    assert sorted(numbers) == list(range(1, 109))
    assert numbers[numbers.index(103) + 1 :][:5] == [104, 105, 106, 107, 108]


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac5_the_row_names_page_section_or_table_and_commands_on_the_document(
    doc_id,
):
    text = GOLDEN.read_text(encoding="utf-8")
    qid = QUESTIONS[doc_id]
    (cells,) = [c for c in _rows(text) if c[0] == qid]
    assert len(cells) == 5, cells
    newest = BATCH[doc_id][1][-1]
    assert cells[2] == f"{doc_id} {newest}"
    where = cells[3]
    assert where.startswith(f"{doc_id} {newest}, ")
    assert re.search(r"\bpages? \d+", where), where
    assert re.search(r"\b(section \d|Table \d|Figure \d)", where), where
    # every backticked command (a verb then a document) names this document;
    # other backticked text, such as a quoted output line, is not a command
    backticked = [c.split() for c in re.findall(r"`([^`]+)`", cells[4])]
    commands = [words for words in backticked if words[0] in VERBS]
    assert commands, cells[4]
    for words in commands:
        assert words[1] == doc_id, words


# ------------------------------------------------------------------ AC-6


@pytest.fixture
def generated(capsys):
    code, out, err = _run(
        capsys, "catalog", "--table", "--by-family", "--golden", str(GOLDEN)
    )
    assert code == 0, out
    assert err == ""
    return out


def test_ac6_support_doc_is_the_generated_table_with_the_five_as_pass(
    shipped, generated
):
    text = SUPPORT.read_text(encoding="utf-8")
    assert text.count(MARKER) == 1
    body = text.split(MARKER + "\n", 1)[1].lstrip("\n")
    assert body == generated
    for doc_id, (_, versions) in BATCH.items():
        doc = shipped.get(doc_id)
        (row,) = [ln for ln in body.splitlines() if ln.startswith(f"| `{doc_id}` ")]
        cells = [c.strip() for c in row.strip().strip("|").split(" | ")]
        assert cells[0] == f"`{doc_id}` {doc.title}"
        assert cells[1:4] == ["open", versions[-1], "PASS"], doc_id
        assert cells[4] == (doc.limits or "-"), doc_id


def test_ac6_each_row_sits_under_its_family_heading(shipped, generated):
    heading = None
    seen = {}
    for line in generated.splitlines():
        if line.startswith("## "):
            heading = line[3:]
        for doc_id in BATCH:
            if line.startswith(f"| `{doc_id}` "):
                seen[doc_id] = heading
    for doc_id, (family, _) in BATCH.items():
        assert seen.get(doc_id) == shipped.families[family].title, doc_id


# ----------------------------------------------------------- AC-6, AC-7


def test_ac7_counts_grew_by_exactly_the_five_open_entries(shipped):
    docs = shipped.documents
    open_docs = [d for d in docs if d.access == "open"]
    assert len(docs) == 119
    assert len(open_docs) == 99
    assert len(docs) - len(open_docs) == 20
    assert len({d.family for d in docs}) == 35
    # the README status line states the same numbers
    readme = " ".join(README.read_text(encoding="utf-8").split())
    assert "lists 119 documents in 35 families" in readme
    assert "The 99 open ones" in readme
