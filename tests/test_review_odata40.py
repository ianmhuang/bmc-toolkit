"""Review tests for the 2026-11-17 catalog batch: the four OData 4.0
documents DSP0266 cites join the shipped catalog in a new OASIS family, each
as the 4.0 OASIS Standard and the 4.0 Plus Errata 03 edition with the latter
as latest (AC-1); 4.01 and Errata 01/02 are not listed (AC-2); the contents
depth limit is recorded where it applies (AC-3, the offline part); each has a
Golden Question of its own on 4.0 Errata 03 (AC-4); docs/SUPPORT.md, the
README counts and its length follow (AC-5). Shipped files only, no network:
the suite's default client refuses every URL."""

import re
import shlex
import tomllib
from pathlib import Path

import pytest

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import load_catalog, parse_catalog
from bmc_toolkit.spec.cli import main
from bmc_toolkit.spec.library import safe_name

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "bmc_toolkit" / "spec" / "catalog.toml"
GOLDEN = ROOT / "docs" / "golden-questions.md"
SUPPORT = ROOT / "docs" / "SUPPORT.md"
README = ROOT / "README.md"
MARKER = (
    "<!-- generated below: catalog --table --by-family "
    "--golden docs/golden-questions.md -->"
)
HOST = "https://docs.oasis-open.org/"

# id -> the words AC-1 gives for the document, which its title must carry
DOCS = {
    "ODATA-PROTOCOL": ("Part 1", "Protocol"),
    "ODATA-URL": ("Part 2", "URL Conventions"),
    "ODATA-CSDL": ("Part 3", "CSDL"),
    "ODATA-JSON": ("JSON Format",),
}
STANDARD = ("4.0", "2014-02-24")
ERRATA = ("4.0 Errata 03", "2016-06-02")
QUESTIONS = ["G114", "G115", "G116", "G117"]
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


def _errata_marker(doc_id: str) -> str:
    """AC-1: the complete/ directory, except for JSON Format."""
    if doc_id == "ODATA-JSON":
        return "/v4.0/errata03/os/"
    return "/v4.0/errata03/os/complete/"


# ------------------------------------------------------------------ AC-1


def test_ac1_the_family_is_odata_published_by_oasis_with_the_four(shipped):
    assert "odata" in shipped.families, sorted(shipped.families)
    assert shipped.families["odata"].publisher == "OASIS"
    assert [d.id for d in shipped.by_family("odata")] == list(DOCS)
    # nothing else of OData came along (no 4.01 documents, no CSDL JSON)
    named = [d.id for d in shipped.documents if d.id.upper().startswith("ODATA")]
    assert named == list(DOCS)


@pytest.mark.parametrize("doc_id", list(DOCS))
def test_ac1_entry_is_open_direct_with_the_two_pdf_versions(shipped, doc_id):
    doc = shipped.get(doc_id)
    assert doc is not None, f"{doc_id} is not in the catalog"
    assert doc.id == doc_id
    assert doc.family == "odata"
    for words in DOCS[doc_id]:
        assert words in doc.title, (words, doc.title)
    assert (doc.access, doc.fetch) == ("open", "direct")
    assert [(v.version, v.published) for v in doc.versions] == [STANDARD, ERRATA]
    for v in doc.versions:
        assert v.type == "pdf", v
        assert v.open and not v.wip, v
        assert v.url.startswith(HOST), v.url
        assert v.url.endswith(".pdf"), v.url
    standard, errata = doc.versions
    assert "/v4.0/os/" in standard.url
    assert "errata" not in standard.url.lower()
    assert _errata_marker(doc_id) in errata.url
    assert doc.latest().version == "4.0 Errata 03"
    assert doc.latest(include_wip=True).version == "4.0 Errata 03"
    assert doc.newest_open().version == "4.0 Errata 03"


def test_ac1_the_eight_urls_are_eight_different_files(shipped):
    urls = [v.url for doc_id in DOCS for v in shipped.get(doc_id).versions]
    assert len(urls) == 8
    assert len(set(urls)) == 8
    # no other document of the catalog points at one of them
    others = {
        v.url for d in shipped.documents if d.id not in DOCS for v in d.versions
    }
    assert not others & set(urls)


@pytest.mark.parametrize("doc_id", list(DOCS))
def test_ac1_latest_is_decided_by_the_dates_not_by_the_position(doc_id):
    """The Errata 03 edition is latest because it is dated later, so it
    stays latest with the two version blocks swapped."""
    data = tomllib.loads(CATALOG.read_text(encoding="utf-8"))
    (raw,) = [d for d in data["documents"] if d["id"] == doc_id]
    raw["versions"].reverse()
    doc = parse_catalog(data).get(doc_id)
    assert [v.version for v in doc.versions] == ["4.0 Errata 03", "4.0"]
    assert doc.latest().version == "4.0 Errata 03"


