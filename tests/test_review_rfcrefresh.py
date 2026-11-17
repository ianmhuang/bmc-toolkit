"""Reviewer acceptance tests for the RFC Editor check (T81.3), part two:
``refresh`` over RFCs (AC-5), the monthly workflow's proposal count
(AC-6), and what stays as it was for the other sources (AC-7).

Black-box through the CLI with a scripted client serving synthetic JSON
(AC-9); nothing reaches the network. On the base branch ``refresh`` never
looks at an RFC, ``--skip-source rfc`` is not a source, and the workflow
does not count ``obsoleted``, so every test here fails there.
"""

import json
import re
from pathlib import Path

import pytest

from bmc_toolkit.spec import cli
from bmc_toolkit.spec.fetch import Response
from tests.conftest import MINI_CATALOG, ok
from tests.test_catalog_workflow import _run_refresh_block

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "catalog.yml"

DMTF_PUBLISHED = "https://www.dmtf.org/standards/published_documents"
DMTF_DSP0236 = "https://www.dmtf.org/dsp/DSP0236"
URL_132 = "https://example.test/DSP0236_1.3.2.pdf"
URL_133 = "https://example.test/DSP0236_1.3.3.pdf"
URL_134 = "https://example.test/DSP0236_1.3.4.pdf"
URL_140 = "https://example.test/DSP0236_1.4.0.pdf"

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

DRY = "(dry run; --write adds them)"


def json_url(n) -> str:
    return f"https://www.rfc-editor.org/rfc/rfc{n}.json"


def txt_url(n) -> str:
    return f"https://www.rfc-editor.org/rfc/rfc{n}.txt"


def document(doc_id: str, extra: str = "") -> str:
    return f"""
[[documents]]
id = "{doc_id}"
family = "ietf"
title = "The zebra protocol ({doc_id})"
access = "open"
fetch = "direct"
{extra}

[[documents.versions]]
version = "March 2026"
url = "https://www.rfc-editor.org/rfc/{doc_id.lower()}.txt"
type = "txt"
published = "2026-03-01"
"""


# RFC1111 records no obsoleting RFC; RFC2222 records one.
RFC_CATALOG = (
    MINI_CATALOG
    + """
[families.ietf]
title = "IETF Requests for Comments"
publisher = "IETF"
"""
    + document("RFC1111")
    + document("RFC2222", 'obsoleted_by = ["RFC3333"]')
)


def sentence(doc_id: str, *obsoleting: int) -> str:
    listed = "; ".join(f"RFC{n} ({txt_url(n)})" for n in obsoleting)
    return f"obsoleted {doc_id}: the RFC Editor lists it as obsoleted by {listed}"


def rfc_json(*ids) -> Response:
    body = {"doc_id": "RFC0000", "title": "synthetic", "obsoleted_by": list(ids)}
    return ok(json.dumps(body).encode("utf-8"), "application/json")


def html(text: str) -> Response:
    return ok(text.encode("utf-8"), "text/html")


