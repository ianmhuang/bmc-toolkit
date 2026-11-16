"""The Markdown reader on its own: what counts as Markdown, the Outline of
ATX headings, labels, line numbering, the cite line."""

import json
from pathlib import Path

import pytest

from bmc_toolkit.spec import markdown as md

# Line numbers matter in every test below: keep the text as it is.
MD_TEXT = """\
<p>Title page</p>

# Introduction
Root of trust intro text.

## Goals
Goal one: the fuse.

```python
# not a heading
```

# Fuses
## Goals
Fuse goal text.
### 5.2 Zeroization ###
Zeroize the fuse.
   ## Indented heading
    # four spaces is code, not a heading
#nospace is not a heading
| a | b |
|---|---|
| fuse | 1 |
![diagram](./images/x.png)
"""


def write(tmp_path: Path, text: str = MD_TEXT, *, newline: str = "\n", bom=False):
    path = tmp_path / "original.md"
    data = text.replace("\n", newline).encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)
    return path


# ------------------------------------------------------------ the check


@pytest.mark.parametrize(
    "body",
    [
        b"# Title\n",
        b"\xef\xbb\xbf# Title\n",
        b"plain text, no heading at all\n",
        "# Café\n".encode(),
        b"<p>An inline HTML block first</p>\n# Title\n",
    ],
)
def test_text_is_markdown(body):
    assert md.looks_like_markdown(body)


@pytest.mark.parametrize(
    "body",
    [
        b"<!DOCTYPE html><html><body>Not found</body></html>",
        b"  \n<html><body>Access Denied</body></html>",
        b"<HTML>",
        b"\xef\xbb\xbf<!doctype html>",
        b"%PDF-1.7\n\xff\xfe\x00binary",
        b"\x89PNG\r\n\x1a\n",
        b"",
    ],
)
def test_html_binary_or_empty_is_not_markdown(body):
    assert not md.looks_like_markdown(body)


def test_file_check_reads_the_whole_file(tmp_path):
    good = write(tmp_path)
    assert md.file_is_markdown(good)
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"# fine start\n" + b"\xff" * 10)
    assert not md.file_is_markdown(bad)
    assert not md.file_is_markdown(tmp_path / "missing.md")


# ------------------------------------------------------------- outline


def test_headings_are_atx_outside_fences(tmp_path):
    lines = md.read_lines(write(tmp_path))
    entries = md.outline(lines)
    assert [(e["level"], e["title"], e["line"]) for e in entries] == [
        (0, "Introduction", 3),
        (1, "Goals", 6),
        (0, "Fuses", 13),
        (1, "Goals", 14),
        (2, "5.2 Zeroization", 16),
        (1, "Indented heading", 18),
    ]


def test_a_tilde_fence_and_an_unclosed_fence_hide_headings():
    lines = ["~~~~", "# hidden", "~~~", "# still hidden", "~~~~", "# Shown", "```"]
    lines += ["# hidden to the end"]
    assert [e["title"] for e in md.outline(lines)] == ["Shown"]


def test_a_backtick_fence_is_closed_only_by_backticks():
    lines = ["```", "~~~", "# hidden", "```", "# Shown"]
    assert [e["title"] for e in md.outline(lines)] == ["Shown"]


def test_an_empty_heading_or_one_without_a_space_is_not_an_entry():
    lines = ["#", "##   ", "#Tag", "####### seven", "# Real"]
    assert [e["title"] for e in md.outline(lines)] == ["Real"]


def test_no_headings_gives_an_empty_outline():
    assert md.outline(["just text", "more text"]) == []


# ------------------------------------------------------- line numbering


def test_crlf_and_lf_number_the_same_and_a_bom_is_dropped(tmp_path):
    lf = md.read_lines(write(tmp_path))
    (tmp_path / "lf").mkdir()
    crlf = md.read_lines(write(tmp_path / "lf", newline="\r\n", bom=True))
    assert lf == crlf
    assert lf[0] == "<p>Title page</p>"
    assert len(lf) == 24  # the final newline does not add a line


def test_a_line_break_python_would_split_on_is_kept(tmp_path):
    path = tmp_path / "original.md"
    path.write_bytes("# A B\nnext\n".encode())
    assert md.read_lines(path) == ["# A B", "next"]


# ------------------------------------------------------ version reading