@pytest.mark.parametrize("doc_id", list(DOCS))
def test_ac1_catalog_command_lists_both_with_errata_03_as_latest(
    capsys, shipped, doc_id
):
    code, out, err = _run(capsys, "catalog", doc_id)
    assert code == 0, out
    assert err == ""
    lines = out.splitlines()
    assert f"document: {doc_id}" in lines
    assert "family: odata (OASIS)" in lines
    assert "access: open" in lines and "fetch: direct" in lines
    assert "latest: 4.0 Errata 03" in lines
    # every version, newest first, with its date and URL
    body = out.split("versions:\n", 1)[1].splitlines()
    printed = [ln.split("\t")[1:3] for ln in body if ln.startswith("\t")]
    assert printed == [list(ERRATA), list(STANDARD)]
    for v in shipped.get(doc_id).versions:
        assert v.url in out


def test_ac1_the_id_is_matched_case_insensitively(capsys):
    code, out, _ = _run(capsys, "catalog", "odata-json")
    assert code == 0, out
    assert "document: ODATA-JSON" in out.splitlines()


def test_ac1_the_family_listing_prints_the_four(capsys):
    code, out, _ = _run(capsys, "catalog", "--family", "odata")
    assert code == 0, out
    fields = [ln.split("\t") for ln in out.splitlines()]
    assert [f[1] for f in fields] == list(DOCS)
    for f in fields:
        assert f[0] == "odata"
        assert (f[2], f[3], f[4]) == ("open", "direct", "4.0 Errata 03")
        assert f[6] == "4.0;4.0 Errata 03"


# ------------------------------------------------------------------ AC-2


@pytest.mark.parametrize("doc_id", list(DOCS))
def test_ac2_no_4_01_and_no_earlier_errata_are_listed(shipped, doc_id):
    doc = shipped.get(doc_id)
    assert doc is not None, f"{doc_id} is not in the catalog"
    for v in doc.versions:
        assert not v.version.startswith("4.01"), v.version
        assert "Errata 01" not in v.version and "Errata 02" not in v.version
        lowered = v.url.lower()
        assert "4.01" not in lowered, v.url
        assert "errata01" not in lowered and "errata02" not in lowered, v.url
    assert len(doc.versions) == 2


@pytest.mark.parametrize("doc_id", list(DOCS))
def test_ac2_the_notes_name_dsp0266_and_the_missing_4_01(capsys, shipped, doc_id):
    notes = shipped.get(doc_id).notes
    assert "DSP0266" in notes, notes
    assert "OData 4.0" in notes, notes
    assert "4.01" in notes, notes
    # and a reader of `catalog DOC` sees them
    code, out, _ = _run(capsys, "catalog", doc_id)
    assert code == 0, out
    assert f"notes: {notes}" in out.splitlines()


@pytest.mark.parametrize("doc_id", list(DOCS))
def test_ac2_asking_for_4_01_is_refused_naming_the_known_versions(
    library, capsys, doc_id
):
    """A version the Catalog does not know: a reading command stops before
    any download and lists the two it holds."""
    code, out, _ = _run(capsys, "page", doc_id, "1", "--version", "4.01")
    assert code == 2, out
    assert f"{doc_id} 4.01 is not in the Library" in out
    assert "Known: 4.0, 4.0 Errata 03." in out


# ------------------------------------------- AC-1 and the Goal, error paths


@pytest.mark.parametrize("doc_id", list(DOCS))
def test_a_question_goes_to_errata_03_and_a_failed_download_says_what_to_do(
    library, capsys, shipped, doc_id
):
    """Network failure with nothing held: a reading command without
    --version asks for the Errata 03 edition, and on failure names its URL
    and the path to save it under (exit 2)."""
    code, out, _ = _run(capsys, "section", doc_id, "1")
    assert code == 2, out
    lines = out.splitlines()
    assert any(ln.startswith(f"failed {doc_id} 4.0 Errata 03") for ln in lines), out
    errata = shipped.get(doc_id).find_version("4.0 Errata 03")
    assert f"Open in a browser: {errata.url}" in lines
    tail = Path("specs", "odata", doc_id, safe_name("4.0 Errata 03"), "original.pdf")
    (save,) = [ln for ln in lines if ln.startswith("Save it as: ")]
    assert save.endswith(str(tail)), save


