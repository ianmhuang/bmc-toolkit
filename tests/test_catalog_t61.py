"""The 2026-10-21 catalog batch: DSP0282, DSP0293, DSP0288, DSP2058 and the
NVM Command Set, with their versions, limits, Golden Questions and the
DMTF ids leaving not_taken. Shipped files only, no network."""

import re
from pathlib import Path

from bmc_toolkit.spec import support
from bmc_toolkit.spec.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "docs" / "golden-questions.md"

NEW = {
    "DSP0282": ("mctp", ["1.0.0", "1.0.1", "1.0.2", "1.1.0"]),
    "DSP0293": ("pldm", ["1.0.0"]),
    "DSP0288": ("redfish", ["1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0"]),
    "DSP2058": ("spdm", ["1.0.0", "1.1.0", "1.2.0", "1.3.0"]),
    "NVME-NVM": ("nvme", ["1.3"]),
}
QUESTIONS = {
    "G104": "DSP0282 1.1.0",
    "G105": "DSP0293 1.0.0",
    "G106": "DSP0288 1.4.0",
    "G107": "DSP2058 1.3.0",
    "G108": "NVME-NVM 1.3",
}


def test_the_five_follow_dsp0251_with_every_listed_version():
    cat = load_catalog()
    ids = [d.id for d in cat.documents]
    at = ids.index("DSP0251")
    assert ids[at + 1 :] == list(NEW)
    for doc_id, (family, versions) in NEW.items():
        doc = cat.get(doc_id)
        assert doc.family == family, doc_id
        assert (doc.access, doc.fetch) == ("open", "direct"), doc_id
        assert [v.version for v in doc.versions] == versions, doc_id
        assert doc.latest().version == versions[-1], doc_id
        assert all(v.type == "pdf" and v.url.endswith(".pdf") for v in doc.versions)
        dates = [v.published for v in doc.versions]
        assert dates == sorted(dates), doc_id
    assert cat.get("NVME-NVM").listing == "nvme:nvm-command-set-specification"
    assert {d.listing for d in cat.documents if d.id in NEW and d.id != "NVME-NVM"} == {
        f"dmtf:{d}" for d in NEW if d != "NVME-NVM"
    }


def test_the_dmtf_ones_left_not_taken():
    cat = load_catalog()
    for dsp in ("DSP0282", "DSP0293", "DSP0288", "DSP2058"):
        assert dsp in cat.dmtf_listed()
        assert not cat.dmtf_not_taken_covers(dsp), dsp
    text = (ROOT / "bmc_toolkit" / "spec" / "catalog.toml").read_text("utf-8")
    comment = text[text.index("DMTF left out") : text.index("[listings.dmtf]")]
    for dsp in ("DSP0282", "DSP0288", "DSP0293"):
        assert dsp not in comment, dsp


def test_limits_name_the_caption_cases_and_where_to_read_them():
    cat = load_catalog()
    assert "Table 2's caption" in cat.get("DSP0282").limits
    assert "byte number" in cat.get("DSP0282").limits
    assert "page 14" in cat.get("DSP2058").limits
    assert "Figure 123" in cat.get("NVME-NVM").limits
    for doc_id in ("DSP0282", "DSP2058", "NVME-NVM"):
        assert re.search(r"\bpage\b", cat.get(doc_id).limits), doc_id
    assert cat.get("DSP0293").limits == "" and cat.get("DSP0288").limits == ""


def test_each_is_verified_by_its_own_question():
    cat = load_catalog()
    verified, problems = support.read_golden(GOLDEN, cat)
    assert problems == []
    for doc_id in NEW:
        assert doc_id.lower() in verified, doc_id
    text = GOLDEN.read_text("utf-8")
    section = text[
        text.index("## Catalog additions of 2026-10-21") : text.index("## OpenBMC")
    ]
    for qid, doc in QUESTIONS.items():
        (row,) = [ln for ln in section.splitlines() if ln.startswith(f"| {qid} |")]
        assert row.split(" | ")[2] == doc, qid


def test_readme_counts_the_catalog():
    cat = load_catalog()
    docs = cat.documents
    readme = " ".join((ROOT / "README.md").read_text("utf-8").split())
    total = len(docs)
    open_docs = sum(d.access == "open" for d in docs)
    families = len({d.family for d in docs})
    assert (total, open_docs, families) == (119, 99, 35)
    assert f"lists {total} documents in {families} families" in readme
    assert f"The {open_docs} open ones" in readme
