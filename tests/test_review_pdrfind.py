"""Reviewer acceptance tests for AC-3's behaviour on the shipped catalog:
``find DSP0248`` also searches DSP0251, bringing it to Ready when the
Library lacks it, reports the companion's hits first, leaves it out under
``--only``, searches DSP0251 alone when it is the named document, and
keeps answering from DSP0248 when DSP0251 cannot be fetched. Synthetic
PDFs are served at the catalog's own URLs; no test reaches the network."""

import pytest

from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

pytest.importorskip("pypdfium2")

DMTF_FILES = "https://www.dmtf.org/sites/default/files/standards/documents/"
DSP0251_URL = f"{DMTF_FILES}DSP0251_1.0.0.pdf"
DSP0248_URL = f"{DMTF_FILES}DSP0248_1.4.0.pdf"

BASE_LINES = ["GetSensorReading command", "the conversion formula moved out"]
PDR_LINES = ["Numeric Sensor PDR format", "sensor conversion formula here"]


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def run(capsys, *argv):
    code = main(list(argv))
    return code, capsys.readouterr().out


def pdf_bytes(tmp_path, name, lines):
    return pdfgen.write_pdf(tmp_path / name, [pdfgen.plain_page(lines)]).read_bytes()


def split(out):
    lines = out.strip().splitlines()
    notes = [ln for ln in lines if ln.startswith("note: ")]
    hits = [ln for ln in lines if not ln.startswith("note: ")]
    return notes, hits


def test_shipped_urls_are_the_ones_the_tests_serve(shipped):
    assert shipped.get("DSP0248").latest().url == DSP0248_URL
    assert shipped.get("DSP0251").latest().url == DSP0251_URL


def test_find_dsp0248_fetches_dsp0251_and_lists_its_hits_first(
    shipped, library, scripted, tmp_path, capsys
):
    scripted.responses[DSP0248_URL] = ok(pdf_bytes(tmp_path, "base.pdf", BASE_LINES))
    scripted.responses[DSP0251_URL] = ok(pdf_bytes(tmp_path, "pdr.pdf", PDR_LINES))
    code, out = run(capsys, "fetch", "DSP0248")
    assert code == 0, out
    assert DSP0251_URL not in scripted.calls, "fetch does not pull companions"

    # both documents hold the pattern: the companion's hit comes first
    code, out = run(capsys, "find", "DSP0248", "conversion formula")
    assert code == 0, out
    notes, hits = split(out)
    assert any("DSP0251 1.0.0" in n for n in notes), out
    assert any(n.startswith("note: fetched DSP0251 1.0.0") for n in notes), out
    assert hits == [
        "DSP0251 p.1 | - | sensor conversion formula here",
        "DSP0248 p.1 | - | the conversion formula moved out",
    ], out
    assert scripted.calls.count(DSP0251_URL) == 1
    assert library.find("DSP0251", "1.0.0") is not None

    # the second search has nothing to fetch: no note, same hits
    code, out = run(capsys, "find", "DSP0248", "conversion formula")
    assert code == 0, out
    notes, hits = split(out)
    assert notes == [], out
    assert len(hits) == 2 and hits[0].startswith("DSP0251 p.1")
    assert scripted.calls.count(DSP0251_URL) == 1

    # text that only DSP0251 holds is still a hit of find DSP0248
    code, out = run(capsys, "find", "DSP0248", "Numeric Sensor PDR")
    assert code == 0, out
    assert out.strip() == "DSP0251 p.1 | - | Numeric Sensor PDR format"


def test_only_restricts_find_to_dsp0248_and_never_fetches_dsp0251(
    shipped, library, scripted, tmp_path, capsys
):
    scripted.responses[DSP0248_URL] = ok(pdf_bytes(tmp_path, "base.pdf", BASE_LINES))
    scripted.responses[DSP0251_URL] = ok(pdf_bytes(tmp_path, "pdr.pdf", PDR_LINES))
    code, out = run(capsys, "fetch", "DSP0248")
    assert code == 0, out

    # --only while DSP0251 is not held: no download, no note, the base hit
    code, out = run(capsys, "find", "DSP0248", "conversion formula", "--only")
    assert code == 0, out
    assert out.strip() == "DSP0248 p.1 | - | the conversion formula moved out"
    assert DSP0251_URL not in scripted.calls
    code, out = run(capsys, "find", "DSP0248", "Numeric Sensor PDR", "--only")
    assert code == 0 and out.strip() == "no hits", out
    assert DSP0251_URL not in scripted.calls

    # --only while DSP0251 is held: still left out
    code, out = run(capsys, "fetch", "DSP0251")
    assert code == 0, out
    code, out = run(capsys, "find", "DSP0248", "Numeric Sensor PDR", "--only")
    assert code == 0 and out.strip() == "no hits", out
    assert "DSP0251" not in out


def test_find_dsp0251_itself_does_not_pull_in_dsp0248(
    shipped, library, scripted, tmp_path, capsys
):
    scripted.responses[DSP0251_URL] = ok(pdf_bytes(tmp_path, "pdr.pdf", PDR_LINES))
    # DSP0248 is neither held nor served: a one-way link means find DSP0251
    # never asks for it
    code, out = run(capsys, "find", "DSP0251", "conversion formula")
    assert code == 0, out
    notes, hits = split(out)
    assert hits == ["DSP0251 p.1 | - | sensor conversion formula here"], out
    assert not any("DSP0248" in n for n in notes), out
    assert DSP0248_URL not in scripted.calls
    assert library.find("DSP0248", "1.4.0") is None


def test_unreachable_dsp0251_is_a_note_and_dsp0248_still_answers(
    shipped, library, scripted, tmp_path, capsys
):
    scripted.responses[DSP0248_URL] = ok(pdf_bytes(tmp_path, "base.pdf", BASE_LINES))
    code, out = run(capsys, "fetch", "DSP0248")
    assert code == 0, out

    # no route to DSP0251: the failure is a note, the search goes on
    code, out = run(capsys, "find", "DSP0248", "conversion formula")
    assert code == 0, out
    notes, hits = split(out)
    assert "note: failed DSP0251 1.0.0" in notes, out
    assert any("DSP0251" in n and "Save it as: " in n for n in notes), out
    assert hits == ["DSP0248 p.1 | - | the conversion formula moved out"], out
    assert library.find("DSP0251", "1.0.0") is None

    # a pattern neither holds is "no hits", not an error
    code, out = run(capsys, "find", "DSP0248", "Numeric Sensor PDR")
    assert code == 0, out
    notes, hits = split(out)
    assert "note: failed DSP0251 1.0.0" in notes, out
    assert hits == ["no hits"], out