def test_the_4_0_standard_is_served_on_request(library, capsys, shipped):
    code, out, _ = _run(capsys, "section", "ODATA-URL", "5", "--version", "4.0")
    assert code == 2, out
    lines = out.splitlines()
    standard = shipped.get("ODATA-URL").find_version("4.0")
    assert "failed ODATA-URL 4.0" in lines
    assert f"Open in a browser: {standard.url}" in lines
    assert not any("Errata 03" in ln for ln in lines if ln.startswith("failed ")), out


@pytest.mark.parametrize("doc_id", list(DOCS))
def test_the_four_are_hand_listed_and_check_says_so(library, capsys, shipped, doc_id):
    """Out of scope: refresh does not watch docs.oasis-open.org, so the
    documents carry no listing and `check DOC` refuses with exit 2."""
    assert shipped.get(doc_id).listing == ""
    code, out, _ = _run(capsys, "check", doc_id)
    assert code == 2, out
    assert out.startswith(f"{doc_id} has no publisher listing")


# ------------------------------------------------------------------ AC-3


def test_ac3_the_limit_sits_on_the_three_parts_and_not_on_json(capsys, shipped):
    for doc_id in DOCS:
        doc = shipped.get(doc_id)
        assert doc is not None, f"{doc_id} is not in the catalog"
        code, out, _ = _run(capsys, "catalog", doc_id)
        assert code == 0, out
        printed = [ln for ln in out.splitlines() if ln.startswith("limits: ")]
        if doc_id == "ODATA-JSON":
            assert doc.limits == ""
            assert printed == []
        else:
            # the defect is the Errata 03 edition's, and the limit says so
            assert "Errata 03" in doc.limits, doc.limits
            assert printed == [f"limits: {doc.limits}"]


# ------------------------------------------------------------------ AC-4


def test_ac4_each_has_one_golden_question_on_errata_03(shipped):
    verified, problems = support.read_golden(GOLDEN, shipped)
    assert problems == []
    pairs = [verified.get(doc_id.lower()) for doc_id in DOCS]
    assert pairs == [[(qid, "4.0 Errata 03")] for qid in QUESTIONS]


def test_ac4_the_ids_stay_gap_free_and_end_at_g117():
    numbers = [int(cells[0][1:]) for cells in _rows(GOLDEN.read_text("utf-8"))]
    assert len(numbers) == len(set(numbers))
    # T81.2 (2026-11-17) added G118-G134 after them
    assert sorted(numbers) == list(range(1, 135))


def test_ac4_the_group_follows_the_documents_before_it_in_the_catalog(shipped):
    """Catalog order: the four follow DSP0280, so their rows form the group
    directly after the one that holds DSP0280's question."""
    ids = [d.id for d in shipped.documents]
    before = ids[ids.index("ODATA-PROTOCOL") - 1]
    verified, _ = support.read_golden(GOLDEN, shipped)
    previous_question = verified[before.lower()][-1][0]
    text = GOLDEN.read_text(encoding="utf-8")
    groups = [[cells[0] for cells in _rows(part)] for part in text.split("\n## ")]
    groups = [g for g in groups if g]
    (at,) = [i for i, g in enumerate(groups) if "G114" in g]
    assert groups[at] == QUESTIONS
    assert previous_question in groups[at - 1], (previous_question, groups[at - 1])


@pytest.mark.parametrize("doc_id, qid", list(zip(DOCS, QUESTIONS, strict=True)))
def test_ac4_the_row_cites_section_and_page_with_commands_on_the_document(
    doc_id, qid
):
    text = GOLDEN.read_text(encoding="utf-8")
    (cells,) = [c for c in _rows(text) if c[0] == qid]
    assert len(cells) == 5, cells
    assert cells[2] == f"{doc_id} 4.0 Errata 03"
    where = cells[3]
    assert where.startswith(f"{doc_id} 4.0 Errata 03, ")
    assert re.search(r"\bpages? \d+", where), where
    assert re.search(r"\bsection \d", where), where
    backticked = [c.split() for c in re.findall(r"`([^`]+)`", cells[4])]
    commands = [words for words in backticked if words[0] in VERBS]
    assert commands, cells[4]
    for words in commands:
        assert words[1] == doc_id, words
        # the latest version is the one asked on: no --version needed
        assert "--version" not in words, words
    # the answer is read with a page or table command, not only located
    assert any(words[0] in ("page", "table") for words in commands), commands


