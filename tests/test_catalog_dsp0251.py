"""DSP0251 in the shipped catalog: DSP0248 1.4.0 moved the PDR definitions
and the sensor conversion formula there, so a search of DSP0248 also
searches DSP0251 (the companion path IPMI takes with IPMI-UPDATE)."""

import pytest

from bmc_toolkit.spec.catalog import load_catalog
from bmc_toolkit.spec.cli import main
from tests import pdfgen
from tests.conftest import ok

DSP0251_URL = (
    "https://www.dmtf.org/sites/default/files/standards/documents/DSP0251_1.0.0.pdf"
)


@pytest.fixture(scope="module")
def shipped():
    return load_catalog()


def run(capsys, *argv):
    code = main(list(argv))
    return code, capsys.readouterr().out


def test_dsp0251_is_an_open_pldm_document_fetched_directly(shipped):
    doc = shipped.get("DSP0251")
    assert doc is not None
    assert doc.family == "pldm"
    assert doc.title == (
        "Platform Level Data Model (PLDM) Platform Descriptor Record (PDR)"
        " Specification"
    )
    assert doc.access == "open" and doc.fetch == "direct"
    latest = doc.latest()
    assert latest.version == "1.0.0"
    assert latest.url == DSP0251_URL
    assert latest.type == "pdf"
    assert latest.published == "2026-10-12"


def test_dsp0251_sits_after_the_redfish_bundles(shipped):
    # Golden ids follow file order and their groups catalog order, so a
    # document added after M8 goes at the end, as DSP8011 and DSP8013 did.
    ids = [doc.id for doc in shipped.documents]
    assert ids.index("DSP0251") > ids.index("DSP8013")


def test_dsp0248_is_searched_with_dsp0251_and_says_why(shipped):
    doc = shipped.get("DSP0248")
    assert doc.searched_with == ("DSP0251",)
    assert "DSP0251" in doc.notes and "1.4.0" in doc.notes


def test_find_dsp0248_reaches_text_only_dsp0251_holds(
    shipped, library, scripted, tmp_path, capsys
):
    base = pdfgen.write_pdf(
        tmp_path / "dsp0248.pdf",
        [pdfgen.plain_page(["GetSensorReading command", "PDRs are in DSP0251"])],
    )
    pdr = pdfgen.write_pdf(
        tmp_path / "dsp0251.pdf",
        [pdfgen.plain_page(["Numeric Sensor PDR format", "conversion formula"])],
    )
    scripted.responses[shipped.get("DSP0248").latest().url] = ok(base.read_bytes())
    scripted.responses[DSP0251_URL] = ok(pdr.read_bytes())
    code, out = run(capsys, "fetch", "DSP0248")
    assert code == 0, out

    # DSP0251 is not held yet: find brings it to Ready, says so in notes,
    # and the hit is DSP0251's
    code, out = run(capsys, "find", "DSP0248", "Numeric Sensor PDR")
    assert code == 0, out
    lines = out.strip().splitlines()
    assert any(ln.startswith("note: ") and "DSP0251 1.0.0" in ln for ln in lines), out
    hits = [ln for ln in lines if not ln.startswith("note:")]
    assert hits == ["DSP0251 p.1 | - | Numeric Sensor PDR format"]

    code, out = run(capsys, "find", "DSP0248", "Numeric Sensor PDR", "--only")
    assert code == 0, out
    assert "DSP0251" not in out
