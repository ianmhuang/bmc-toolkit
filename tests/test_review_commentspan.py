"""Reviewer acceptance tests: ``refresh --write`` keeps a comment line with
the block it introduces (AC-1 to AC-6).

Black-box through ``refresh.append_versions`` (the writer) and the
``refresh --write`` CLI with a scripted DMTF listing; the real catalog is
read only from disk. Nothing touches the network.
"""

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec import listing as listing_mod
from bmc_toolkit.spec import refresh as refresh_mod
from bmc_toolkit.spec.catalog import DEFAULT_CATALOG, load_catalog
from bmc_toolkit.spec.fetch import Response
from tests.conftest import MINI_CATALOG, ScriptedClient

HEAD = """schema_version = 1

[families.f]
title = "F"
publisher = "P"

[[documents]]
id = "ONE"
family = "f"
title = "One"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "https://example.test/ONE_1.0.pdf"
type = "pdf"
published = "2024-01-02"
"""

# a manual document is the only kind that may list no versions
HEADER_ONLY = """schema_version = 1

[families.f]
title = "F"
publisher = "P"

[[documents]]
id = "ONE"
family = "f"
title = "One"
access = "member"
fetch = "manual"
"""

TWO = """[[documents]]
id = "TWO"
family = "f"
title = "Two"
access = "open"
fetch = "direct"

[[documents.versions]]
version = "1.0"
url = "https://example.test/TWO_1.0.pdf"
type = "pdf"
published = "2024-01-02"
"""

NEWEST = listing_mod.Seen("2.0", "https://example.test/ONE_2.0.pdf", "2026-09-01")
NEWEST_BLOCK = (
    '[[documents.versions]]\nversion = "2.0"\nurl = "https://example.test/ONE_2.0.pdf"\n'
    'type = "pdf"\npublished = "2026-09-01"\n'
)


def write(tmp_path, text, seen=NEWEST, doc="ONE"):
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    refresh_mod.append_versions(path, doc, [seen])
    after = path.read_text("utf-8")
    assert "\r" not in path.read_bytes().decode("utf-8")
    return after


def versions(path, doc):
    return [v.version for v in load_catalog(path).get(doc).versions]


# ------------------------------------------------------------------ AC-1


def test_ac1_a_new_version_goes_above_the_single_comment_line(tmp_path):
    tail = "\n# two\n\n" + TWO
    after = write(tmp_path, HEAD + tail)
    assert after == HEAD + "\n" + NEWEST_BLOCK + tail
    assert versions(tmp_path / "catalog.toml", "ONE") == ["1.0", "2.0"]


def test_ac1_comment_without_a_blank_line_before_it(tmp_path):
    tail = "# two\n\n" + TWO
    after = write(tmp_path, HEAD + tail)
    # the comment still sits directly above the block it introduces
    assert after.endswith("\n# two\n\n" + TWO)
    assert NEWEST_BLOCK in after
    assert after.index(NEWEST_BLOCK) < after.index("# two")
    assert 'published = "2024-01-02"\n\n' + NEWEST_BLOCK in after


DMTF_DSP0236 = "https://www.dmtf.org/dsp/DSP0236"


def dsp_page(rows) -> str:
    body = "".join(
        f'<tr><td>{v}</td><td><a href="https://example.test/DSP0236_{v}.pdf">'
        f"MCTP Base</a></td><td>{date}</td><td>Standard</td></tr>"
        for v, date in rows
    )
    return (
        "<html><body><table><thead><tr><th>Version</th><th>Title</th>"
        "<th>Publication Date</th><th>Comments</th></tr></thead>"
        f"<tbody>{body}</tbody></table></body></html>"
    )


@pytest.fixture
def commented_catalog(tmp_path):
    marker = '[[documents]]\nid = "IPMI"'
    assert MINI_CATALOG.count(marker) == 1
    text = MINI_CATALOG.replace(marker, "# ipmi\n\n" + marker)
    path = tmp_path / "catalog.toml"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def test_ac1_refresh_write_cli_keeps_the_comment_with_the_next_document(
    commented_catalog, library, monkeypatch, capsys
):
    page = dsp_page((("1.3.4", "3 Aug 2026"),))
    client = ScriptedClient(
        {DMTF_DSP0236: Response(200, {"content-type": "text/html"}, page.encode())}
    )
    monkeypatch.setattr(cli, "CLIENT_FACTORY", lambda: client)
    before = commented_catalog.read_text("utf-8")
    code = cli.main(["--catalog", str(commented_catalog), "refresh", "DSP0236", "--write"])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "written 1" in out.splitlines()[-1], out
    after = commented_catalog.read_text("utf-8")
    assert "\n\n\n" not in after
    # the new block ends the DSP0236 document, above the comment
    assert (
        'published = "2025-06-01"\nwip = true\n\n'
        '[[documents.versions]]\nversion = "1.3.4"\n'
        'url = "https://example.test/DSP0236_1.3.4.pdf"\ntype = "pdf"\n'
        'published = "2026-08-03"\n\n# ipmi\n\n[[documents]]\nid = "IPMI"\n'
    ) in after
    # every original line survives, in order
    it = iter(after.split("\n"))
    for original in before.split("\n"):
        assert any(got == original for got in it), original
    assert versions(commented_catalog, "DSP0236") == ["1.3.2", "1.3.3", "1.4.0", "1.3.4"]
    assert versions(commented_catalog, "IPMI") == ["2.0 rev 1.1"]