def _shell_rewrites(command: str) -> bool:
    """True when bash or PowerShell would expand part of the command: a `$`
    that starts a variable or a substitution anywhere but inside single
    quotes (both shells expand it in a bare word and inside double quotes)."""
    single = double = False
    for at, ch in enumerate(command):
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        elif ch == "$" and not single:
            following = command[at + 1 : at + 2]
            if following.isalnum() or following in ("_", "{", "("):
                return True
    return False


@pytest.mark.parametrize("qid", QUESTIONS)
def test_ac4_the_commands_reach_the_tool_as_they_are_written(qid):
    """Round 1 F1: the Commands column is typed into bash or PowerShell, so
    a command must not carry a `$name` either shell expands (G115's
    `"$expand"` reached the tool as an empty query), and each one names a
    document and a non-empty argument."""
    text = GOLDEN.read_text(encoding="utf-8")
    (cells,) = [c for c in _rows(text) if c[0] == qid]
    # the check itself tells the round 1 command from its safe spellings
    assert _shell_rewrites('section ODATA-URL "$expand"')
    assert _shell_rewrites("find ODATA-URL $levels")
    assert not _shell_rewrites("section ODATA-URL '$expand'")
    assert not _shell_rewrites("section ODATA-URL 5.1.2")
    backticked = re.findall(r"`([^`]+)`", cells[4])
    commands = [c for c in backticked if c.split()[0] in VERBS]
    assert commands, cells[4]
    for command in commands:
        assert not _shell_rewrites(command), command
        words = shlex.split(command)
        assert len(words) >= 3, words
        assert all(word.strip() for word in words), words


# ------------------------------------------------------------------ AC-5


@pytest.fixture
def generated(capsys):
    code, out, err = _run(
        capsys, "catalog", "--table", "--by-family", "--golden", str(GOLDEN)
    )
    assert code == 0, out
    assert err == ""
    return out


def test_ac5_support_doc_is_the_generated_table(generated):
    text = SUPPORT.read_text(encoding="utf-8")
    assert b"\r" not in SUPPORT.read_bytes()
    assert text.count(MARKER) == 1
    body = text.split(MARKER + "\n", 1)[1].lstrip("\n")
    assert body == generated


def test_ac5_the_odata_section_has_the_four_rows_as_pass(shipped, generated):
    assert "odata" in shipped.families, sorted(shipped.families)
    title = shipped.families["odata"].title
    sections = generated.split("\n## ")
    (section,) = [s for s in sections if s.splitlines()[0].removeprefix("## ") == title]
    rows = [ln for ln in section.splitlines() if ln.startswith("| `")]
    assert len(rows) == 4
    for row, doc_id in zip(rows, DOCS, strict=True):
        doc = shipped.get(doc_id)
        cells = [c.strip() for c in row.strip().strip("|").split(" | ")]
        assert cells == [
            f"`{doc_id}` {doc.title}",
            "open",
            "4.0 Errata 03",
            "PASS",
            doc.limits or "-",
        ]
    # the three limits are shown, JSON Format has none
    assert [row.endswith("| - |") for row in rows] == [False, False, False, True]


def test_ac5_the_section_sits_where_the_family_is_declared(shipped, generated):
    """Families come in catalog order; every other family keeps its place."""
    headings = [ln[3:] for ln in generated.splitlines() if ln.startswith("## ")]
    listed = [d for d in shipped.documents if not d.unlisted]
    expected = [
        f.title
        for f in shipped.families.values()
        if any(d.family == f.id for d in listed)
    ]
    assert headings == expected
    assert "odata" in shipped.families, sorted(shipped.families)
    assert headings.count(shipped.families["odata"].title) == 1


def test_ac5_readme_counts_the_catalog_and_stays_within_200_lines(shipped):
    docs = shipped.documents
    open_docs = [d for d in docs if d.access == "open"]
    families = {d.family for d in docs}
    # T81.2 (2026-11-17) seventeen RFCs in a new family
    assert (len(docs), len(open_docs), len(families)) == (145, 125, 37)
    # the gated, member and NDA documents are untouched
    assert len(docs) - len(open_docs) == 20
    text = README.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 200
    readme = " ".join(text.split())
    listed = re.search(r"lists (\d+) documents in (\d+) families", readme)
    opened = re.search(r"The (\d+) open ones", readme)
    closed = re.search(r"the (\d+) gated, member and NDA documents", readme)
    assert listed and opened and closed, "the status line no longer states the counts"
    assert (int(listed.group(1)), int(listed.group(2))) == (len(docs), len(families))
    assert int(opened.group(1)) == len(open_docs)
    assert int(closed.group(1)) == len(docs) - len(open_docs)
