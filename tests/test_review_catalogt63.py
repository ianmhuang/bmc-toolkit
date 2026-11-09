"""Review tests for the 2026-11-08 catalog batch: DSP0285 RedPath and
DSP0294 DMTF Authorization Policy join the shipped catalog after NVME-NVM
(AC-1), leave ``[listings.dmtf] not_taken`` (AC-2), carry no limits
(AC-3), each has a Golden Question of its own (AC-5), and docs/SUPPORT.md
and the counts follow (AC-6, AC-7). Shipped files only, no network."""

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

# id -> (family, title, (version, published) in publication order)
BATCH = {
    "DSP0285": (
        "redfish",
        "RedPath Specification",
        (
            ("1.0.0", "2022-11-30"),
            ("1.0.1", "2023-01-23"),
            ("1.1.0", "2023-05-22"),
        ),
    ),
    "DSP0294": (
        "spdm",
        "DMTF Authorization Policy Specification",
        (("1.0.0", "2026-08-31"),),
    ),
}
QUESTIONS = {"DSP0285": "G109", "DSP0294": "G110"}
HEADING = "## Catalog additions of 2026-11-08"
PREVIOUS_HEADING = "## Catalog additions of 2026-10-21"
# the candidates the request left for later: still not taken
# T72 (2026-11-09) took DSP0220, DSP0244 and DSP0280; white papers are left
LEFT = ("DSP2015", "DSP2054", "DSP2072")
VERBS = ("find", "page", "table", "section", "extract", "fetch", "registry")


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def _run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _rows(text: str) -> list[list[str]]:
    """The cells of every Golden row, in file order."""
    rows = []
    for line in text.splitlines():
        if not line.startswith("| G"):
            continue
        rows.append([c.strip() for c in line.strip().strip("|").split(" | ")])
    return rows


# ------------------------------------------------------------------ AC-1


def test_ac1_the_two_follow_nvme_nvm(shipped):
    ids = [d.id for d in shipped.documents]
    # T72 (2026-11-09) added DSP0220, DSP0244 and DSP0280 after the two
    assert ids[ids.index("NVME-NVM") + 1 :] == [
        "DSP0285",
        "DSP0294",
        "DSP0220",
        "DSP0244",
        "DSP0280",
    ]
    assert len(ids) == len({i.lower() for i in ids})


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac1_entry_is_open_direct_pdf_with_every_version_in_order(shipped, doc_id):
    family, title, versions = BATCH[doc_id]
    doc = shipped.get(doc_id)
    assert doc is not None, f"{doc_id} is not in the catalog"
    assert doc.id == doc_id
    assert doc.family == family
    assert doc.title == title
    assert doc.access == "open"
    assert doc.fetch == "direct"
    assert doc.unlisted is False
    assert [(v.version, v.published) for v in doc.versions] == list(versions)
    for v in doc.versions:
        assert v.type == "pdf", (doc_id, v.version)
        assert v.url == f"{DMTF_FILES}{doc_id}_{v.version}.pdf", v.url
        assert v.wip is False and v.access == "open" and v.open
    dates = [v.published for v in doc.versions]
    assert dates == sorted(dates), doc_id
    newest = doc.latest()
    assert newest is not None and newest.version == versions[-1][0]
    # a DMTF document without an explicit listing is listed under its own id
    assert shipped.families[family].publisher == "DMTF"
    assert doc.listing == f"dmtf:{doc_id}"


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac1_catalog_command_names_the_newest_as_latest(capsys, doc_id):
    family, _, versions = BATCH[doc_id]
    code, out, err = _run(capsys, "catalog", doc_id)
    assert code == 0, out
    assert err == ""
    lines = out.splitlines()
    assert f"document: {doc_id}" in lines
    assert f"latest: {versions[-1][0]}" in lines
    assert f"family: {family} (" in out
    assert "access: open" in lines and "fetch: direct" in lines
    body = out.split("versions:", 1)[1]
    for version, _ in versions:
        assert version in body, version


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac1_an_unknown_version_is_refused_naming_the_known_ones(
    tmp_path, monkeypatch, capsys, doc_id
):
    """A reading command on a version the Catalog does not know stops
    before any download and lists the versions the catalog holds."""
    monkeypatch.setenv("BMC_SPEC_LIBRARY", str(tmp_path / "lib"))
    code, out, err = _run(capsys, "page", doc_id, "1", "--version", "9.9.9")
    assert code == 2, out
    assert f"{doc_id} 9.9.9 is not in the Library" in out
    known = ", ".join(v for v, _ in BATCH[doc_id][2])
    assert f"Known: {known}." in out


# ------------------------------------------------------------------ AC-2


def test_ac2_the_two_are_listed_and_left_not_taken(shipped):
    listed = shipped.dmtf_listed()
    for dsp in BATCH:
        assert listed.get(dsp) == dsp, dsp
        assert dsp not in shipped.dmtf_not_taken, dsp
        assert not shipped.dmtf_not_taken_covers(dsp), dsp
    assert len(shipped.dmtf_not_taken) == 130
    for dsp in LEFT:
        assert shipped.dmtf_not_taken_covers(dsp), dsp
        assert dsp not in listed, dsp
        assert shipped.get(dsp) is None, dsp


def test_ac2_the_list_is_clean(shipped):
    listed = shipped.dmtf_listed()
    assert len(set(shipped.dmtf_not_taken)) == len(shipped.dmtf_not_taken)
    for entry in shipped.dmtf_not_taken:
        assert entry.startswith("DSP"), entry
        assert entry not in listed, entry


