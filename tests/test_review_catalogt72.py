"""Review tests for the 2026-11-09 catalog batch: DSP0220 FRU Data, DSP0244
IPMI PET to Platform Message Registry Mapping and DSP0280 PMCI Test Tools
join the shipped catalog after DSP0294 (AC-1), DSP0244 1.1.0 carries its
cover date so that 1.2.0 stays latest (AC-2), the three leave
``[listings.dmtf] not_taken`` (AC-3), only DSP0220 has a limit (AC-4), each
has a Golden Question of its own (AC-6), and docs/SUPPORT.md and the counts
follow (AC-7, AC-8). Shipped files only, no network."""

import re
import tomllib
from pathlib import Path

import pytest

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import CatalogError, load_catalog, parse_catalog
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
    "DSP0220": (
        "pldm",
        "Field Replaceable Unit (FRU) Data Specification",
        (("1.0.0", "2025-05-19"), ("1.0.1", "2025-09-22")),
    ),
    "DSP0244": (
        "ipmi",
        "IPMI PET to Platform Message Registry Mapping",
        (
            ("1.0.0", "2009-05-13"),
            ("1.1.0", "2009-11-02"),
            ("1.2.0", "2010-10-27"),
        ),
    ),
    "DSP0280": (
        "mctp",
        "PMCI Test Tools Interface and Design Specification",
        (("1.0.0", "2022-10-10"), ("1.1.0", "2026-07-02")),
    ),
}
QUESTIONS = {"DSP0220": "G111", "DSP0244": "G112", "DSP0280": "G113"}
# the tables AC-6 says each answer is read from
TABLES = {"DSP0220": (5,), "DSP0244": (1,), "DSP0280": (2, 3)}
HEADING = "## Catalog additions of 2026-11-09"
PREVIOUS_HEADING = "## Catalog additions of 2026-11-08"
# what the change leaves in not_taken: the document DSP0244 maps to (XML)
# and one each of the PMCI, PLDM modeling and SPDM white papers
LEFT = ("DSP8007", "DSP2015", "DSP2054", "DSP2072")
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


def test_ac1_the_three_follow_dsp0294_and_close_the_documents(shipped):
    ids = [d.id for d in shipped.documents]
    assert ids[ids.index("DSP0294") + 1 :] == ["DSP0220", "DSP0244", "DSP0280"]
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
    assert doc.newest_open().version == versions[-1][0]
    # each is followed on DMTF's listing under its own id
    assert doc.listing == f"dmtf:{doc_id}"
    assert shipped.dmtf_listed().get(doc_id) == doc_id


def test_ac1_dsp0244_names_its_dmtf_listing_in_a_family_dmtf_does_not_publish(
    shipped,
):
    """The ipmi family's publisher is not DMTF, so nothing gives DSP0244 a
    DMTF listing unless its entry names one."""
    assert shipped.families["ipmi"].publisher != "DMTF"
    data = tomllib.loads(CATALOG.read_text(encoding="utf-8"))
    (raw,) = [d for d in data["documents"] if d["id"] == "DSP0244"]
    assert raw.get("listing") == "dmtf:DSP0244"
    # the same entry without the key would not be followed at all
    del raw["listing"]
    assert parse_catalog(data).get("DSP0244").listing == ""
    # the other two sit in families DMTF publishes
    for doc_id in ("DSP0220", "DSP0280"):
        assert shipped.families[BATCH[doc_id][0]].publisher == "DMTF"


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac1_catalog_command_names_the_newest_as_latest(capsys, shipped, doc_id):
    family, title, versions = BATCH[doc_id]
    code, out, err = _run(capsys, "catalog", doc_id)
    assert code == 0, out
    assert err == ""
    lines = out.splitlines()
    assert f"document: {doc_id}" in lines
    assert f"title: {title}" in lines
    assert f"latest: {versions[-1][0]}" in lines
    assert f"family: {family} ({shipped.families[family].publisher})" in lines
    assert "access: open" in lines and "fetch: direct" in lines
    assert f"listing: dmtf:{doc_id}" in lines
    # every version, newest first, with its date and URL
    body = out.split("versions:\n", 1)[1].splitlines()
    printed = [ln.split("\t")[1:3] for ln in body if ln.startswith("\t")]
    assert printed == [[v, d] for v, d in reversed(versions)]
    for version, _ in versions:
        assert f"{DMTF_FILES}{doc_id}_{version}.pdf" in out


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