@pytest.fixture
def rfc_catalog(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text(RFC_CATALOG, encoding="utf-8", newline="")
    return path


def run(capsys, catalog, *argv):
    code = cli.main(["--catalog", str(catalog), *argv])
    return code, capsys.readouterr().out


def summary_of(out: str) -> str:
    lines = [ln for ln in out.splitlines() if ln.startswith("summary: ")]
    assert len(lines) == 1, out
    return lines[0]


def counts_of(out: str) -> dict[str, int]:
    found = re.findall(
        r"\b(add|confirm|changed|unreachable|obsoleted|unlisted|written) (\d+)",
        summary_of(out),
    )
    return {kind: int(n) for kind, n in found}


def hosts(calls) -> set[str]:
    return {re.match(r"https://([^/]+)/", url).group(1) for url in calls}


# ----------------------------------------------------------------- AC-5


def test_ac5_refresh_of_one_rfc_prints_the_obsoleted_line_and_counts_it(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[json_url(1111)] = rfc_json("RFC4444")
    code, out = run(capsys, rfc_catalog, "refresh", "RFC1111")
    assert code == 0, out
    lines = out.splitlines()
    # the same line as check prints
    assert lines[0] == (
        "obsoleted RFC1111: the RFC Editor lists it as obsoleted by RFC4444 "
        "(https://www.rfc-editor.org/rfc/rfc4444.txt)"
    )
    assert len(lines) == 2, out
    counts = counts_of(out)
    assert counts["obsoleted"] == 1
    assert (counts["add"], counts["confirm"], counts["changed"]) == (0, 0, 0)
    assert counts["unreachable"] == 0
    assert summary_of(out).endswith(DRY)
    assert scripted.calls == [json_url(1111)]


def test_ac5_refresh_over_all_prints_one_line_per_rfc_and_none_for_a_current_one(
    rfc_catalog, library, scripted, capsys
):
    # RFC1111: two obsoleting RFCs the catalog lacks; RFC2222: the one it
    # records. DMTF is left out so the run is over the RFCs alone.
    scripted.responses[json_url(1111)] = rfc_json("RFC4444", "rfc 6666")
    scripted.responses[json_url(2222)] = rfc_json("RFC3333")
    code, out = run(capsys, rfc_catalog, "refresh", "--skip-source", "dmtf")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == sentence("RFC1111", 4444, 6666)
    assert len(lines) == 2, out
    assert "RFC2222" not in out
    # one RFC is obsoleted, whatever the number of RFCs obsoleting it
    assert counts_of(out)["obsoleted"] == 1
    assert counts_of(out)["unreachable"] == 0
    assert sorted(scripted.calls) == [json_url(1111), json_url(2222)]


def test_ac5_a_known_rfc_beside_a_new_one_names_only_the_new_one(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[json_url(2222)] = rfc_json("RFC3333", "RFC4444")
    code, out = run(capsys, rfc_catalog, "refresh", "RFC2222")
    assert code == 0, out
    assert out.splitlines()[0] == sentence("RFC2222", 4444)
    assert "RFC3333" not in out
    assert counts_of(out)["obsoleted"] == 1


def test_ac5_refresh_of_a_current_rfc_prints_only_the_summary(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[json_url(2222)] = rfc_json("RFC3333")
    code, out = run(capsys, rfc_catalog, "refresh", "RFC2222")
    assert code == 0, out
    assert len(out.splitlines()) == 1, out
    assert counts_of(out)["obsoleted"] == 0
    assert "RFC2222" not in out


@pytest.mark.parametrize("target", [("RFC1111",), ("--skip-source", "dmtf")])
def test_ac5_write_writes_nothing_for_an_obsoleted_rfc(
    rfc_catalog, library, scripted, capsys, target
):
    before = rfc_catalog.read_bytes()
    scripted.responses[json_url(1111)] = rfc_json("RFC4444")
    scripted.responses[json_url(2222)] = rfc_json("RFC3333")
    code, out = run(capsys, rfc_catalog, "refresh", *target, "--write")
    assert code == 0, out
    assert out.splitlines()[0] == sentence("RFC1111", 4444)
    counts = counts_of(out)
    assert counts["obsoleted"] == 1 and counts["written"] == 0
    assert "wrote " not in out
    assert rfc_catalog.read_bytes() == before


def test_ac5_skip_source_rfc_leaves_the_rfcs_out_and_the_summary_as_it_was(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[DMTF_PUBLISHED] = html(PUBLISHED_HTML)
    scripted.responses[DMTF_DSP0236] = html(DSP_HTML)
    scripted.responses[json_url(1111)] = rfc_json("RFC4444")
    scripted.responses[json_url(2222)] = rfc_json("RFC4444")
    code, out = run(capsys, rfc_catalog, "refresh", "--skip-source", "rfc")
    assert code == 0, out
    # neither read nor reported
    assert hosts(scripted.calls) == {"www.dmtf.org"}
    assert "RFC1111" not in out and "RFC2222" not in out
    # AC-7: DMTF is reported as before, and the summary carries no count
    # for a source that was not checked
    assert any(ln.startswith("add DSP0236 1.3.4 ") for ln in out.splitlines()), out
    assert "obsoleted" not in out
    counts = counts_of(out)
    assert (counts["add"], counts["confirm"], counts["changed"]) == (1, 0, 0)
    assert counts["unreachable"] == 0
    assert summary_of(out).endswith(DRY)


def test_ac5_naming_an_rfc_while_skipping_rfc_says_the_rfc_editor_is_skipped(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[json_url(1111)] = rfc_json("RFC4444")
    code, out = run(capsys, rfc_catalog, "refresh", "RFC1111", "--skip-source", "rfc")
    assert code == 2, out
    assert "RFC1111" in out and "the RFC Editor" in out
    assert "--skip-source" in out
    assert "obsoleted" not in out and "summary:" not in out
    assert scripted.calls == []


@pytest.mark.parametrize(
    "reply",
    [
        Response(404, {"content-type": "text/html"}, b"Not Found"),
        None,
        ok(b"", "application/json"),
        ok(b"<html>busy</html>", "text/html"),
        ok(b'{"doc_id": "RFC1111"}', "application/json"),
    ],
    ids=["http-404", "no-route", "empty-body", "not-json", "no-field"],
)
def test_ac5_an_rfc_whose_json_cannot_be_read_is_unreachable_not_obsoleted(
    rfc_catalog, library, scripted, capsys, reply
):
    if reply is not None:
        scripted.responses[json_url(1111)] = reply
    before = rfc_catalog.read_bytes()
    code, out = run(capsys, rfc_catalog, "refresh", "RFC1111", "--write")
    assert code == 0, out
    assert "Traceback" not in out
    assert out.splitlines()[0].startswith("unreachable RFC1111: "), out
    counts = counts_of(out)
    assert counts["unreachable"] == 1 and counts["obsoleted"] == 0
    assert rfc_catalog.read_bytes() == before


# ----------------------------------------------------------------- AC-7


def test_ac7_the_other_sources_are_reported_as_before_beside_the_rfcs(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[DMTF_PUBLISHED] = html(PUBLISHED_HTML)
    scripted.responses[DMTF_DSP0236] = html(DSP_HTML)
    scripted.responses[json_url(1111)] = rfc_json("RFC4444")
    scripted.responses[json_url(2222)] = rfc_json()
    # --skip-source github and nvme still mean what they meant: the RFCs
    # and DMTF are both read
    code, out = run(
        capsys,
        rfc_catalog,
        "refresh",
        "--skip-source",
        "github",
        "--skip-source",
        "nvme",
    )
    assert code == 0, out
    lines = out.splitlines()
    assert hosts(scripted.calls) == {"www.dmtf.org", "www.rfc-editor.org"}
    dmtf = [ln for ln in lines if ln.startswith("add DSP0236 ")]
    assert len(dmtf) == 1 and dmtf[0].startswith("add DSP0236 1.3.4 "), out
    assert URL_134 in dmtf[0]
    assert sentence("RFC1111", 4444) in lines
    counts = counts_of(out)
    assert (counts["add"], counts["confirm"], counts["changed"]) == (1, 0, 0)
    assert counts["unreachable"] == 0 and counts["obsoleted"] == 1
    assert counts["unlisted"] == 0
    # the counts that were there keep their order at the head of the line
    assert summary_of(out).startswith(
        "summary: add 1, confirm 0, changed 0, unreachable 0"
    )


# ----------------------------------------------------------------- AC-6


def _count_pattern() -> str:
    """The ``grep -oE`` pattern the workflow counts proposals with."""
    lines = [
        ln.strip()
        for ln in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if ln.strip().startswith("proposals=$(")
    ]
    assert len(lines) == 1, lines
    assert "grep '^summary:'" in lines[0]
    found = re.search(r"grep -oE '([^']+)'", lines[0])
    assert found, lines[0]
    return found.group(1)


def _proposals(output: str) -> int:
    """What the workflow's count comes to for a refresh output: the numbers
    its pattern matches on the summary line, added up."""
    pattern = re.compile(_count_pattern())
    total = 0
    for line in output.splitlines():
        if line.startswith("summary:"):
            total += sum(int(m.group(0).split()[1]) for m in pattern.finditer(line))
    return total


def test_ac6_the_workflow_counts_a_real_obsoleted_refresh_as_a_proposal(
    rfc_catalog, library, scripted, capsys
):
    scripted.responses[json_url(1111)] = rfc_json("RFC4444")
    scripted.responses[json_url(2222)] = rfc_json("RFC3333")
    code, out = run(capsys, rfc_catalog, "refresh", "--skip-source", "dmtf")
    assert code == 0, out
    assert sentence("RFC1111", 4444) in out.splitlines()
    assert _proposals(out) == 1
    # nothing new at the RFC Editor: nothing to open an issue for
    scripted.responses[json_url(1111)] = rfc_json()
    code, out = run(capsys, rfc_catalog, "refresh", "--skip-source", "dmtf")
    assert code == 0, out
    assert _proposals(out) == 0


CASES = [
    ("add 0, confirm 0, changed 0, unreachable 0, obsoleted 1", 1),
    ("add 0, confirm 0, changed 0, unreachable 0, obsoleted 0", 0),
    ("add 0, confirm 0, changed 0, unreachable 4, obsoleted 0", 0),
    ("add 2, confirm 0, changed 1, unreachable 3, obsoleted 2, unlisted 1", 6),
    ("add 0, confirm 0, changed 0, unreachable 0, obsoleted 12, unlisted 0", 12),
]


@pytest.mark.parametrize(("counts", "expected"), CASES)
def test_ac6_the_count_pattern_adds_obsoleted_to_the_proposals(counts, expected):
    output = f"{sentence('RFC1111', 4444)}\nsummary: {counts} {DRY}\n"
    assert _proposals(output) == expected


@pytest.mark.parametrize(("counts", "expected"), CASES)
def test_ac6_the_refresh_step_reports_obsoleted_as_proposals(
    tmp_path, counts, expected
):
    # the step's own script, run by bash as GitHub runs it (skipped where
    # no usable bash is on PATH; the test above covers the pattern there)
    output = f"{sentence('RFC1111', 4444)}\nsummary: {counts} {DRY}\n"
    proc, summary, proposals = _run_refresh_block(tmp_path, output)
    assert proc.returncode == 0, proc.stderr
    assert proposals == str(expected)
    assert sentence("RFC1111", 4444) in summary