@pytest.mark.parametrize("dsp", list(BATCH))
def test_ac2_the_catalog_refuses_a_not_taken_entry_naming_one(tmp_path, dsp):
    text = CATALOG.read_text(encoding="utf-8")
    assert text.count("not_taken = [\n") == 1
    bad = text.replace("not_taken = [\n", f'not_taken = [\n    "{dsp}",\n', 1)
    path = tmp_path / f"{dsp}.toml"
    path.write_text(bad, encoding="utf-8", newline="")
    with pytest.raises(CatalogError, match=dsp):
        load_catalog(path)


# ------------------------------------------------------------------ AC-3


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac3_neither_has_a_limit(shipped, doc_id):
    assert shipped.get(doc_id).limits == ""


# ------------------------------------------------------------------ AC-5


def test_ac5_each_has_one_golden_question_on_its_newest_version(shipped):
    verified, problems = support.read_golden(GOLDEN, shipped)
    assert problems == []
    for doc_id, qid in QUESTIONS.items():
        assert verified.get(doc_id.lower()) == [(qid, BATCH[doc_id][2][-1][0])]


def test_ac5_the_group_follows_the_previous_batch_and_ids_stay_gap_free():
    text = GOLDEN.read_text(encoding="utf-8")
    headings = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert text.count(HEADING) == 1
    assert headings.index(PREVIOUS_HEADING) + 1 == headings.index(HEADING), headings
    section = text.split(HEADING, 1)[1].split("\n## ", 1)[0]
    assert [cells[0] for cells in _rows(section)] == list(QUESTIONS.values())
    numbers = [int(cells[0][1:]) for cells in _rows(text)]
    # T72 (2026-11-09) added G111-G113
    assert sorted(numbers) == list(range(1, 114))
    assert numbers[numbers.index(108) + 1 :][:2] == [109, 110]


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac5_the_row_names_page_section_table_and_commands_on_the_document(
    doc_id,
):
    text = GOLDEN.read_text(encoding="utf-8")
    (cells,) = [c for c in _rows(text) if c[0] == QUESTIONS[doc_id]]
    assert len(cells) == 5, cells
    newest = BATCH[doc_id][2][-1][0]
    assert cells[2] == f"{doc_id} {newest}"
    where = cells[3]
    assert where.startswith(f"{doc_id} {newest}, ")
    assert re.search(r"\bpages? \d+", where), where
    assert re.search(r"\bsection \d", where), where
    assert re.search(r"\bTable \d", where), where
    backticked = [c.split() for c in re.findall(r"`([^`]+)`", cells[4])]
    commands = [words for words in backticked if words[0] in VERBS]
    assert commands, cells[4]
    for words in commands:
        assert words[1] == doc_id, words
    # the newest version is read with a page or table command, not only find
    assert any(words[0] in ("page", "table") for words in commands), commands


def test_ac5_freshness_records_the_batch():
    text = GOLDEN.read_text(encoding="utf-8")
    fresh = text.split("## Freshness", 1)[1]
    paragraph = [p for p in fresh.split("\n\n") if "2026-11-08" in p]
    assert len(paragraph) == 1, paragraph
    for doc_id in BATCH:
        assert doc_id in paragraph[0], doc_id


# ------------------------------------------------------------------ AC-6


@pytest.fixture
def generated(capsys):
    code, out, err = _run(
        capsys, "catalog", "--table", "--by-family", "--golden", str(GOLDEN)
    )
    assert code == 0, out
    assert err == ""
    return out


def test_ac6_support_doc_is_the_generated_table_with_the_two_as_pass(
    shipped, generated
):
    text = SUPPORT.read_text(encoding="utf-8")
    assert text.count(MARKER) == 1
    body = text.split(MARKER + "\n", 1)[1].lstrip("\n")
    assert body == generated
    for doc_id, (_, title, versions) in BATCH.items():
        (row,) = [ln for ln in body.splitlines() if ln.startswith(f"| `{doc_id}` ")]
        cells = [c.strip() for c in row.strip().strip("|").split(" | ")]
        assert cells == [f"`{doc_id}` {title}", "open", versions[-1][0], "PASS", "-"]


def test_ac6_each_row_sits_under_its_family_heading(shipped, generated):
    heading = None
    seen = {}
    for line in generated.splitlines():
        if line.startswith("## "):
            heading = line[3:]
        for doc_id in BATCH:
            if line.startswith(f"| `{doc_id}` "):
                seen[doc_id] = heading
    for doc_id, (family, _, _) in BATCH.items():
        assert seen.get(doc_id) == shipped.families[family].title, doc_id


# ------------------------------------------------------------------ AC-7


def test_ac7_counts_grew_by_exactly_the_two_open_entries(shipped):
    docs = shipped.documents
    open_docs = [d for d in docs if d.access == "open"]
    # T72 (2026-11-09) added three open documents
    assert len(docs) == 124
    assert len(open_docs) == 104
    assert len(docs) - len(open_docs) == 20
    families = len({d.family for d in docs})
    assert families == 35
    # the README status line states the catalog's own numbers
    readme = " ".join(README.read_text(encoding="utf-8").split())
    assert f"lists {len(docs)} documents in {families} families" in readme
    assert f"The {len(open_docs)} open ones" in readme