def test_ac2_dsp0244_1_1_0_carries_the_cover_date_with_a_note(shipped):
    doc = shipped.get("DSP0244")
    v110 = doc.find_version("1.1.0")
    assert v110 is not None
    assert v110.published == "2009-11-02"
    # the note says where the date comes from and what DMTF's page says
    assert "2010-11-02" in v110.notes
    assert "cover" in v110.notes.lower()
    # the other versions need no such note
    assert doc.find_version("1.0.0").notes == ""
    assert doc.find_version("1.2.0").notes == ""
    assert doc.latest().version == "1.2.0"


def test_ac2_with_dmtfs_date_1_1_0_would_pass_for_the_latest():
    """Why the cover date is recorded: the date on DMTF's page (2010-11-02)
    falls after 1.2.0 (2010-10-27), and ``latest`` goes by date."""
    data = tomllib.loads(CATALOG.read_text(encoding="utf-8"))
    (raw,) = [d for d in data["documents"] if d["id"] == "DSP0244"]
    (v110,) = [v for v in raw["versions"] if v["version"] == "1.1.0"]
    assert parse_catalog(data).get("DSP0244").latest().version == "1.2.0"
    v110["published"] = "2010-11-02"
    assert parse_catalog(data).get("DSP0244").latest().version == "1.1.0"


# ------------------------------------------------------------------ AC-3


def test_ac3_the_three_are_listed_and_left_not_taken(shipped):
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


def test_ac3_the_list_is_clean(shipped):
    listed = shipped.dmtf_listed()
    for dsp in BATCH:
        assert dsp in listed, dsp
    assert len(set(shipped.dmtf_not_taken)) == len(shipped.dmtf_not_taken)
    for entry in shipped.dmtf_not_taken:
        assert entry.startswith("DSP"), entry
        assert entry not in listed, entry
    # no prefix entry swallows one of the three either
    for dsp in BATCH:
        assert not any(dsp.startswith(e) for e in shipped.dmtf_not_taken), dsp


@pytest.mark.parametrize("dsp", list(BATCH))
def test_ac3_the_catalog_refuses_a_not_taken_entry_naming_one(tmp_path, dsp):
    text = CATALOG.read_text(encoding="utf-8")
    assert text.count("not_taken = [\n") == 1
    bad = text.replace("not_taken = [\n", f'not_taken = [\n    "{dsp}",\n', 1)
    path = tmp_path / f"{dsp}.toml"
    path.write_text(bad, encoding="utf-8", newline="")
    # refused because a document lists the id, not as a repeated entry
    with pytest.raises(CatalogError, match=f"'{dsp}' is the listing of {dsp}"):
        load_catalog(path)


# ------------------------------------------------------------------ AC-4


def test_ac4_only_dsp0220_has_a_limit_and_it_names_table_1_on_page_13(shipped):
    limit = shipped.get("DSP0220").limits
    assert limit, "DSP0220 carries no limit"
    assert re.search(r"\bTable 1\b", limit), limit
    assert re.search(r"\bpage 13\b", limit), limit
    assert shipped.get("DSP0244").limits == ""
    assert shipped.get("DSP0280").limits == ""


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac4_the_catalog_command_prints_a_limit_only_for_dsp0220(
    capsys, shipped, doc_id
):
    code, out, _ = _run(capsys, "catalog", doc_id)
    assert code == 0, out
    limits = [ln for ln in out.splitlines() if ln.startswith("limits: ")]
    if doc_id == "DSP0220":
        assert limits == [f"limits: {shipped.get(doc_id).limits}"]
    else:
        assert limits == []


# ------------------------------------------------------------------ AC-6


def test_ac6_each_has_one_golden_question_on_its_newest_version(shipped):
    verified, problems = support.read_golden(GOLDEN, shipped)
    assert problems == []
    for doc_id, qid in QUESTIONS.items():
        assert verified.get(doc_id.lower()) == [(qid, BATCH[doc_id][2][-1][0])]