# ------------------------------------------------------------------ AC-2


def test_ac2_a_run_of_comments_with_blank_lines_stays_whole(tmp_path):
    tail = "\n# two\n# still about two\n\n# and more\n\n\n# last\n\n" + TWO
    after = write(tmp_path, HEAD + tail)
    assert after == HEAD + "\n" + NEWEST_BLOCK + tail


def test_ac2_two_versions_both_go_above_the_comment_run(tmp_path):
    tail = "\n# two\n\n# more\n\n" + TWO
    path = tmp_path / "catalog.toml"
    path.write_text(HEAD + tail, encoding="utf-8", newline="")
    older = listing_mod.Seen("1.5", "https://example.test/ONE_1.5.pdf", "2025-01-02")
    refresh_mod.append_versions(path, "ONE", [NEWEST, older])
    after = path.read_text("utf-8")
    older_block = (
        '[[documents.versions]]\nversion = "1.5"\n'
        'url = "https://example.test/ONE_1.5.pdf"\ntype = "pdf"\n'
        'published = "2025-01-02"\n'
    )
    assert after == HEAD + "\n" + older_block + "\n" + NEWEST_BLOCK + tail
    assert versions(path, "ONE") == ["1.0", "1.5", "2.0"]


# ------------------------------------------------------------------ AC-3


def test_ac3_a_comment_followed_by_a_version_block_stays_inside(tmp_path):
    inner = (
        "\n# 1.1 confirmed by hand\n\n[[documents.versions]]\n"
        'version = "1.1"\nurl = "https://example.test/ONE_1.1.pdf"\n'
        'type = "pdf"\npublished = "2025-01-02"\n'
    )
    tail = "\n# two\n\n" + TWO
    after = write(tmp_path, HEAD + inner + tail)
    assert after == HEAD + inner + "\n" + NEWEST_BLOCK + tail
    assert versions(tmp_path / "catalog.toml", "ONE") == ["1.0", "1.1", "2.0"]


def test_ac3_a_comment_in_the_document_header_stays_inside(tmp_path):
    # a comment between the header keys and the first version block, as the
    # M10 review fixture has it
    text = HEAD.replace(
        'fetch = "direct"\n\n', 'fetch = "direct"\n# the oldest block first\n\n'
    )
    assert text != HEAD
    tail = "\n# two\n\n" + TWO
    after = write(tmp_path, text + tail)
    assert after == text + "\n" + NEWEST_BLOCK + tail


# ------------------------------------------------------------------ AC-4


def test_ac4_trailing_comments_at_the_end_of_the_file(tmp_path):
    tail = "\n# about the end of the file\n# a second line\n"
    after = write(tmp_path, HEAD + tail)
    assert after == HEAD + "\n" + NEWEST_BLOCK + tail


def test_ac4_trailing_comments_after_the_last_document_of_a_real_layout(tmp_path):
    tail = "\n# end of the catalog\n"
    path = tmp_path / "catalog.toml"
    path.write_text(MINI_CATALOG + tail, encoding="utf-8", newline="")
    seen = listing_mod.Seen("1.0", "https://example.test/secret_1.0.pdf", "2026-01-01")
    refresh_mod.append_versions(path, "SECRET", [seen])
    after = path.read_text("utf-8")
    block = (
        '[[documents.versions]]\nversion = "1.0"\n'
        'url = "https://example.test/secret_1.0.pdf"\ntype = "pdf"\n'
        'published = "2026-01-01"\n'
    )
    assert after == MINI_CATALOG + "\n" + block + tail
    assert versions(path, "SECRET") == ["0.9", "1.0"]


def test_ac4_trailing_comment_with_no_blank_line_and_no_final_newline(tmp_path):
    after = write(tmp_path, HEAD + "# the end")
    assert after == HEAD + "\n" + NEWEST_BLOCK + "# the end\n"


# ------------------------------------------------------------------ AC-5


def test_ac5_a_section_separator_still_ends_the_span(tmp_path):
    separator = "# ---------------------------------------------------------------- next\n"
    tail = "\n" + separator + "# what the next section holds\n\n" + TWO
    after = write(tmp_path, HEAD + tail)
    assert after == HEAD + "\n" + NEWEST_BLOCK + tail