@pytest.fixture
def version(tmp_path):
    original = write(tmp_path)
    md.extract(original, tmp_path)
    return md.MarkdownVersion.load(
        family="security",
        document="ROT",
        version="2.1",
        path=tmp_path,
        original=original,
        origin="https://example.test/raw/abc/RoT.md",
    )


def test_duplicate_titles_get_their_path_as_label(version):
    labels = [h.label for h in version.headings]
    assert labels == [
        "Introduction",
        "Introduction > Goals",
        "Fuses",
        "Fuses > Goals",
        "5.2 Zeroization",
        "Indented heading",
    ]


def test_owner_of_a_line(version):
    assert version.owner(1) is None
    assert version.owner(3).label == "Introduction"
    assert version.owner(10).label == "Introduction > Goals"  # inside the fence
    assert version.owner(15).label == "Fuses > Goals"
    assert version.owner(24).label == "Indented heading"


def test_sections_end_before_the_next_same_or_higher_heading(version):
    spans = [(h.label, h.line, version.end_of(h)) for h in version.headings]
    assert spans == [
        ("Introduction", 3, 12),
        ("Introduction > Goals", 6, 12),
        ("Fuses", 13, 24),
        ("Fuses > Goals", 14, 17),
        ("5.2 Zeroization", 16, 17),
        ("Indented heading", 18, 24),
    ]


def test_match_by_words_by_path_and_by_number(version):
    def found(query):
        return [h.label for _, h, _ in version.match_sections(query)]

    assert found("goals") == ["Introduction > Goals", "Fuses > Goals"]
    assert found("fuses goals") == ["Fuses > Goals"]
    assert found("Fuses > Goals") == ["Fuses > Goals"]
    assert found("5.2") == ["5.2 Zeroization"]
    assert found("5") == ["5.2 Zeroization"]
    assert found("5.3") == []
    assert found("nothing like it") == []


def test_find_reports_file_line_numbers(version):
    hits = list(version.find("fuse"))
    assert [(h.line, h.section.label if h.section else "-") for h in hits] == [
        (7, "Introduction > Goals"),
        (13, "Fuses"),
        (15, "Fuses > Goals"),
        (17, "5.2 Zeroization"),
        (23, "Indented heading"),
    ]
    assert [h.line for h in version.find("fuse", case=True)] == [7, 17, 23]
    assert [h.line for h in version.find(r"^#\w", regex=True)] == [20]


def test_cite_line_fields(version):
    assert version.cite(14, 17) == (
        "cite: security | ROT 2.1 | Fuses > Goals; 5.2 Zeroization | Markdown | "
        f"lines 14-17 | https://example.test/raw/abc/RoT.md | {version.path}"
    )
    assert version.cite(1, 2).split(" | ")[2] == "-"
    assert version.cite(1, 4).split(" | ")[2] == "Introduction"
    assert version.cite(7, 7).split(" | ")[2:5] == [
        "Introduction > Goals",
        "Markdown",
        "lines 7-7",
    ]
    assert version.cite(14, 17, section="Fuses > Goals").split(" | ")[2] == (
        "Fuses > Goals"
    )


def test_printed_lines_are_numbered_and_stripped(tmp_path):
    original = write(tmp_path, "# T\nend with spaces   \n\n", newline="\r\n")
    md.extract(original, tmp_path)
    v = md.MarkdownVersion.load(
        family="f", document="D", version="1", path=tmp_path, original=original
    )
    assert v.format_lines(1, 3) == ["1  # T", "2  end with spaces", "3"]


def test_extract_writes_meta_and_outline_and_is_current(tmp_path):
    original = write(tmp_path)
    result = md.extract(original, tmp_path)
    assert (result.lines, result.entries) == (24, 6)
    meta = md.read_meta(tmp_path)
    assert meta["kind"] == md.KIND
    assert meta["extractor_version"] == md.MARKDOWN_VERSION
    assert meta["outline_source"] == "headings"
    assert md.is_current(tmp_path)
    meta["extractor_version"] = 0
    (tmp_path / "extract.json").write_text(json.dumps(meta), "utf-8")
    assert not md.is_current(tmp_path)


def test_a_pdf_extract_is_not_a_current_markdown_extract(tmp_path):
    (tmp_path / "extract.json").write_text('{"extractor_version": 1}', "utf-8")
    (tmp_path / "outline.json").write_text("[]", "utf-8")
    assert not md.is_current(tmp_path)