def test_ac6_the_group_follows_the_previous_batch_and_ids_stay_gap_free():
    text = GOLDEN.read_text(encoding="utf-8")
    headings = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert text.count(HEADING) == 1
    assert headings.index(PREVIOUS_HEADING) + 1 == headings.index(HEADING), headings
    section = text.split(HEADING, 1)[1].split("\n## ", 1)[0]
    assert [cells[0] for cells in _rows(section)] == list(QUESTIONS.values())
    numbers = [int(cells[0][1:]) for cells in _rows(text)]
    assert sorted(numbers) == list(range(1, 114))
    assert len(numbers) == len(set(numbers))
    assert numbers[numbers.index(110) + 1 :][:3] == [111, 112, 113]


@pytest.mark.parametrize("doc_id", list(BATCH))
def test_ac6_the_row_names_page_section_table_and_commands_on_the_document(
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
    for number in TABLES[doc_id]:
        assert re.search(rf"\bTable {number}\b", where), (number, where)
    backticked = [c.split() for c in re.findall(r"`([^`]+)`", cells[4])]
    commands = [words for words in backticked if words[0] in VERBS]
    assert commands, cells[4]
    for words in commands:
        assert words[1] == doc_id, words
    # the answer is read with a page or table command, not only find
    assert any(words[0] in ("page", "table") for words in commands), commands


def test_ac6_freshness_records_the_batch_and_the_dsp0244_date():
    text = GOLDEN.read_text(encoding="utf-8")
    fresh = text.split("## Freshness", 1)[1]
    wanted = ("2026-11-09", *BATCH, "2010-11-02", "2009-11-02")
    paragraphs = [p for p in fresh.split("\n\n") if all(w in p for w in wanted)]
    assert len(paragraphs) == 1, paragraphs


# ------------------------------------------------------------------ AC-7


@pytest.fixture
def generated(capsys):
    code, out, err = _run(
        capsys, "catalog", "--table", "--by-family", "--golden", str(GOLDEN)
    )
    assert code == 0, out
    assert err == ""
    return out


def test_ac7_support_doc_is_the_generated_table_with_the_three_as_pass(
    shipped, generated
):
    text = SUPPORT.read_text(encoding="utf-8")
    assert text.count(MARKER) == 1
    body = text.split(MARKER + "\n", 1)[1].lstrip("\n")
    assert body == generated
    for doc_id, (_, title, versions) in BATCH.items():
        (row,) = [ln for ln in body.splitlines() if ln.startswith(f"| `{doc_id}` ")]
        cells = [c.strip() for c in row.strip().strip("|").split(" | ")]
        limit = shipped.get(doc_id).limits or "-"
        assert cells == [f"`{doc_id}` {title}", "open", versions[-1][0], "PASS", limit]
    # DSP0220 shows its limit, the other two none
    (row,) = [ln for ln in body.splitlines() if ln.startswith("| `DSP0220` ")]
    assert not row.endswith("| - |")


def test_ac7_each_row_sits_under_its_family_heading(shipped, generated):
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


def test_ac7_readme_states_the_catalogs_own_counts(shipped):
    docs = shipped.documents
    open_docs = [d for d in docs if d.access == "open"]
    families = {d.family for d in docs}
    readme = " ".join(README.read_text(encoding="utf-8").split())
    listed = re.search(r"lists (\d+) documents in (\d+) families", readme)
    opened = re.search(r"The (\d+) open ones", readme)
    assert listed and opened, "the status line no longer states the counts"
    assert (int(listed.group(1)), int(listed.group(2))) == (len(docs), len(families))
    assert int(opened.group(1)) == len(open_docs)
    assert (len(docs), len(families), len(open_docs)) == (124, 35, 104)


# ------------------------------------------------------------------ AC-8


def test_ac8_counts_grew_by_exactly_the_three_open_entries(shipped):
    docs = shipped.documents
    open_docs = [d for d in docs if d.access == "open"]
    assert len(docs) == 124
    assert len(open_docs) == 104
    # the gated, member and NDA documents and the families are untouched
    assert len(docs) - len(open_docs) == 20
    assert len({d.family for d in docs}) == 35
    assert set(shipped.families) >= {BATCH[d][0] for d in BATCH}
    # the Golden rows grew by one per new document
    numbers = [int(c[0][1:]) for c in _rows(GOLDEN.read_text(encoding="utf-8"))]
    assert max(numbers) == 113