def test_ac5_a_document_with_no_comment_after_it_is_unchanged_in_layout(tmp_path):
    tail = "\n" + TWO
    after = write(tmp_path, HEAD + tail)
    assert after == HEAD + "\n" + NEWEST_BLOCK + tail


def test_ac5_existing_span_shape_for_a_separator_and_the_last_document():
    text = (
        '# head\n\n[[documents]]\nid = "A"\n\n[[documents.versions]]\nversion = "1"\n\n'
        '# ---------------- next\n\n[[documents]]\nid = "B"\n'
    )
    lines = text.split("\n")
    assert refresh_mod._document_span(lines, "A") == (2, 8)
    assert refresh_mod._document_span(lines, "B") == (10, len(lines))


# ---------------------------------------------------------------- edges


def test_a_document_without_versions_gets_its_first_block_above_the_comment(
    tmp_path,
):
    tail = "\n# two\n\n" + TWO
    after = write(tmp_path, HEADER_ONLY + tail)
    assert after == HEADER_ONLY + "\n" + NEWEST_BLOCK + tail
    assert versions(tmp_path / "catalog.toml", "ONE") == ["2.0"]


def test_a_comment_before_a_repos_block_stays_with_the_repos_block(tmp_path):
    repo = (
        '[[repos]]\nid = "r"\nurl = "https://example.test/r.git"\n'
        'topics = ["review"]\n'
    )
    tail = "\n# repositories\n\n" + repo
    after = write(tmp_path, HEAD + tail)
    assert after == HEAD + "\n" + NEWEST_BLOCK + tail


# ------------------------------------------------------------------ AC-6


def test_ac6_dsp0134_3_10_0_sits_inside_its_document_above_redfish():
    text = DEFAULT_CATALOG.read_text("utf-8")
    lines = text.split("\n")
    redfish = lines.index("# redfish")
    block = lines.index('version = "3.10.0"')
    url = lines[block + 1]
    assert url.endswith("DSP0134_3.10.0.pdf\"")
    assert lines[block - 1] == "[[documents.versions]]"
    assert block < redfish
    # nothing but that block's lines and one blank line between it and the comment
    assert lines[redfish - 1] == ""
    assert lines[redfish - 2] == 'published = "2026-09-07"'
    assert lines[redfish + 1] == ""
    assert lines[redfish + 2] == "[[documents]]"
    assert lines[redfish + 3] == 'id = "DSP0266"'
    # no [[documents]] line between the block and the comment
    assert "[[documents]]" not in lines[block:redfish]


def test_ac6_the_parsed_catalog_reads_dsp0134_and_dsp0266_as_before():
    catalog = load_catalog(DEFAULT_CATALOG)
    dsp0134 = catalog.get("DSP0134")
    assert [v.version for v in dsp0134.versions][-2:] == ["3.9.0", "3.10.0"]
    assert dsp0134.latest().version == "3.10.0"
    assert dsp0134.find_version("3.10.0").published == "2026-09-07"
    assert dsp0134.family == "smbios"
    dsp0266 = catalog.get("DSP0266")
    assert dsp0266.family == "redfish"
    assert dsp0266.versions[0].version == "1.0.0"
    # the versions the parser reads are the version lines of the DSP0134 span,
    # in file order: the text and the parse agree on what belongs to it
    lines = DEFAULT_CATALOG.read_text("utf-8").split("\n")
    start, end = refresh_mod._document_span(lines, "DSP0134")
    in_text = [
        ln.split('"')[1] for ln in lines[start:end] if ln.startswith("version = ")
    ]
    assert in_text == [v.version for v in dsp0134.versions]


def test_ac6_a_further_dsp0134_version_lands_above_redfish_on_the_real_catalog(
    tmp_path,
):
    path = tmp_path / "catalog.toml"
    path.write_text(DEFAULT_CATALOG.read_text("utf-8"), encoding="utf-8", newline="")
    seen = listing_mod.Seen(
        "3.11.0",
        "https://www.dmtf.org/sites/default/files/standards/documents/DSP0134_3.11.0.pdf",
        "2027-01-01",
    )
    refresh_mod.append_versions(path, "DSP0134", [seen])
    after = path.read_text("utf-8")
    assert "\n\n\n" not in after
    assert after.count("# redfish") == 1
    assert (
        'published = "2026-09-07"\n\n[[documents.versions]]\nversion = "3.11.0"\n'
        in after
    )
    assert 'published = "2027-01-01"\n\n# redfish\n\n[[documents]]\nid = "DSP0266"' in after
    assert versions(path, "DSP0134")[-3:] == ["3.9.0", "3.10.0", "3.11.0"]
    assert versions(path, "DSP0266") == [
        v.version for v in load_catalog(DEFAULT_CATALOG).get("DSP0266").versions
    ]
